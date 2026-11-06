"""Decode private startup PCAPs into an allowlisted native protocol receipt."""
import argparse
import hashlib
import ipaddress
import json
from pathlib import Path
import re
import struct
from urllib.parse import parse_qs, urlsplit

from capture_friend_battle_http import runs


def packets(path):
    data = Path(path).read_bytes()
    assert len(data) >= 24, 'Truncated PCAP'
    magic = data[:4]
    assert magic in (b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4', b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d'), 'Classic PCAP required'
    endian = '<' if magic[:1] in (b'\xd4', b'\x4d') else '>'
    scale = 1e9 if magic in (b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d') else 1e6
    link = struct.unpack_from(endian + 'I', data, 20)[0]
    assert link in (1, 113, 276), 'Unsupported link type'
    pos = 24
    while pos < len(data):
        assert pos + 16 <= len(data), 'Truncated packet header'
        seconds, fraction, size, original = struct.unpack_from(endian + 'IIII', data, pos)
        pos += 16
        assert size == original and pos + size <= len(data), 'Truncated packet'
        packet, pos = data[pos:pos + size], pos + size
        offset = {1: 14, 113: 16, 276: 20}[link]
        protocol = packet[12:14] if link == 1 else packet[14:16] if link == 113 else packet[:2]
        if protocol != b'\x08\x00':
            continue
        ip = packet[offset:]
        assert len(ip) >= 20 and ip[0] >> 4 == 4, 'Invalid IPv4'
        if ip[9] != 6:
            continue
        assert struct.unpack_from('!H', ip, 6)[0] & 0x3fff == 0, 'Fragmentation unsupported'
        ihl, total = (ip[0] & 15) * 4, struct.unpack_from('!H', ip, 2)[0]
        assert len(ip) >= total and ihl >= 20, 'Truncated IPv4'
        tcp = ip[ihl:total]
        assert len(tcp) >= 20, 'Truncated TCP'
        source, target, seq, ack = struct.unpack_from('!HHII', tcp)
        header = (tcp[12] >> 4) * 4
        assert 20 <= header <= len(tcp), 'Invalid TCP header'
        if not {source, target} & {8087, 8089}:
            continue
        key = (str(ipaddress.ip_address(ip[12:16])), source, str(ipaddress.ip_address(ip[16:20])), target)
        yield dict(key=key, seq=seq, ack=ack, flags=tcp[13], payload=tcp[header:], time=seconds + fraction / scale)


def assemble(rows):
    segments = [(p['seq'], p['ack'], p['payload']) for p in rows if p['payload']]
    if not segments:
        return None
    joined = list(runs(segments))
    assert len(joined) == 1, 'TCP gap; cannot establish complete protocol evidence'
    return joined[0]


def chunks(data):
    """Return complete chunk data and offsets; a trailing partial chunk stays unobserved."""
    pos, decoded, spans = 0, bytearray(), []
    while pos < len(data):
        end = data.find(b'\r\n', pos)
        if end < 0:
            return bytes(decoded), spans, None
        assert re.fullmatch(rb'[0-9a-fA-F]+', data[pos:end]), 'Invalid chunk size'
        size = int(data[pos:end], 16)
        start = end + 2
        if len(data) < start + size + 2:
            return bytes(decoded), spans, None
        assert data[start + size:start + size + 2] == b'\r\n', 'Invalid chunk boundary'
        if size == 0:
            return bytes(decoded), spans, start + 2
        spans.append((len(decoded), len(decoded) + size, start))
        decoded.extend(data[start:start + size])
        pos = start + size + 2
    return bytes(decoded), spans, None


def messages(data):
    """Parse complete HTTP messages; streaming SSE may remain open at capture end."""
    pos = 0
    while pos < len(data):
        end = data.find(b'\r\n\r\n', pos)
        if end < 0:
            return
        lines = data[pos:end].decode('ascii').split('\r\n')
        assert re.match(r'(?:POST|GET) /|HTTP/1\.[01] \d{3}', lines[0]), 'Unexpected HTTP start'
        headers = {}
        for line in lines[1:]:
            key, value = line.split(':', 1)
            assert key.lower() not in headers, 'Duplicate header'
            headers[key.lower()] = value.strip()
        body_start = end + 4
        if headers.get('transfer-encoding'):
            assert headers['transfer-encoding'].lower() == 'chunked', 'Unsupported transfer encoding'
            assert 'content-length' not in headers, 'Ambiguous HTTP framing'
            body, spans, consumed = chunks(data[body_start:])
            finish = body_start + consumed if consumed is not None else None
        else:
            size = int(headers.get('content-length', '0'))
            assert size >= 0, 'Invalid Content-Length'
            finish = body_start + size
            if finish > len(data):
                return
            body, spans = data[body_start:finish], [(0, size, 0)]
        sse = headers.get('content-type', '').split(';')[0] == 'text/event-stream'
        if finish is None and not sse:
            return
        yield dict(line=lines[0], headers=headers, body=body, start=pos, finish=finish,
                   body_start=body_start, spans=spans, sse=sse)
        if finish is None:
            return
        pos = finish


def frames(body, skip_first=False):
    pos = 0
    for match in re.finditer(rb'\r?\n\r?\n', body):
        frame = body[pos:match.start()]
        start, pos = pos, match.end()
        if skip_first:
            skip_first = False
            continue
        fields = {}
        for line in frame.splitlines():
            if line.startswith(b':') or not line:
                continue
            key, value = line.split(b':', 1)
            fields.setdefault(key.decode('ascii'), []).append(value.lstrip(b' '))
        if 'event' in fields and 'data' in fields:
            assert len(fields['event']) == 1, 'Ambiguous SSE event'
            yield start, pos, fields['event'][0].decode('ascii'), json.loads(b'\n'.join(fields['data']))


def flows(path):
    result = {}
    rows = list(packets(path))
    for row in rows:
        result.setdefault(row['key'], []).append(row)
    return result, min(row['time'] for row in rows)


def at(rows, absolute):
    times = [p['time'] for p in rows if p['seq'] <= absolute < p['seq'] + len(p['payload'])]
    assert times, 'Missing timestamp for stream byte'
    return min(times)


def move_summary(body, reply, account, fixture):
    """Allowlist catalog IDs; owned IDs and authentication never enter the receipt."""
    assert body.get('battle_id') == fixture['battle'], 'Unexpected selection battle'
    kind = body.get('type')
    assert kind in ('ATTACK', 'SWITCH', 'RUN', 'ITEM'), 'Unsafe move type'
    catalog = json.loads((Path(__file__).resolve().parents[2] / 'config/attack_max_ap.json').read_text())
    move = body.get('move_id')
    if kind == 'ATTACK':
        assert isinstance(move, str) and move in catalog, 'Unknown native attack ID'
    else:
        move = None
    owned = fixture['before']['owned']
    decks = [deck for deck in owned['decks'] if deck['player_id'] == account['player_id']
             and int(deck['deck_id']) == int(account['active_deck_id'])]
    assert len(decks) == 1, 'Ambiguous fixture active deck'
    ids = json.loads(decks[0]['owned_morty_ids'])
    assert isinstance(ids, list) and len(ids) == len(set(ids)), 'Invalid fixture active deck'
    morties = {morty['owned_morty_id']: morty for morty in owned['owned_morties']
               if morty['player_id'] == account['player_id']}
    assert all(owned_id in morties for owned_id in ids), 'Missing fixture party member'
    active = next((owned_id for owned_id in ids if int(morties[owned_id]['hp']) > 0), None)
    return dict(battle_id='<shared-battle>', type=kind, move_id=move,
                actor_is_local_active=active is not None and body.get('owned_morty_id') == active,
                success=reply.get('success') is True)


def capture_original_session(flow, own, recovered):
    """Anchor a rotated native session to an authenticated captured identity response."""
    candidates = set()
    for key, rows in flow.items():
        assembled = assemble(rows)
        if not assembled or key[3] not in (8087, 8089):
            continue
        first, data, _ = assembled
        reverse = (key[2], key[3], key[0], key[1])
        response_first, response_data, ack_spans = assemble(flow[reverse])
        requests, responses = list(messages(data)), list(messages(response_data))
        assert len(requests) == len(responses), 'Ambiguous identity exchange order'
        for request, response in zip(requests, responses):
            method, target, _ = request['line'].split(' ')
            if method != 'POST' or urlsplit(target).path != '/session/player-details':
                continue
            assert request['finish'] is not None and response['finish'] is not None, 'Incomplete identity exchange'
            acknowledged = {ack for lo, hi, ack in ack_spans if lo <= response_first + response['start'] < hi}
            assert acknowledged and all(ack >= first + request['finish'] for ack in acknowledged), 'Identity response does not acknowledge request'
            body, reply = json.loads(request['body']), json.loads(response['body'])
            assert int(response['line'].split()[1]) == 200 and 'error' not in reply, 'Identity request failed'
            assert reply.get('player_id') == own['player_id'] and reply.get('username') == own['username'], 'Captured identity differs from role'
            session = body.get('session_id')
            assert isinstance(session, str) and session, 'Invalid captured identity session'
            if session not in recovered:
                candidates.add(session)
    assert len(candidates) == 1, 'Require one authenticated capture-original session'
    return next(iter(candidates))


def analyze(root, role, accounts, fixture, expect_selections=False):
    directory = root / (role + '-capture')
    path = directory / (role + '-http.pcap')
    manifest = json.loads((directory / 'manifest.json').read_text())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == manifest['pcap_sha256'], 'Capture hash mismatch'
    flow, zero = flows(path)
    events, exchanges, starts, closures = [], [], [], []
    stream_request_tokens = []
    for key, rows in flow.items():
        assembled = assemble(rows)
        if assembled and key[3] in (8087, 8089):
            for request in messages(assembled[1]):
                target = urlsplit(request['line'].split(' ')[1])
                if target.path == '/sse/':
                    stream_request_tokens.extend(parse_qs(target.query).get('token', []))
    own = accounts[role]
    other = accounts['peer' if role == 'primary' else 'primary']
    for key, rows in flow.items():
        assembled = assemble(rows)
        if not assembled or key[1] not in (8087, 8089):
            continue
        first, data, _ = assembled
        midstream = not data.startswith(b'HTTP/')
        if midstream:
            body, spans, terminal = chunks(data)
            streams = [dict(body=body, spans=spans, body_start=0, finish=terminal, sse=True)]
        else:
            streams = [m for m in messages(data) if m['sse']]
        for stream in streams:
            def wire_offset(decoded_offset):
                matching = [(a, c) for a, b, c in stream['spans'] if a <= decoded_offset < b]
                assert len(matching) == 1, 'Unmapped chunk byte'
                a, c = matching[0]
                return stream['body_start'] + c + decoded_offset - a
            for begin, finish, name, payload in frames(stream['body'], skip_first=midstream):
                allowed = ('battle:start', 'session:end', 'session:start') + (('battle:turn-result',) if expect_selections else ())
                if name not in allowed:
                    continue
                timestamp = at(rows, first + wire_offset(finish - 1))
                item = dict(kind='sse', event=name, seconds=round(timestamp - zero, 6))
                if name == 'battle:start':
                    assert payload['battle_id'] == fixture['battle'], 'Unexpected shared battle'
                    assert payload['player']['player_id'] == own['player_id'], 'Wrong native player view'
                    assert payload['opponent']['player_id'] == other['player_id'], 'Wrong opponent view'
                    parties = {}
                    for side, account in (('player', own), ('opponent', other)):
                        party = payload[side]['owned_morties']
                        before = [m for m in fixture['before']['owned']['owned_morties'] if m['player_id'] == account['player_id']]
                        assert {m['owned_morty_id'] for m in party} <= {m['owned_morty_id'] for m in before}, 'Invented owned party'
                        assert payload[side]['active_owned_morty'] in {m['owned_morty_id'] for m in party}, 'Invalid active Morty'
                        parties[side] = [{field: m[field] for field in ('morty_id', 'variant', 'level', 'hp', 'hp_stat')} for m in party]
                    item.update(battle_id='<shared-battle>', battle_type=payload['battle_type'], parties=parties,
                                player_is_capture_role=True, opponent_is_other_role=True, meta_empty=payload['meta'] == {})
                elif name == 'session:end':
                    item['data_is_empty_object'] = payload == {}
                    fins = [p for p in rows if p['flags'] & 1 and p['seq'] + len(p['payload']) == first + len(data)]
                    resets = [p for p in rows if p['flags'] & 4]
                    reverse = flow.get((key[2], key[3], key[0], key[1]), [])
                    closure = dict(terminal_chunk=stream['finish'] is not None,
                                   server_fin=bool(fins), server_reset=bool(resets))
                    if fins:
                        closure['fin_seconds'] = round(min(p['time'] for p in fins) - zero, 6)
                        closure['client_acked_fin'] = any(p['ack'] == first + len(data) + 1 for p in reverse)
                    closure['clean_eof_observed'] = closure['terminal_chunk'] and closure['server_fin'] and not closure['server_reset']
                    item['closure'] = closure
                    closures.append(closure)
                elif name == 'session:start':
                    assert payload['player_id'] == own['player_id'], 'Wrong recovered session player'
                    starts.append(payload['session_id'])
                    item['fresh_session_differs_from_before'] = payload['session_id'] != own['session_id']
                events.append(item)
    capture_session = capture_original_session(flow, own, starts) if expect_selections else own['session_id']
    for key, rows in flow.items():
        assembled = assemble(rows)
        if not assembled or key[3] not in (8087, 8089):
            continue
        first, data, _ = assembled
        reverse = (key[2], key[3], key[0], key[1])
        response_first, response_data, ack_spans = assemble(flow[reverse])
        requests, responses = list(messages(data)), list(messages(response_data))
        assert len(requests) == len(responses), 'Ambiguous HTTP request/response order'
        for request, response in zip(requests, responses):
            method, target, _ = request['line'].split(' ')
            endpoint = urlsplit(target).path
            if method != 'POST':
                continue
            assert request['finish'] is not None and response['finish'] is not None, 'Incomplete POST exchange'
            acknowledged = {ack for lo, hi, ack in ack_spans if lo <= response_first + response['start'] < hi}
            assert acknowledged and all(ack >= first + request['finish'] for ack in acknowledged), 'Response does not acknowledge request'
            if endpoint not in ('/session/battle/ready', '/user/login', '/session/join-room', '/session/battle-invite/response') and not re.search(r'/battle/(?:move|attack|switch|item)', endpoint):
                continue
            body, reply = json.loads(request['body']), json.loads(response['body'])
            timestamp = at(rows, first + request['start'])
            item = dict(kind='http', method=method, path=endpoint, seconds=round(timestamp - zero, 6),
                        response_seconds=round(at(flow[reverse], response_first + response['finish'] - 1) - zero, 6),
                        status=int(response['line'].split()[1]), request_fields=sorted(body))
            if 'session_id' in body:
                item['session_identity'] = 'original' if body['session_id'] == capture_session else 'recovered' if body['session_id'] in starts else 'unknown'
                assert item['session_identity'] != 'unknown', 'Unmapped session identity'
            if endpoint == '/session/battle/ready':
                assert body['battle_id'] == fixture['battle'], 'Unexpected ready battle'
                item.update(battle_id='<shared-battle>', success=reply.get('success') is True)
            elif endpoint == '/user/login':
                item['secret_matches_capture_role'] = body['secret'] == own['secret']
                token = parse_qs(urlsplit(reply['session_url']).query)['token'][0]
                item['returned_url_token_matches_recovered_sse_request'] = token in stream_request_tokens
            elif endpoint == '/session/battle-invite/response':
                assert isinstance(body['accept'], bool), 'Nonboolean native invite response'
                code = reply.get('error', {}).get('code')
                assert code is None or re.fullmatch(r'[A-Z_]+', code), 'Unsafe error code'
                item.update(accept=body['accept'], error_code=code)
            elif re.search(r'/battle/(?:move|attack|switch|item)', endpoint):
                assert endpoint in ('/session/battle/move', '/session/battle/attack', '/session/battle/switch', '/session/battle/item'), 'Unexpected move endpoint'
                item.update(move_summary(body, reply, own, fixture))
            else:
                item['room_response_received'] = 'room_id' in reply and 'users' in reply and 'error' not in reply
            exchanges.append(item)
    timeline = sorted(events + exchanges, key=lambda event: event['seconds'])
    counts = {name: sum(event.get('event') == name for event in events) for name in ('battle:start', 'session:end', 'session:start')}
    if expect_selections:
        counts['battle:turn-result'] = sum(event.get('event') == 'battle:turn-result' for event in events)
    counts['repeated_battle_start'] = max(0, counts['battle:start'] - 1)
    battle_times = [event['seconds'] for event in events if event['event'] == 'battle:start']
    for event in exchanges:
        if event['path'] == '/session/battle-invite/response' and battle_times:
            event['seconds_before_battle_start_frame_complete'] = round(min(battle_times) - event['seconds'], 6)
    for name, endpoint in (('native_ready', '/session/battle/ready'), ('native_login', '/user/login'), ('native_join', '/session/join-room'), ('native_invite_response', '/session/battle-invite/response')):
        counts[name] = sum(event['path'] == endpoint for event in exchanges)
    counts['native_battle_moves'] = sum(bool(re.search(r'/battle/(?:move|attack|switch|item)', event['path'])) for event in exchanges)
    ends = [event['seconds'] for event in events if event['event'] == 'session:end']
    result = dict(capture_sha256=digest, capture_duration_seconds=manifest['duration_seconds'],
                client_version=manifest['apk']['version'], apk_sha256=manifest['apk']['source_apk_sha256'],
                installed_apk_hashes_match_sources=set(manifest['apk']['installed_apk_sha256'].values()) == set(manifest['apk']['source_apk_sha256'].values()),
                relative_time_origin='first matching TCP packet in this role capture', counts=counts, timeline=timeline,
                login_and_join_after_session_end=bool(ends) and all(event['seconds'] > max(ends) for event in exchanges if event['path'] in ('/user/login', '/session/join-room')),
                clean_eof_observed=bool(closures) and all(item['clean_eof_observed'] for item in closures))
    if expect_selections:
        assert starts and all(session != capture_session for session in starts), 'Recovery did not rotate capture session'
        result.update(capture_session_identity_source='Complete ACK-paired HTTP 200 player-details response matches immutable fixture player and username',
                      capture_session_differs_from_fixture_before=capture_session != own['session_id'],
                      recovered_session_differs_from_capture_original=True)
    return result


def export(root, output, expect_selections=False):
    root = Path(root).resolve()
    assert root.is_relative_to((Path(__file__).resolve().parents[2] / '.research').resolve()), 'Raw captures must remain private'
    fixture = json.loads((root / 'fixture/startup-fixture.json').read_text())
    names = fixture['names']
    accounts = {role: next(account for account in fixture['before']['accounts'] if account['username'] == name) for role, name in zip(('primary', 'peer'), names)}
    result = dict(evidence_kind='Observed Android 2.41.0 diagnostic client against isolated replacement backend; not original-server evidence',
                  setup='Scripted HTTP social setup and internal CLI startup activation; no successful native acceptance established.',
                  scope='Existing native-owned parties on dedicated fresh accounts; no battle completion or wider roster compatibility claimed.',
                  roles={role: analyze(root, role, accounts, fixture, expect_selections) for role in ('primary', 'peer')})
    verified=[item['status'] for item in fixture.get('observations',[]) if item.get('action')=='verify' and item['status'].get('persistent_data_unchanged')]
    assert verified, 'Require explicit post-capture persistent-save verification'
    final=verified[-1]
    if expect_selections:
        last_verify = [item['status'] for item in fixture.get('observations', []) if item.get('action') == 'verify'][-1]
        assert last_verify.get('persistent_data_unchanged') is True, 'Last verification must preserve save data'
        final = last_verify
    assert final['startup']['state']=='CANCELLED' and final['startup']['claims_for_battle']==0, 'Require terminal startup with released claims'
    assert final['startup']['intent_count']==final['startup']['retired_intent_count']==2, 'Require both retired intents'
    assert all(role['state']=='WORLD' for role in final['roles'].values()), 'Require both database users restored'
    result['database_verification']={'source':'Post-capture dedicated fixture verification; immutable participant identity and persistent-save guards',
        'state':final['startup']['state'],'cancel_reason':final['startup']['cancel_reason'],
        'both_users_world':True,'claims_for_battle':0,'intent_count':2,'retired_intent_count':2,'persistent_data_unchanged':True}
    if expect_selections:
        expected = dict(selection_count=2, retired_selection_count=2, pair_count=1, retired_pair_count=1)
        assert all(final['startup'].get(key) == value for key, value in expected.items()), 'Require exactly one retired selection pair'
        result['database_verification'].update(expected)
        result['scope'] = ('Observed first native ATTACK from each local initial active Morty queued as one immutable pair, then retired at startup expiry; '
                           'no combat resolution or turn-result observed; persistent HP and PP unchanged. No original-server combat formulas claimed.')
    for role in result['roles'].values():
        assert role['counts']['battle:start'] and role['counts']['native_ready'] and role['counts']['session:end'], 'Missing required native evidence'
        assert role['counts']['native_login'] and role['counts']['native_join'] and role['counts']['session:start'], 'Missing recovered session exchange'
        assert role['clean_eof_observed'] and role['login_and_join_after_session_end'], 'Missing automatic recovery evidence'
        if expect_selections:
            moves = [event for event in role['timeline'] if event.get('kind') == 'http' and re.search(r'/battle/(?:move|attack|switch|item)', event.get('path', ''))]
            assert role['counts']['native_battle_moves'] == len(moves) == 1, 'Require exactly one native selection per role'
            move = moves[0]
            assert move['path'] == '/session/battle/move' and move['type'] == 'ATTACK', 'Require native ATTACK selection'
            assert move['status'] == 200 and move['success'] and move['actor_is_local_active'], 'Native selection failed or actor differs'
            assert move['session_identity'] == 'original', 'Selection must use original capture session'
            assert role['counts']['battle:turn-result'] == 0, 'Unexpected combat resolution event'
        for event in role['timeline']:
            if event.get('path') == '/session/battle/ready':
                assert event['status'] == 200 and event['success'], 'Native ready failed'
            if event.get('path') == '/user/login':
                assert event['status'] == 200 and event['secret_matches_capture_role'] and event['returned_url_token_matches_recovered_sse_request'], 'Native login identity mismatch'
            if event.get('path') == '/session/join-room':
                assert event['status'] == 200 and event['room_response_received'] and event['session_identity'] == 'recovered', 'Native recovery join failed'
    Path(output).write_text(json.dumps(result, indent=2) + '\n')
    print('Sanitized native startup receipt written: ' + str(output))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture-root', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expect-selections', action='store_true', help='Require one native ATTACK per role and one retired pair, with no turn-result')
    args = parser.parse_args()
    export(args.capture_root, args.output, args.expect_selections)

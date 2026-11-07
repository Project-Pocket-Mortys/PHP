"""Read-only native reject/accept evidence; private inputs stay in .research.

Captures retain separate TCP flows and merge by their packet timestamps.
Scripted setup/cleanup is never counted as native evidence. Full acceptance
requires both owners' native refresh.
"""
import argparse
import base64
import datetime
from http.cookies import SimpleCookie
import json
from pathlib import Path
import re
import struct
from urllib.parse import parse_qs, urlsplit

from capture_friend_battle_http import ROOT, message, packets, runs
from sanitize_native_trade_cancellation import require, digest
from native_trade_decision_fixture import (USER_DYNAMICS, compare_snapshot,
                                            validate_baseline, verify_history)


STAGES = ('before-parent', 'parent-created', 'reject-offer-created',
          'before-reject', 'after-reject', 'accept-offer-created',
          'before-accept', 'after-accept')
RECEIPTS = (
    ('reject-before-parent', 'initial', 'before-parent'),
    ('reject-parent-created', 'parent', 'parent-created'),
    ('reject-offer-created', 'offer', 'reject-offer-created'),
    ('reject-before-decision', 'offer', 'before-reject'),
    ('reject-decision-complete', 'rejected', 'after-reject'),
    ('accept-before-parent', 'parent', None),
    ('accept-parent-created', 'parent', None),
    ('accept-offer-created', 'offer', 'accept-offer-created'),
    ('accept-before-decision', 'offer', 'before-accept'),
    ('accept-decision-complete', 'accepted', 'after-accept'))
PATHS = {'/user/login', '/user/login/', '/trading/request-morty',
         '/trading/offer-morty', '/trading/offer-response',
         '/trading/get-trades', '/trading/config', '/session/player-details'}
TABLES = {'users', 'owned_morties', 'owned_attacks', 'owned_items', 'decks',
          'trades', 'trade_offers', 'completed_trades', 'friend_list',
          'event_queue', 'friend_battle_memberships'}
SAFE_BODY_KEYS = {'secret', 'consent_identifier', 'session_id', 'player_id', 'include',
                  'owned_morty_id', 'requested_morty_id', 'request_variant', 'is_free_trade',
                  'offered_morty_id', 'trade_request_id', 'trade_offer_id', 'request_accepted'}


def strict_json(data):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result)
            result[key] = value
        return result
    def invalid(_):
        raise ValueError()
    return json.loads(data, object_pairs_hook=pairs, parse_constant=invalid)


def capture_packet_times(path):
    """Return nanosecond timestamps for exactly the shared parser's payloads."""
    data = path.read_bytes()
    require(len(data) >= 24)
    magic = data[:4]
    require(magic in (b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4',
                      b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d'))
    endian = '<' if magic in (b'\xd4\xc3\xb2\xa1', b'\x4d\x3c\xb2\xa1') else '>'
    nano = magic in (b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d')
    link = struct.unpack_from(endian + 'I', data, 20)[0]
    require(link in (1, 113, 276))
    pos, previous, result = 24, None, []
    while pos < len(data):
        require(pos + 16 <= len(data))
        seconds, fraction, size, original = struct.unpack_from(endian + 'IIII', data, pos)
        pos += 16
        require(fraction < (10**9 if nano else 10**6))
        stamp = seconds * 10**9 + fraction * (1 if nano else 1000)
        require(previous is None or stamp >= previous)
        previous = stamp
        require(size == original and pos + size <= len(data))
        frame = data[pos:pos+size]
        pos += size
        offset = {1: 14, 113: 16, 276: 20}[link]
        protocol = frame[12:14] if link == 1 else frame[14:16] if link == 113 else frame[:2]
        if protocol != b'\x08\x00':
            continue
        ip = frame[offset:]
        require(len(ip) >= 20)
        if ip[9] != 6:
            continue
        ihl, total = (ip[0] & 15) * 4, struct.unpack_from('!H', ip, 2)[0]
        tcp = ip[ihl:total]
        require(len(tcp) >= 20)
        source, target = struct.unpack_from('!HH', tcp)
        header = (tcp[12] >> 4) * 4
        require(20 <= header <= len(tcp))
        if (source == 8087 or target == 8087) and len(tcp) > header:
            result.append(stamp)
    return result


def exchanges(pcap):
    """Reassemble without gaps; pair one exact TCP ACK with each HTTP request."""
    flows, positions = {}, {}
    captured = list(packets(pcap))
    times = capture_packet_times(pcap)
    require(len(captured) == len(times))
    for ordinal, (key, seq, ack, payload) in enumerate(captured):
        flows.setdefault(key, []).append((seq, ack, payload))
        positions.setdefault((key, seq), ordinal)

    def index(key, absolute):
        found = [positions[(key, seq)] for seq, _, body in flows[key]
                 if seq <= absolute < seq + len(body)]
        require(bool(found))
        return min(found)

    def completed_index(key, lo, hi):
        covered = []
        for seq, _, body in sorted(flows[key], key=lambda s: positions[(key, s[0])]):
            if seq >= hi or seq + len(body) <= lo:
                continue
            covered.append((max(lo, seq), min(hi, seq + len(body))))
            cursor = lo
            for a, b in sorted(covered):
                if a > cursor:
                    break
                cursor = max(cursor, b)
            if cursor >= hi:
                return positions[(key, seq)]
        require(False)

    def messages(stream, pattern):
        finish = 0
        for hit in re.finditer(pattern, stream):
            if hit.start() < finish:
                continue
            line, headers, body, finish = message(stream, hit.start())
            yield hit.start(), line, headers, body, finish

    result, used = [], set()
    for key, segments in flows.items():
        if key[3] != 8087:
            continue
        for start, stream, _ in runs(segments):
            for offset, line, headers, body, finish in messages(
                    stream, rb'POST /[^ ?\r\n]+ HTTP/1\.1\r\n'):
                path = line.split()[1]
                require(not path.startswith('/trading/') or path in PATHS)
                if path not in PATHS:
                    continue
                require(headers.get('user-agent') == 'UnityApp/2.41.0 (Android)')
                require(type(headers.get('x-pmclient')) is str and bool(headers['x-pmclient']))
                reverse = (key[2], key[3], key[0], key[1])
                replies = []
                for rstart, response_stream, spans in runs(flows.get(reverse, [])):
                    parsed_finish = 0
                    for hit in re.finditer(rb'HTTP/1\.[01] [0-9]{3} [^\r\n]*\r\n', response_stream):
                        if hit.start() < parsed_finish:
                            continue
                        absolute = rstart + hit.start()
                        acks = {ack for lo, hi, ack in spans if lo <= absolute < hi}
                        if start + finish not in acks:
                            continue
                        require(acks == {start + finish})
                        status, rh, reply, rfinish = message(response_stream, hit.start())
                        parsed_finish = rfinish
                        require(status.split()[1] == '200')
                        replies.append((strict_json(reply), rh, index(reverse, absolute),
                                        completed_index(reverse, absolute, rstart + rfinish), (reverse, absolute)))
                require(len(replies) == 1)
                response, response_headers, response_index, response_complete, response_key = replies[0]
                require(response_key not in used)
                used.add(response_key)
                request_index = index(key, start + offset)
                require(response_index > request_index)
                request_complete = completed_index(key, start + offset, start + finish)
                require(response_index > request_complete)
                require(times[response_index] > times[request_complete])
                request = strict_json(body)
                require(type(request) is dict)
                result.append(dict(path=path, headers=headers, request=request,
                    response=response, response_headers=response_headers,
                    request_packet_index=request_index, response_packet_index=response_index,
                    request_time=times[request_index], response_time=times[response_complete]))
    return sorted(result, key=lambda row: row['request_packet_index'])


def keyed(rows, key):
    require(type(rows) is list)
    result = {row[key]: row for row in rows}
    require(len(result) == len(rows))
    return result


def users(snapshot):
    result = keyed(snapshot['users'], 'username')
    require(set(result) == {'PMTrade01', 'PMTrade02'})
    for field in ('id', 'player_id', 'session_id', 'secret'):
        require(len({u[field] for u in result.values()}) == 2)
    for user in result.values():
        require(all(type(user[k]) is str and bool(user[k])
                    for k in ('player_id', 'session_id', 'secret')))
    return result


def stable_users(snapshot, omit_expiry=False):
    omitted = set(USER_DYNAMICS) | ({'expiry_trade'} if omit_expiry else set())
    # Native login legitimately rotates a session; each wire decision is bound
    # separately to the before-decision current session and login receipt.
    omitted.add('session_id')
    return {name: {k: v for k, v in row.items() if k not in omitted}
            for name, row in users(snapshot).items()}


def party(snapshot, user):
    decks = [d for d in snapshot['decks'] if d['player_id'] == user['player_id']
             and str(d['deck_id']) == str(user['active_deck_id'])]
    require(len(decks) == 1)
    ids = strict_json(decks[0]['owned_morty_ids'])
    require(type(ids) is list and bool(ids) and len(set(ids)) == len(ids))
    owned = keyed(snapshot['owned_morties'], 'owned_morty_id')
    require(all(i in owned and owned[i]['player_id'] == user['player_id'] for i in ids))
    return ids


def validate_snapshots(snapshots):
    """Validate the entire reject-then-accept DB history without emitting IDs."""
    require(set(snapshots) == set(STAGES))
    before = snapshots['before-parent']
    base_users = users(before)
    requester, offerer = base_users['PMTrade02'], base_users['PMTrade01']
    originals = keyed(before['owned_morties'], 'owned_morty_id')
    require(len(originals) == 4)
    for user in base_users.values():
        require(sum(m['player_id'] == user['player_id'] for m in originals.values()) == 2)
        party(before, user)
    for snapshot in snapshots.values():
        require(set(snapshot) == TABLES)
        require(stable_users(snapshot, True) == stable_users(before, True))
        require(set(keyed(snapshot['owned_morties'], 'owned_morty_id')) == set(originals))
        require(not snapshot['friend_battle_memberships'])
        for table in TABLES - {'users', 'owned_morties', 'trades', 'trade_offers', 'completed_trades', 'event_queue'}:
            require(keyed(snapshot[table], 'id') == keyed(before[table], 'id'))
        for user in users(snapshot).values():
            party(snapshot, user)
    require(not before['trades'] and not before['trade_offers'] and not before['completed_trades'])
    parent_state = snapshots['parent-created']
    require(len(parent_state['trades']) == 1 and not parent_state['trade_offers'])
    parent = parent_state['trades'][0]
    require(parent['player_id'] == requester['player_id'])
    require(parent['requested_morty_id'] == 'any' and parent['request_variant'] == 'Normal')
    require(type(parent['is_free_trade']) is int and parent['is_free_trade'] == 1)
    require(type(parent['trade_id']) is str and bool(parent['trade_id']))
    requested = originals[parent['morty_trade_id']]
    require(requested['player_id'] == requester['player_id'])
    require(requested['owned_morty_id'] not in party(before, requester))
    expiry = users(parent_state)['PMTrade02']['expiry_trade']
    require(type(expiry) is str and bool(expiry))
    require(users(before)['PMTrade01']['expiry_trade'] == users(parent_state)['PMTrade01']['expiry_trade'])
    for name, snapshot in snapshots.items():
        if name != 'before-parent':
            require(stable_users(snapshot) == stable_users(parent_state))
        if name != 'after-accept':
            require(snapshot['owned_morties'] == before['owned_morties'])
            require(not snapshot['completed_trades'])
            if name != 'before-parent':
                require(snapshot['trades'] == [parent])
    offers = {}
    for decision in ('reject', 'accept'):
        state = snapshots[decision + '-offer-created']
        require(len(state['trade_offers']) == 1)
        offer = state['trade_offers'][0]
        require(type(offer['trade_offer_id']) is str and bool(offer['trade_offer_id']))
        require(offer['trade_id'] == parent['trade_id'] and offer['player_id'] == offerer['player_id'])
        offered = originals[offer['morty_offer_id']]
        require(offered['player_id'] == offerer['player_id'])
        require(offered['owned_morty_id'] not in party(before, offerer))
        require(snapshots['before-' + decision]['trade_offers'] == state['trade_offers'])
        offers[decision] = offer
    require(offers['reject']['trade_offer_id'] != offers['accept']['trade_offer_id'])
    require(offers['reject']['morty_offer_id'] == offers['accept']['morty_offer_id'])
    require(not snapshots['after-reject']['trade_offers'])
    final = snapshots['after-accept']
    require(not final['trades'] and not final['trade_offers'])
    require(len(final['completed_trades']) == 1)
    completion = final['completed_trades'][0]
    offer = offers['accept']
    expected = dict(request_player_id=requester['player_id'], offer_player_id=offerer['player_id'],
        morty_request_id=parent['morty_trade_id'], morty_offer_id=offer['morty_offer_id'],
        trade_request_id=parent['trade_id'], trade_offer_id=offer['trade_offer_id'], is_free_trade=1)
    require(all(type(completion[k]) is type(v) and completion[k] == v for k, v in expected.items()))
    require(all(type(completion[k]) is str and bool(completion[k])
                for k in ('completed_trade_id', 'fulfilled_at')))
    changed = keyed(final['owned_morties'], 'owned_morty_id')
    swapped = {parent['morty_trade_id']: offerer['player_id'], offer['morty_offer_id']: requester['player_id']}
    for instance, original in originals.items():
        require(original['is_locked'] == 'false' and original['is_trading_locked'] == 'false')
        require(changed[instance] == dict(original, player_id=swapped.get(instance, original['player_id'])))
    return dict(snapshots=snapshots, requester=requester, offerer=offerer,
                parent=parent, offers=offers, requested=requested,
                offered=originals[offer['morty_offer_id']])


def read_fixture(directory, accept_prefix='accept'):
    require(re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,47}', accept_prefix) is not None)
    snapshots, hashes = {}, {}
    baseline_path = directory / 'baseline.json'
    baseline = strict_json(baseline_path.read_text(encoding='utf-8'))
    require(type(baseline['version']) is int and baseline['version'] == 1)
    anchor = validate_baseline(baseline)
    baseline_hash = digest(baseline_path)
    def receipt_time(document):
        require(type(document['created_utc']) is str)
        stamp = datetime.datetime.fromisoformat(document['created_utc'].replace('Z', '+00:00'))
        require(stamp.utcoffset() == datetime.timedelta(0))
        return stamp
    previous_time = receipt_time(baseline)
    hashes['baseline'] = baseline_hash
    entries, labels, resumptions = [], {}, {}
    for path in directory.glob('observe-*.json'):
        if path.name.endswith('-attempt.json'):
            continue
        document = strict_json(path.read_text(encoding='utf-8'))
        require(document['private'] is True and document['version'] == 1)
        require(type(document['version']) is int and type(document['sequence']) is int)
        require(type(document['comparison']['passed']) is bool)
        require(document['accounts'] == ['PMTrade01', 'PMTrade02'])
        label = document['label']
        require(type(label) is str and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', label) is not None)
        require(path.name == 'observe-' + label + '.json' and label not in labels)
        require(document['identity'] == anchor)
        entry = dict(document=document, sha256=digest(path))
        entries.append(entry)
        labels[label] = entry
    entries.sort(key=lambda e: e['document']['sequence'])
    for entry in entries:
        document = entry['document']
        current_time = receipt_time(document)
        require(current_time > previous_time)
        previous_time = current_time
        hashes['observation_' + str(document['sequence'])] = entry['sha256']
    for path in directory.glob('resume-*.json'):
        document = strict_json(path.read_text(encoding='utf-8'))
        require(type(document['version']) is int and document['version'] == 1)
        require(type(document['failed_sequence']) is int and
                type(document['previous_successful_sequence']) is int)
        label = document['label']
        require(type(label) is str and label in labels and label not in resumptions)
        require(path.name == 'resume-' + label + '.json')
        sequence = labels[label]['document']['sequence']
        resumed_time = receipt_time(document)
        require(resumed_time > receipt_time(labels[label]['document']))
        if sequence < len(entries):
            require(resumed_time < receipt_time(entries[sequence]['document']))
        resumptions[label] = dict(document=document, sha256=digest(path))
        hashes['resumption_' + str(sequence)] = resumptions[label]['sha256']
    history = verify_history(baseline, baseline_hash, entries, resumptions)
    require(history['pending_resumption'] is None)
    selected_sequences = []
    for original_label, stage, alias in RECEIPTS:
        label = (accept_prefix + original_label[len('accept'):]
                 if original_label.startswith('accept-') else original_label)
        require(label in labels)
        document = labels[label]['document']
        require(document['stage'] == stage and document['comparison'].get('passed') is True)
        selected_sequences.append(document['sequence'])
        if alias is None:
            require(document['snapshot']['trades'] == snapshots['parent-created']['trades'])
            require(not document['snapshot']['trade_offers'])
        else:
            snapshots[alias] = document['snapshot']
    require(selected_sequences == sorted(set(selected_sequences)))
    fixture = validate_snapshots(snapshots)
    fixture['hashes'] = hashes
    selected_offers = {o['trade_offer_id'] for o in fixture['offers'].values()}
    all_offers = {o['trade_offer_id'] for entry in entries
                  for o in entry['document']['snapshot']['trade_offers']}
    unselected_offers = len(all_offers - selected_offers)
    fixture['history'] = dict(full_append_only_observer_history_validated=True,
        observation_count=len(entries), selected_observation_sequences=selected_sequences,
        intermediate_observation_count=len(entries)-len(selected_sequences),
        intermediate_offer_count=unselected_offers,
        intermediate_offer_capture_gap_disclosed=unselected_offers > 0,
        resumed_failed_unchanged_offer_observations=[{k: v for k, v in row.items() if k != 'label'}
            for row in history['failed_observations']],
        continuous_native_observation_of_all_history_proved=False)
    return fixture


def cookie_value(raw):
    require(type(raw) is str)
    require(len(re.findall(r'(?:^|;)\s*session_id\s*=', raw)) == 1)
    cookie = SimpleCookie()
    cookie.load(raw)
    require('session_id' in cookie and bool(cookie['session_id'].value))
    return cookie


def login_identity(row, account):
    require(row['request'].get('secret') == account['secret'])
    cookie = cookie_value(row['response_headers'].get('set-cookie', ''))
    require(set(cookie) == {'session_id'})
    morsel = cookie['session_id']
    require(morsel['path'] == '/trading/' and morsel['httponly']
            and morsel['samesite'].lower() == 'lax')
    query = parse_qs(urlsplit(row['response']['session_url']).query)
    require(len(query.get('token', [])) == 1)
    pieces = query['token'][0].split('.')
    require(len(pieces) == 3)
    claims = strict_json(base64.urlsafe_b64decode(pieces[1] + '=' * (-len(pieces[1]) % 4)))
    require(claims['player_id'] == account['player_id'] and claims['username'] == account['username'])
    require(claims['session_id'] == morsel.value == account['session_id'])
    return morsel.value


def returned_parent(value, fixture):
    p = fixture['parent']
    expected = dict(trade_id=p['trade_id'], player_id=p['player_id'], morty_trade_id=p['morty_trade_id'],
                    morty_request='any', request_variant='Normal', is_free_trade=True)
    require(all(value.get(k) == v and type(value[k]) is type(v) for k, v in expected.items()))
    require(type(value.get('_created')) is str and bool(value['_created']))


def returned_offer(value, fixture, decision):
    o = fixture['offers'][decision]
    expected = {k: o[k] for k in ('trade_offer_id', 'player_id', 'morty_offer_id', 'trade_id')}
    expected.update(request_user_name='PMTrade02', offering_morty_id=fixture['offered']['morty_id'],
                    request_morty_id=fixture['requested']['morty_id'])
    require(set(value) == set(expected) | {'_created'})
    require(all(type(value[k]) is str and value[k] == v for k, v in expected.items()))
    require(type(value['_created']) is str and bool(value['_created']))


def completion_alias(payload):
    """Legacy baseline is allowed; a supplied native alias must match exactly."""
    require(type(payload) is dict and type(payload.get('completed_trades')) is list)
    present = 'competed_trades' in payload
    if present:
        require(type(payload['competed_trades']) is list)
        require(json.dumps(payload['competed_trades'], sort_keys=True, separators=(',', ':')) ==
                json.dumps(payload['completed_trades'], sort_keys=True, separators=(',', ':')))
    return dict(native_completion_alias_present=present,
                legacy_completed_count=len(payload['completed_trades']),
                native_completed_count=len(payload['competed_trades']) if present else None,
                completion_aliases_equal=True if present else None)


def owned_refresh(row, snapshot, account):
    require(set(row['request']) == {'session_id', 'include'})
    require(row['request']['session_id'] == account['session_id'])
    require(type(row['request']['include']) is list and bool(row['request']['include']))
    payload = row['response']
    require(payload['player_id'] == account['player_id'])
    for resource in ('coins', 'coupons', 'permits', 'active_deck_id'):
        require(type(payload[resource]) is int and payload[resource] == int(account[resource]))
    owned = {m['owned_morty_id']: m for m in snapshot['owned_morties']
             if m['player_id'] == account['player_id']}
    returned = keyed(payload['owned_morties'], 'owned_morty_id')
    require(set(returned) == set(owned))
    for m in returned.values():
        require(m['is_locked'] is False and m['is_trading_locked'] is False)
    expected_decks = {int(d['deck_id']): strict_json(d['owned_morty_ids'])
                      for d in snapshot['decks'] if d['player_id'] == account['player_id']}
    actual_decks = keyed(payload['decks'], 'deck_id')
    require(set(actual_decks) == set(expected_decks))
    require(all(type(k) is int and actual_decks[k]['owned_morty_ids'] == v
                for k, v in expected_decks.items()))


def inspect(pcaps, fixture_dir, allow_bounded=False, accept_prefix='accept'):
    require(__debug__)
    fixture = read_fixture(fixture_dir, accept_prefix)
    if isinstance(pcaps, Path):
        pcaps = [pcaps]
    require(bool(pcaps))
    observed = []
    for capture_index, pcap in enumerate(pcaps):
        for row in exchanges(pcap):
            row['capture_index'] = capture_index
            row['order'] = row['request_time']
            row['reply_order'] = row['response_time']
            observed.append(row)
    observed.sort(key=lambda r: r['order'])
    require(len({r['order'] for r in observed}) == len(observed))
    completion_projections = []
    for row in observed:
        if row['path'] == '/trading/get-trades':
            completion_projections.append(dict(capture_index=row['capture_index'],
                request_packet_index=row['request_packet_index'],
                response_packet_index=row['response_packet_index'], **completion_alias(row['response'])))
    def selected(path):
        return [r for r in observed if r['path'] == path]
    def before(a, b):
        require(a['reply_order'] < b['order'])
    parents = selected('/trading/request-morty')
    offers = selected('/trading/offer-morty')
    decisions = selected('/trading/offer-response')
    require(len(parents) == 1 and len(offers) == 2 and len(decisions) == 2)
    parent = parents[0]
    s = fixture['snapshots']
    parent_actor = users(s['parent-created'])['PMTrade02']
    require(parent['request'] == dict(session_id=parent_actor['session_id'], player_id=parent_actor['player_id'],
        owned_morty_id=fixture['parent']['morty_trade_id'], requested_morty_id='any',
        request_variant='Normal', is_free_trade=True))
    require(parent['request']['is_free_trade'] is True)
    require(set(parent['response']) == {'error', 'trade', 'coupons'} and parent['response']['error'] == 'None')
    require(parent['response']['coupons'] == int(parent_actor['coupons']))
    returned_parent(parent['response']['trade'], fixture)
    logins = [r for r in observed if r['path'].rstrip('/') == '/user/login']
    def native_session(row, actor):
        candidates = [r for r in logins if r['reply_order'] < row['order']
                      and r['request'].get('secret') == actor['secret']]
        require(bool(candidates))
        # Only the latest login for this identity can authorize a current
        # session. An earlier valid cookie cannot survive a later rotation.
        require(login_identity(candidates[-1], actor) == actor['session_id'])
    def authenticate(row, actor):
        cookie = cookie_value(row['headers'].get('cookie', ''))
        require(cookie['session_id'].value == actor['session_id'])
        native_session(row, actor)
        require('authorization' not in row['headers'])
    authenticate(parent, parent_actor)
    for index, decision in enumerate(('reject', 'accept')):
        offer, response = offers[index], decisions[index]
        before(parent if index == 0 else decisions[0], offer)
        before(offer, response)
        actor = users(s['before-' + decision])['PMTrade02']
        offerer = users(s[decision + '-offer-created'])['PMTrade01']
        expected_offer = fixture['offers'][decision]
        require(offer['request'] == dict(session_id=offerer['session_id'], player_id=offerer['player_id'],
            offered_morty_id=expected_offer['morty_offer_id'], trade_request_id=fixture['parent']['trade_id']))
        require(set(offer['response']) == {'error', 'offer'} and offer['response']['error'] == 'None')
        returned_offer(offer['response']['offer'], fixture, decision)
        authenticate(offer, offerer)
        expected = dict(trade_request_id=fixture['parent']['trade_id'],
                        trade_offer_id=expected_offer['trade_offer_id'], request_accepted=index == 1)
        require(set(response['request']) == set(expected))
        require(all(type(response['request'][k]) is type(v) and response['request'][k] == v
                    for k, v in expected.items()))
        require(response['response'] == [None, None])
        authenticate(response, actor)
        reloads = [r for r in selected('/trading/get-trades')
                   if offer['reply_order'] < r['order'] and r['reply_order'] < response['order']]
        require(bool(reloads))
        for row in reloads:
            require(set(row['request']) == {'session_id', 'player_id'})
            accounts = users(s['before-' + decision])
            matching = [u for u in accounts.values() if row['request'] ==
                        dict(session_id=u['session_id'], player_id=u['player_id'])]
            require(len(matching) == 1)
            authenticate(row, matching[0])
            require(len(row['response']['trade_requests']) == 1)
            returned_parent(row['response']['trade_requests'][0], fixture)
            require(len(row['response']['trade_offers']) == 1)
            returned_offer(row['response']['trade_offers'][0], fixture, decision)
            require(not row['response']['completed_trades'])
    final = decisions[1]
    refreshed = set()
    for row in selected('/session/player-details'):
        if row['order'] <= final['reply_order']:
            continue
        accounts = users(s['after-accept'])
        matching = [u for u in accounts.values() if row['request'].get('session_id') == u['session_id']]
        require(len(matching) == 1)
        native_session(row, matching[0])
        owned_refresh(row, s['after-accept'], matching[0])
        refreshed.add(matching[0]['username'])
    complete = len(refreshed) == 2
    require(complete or allow_bounded)
    safe = [dict(path=r['path'], capture_index=r['capture_index'], status=200,
                 request_packet_index=r['request_packet_index'], response_packet_index=r['response_packet_index'],
                 request_body_keys=sorted(set(r['request']) & SAFE_BODY_KEYS),
                 unlisted_request_body_key_count=len(set(r['request']) - SAFE_BODY_KEYS), native_headers_present=True,
                 exact_tcp_ack_pair=True) for r in observed]
    return dict(schema_version=1, evidence_kind='Native Android isolated replacement-server observations',
        pcap_sha256=[digest(p) for p in pcaps], fixture_sha256=fixture['hashes'], exchanges=safe,
        selected_native_decisions_and_refreshes_proved=complete,
        full_native_decision_cycle_proved=complete and not fixture.get('history', {}).get('intermediate_observation_count', 0),
        bounded_stage_only=not complete,
        evidence_scope='Selected native decisions and refreshes; intermediate observer history is disclosed separately',
        observer_history=fixture.get('history', {}),
        proof=dict(native_parent_and_both_offers_match_database=True,
            phase_order_proved_by_actual_capture_packet_times=True,
            exact_three_field_boolean_decisions=[False, True],
            login_scoped_cookie_matches_current_requester_session=True,
            rejection_removes_only_selected_offer_and_preserves_parent=True,
            acceptance_swaps_exactly_two_spares_and_inserts_one_completion=True,
            acceptance_removes_parent_and_all_attached_offers=True,
            database_parent_counts=[len(s[k]['trades']) for k in STAGES],
            database_offer_counts=[len(s[k]['trade_offers']) for k in STAGES],
            database_completion_counts=[len(s[k]['completed_trades']) for k in STAGES],
            protected_database_fields_preserved_with_controlled_native_presence=True,
            active_parties_attacks_items_stats_currencies_raw_flags_preserved=True,
            post_accept_native_owned_refresh_actor_count=len(refreshed),
            both_actors_native_owned_refresh_and_boolean_unlock_proved=complete,
            completion_projection_observations=completion_projections,
            all_observed_native_completion_aliases_match_legacy=True,
            all_get_trades_responses_have_native_completion_alias=all(
                r['native_completion_alias_present'] for r in completion_projections)),
        gaps=dict(other_actor_refresh_missing=not complete, gui_selector_availability_proved=False),
        scripted_setup_cleanup_counted_as_native_evidence=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pcap', type=Path, action='append', required=True)
    parser.add_argument('--fixture-dir', type=Path, required=True)
    parser.add_argument('--allow-bounded', action='store_true')
    parser.add_argument('--accept-prefix', default='accept')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        private = (ROOT / '.research').resolve()
        require(all(p.resolve().is_relative_to(private) for p in args.pcap + [args.fixture_dir, args.output]))
        require(not args.output.exists())
        result = inspect(args.pcap, args.fixture_dir, args.allow_bounded, args.accept_prefix)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2)
            handle.write('\n')
    except Exception as error:
        raise SystemExit('Native decision proof failed: ' + type(error).__name__) from None
    print('Sanitized native decision proof written; selected cycles: ' +
          str(result['selected_native_decisions_and_refreshes_proved']))


if __name__ == '__main__':
    main()

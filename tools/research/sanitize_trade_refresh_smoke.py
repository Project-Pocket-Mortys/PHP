"""Read-only proof of a synthetic invalidation consumed by Android 2.41.0.

Private PCAP and identity/publication receipts stay under .research. This proves
the native consumer only, not an actual trade mutation or original-service use.
"""
import argparse
import base64
import datetime
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from capture_friend_battle_http import ROOT
from export_android_startup import assemble, flows, messages
from sanitize_native_trade_cancellation import digest, require
from sanitize_native_trade_decisions import capture_packet_times, cookie_value, login_identity, strict_json


INCLUDE = ['morties', 'attacks', 'decks', 'mortydex']
PATHS = {'/user/login', '/session/join-room', '/session/player-details',
         '/trading/get-trades', '/trading/config'}


def completed_time(rows, lo, hi):
    """First time the entire byte interval is present, including reordered TCP."""
    require(lo < hi)
    covered = []
    for row in sorted(rows, key=lambda p: p['time']):
        start, end = row['seq'], row['seq'] + len(row['payload'])
        if start >= hi or end <= lo:
            continue
        covered.append((max(lo, start), min(hi, end)))
        cursor = lo
        for a, b in sorted(covered):
            if a > cursor:
                break
            cursor = max(cursor, b)
        if cursor >= hi:
            return row['time']
    require(False)


def native(headers, sse=False):
    agent = ('com.Tivadar.Best.HTTP v3.0.17.0/Unity 2022.3.62f2'
             if sse else 'UnityApp/2.41.0 (Android)')
    require(headers.get('user-agent') == agent)
    require(type(headers.get('x-pmclient')) is str and bool(headers['x-pmclient']))
    require('authorization' not in headers)


def wire_observations(pcap):
    capture_packet_times(pcap)  # Fail on regressing/truncated capture timestamps.
    flow, zero = flows(pcap)
    exchanges, events = [], []
    for key, rows in flow.items():
        if key[3] != 8087:
            continue
        joined = assemble(rows)
        if not joined:
            continue
        start, data, _ = joined
        reverse = (key[2], key[3], key[0], key[1])
        reply_rows = flow.get(reverse, [])
        assembled_reply = assemble(reply_rows)
        require(assembled_reply is not None)
        rstart, rdata, spans = assembled_reply
        replies = list(messages(rdata))
        used = set()
        for request in messages(data):
            method, target, _ = request['line'].split(' ')
            path = urlsplit(target).path.rstrip('/')
            if path.startswith('/trading/'):
                require(path in PATHS)  # No gameplay mutation may masquerade as smoke.
            if path not in PATHS and path != '/sse':
                continue
            native(request['headers'], path == '/sse')
            require(request['finish'] is not None)
            matches = []
            for i, reply in enumerate(replies):
                absolute = rstart + reply['start']
                acks = {ack for lo, hi, ack in spans if lo <= absolute < hi}
                if start + request['finish'] in acks:
                    require(acks == {start + request['finish']})
                    matches.append((i, reply))
            require(len(matches) == 1)
            i, reply = matches[0]
            require(i not in used)
            used.add(i)
            require(reply['line'].split()[1] == '200')
            request_time = completed_time(rows, start + request['start'], start + request['finish'])
            if path == '/sse':
                require(method == 'GET' and reply['sse'])
                token = parse_qs(urlsplit(target).query).get('token', [])
                require(len(token) == 1)
                pos = 0
                for boundary in re.finditer(rb'\r?\n\r?\n', reply['body']):
                    raw = reply['body'][pos:boundary.start()]
                    begin, pos = pos, boundary.end()
                    fields = {}
                    for line in raw.splitlines():
                        if not line or line.startswith(b':'):
                            continue
                        name, value = line.split(b':', 1)
                        fields.setdefault(name, []).append(value.lstrip(b' '))
                    if b'event' not in fields:
                        continue
                    require(len(fields[b'event']) == 1)
                    name = fields[b'event'][0].decode('ascii')
                    if name != 'session:start' and not name.startswith('trade:'):
                        continue
                    require(b'data' in fields)
                    payload = strict_json(b'\n'.join(fields[b'data']))
                    stamps = []
                    covered = 0
                    for lo, hi, wire_start in reply['spans']:
                        a, b = max(begin, lo), min(pos, hi)
                        if a < b:
                            absolute = rstart + reply['body_start'] + wire_start + a - lo
                            stamps.append(completed_time(reply_rows, absolute, absolute + b-a))
                            covered += b-a
                    require(covered == pos-begin and bool(stamps))
                    events.append(dict(event=name, payload=payload, time=max(stamps),
                        token=token[0], request_time=request_time,
                        client=request['headers']['x-pmclient']))
            else:
                require(method == 'POST' and reply['finish'] is not None)
                exchanges.append(dict(path=path, headers=request['headers'],
                    request=strict_json(request['body']), response=strict_json(reply['body']),
                    response_headers=reply['headers'], request_time=request_time,
                    response_time=completed_time(reply_rows, rstart+reply['start'], rstart+reply['finish'])))
    return sorted(exchanges, key=lambda r: r['request_time']), sorted(events, key=lambda e: e['time']), zero


def primary(document):
    require(document.get('private') is True)
    users = document['snapshot']['users']
    found = [u for u in users if u['username'] == 'PMTrade01']
    require(len(found) == 1)
    user = found[0]
    require(all(type(user[k]) is str and bool(user[k]) for k in ('secret', 'session_id', 'player_id')))
    return user


def token_claims(token):
    pieces = token.split('.')
    require(len(pieces) == 3)
    return strict_json(base64.urlsafe_b64decode(pieces[1] + '=' * (-len(pieces[1]) % 4)))


def validate(rows, events, anchor, current, publication, zero):
    old, user = primary(anchor), primary(current)
    require(all(old[k] == user[k] for k in ('secret', 'player_id', 'username')))
    require(publication.get('private') is True and publication.get('synthetic') is True)
    require(publication['event'] == 'trade:offer-submit')
    require(publication['player_id'] == user['player_id'] and publication['session_id'] == user['session_id'])
    revision = publication['revision']
    require(type(revision) is str and revision.isascii() and revision.isdigit() and int(revision) > 0)
    stamp = datetime.datetime.fromisoformat(publication['published_utc'])
    require(stamp.tzinfo is not None)
    # Docker/WSL publication UTC and Android guest PCAP timestamps are distinct
    # clocks. The receipt establishes operator-declared synthetic provenance;
    # its UTC timestamp cannot establish ordering or latency in the PCAP.
    logins = [r for r in rows if r['path'] == '/user/login']
    require(len(logins) == 1 and login_identity(logins[0], user) == user['session_id'])
    login = logins[0]
    starts = [e for e in events if e['event'] == 'session:start']
    trades = [e for e in events if e['event'].startswith('trade:')]
    require(len(starts) == len(trades) == 1)
    start, trade = starts[0], trades[0]
    claims = token_claims(start['token'])
    require(all(claims[k] == user[k] for k in ('player_id', 'session_id', 'username')))
    require(trade['token'] == start['token'])
    login_token = parse_qs(urlsplit(login['response']['session_url']).query)['token']
    require(login_token == [start['token']])
    require(start['client'] == trade['client'] == login['headers']['x-pmclient'])
    require(all(start['payload'][k] == user[k] for k in ('player_id', 'session_id', 'username')))
    require(trade['event'] == publication['event'] and type(trade['payload']) is dict and trade['payload'] == {})
    require(login['response_time'] < start['time'])
    joins = [r for r in rows if r['path'] == '/session/join-room']
    require(len(joins) == 1)
    join = joins[0]
    require(join['request']['session_id'] == user['session_id'])
    require(type(join['response']) is dict and 'error' not in join['response'])
    require(start['time'] < join['request_time'] < join['response_time'] < trade['time'])
    details = [r for r in rows if r['path'] == '/session/player-details']
    initial = [r for r in details if start['time'] < r['request_time'] < join['request_time']]
    require(bool(initial))
    require(all(r['response_time'] < join['request_time'] for r in initial))
    require(any(type(r['request'].get('include')) is list
                and set(INCLUDE) < set(r['request']['include']) for r in initial))
    post = [r for r in rows if r['request_time'] > trade['time']]
    listings = [r for r in post if r['path'] == '/trading/get-trades']
    refreshed = [r for r in post if r['path'] == '/session/player-details']
    require(len(listings) == len(refreshed) == 1)
    listing, detail = listings[0], refreshed[0]
    # There must be no competing trade refresh after join and before the event.
    require(not [r for r in rows if r['path'] in ('/trading/get-trades', '/session/player-details')
                 and join['response_time'] < r['request_time'] <= trade['time']])
    for row in [*initial, listing, detail]:
        require(type(row['request']) is dict and row['request']['session_id'] == user['session_id'])
        require(row['request_time'] < row['response_time'])
        require(type(row['response']) is dict and 'error' not in row['response'])
        require(row['headers']['x-pmclient'] == start['client'])
    require(listing['request'].get('player_id') == user['player_id'])
    require(set(listing['request']) == {'session_id', 'player_id'})
    require(cookie_value(listing['headers'].get('cookie', ''))['session_id'].value == user['session_id'])
    require(all(type(listing['response'].get(k)) is list for k in
                ('trade_requests', 'trade_offers', 'competed_trades')))
    require(set(detail['request']) == {'session_id', 'include'})
    require(type(detail['request']['include']) is list and len(detail['request']['include']) == 4)
    require(set(detail['request']['include']) == set(INCLUDE))
    require(detail['response'].get('player_id') == user['player_id'])
    require(detail['response'].get('username') == user['username'])
    require(all(type(detail['response'].get(k)) is list for k in ('owned_morties', 'decks', 'mortydex')))
    times = [('native_login_response', login['response_time']), ('session_start', start['time']),
             ('native_join_response', join['response_time']),
             ('trade_event_frame_complete', trade['time']), ('native_get_trades_request', listing['request_time']),
             ('native_player_details_request', detail['request_time']),
             ('native_get_trades_response', listing['response_time']), ('native_player_details_response', detail['response_time'])]
    return dict(version=1, evidence_kind='Synthetic replacement-server invalidation consumed by native Android 2.41.0',
        native_consumer_smoke_proved=True, actual_trade_mutation_publication_proved=False,
        original_service_behavior_proved=False, immediate_offer_cancellation_unlock_proved=False,
        publication_clock_order_proved=False, publication_to_sse_latency_proved=False,
        timing_scope='Relative Android PCAP timestamps only; Docker/WSL publication receipt uses an independent clock',
        account='PMTrade01', event='trade:offer-submit', data_is_empty_object=True,
        details_include=INCLUDE, details_mask='0x78',
        identity_bound_through_native_login_cookie_session_start_and_current_snapshot=True,
        timestamps=[dict(action=action, seconds=round(time-zero, 6)) for action, time in times])


def inspect(pcap, anchor, auth_snapshot, publication):
    require(__debug__)
    rows, events, zero = wire_observations(pcap)
    result = validate(rows, events, strict_json(anchor.read_text(encoding='utf-8')),
        strict_json(auth_snapshot.read_text(encoding='utf-8')),
        strict_json(publication.read_text(encoding='utf-8')), zero)
    result['input_sha256'] = {name: digest(path) for name, path in
        [('pcap', pcap), ('identity_anchor', anchor), ('current_auth_snapshot', auth_snapshot), ('synthetic_publication', publication)]}
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('pcap', 'anchor', 'auth-snapshot', 'publication', 'output'):
        parser.add_argument('--'+name, required=True, type=Path)
    args = parser.parse_args()
    paths = [args.pcap, args.anchor, args.auth_snapshot, args.publication, args.output]
    require(all(path.resolve().is_relative_to((ROOT/'.research').resolve()) for path in paths))
    require(not args.output.exists())
    try:
        result = inspect(args.pcap, args.anchor, args.auth_snapshot, args.publication)
        with args.output.open('x', encoding='utf-8') as file:
            json.dump(result, file, indent=2)
            file.write('\n')
    except Exception as error:
        raise SystemExit('Native trade refresh smoke proof failed: '+type(error).__name__) from None
    print('Sanitized synthetic native trade refresh smoke proof written.')


if __name__ == '__main__':
    main()

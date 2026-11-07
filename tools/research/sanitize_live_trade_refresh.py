"""Read-only proof of live offer, rejection and acceptance refresh on two clients.

Each device keeps its own packet clock. Empty SSE payloads prove phase-level
consumption only; they cannot bind a notification frame to an individual ID.
Private captures/receipts and the redacted output stay below .research.
"""
import argparse
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
import re

from capture_friend_battle_http import ROOT
from export_android_startup import assemble, flows, messages
from sanitize_native_trade_cancellation import digest, require
from sanitize_native_trade_decisions import (capture_packet_times, cookie_value,
    login_identity, strict_json)
from sanitize_trade_refresh_smoke import INCLUDE, completed_time, native, token_claims
from live_trade_refresh_fixture import verify_history

PATHS = {'/user/login', '/session/join-room', '/session/player-details',
         '/trading/get-trades', '/trading/config', '/trading/request-morty',
         '/trading/offer-morty', '/trading/offer-response'}


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
                require(path in PATHS)  # Only explicitly reviewed native mutations are admissible.
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


def accounts(document):
    require(document.get('private') is True)
    rows = document['snapshot']['users']
    result = {row['username']: row for row in rows}
    require(len(rows) == len(result) == 2 and set(result) == {'PMTrade01', 'PMTrade02'})
    for key in ('secret', 'session_id', 'player_id'):
        require(all(type(u[key]) is str and bool(u[key]) for u in rows))
        require(len({u[key] for u in rows}) == 2)
    return result


def identity(rows, events, user):
    """Bind every observed request and frame to the latest native login."""
    logins = [row for row in rows if row['path'] == '/user/login']
    require(bool(logins))
    for row in logins:
        login_identity(row, user)
        require(type(row['request']) is dict)
    client = logins[0]['headers']['x-pmclient']
    require(all(row['headers']['x-pmclient'] == client for row in rows))
    for row in rows:
        require(row['request_time'] < row['response_time'])
        require('authorization' not in row['headers'])
        if row['path'] == '/user/login':
            continue
        prior = [login for login in logins if login['response_time'] < row['request_time']]
        require(bool(prior))
        require(type(row['request']) is dict)
        if row['path'] == '/trading/config' and row['request'] == {'session_id': None}:
            # Native startup asks for static trading configuration before
            # assigning the login session into its request model. Its cookie
            # already identifies the current login; no gameplay is authorized.
            require(not [entry for entry in rows if entry['path'] == '/session/player-details'
                         and entry['request_time'] < row['request_time']])
        elif 'session_id' in row['request']:
            require(row['request']['session_id'] == user['session_id'])
        if row['path'].startswith('/trading/'):
            require(cookie_value(row['headers'].get('cookie', ''))['session_id'].value == user['session_id'])
        if type(row['response']) is dict:
            require('error' not in row['response'] or row['response']['error'] == 'None')
    starts = [event for event in events if event['event'] == 'session:start']
    require(bool(starts))
    for event in events:
        prior = [login for login in logins if login['response_time'] < event['time']]
        require(bool(prior))
        login = prior[-1]
        tokens = parse_qs(urlsplit(login['response']['session_url']).query)['token']
        require(tokens == [event['token']] and event['client'] == client)
        claims = token_claims(event['token'])
        require(all(claims[key] == user[key] for key in ('username', 'player_id', 'session_id')))
        if event['event'] == 'session:start':
            require(all(event['payload'][key] == user[key] for key in ('username', 'player_id', 'session_id')))
        else:
            require(event['payload'] == {} and type(event['payload']) is dict)
            require(any(start['token'] == event['token'] and start['time'] < event['time'] for start in starts))
    return client


def notification(before, after, actor, recipient, event):
    def index(snapshot):
        rows = snapshot['trade_refresh_notifications']
        result = {row['player_id']: row for row in rows}
        require(len(result) == len(rows))
        for row in rows:
            require(type(row['revision']) is str and row['revision'].isascii()
                    and row['revision'].isdigit() and int(row['revision']) > 0)
        return result
    old, new = index(before), index(after)
    player = recipient['player_id']
    require(player != actor['player_id'])
    require(player in new and new[player]['event_name'] == event)
    require(int(new[player]['revision']) == int(old.get(player, {}).get('revision', '0')) + 1)
    require({k: v for k, v in old.items() if k != player} ==
            {k: v for k, v in new.items() if k != player})
    return dict(event=event, recipient=recipient['username'], actor=actor['username'],
                exact_recipient_revision_increment=True)


def fixture_states(parent_doc, offer_doc, rejected_doc):
    users = accounts(offer_doc)
    for doc in (parent_doc, rejected_doc):
        current = accounts(doc)
        require(all(all(current[name][key] == users[name][key]
                        for key in ('username', 'secret', 'player_id', 'session_id')) for name in users))
    before, offered, rejected = [doc['snapshot'] for doc in (parent_doc, offer_doc, rejected_doc)]
    require(len(before['trades']) == 1 and not before['trade_offers'])
    require(before['trades'] == offered['trades'] == rejected['trades'])
    require(len(offered['trade_offers']) == 1 and not rejected['trade_offers'])
    require(before['completed_trades'] == offered['completed_trades'] == rejected['completed_trades'])
    parent, offer = before['trades'][0], offered['trade_offers'][0]
    require(parent['player_id'] == users['PMTrade02']['player_id'])
    require(offer['player_id'] == users['PMTrade01']['player_id'] and offer['trade_id'] == parent['trade_id'])
    require(all(type(value) is str and bool(value) for value in
                (parent['trade_id'], parent['morty_trade_id'], offer['trade_offer_id'], offer['morty_offer_id'])))
    # Reject never moves physical inventory. Sessions are checked above; any
    # broader state invariants are rechecked by the fixture's pure validator.
    require(before['owned_morties'] == offered['owned_morties'] == rejected['owned_morties'])
    notes = [notification(before, offered, users['PMTrade01'], users['PMTrade02'], 'trade:offer-submit'),
             notification(offered, rejected, users['PMTrade02'], users['PMTrade01'], 'trade:offer-rejected')]
    return users, parent, offer, notes


def returned_offer(value, parent, offer, users, snapshot):
    expected = {key: offer[key] for key in ('trade_offer_id', 'trade_id', 'player_id', 'morty_offer_id')}
    owned = {morty['owned_morty_id']: morty for morty in snapshot['owned_morties']}
    require(len(owned) == len(snapshot['owned_morties']))
    expected.update(request_user_name=users['PMTrade02']['username'],
                    request_morty_id=owned[parent['morty_trade_id']]['morty_id'],
                    offering_morty_id=owned[offer['morty_offer_id']]['morty_id'])
    require(type(value) is dict and set(value) == set(expected) | {'_created'})
    require(all(type(value[key]) is str and value[key] == wanted for key, wanted in expected.items()))
    require(type(value['_created']) is str and bool(value['_created']))


def detail(row, user, snapshot, locked):
    require(row['request'] == {'session_id': user['session_id'], 'include': INCLUDE}
            or (set(row['request']) == {'session_id', 'include'}
                and row['request']['session_id'] == user['session_id']
                and type(row['request']['include']) is list
                and len(row['request']['include']) == 4 and set(row['request']['include']) == set(INCLUDE)))
    value = row['response']
    require(value['player_id'] == user['player_id'] and value['username'] == user['username'])
    require(all(type(value[key]) is list for key in ('owned_morties', 'decks', 'mortydex')))
    expected = {morty['owned_morty_id'] for morty in snapshot['owned_morties'] if morty['player_id'] == user['player_id']}
    returned = {morty['owned_morty_id']: morty for morty in value['owned_morties']}
    require(len(returned) == len(value['owned_morties']) and set(returned) == expected)
    for key, morty in returned.items():
        require(morty['is_locked'] is False and type(morty['is_trading_locked']) is bool)
        require(morty['is_trading_locked'] is (key in locked))


def listing(row, user, parent, offer, users, snapshot, offer_present):
    require(row['request'] == {'session_id': user['session_id'], 'player_id': user['player_id']})
    payload = row['response']
    require(type(payload) is dict)
    require(type(payload.get('completed_trades')) is list)
    require(payload.get('completed_trades') == payload.get('competed_trades'))
    require('completed_trades' in payload and 'competed_trades' in payload)
    completed = payload['completed_trades']
    stored = {row['completed_trade_id']: row for row in snapshot['completed_trades']}
    require(len(stored) == len(snapshot['completed_trades']) == len(completed))
    require({row['completed_trade_id'] for row in completed} == set(stored))
    for row in completed:
        expected = stored[row['completed_trade_id']]
        require(all(row[key] == expected[key] for key in ('completed_trade_id', 'request_player_id',
            'offer_player_id', 'morty_request_id', 'morty_offer_id', 'trade_offer_id', 'trade_request_id')))
        require(type(row['is_free_trade']) is bool and row['is_free_trade'] == bool(expected['is_free_trade']))
    require(type(payload.get('trade_requests')) is list)
    if parent is None:
        require(payload['trade_requests'] == [])
    else:
        require(len(payload['trade_requests']) == 1)
        request = payload['trade_requests'][0]
        require(all(request[key] == parent[key] for key in ('trade_id', 'player_id', 'morty_trade_id')))
    require(type(payload.get('trade_offers')) is list)
    if offer_present:
        require(len(payload['trade_offers']) == 1)
        returned_offer(payload['trade_offers'][0], parent, offer, users, snapshot)
    else:
        require(payload['trade_offers'] == [])
    return dict(native_completion_alias_present=True, completion_aliases_equal=True,
                offer_metadata='owner_username_and_species_ids' if offer_present else 'no_offer_after_rejection')


def event_refresh(rows, events, name, phase):
    found = [event for event in events if event['event'] == name and event.get('phase', phase) == phase]
    require(len(found) == 1)
    event = found[0]
    next_events = [entry['time'] for entry in events if entry['time'] > event['time']]
    bound = min(next_events, default=float('inf'))
    candidates = [row for row in rows if event['time'] < row['request_time'] < bound
                  and row.get('phase', phase) == phase
                  and row['path'] in ('/trading/get-trades', '/session/player-details')]
    require(len(candidates) >= 2)
    first = candidates[:2]
    require({row['path'] for row in first} == {'/trading/get-trades', '/session/player-details'})
    require(all(row['response_time'] < bound for row in first))
    # A duplicate/poll cannot compete before both native refresh replies finish.
    finish = max(row['response_time'] for row in first)
    require(not [row for row in candidates[2:] if row['request_time'] <= finish])
    return event, next(row for row in first if row['path'] == '/trading/get-trades'), next(
        row for row in first if row['path'] == '/session/player-details')


def validate(primary_rows, primary_events, peer_rows, peer_events, parent_doc, offer_doc, rejected_doc,
             primary_zero=0, peer_zero=0):
    users, parent, offer, notifications = fixture_states(parent_doc, offer_doc, rejected_doc)
    primary, peer = users['PMTrade01'], users['PMTrade02']
    identity(primary_rows, primary_events, primary)
    identity(peer_rows, peer_events, peer)
    offers = [row for row in primary_rows if row['path'] == '/trading/offer-morty']
    decisions = [row for row in peer_rows if row['path'] == '/trading/offer-response']
    require(len(offers) == len(decisions) == 1)
    require(not [row for row in peer_rows if row['path'] == '/trading/offer-morty'])
    require(not [row for row in primary_rows if row['path'] in ('/trading/offer-response', '/trading/request-morty')])
    create, reject = offers[0], decisions[0]
    require(create['request'] == dict(session_id=primary['session_id'], player_id=primary['player_id'],
            offered_morty_id=offer['morty_offer_id'], trade_request_id=parent['trade_id']))
    require(set(create['response']) == {'error', 'offer'} and create['response']['error'] == 'None')
    returned_offer(create['response']['offer'], parent, offer, users, offer_doc['snapshot'])
    require(reject['request'] == dict(trade_request_id=parent['trade_id'],
            trade_offer_id=offer['trade_offer_id'], request_accepted=False))
    require(reject['request']['request_accepted'] is False and reject['response'] == [None, None])
    offer_event, offer_listing, offer_detail = event_refresh(peer_rows, peer_events, 'trade:offer-submit', 'offer')
    reject_event, reject_listing, reject_detail = event_refresh(primary_rows, primary_events, 'trade:offer-rejected', 'reject')
    require(offer_detail['response_time'] < reject['request_time'])
    require(offer_listing['response_time'] < reject['request_time'])
    require(create['response_time'] < reject_event['time'])
    own = [row for row in primary_rows if row['path'] == '/session/player-details'
           and create['response_time'] < row['request_time'] < reject_event['time']]
    require(bool(own))
    own_detail = own[0]
    require(own_detail['response_time'] < reject_event['time'])
    detail(own_detail, primary, offer_doc['snapshot'], {offer['morty_offer_id']})
    detail(offer_detail, peer, offer_doc['snapshot'], {parent['morty_trade_id']})
    detail(reject_detail, primary, rejected_doc['snapshot'], set())
    projections = [listing(offer_listing, peer, parent, offer, users, offer_doc['snapshot'], True),
                   listing(reject_listing, primary, parent, offer, users, rejected_doc['snapshot'], False)]
    allowed = {'session:start', 'trade:request-submit', 'trade:offer-submit', 'trade:offer-rejected'}
    require(all(event['event'] in allowed for event in primary_events + peer_events))
    require(not [event for event in primary_events if event['event'] == 'trade:offer-submit'
                 and event.get('phase') != 'startup' and event['time'] > create['request_time']])
    require(not [event for event in peer_events if event['event'] == 'trade:offer-rejected' and event.get('phase') != 'startup'])
    timings = []
    for device, zero, entries in [
        ('primary', primary_zero, [('native_offer_response', create['response_time']),
          ('local_owned_details_request', own_detail['request_time']), ('rejection_frame_complete', reject_event['time']),
          ('rejection_get_trades_request', reject_listing['request_time']), ('rejection_owned_details_request', reject_detail['request_time'])]),
        ('peer', peer_zero, [('offer_frame_complete', offer_event['time']),
          ('offer_get_trades_request', offer_listing['request_time']), ('offer_owned_details_request', offer_detail['request_time']),
          ('native_owner_reject_response', reject['response_time'])])]:
        timings.append(dict(device=device, timestamps=[dict(action=action, seconds=round(stamp-zero, 6)) for action, stamp in entries]))
    return dict(schema_version=1, evidence_kind='Live replacement-server native Android 2.41.0 offer and owner rejection',
        actual_native_offer_and_owner_rejection_proved=True, native_cross_client_refresh_observed=True,
        acceptance_proved=False, original_service_behavior_proved=False,
        cross_device_clock_order_proved=False, mutation_to_sse_latency_proved=False,
        exact_sse_frame_trade_id_binding_proved=False,
        sse_correlation_scope='Empty payload invalidations correlated by capture phase, exact HTTP trade IDs and DB recipient revisions',
        timing_scope='Only ordering within each device capture clock; no cross-device or server clock alignment',
        details_include=INCLUDE, details_mask='0x78', separate_native_client_identities_proved=True,
        notifications=notifications, listing_classification=projections, device_timelines=timings)


def device_observations(captures):
    """Merge only one device's ordered captures; never compare device clocks."""
    rows, events, zero, hashes, previous = [], [], None, [], None
    require(bool(captures))
    if isinstance(captures, Path):
        rows, events, zero = wire_observations(captures)
        return rows, events, zero, [dict(phase='continuous', sha256=digest(captures))]
    require(set(captures) == {'startup', 'offer', 'reject'})
    for phase in ('startup', 'offer', 'reject'):
        require(bool(captures[phase]))
        for pcap in captures[phase]:
            captured_rows, captured_events, start = wire_observations(pcap)
            stamps = [r['request_time'] for r in captured_rows] + [r['response_time'] for r in captured_rows] + [e['time'] for e in captured_events]
            require(bool(stamps) and (previous is None or min(stamps) > previous))
            previous = max(stamps)
            zero = start if zero is None else zero
            for item in captured_rows + captured_events:
                item['phase'] = phase
            rows.extend(captured_rows)
            events.extend(captured_events)
            hashes.append(dict(phase=phase, sha256=digest(pcap)))
    return rows, events, zero, hashes


def bounded_rejection_prefix(primary_rows, primary_events, peer_rows, peer_events):
    """Bound later phases using separate local-device markers, never an offset."""
    offers = [row for row in primary_rows if row['path'] == '/trading/offer-morty']
    require(1 <= len(offers) <= 2)
    if len(offers) == 1:
        return primary_rows, primary_events, peer_rows, peer_events, False
    peer_offers = [event for event in peer_events if event['event'] == 'trade:offer-submit']
    require(len(peer_offers) == 2)
    primary_cutoff, peer_cutoff = offers[1]['request_time'], peer_offers[1]['time']
    selected_primary = [row for row in primary_rows if row['request_time'] < primary_cutoff]
    selected_peer = [row for row in peer_rows if row['request_time'] < peer_cutoff]
    require(all(row['response_time'] < primary_cutoff for row in selected_primary))
    require(all(row['response_time'] < peer_cutoff for row in selected_peer))
    return (selected_primary, [event for event in primary_events if event['time'] < primary_cutoff],
            selected_peer, [event for event in peer_events if event['time'] < peer_cutoff], True)


def validate_acceptance(primary_rows, primary_events, peer_rows, peer_events, rejected_doc, offered_doc, accepted_doc):
    """Optional second offer + acceptance; each local refresh is required."""
    users = accounts(offered_doc)
    primary, peer = users['PMTrade01'], users['PMTrade02']
    for doc in (rejected_doc, accepted_doc):
        current = accounts(doc)
        require(all(all(current[name][key] == users[name][key] for key in
                       ('secret', 'player_id', 'session_id')) for name in users))
    before, offered, accepted = [doc['snapshot'] for doc in (rejected_doc, offered_doc, accepted_doc)]
    require(len(offered['trades']) == len(offered['trade_offers']) == 1)
    require(before['trades'] == offered['trades'] and before['trade_offers'] == [])
    require(before['owned_morties'] == offered['owned_morties'])
    require(accepted['trades'] == accepted['trade_offers'] == [])
    require(len(accepted['completed_trades']) == len(before['completed_trades']) + 1)
    parent, offer = offered['trades'][0], offered['trade_offers'][0]
    require(offer['trade_id'] == parent['trade_id'] and offer['player_id'] == primary['player_id'])
    notifications = [notification(before, offered, primary, peer, 'trade:offer-submit'),
                     notification(offered, accepted, peer, primary, 'trade:offer-accepted')]
    identity(primary_rows, primary_events, primary)
    identity(peer_rows, peer_events, peer)
    offers = [row for row in primary_rows if row['path'] == '/trading/offer-morty']
    decisions = [row for row in peer_rows if row['path'] == '/trading/offer-response']
    require(len(offers) == len(decisions) == 2)
    create, accept = offers[1], decisions[1]
    require(create['request'] == dict(session_id=primary['session_id'], player_id=primary['player_id'],
            offered_morty_id=offer['morty_offer_id'], trade_request_id=parent['trade_id']))
    require(set(create['response']) == {'error', 'offer'} and create['response']['error'] == 'None')
    returned_offer(create['response']['offer'], parent, offer, users, offered)
    require(create['response']['offer']['trade_offer_id'] != offers[0]['response']['offer']['trade_offer_id'])
    require(accept['request'] == dict(trade_request_id=parent['trade_id'],
            trade_offer_id=offer['trade_offer_id'], request_accepted=True))
    require(accept['request']['request_accepted'] is True and accept['response'] == [None, None])
    require(decisions[0]['response_time'] < accept['request_time'])
    peer_offers = [event for event in peer_events if event['event'] == 'trade:offer-submit']
    require(len(peer_offers) == 2)
    boundary = peer_offers[1]['time']
    peer_suffix = [event for event in peer_events if event['time'] >= boundary]
    offer_event, offer_listing, offer_detail = event_refresh(peer_rows, peer_suffix, 'trade:offer-submit', 'offer')
    accepted_event, accepted_listing, accepted_detail = event_refresh(primary_rows, primary_events, 'trade:offer-accepted', 'accept')
    require(max(offer_listing['response_time'], offer_detail['response_time']) < accept['request_time'])
    require(create['response_time'] < accepted_event['time'])
    own_offer = [row for row in primary_rows if row['path'] == '/session/player-details'
                 and create['response_time'] < row['request_time'] < accepted_event['time']]
    require(bool(own_offer) and own_offer[0]['response_time'] < accepted_event['time'])
    own_accept = [row for row in peer_rows if row['path'] == '/session/player-details'
                  and accept['response_time'] < row['request_time']]
    require(bool(own_accept))
    detail(own_offer[0], primary, offered, {offer['morty_offer_id']})
    detail(offer_detail, peer, offered, {parent['morty_trade_id']})
    detail(accepted_detail, primary, accepted, set())
    detail(own_accept[0], peer, accepted, set())
    projections = [listing(offer_listing, peer, parent, offer, users, offered, True),
                   listing(accepted_listing, primary, None, offer, users, accepted, False)]
    projections[-1]['offer_metadata'] = 'no_offer_after_acceptance'
    # Inventory IDs in both native responses must match the accepted DB owners;
    # the pure history validator separately checks the exact physical swap.
    return dict(acceptance_proved=True, acceptance_both_clients_owned_refresh_proved=True,
                acceptance_notifications=notifications, acceptance_listing_classification=projections,
                acceptance_refresh_details_mask='0x78')


def inspect(primary_pcaps, peer_pcaps, parent_path, offer_path, rejected_path,
            accept_offer_path=None, accepted_path=None):
    require(__debug__)
    primary_rows, primary_events, primary_zero, primary_hashes = device_observations(primary_pcaps)
    peer_rows, peer_events, peer_zero, peer_hashes = device_observations(peer_pcaps)
    docs = [strict_json(path.read_text(encoding='utf-8')) for path in (parent_path, offer_path, rejected_path)]
    require((accept_offer_path is None) == (accepted_path is None))
    extra_docs = ([strict_json(path.read_text(encoding='utf-8')) for path in (accept_offer_path, accepted_path)]
                  if accepted_path is not None else [])
    require(all(path.parent.resolve() == parent_path.parent.resolve() for path in (offer_path, rejected_path)))
    baseline_path = parent_path.parent / 'baseline.json'
    baseline = strict_json(baseline_path.read_text(encoding='utf-8'))
    entries = []
    receipts, attempts = set(), set()
    for path in parent_path.parent.glob('observe-*.json'):
        document = strict_json(path.read_text(encoding='utf-8'))
        if path.name.endswith('-attempt.json'):
            require(document == {'action': 'observe', 'private': True})
            attempts.add(path.name.removesuffix('-attempt.json') + '.json')
            continue
        require(path.name == 'observe-' + document['label'] + '.json')
        receipts.add(path.name)
        if document['sequence'] <= (extra_docs[-1] if extra_docs else docs[-1])['sequence']:
            entries.append(dict(document=document, sha256=digest(path)))
    require(receipts == attempts)  # Unresolved attempts halt the append-only chain.
    entries.sort(key=lambda entry: entry['document']['sequence'])
    verify_history(baseline, digest(baseline_path), entries)
    require([doc['stage'] for doc in docs] == ['parent', 'offer', 'rejected'])
    require(all(any(entry['document'] == doc for entry in entries) for doc in docs + extra_docs))
    require(docs[0]['sequence'] < docs[1]['sequence'] < docs[2]['sequence'])
    p_rows, p_events, q_rows, q_events, later = bounded_rejection_prefix(
        primary_rows, primary_events, peer_rows, peer_events)
    result = validate(p_rows, p_events, q_rows, q_events, *docs, primary_zero, peer_zero)
    result['later_native_trade_phase_present'] = later
    result['proof_capture_scope'] = ('Offer/reject prefix bounded by the next primary native offer and next peer offer invalidation, on their separate clocks'
                                     if later else 'Complete supplied captures')
    if extra_docs:
        require(later and [doc['stage'] for doc in extra_docs] == ['offer', 'accepted'])
        require(docs[-1]['sequence'] < extra_docs[0]['sequence'] < extra_docs[1]['sequence'])
        result.update(validate_acceptance(primary_rows, primary_events, peer_rows, peer_events,
                                         docs[-1], *extra_docs))
        result['evidence_kind'] = 'Live replacement-server native Android 2.41.0 offer, rejection and acceptance refreshes'
        result['proof_capture_scope'] = 'Offer, owner rejection, second offer and owner acceptance in complete supplied captures'
    result['input_sha256'] = {key: digest(path) for key, path in [
        ('parent', parent_path),
        ('offered', offer_path), ('rejected', rejected_path)]}
    result['capture_sha256'] = dict(primary=primary_hashes, peer=peer_hashes)
    result['fixture_history_sha256'] = [entry['sha256'] for entry in entries]
    result['baseline_sha256'] = digest(baseline_path)
    result['protected_fixture_history_revalidated'] = True
    if accepted_path is not None:
        result['input_sha256'].update(accept_offer=digest(accept_offer_path), accepted=digest(accepted_path))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for device in ('primary', 'peer'):
        parser.add_argument('--'+device+'-pcap', type=Path)
        for phase in ('startup', 'offer', 'reject'):
            parser.add_argument('--'+device+'-'+phase+'-pcap', action='append', type=Path)
    for key in ('parent', 'offer', 'rejected', 'output'):
        parser.add_argument('--'+key, required=True, type=Path)
    parser.add_argument('--accept-offer', type=Path)
    parser.add_argument('--accepted', type=Path)
    args = parser.parse_args()
    primary = {phase: getattr(args, 'primary_'+phase+'_pcap') for phase in ('startup', 'offer', 'reject')}
    peer = {phase: getattr(args, 'peer_'+phase+'_pcap') for phase in ('startup', 'offer', 'reject')}
    for direct, grouped in ((args.primary_pcap, primary), (args.peer_pcap, peer)):
        require((direct is not None and all(values is None for values in grouped.values()))
                or (direct is None and all(values for values in grouped.values())))
    primary = args.primary_pcap or primary
    peer = args.peer_pcap or peer
    paths = [path for captures in (primary, peer) for path in
             ([captures] if isinstance(captures, Path) else [p for values in captures.values() for p in values])]
    paths += [args.parent, args.offer, args.rejected, args.output]
    paths += [path for path in (args.accept_offer, args.accepted) if path is not None]
    require(all(path.resolve().is_relative_to((ROOT/'.research').resolve()) for path in paths))
    require(not args.output.exists())
    try:
        result = inspect(primary, peer, args.parent, args.offer, args.rejected, args.accept_offer, args.accepted)
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(result, output, indent=2)
            output.write('\n')
    except Exception as error:
        raise SystemExit('Live native trade refresh proof failed: '+type(error).__name__) from None
    print('Sanitized live native trade refresh proof written.')


if __name__ == '__main__':
    main()

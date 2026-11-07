"""Read-only proof of counterpart cancellation refresh across three native captures.

Primary requests, peer offers and withdraws, peer cold logs in, peer offers again,
primary cancels the parent. A cold login is an explicit continuity boundary.
No device, database, server request or synthetic publication is performed here.
"""
import argparse
import copy
import json
from pathlib import Path

from capture_friend_battle_http import ROOT
from sanitize_native_trade_cancellation import digest, require
from sanitize_native_trade_decisions import strict_json, returned_parent
from sanitize_live_trade_refresh import (PATHS, accounts, identity, notification,
    detail, listing, event_refresh, wire_observations)
from sanitize_trade_refresh_smoke import INCLUDE
from cancel_trade_refresh_fixture import ANCHOR, verify_history

ALLOWED_PATHS = PATHS | {'/trading/cancel-trade', '/trading/cancel-trade-offer'}
MUTATIONS = {'/trading/request-morty', '/trading/offer-morty',
             '/trading/offer-response', '/trading/cancel-trade', '/trading/cancel-trade-offer'}


def returned_offer(value, parent, offer, users, snapshot):
    owned = {row['owned_morty_id']: row for row in snapshot['owned_morties']}
    owner = next(user for user in users.values() if user['player_id'] == parent['player_id'])
    expected = {key: offer[key] for key in ('trade_offer_id', 'trade_id', 'player_id', 'morty_offer_id')}
    expected.update(request_user_name=owner['username'],
                    request_morty_id=owned[parent['morty_trade_id']]['morty_id'],
                    offering_morty_id=owned[offer['morty_offer_id']]['morty_id'])
    require(type(value) is dict and set(value) == set(expected) | {'_created'})
    require(all(type(value[key]) is str and value[key] == wanted for key, wanted in expected.items()))
    require(type(value['_created']) is str and bool(value['_created']))


def cancellation_listing(row, user, parent, offer, users, snapshot, present):
    # The existing listing validator has a fixed requester username for the
    # earlier reversed-role experiment. Validate enrichment here, then reuse
    # its completion-alias/ID checks through an isolated normalized copy.
    payload = row['response']
    if present:
        require(type(payload.get('trade_offers')) is list and len(payload['trade_offers']) == 1)
        returned_offer(payload['trade_offers'][0], parent, offer, users, snapshot)
    normalized = copy.deepcopy(row)
    if present:
        normalized['response']['trade_offers'][0]['request_user_name'] = 'PMTrade02'
    result = listing(normalized, user, parent, offer, users, snapshot, present)
    if not present:
        result['offer_metadata'] = 'no_offer_after_cancellation'
    return result


def fixture_states(documents):
    require(len(documents) == 5)
    require([d['stage'] for d in documents] == ['parent', 'offer', 'offer-cancelled', 'offer', 'parent-cancelled'])
    require(all(d.get('private') is True for d in documents))
    users = [accounts(doc) for doc in documents]
    for name in ('PMTrade01', 'PMTrade02'):
        for key in ('secret', 'player_id', 'username'):
            require(len({u[name][key] for u in users}) == 1)
    require(len({u['PMTrade01']['session_id'] for u in users}) == 1)
    require(len({u['PMTrade02']['session_id'] for u in users[:3]}) == 1)
    require(users[3]['PMTrade02']['session_id'] == users[4]['PMTrade02']['session_id'])
    require(users[2]['PMTrade02']['session_id'] != users[3]['PMTrade02']['session_id'])
    snapshots = [d['snapshot'] for d in documents]
    parent = snapshots[0]['trades'][0]
    first, second = snapshots[1]['trade_offers'][0], snapshots[3]['trade_offers'][0]
    require(parent['player_id'] == users[0]['PMTrade01']['player_id'])
    require(all(s['trades'] == [parent] for s in snapshots[:4]))
    require(snapshots[0]['trade_offers'] == snapshots[2]['trade_offers'] == [])
    require(snapshots[1]['trade_offers'] == [first] and snapshots[3]['trade_offers'] == [second])
    require(snapshots[4]['trades'] == snapshots[4]['trade_offers'] == [])
    require(first['trade_offer_id'] != second['trade_offer_id'])
    for offer in (first, second):
        require(offer['player_id'] == users[0]['PMTrade02']['player_id'] and offer['trade_id'] == parent['trade_id'])
    require(first['morty_offer_id'] == second['morty_offer_id'])
    require(all(s['owned_morties'] == snapshots[0]['owned_morties'] for s in snapshots))
    require(len(snapshots[0]['completed_trades']) == 2)
    require(all(s['completed_trades'] == snapshots[0]['completed_trades'] for s in snapshots))
    publications = [notification(snapshots[i-1], snapshots[i],
        users[i]['PMTrade01' if i == 4 else 'PMTrade02'],
        users[i]['PMTrade02' if i == 4 else 'PMTrade01'],
        'trade:offer-rejected' if i == 4 else 'trade:offer-submit') for i in range(1, 5)]
    return users, snapshots, parent, first, second, publications


def capture_identity(rows, events, user):
    identity(rows, events, user)
    require(len([r for r in rows if r['path'] == '/user/login']) == 1)
    require(len([e for e in events if e['event'] == 'session:start']) == 1)
    require(len({e['request_time'] for e in events}) == 1)
    require(bool([r for r in rows if r['path'] == '/session/join-room']))


def one_mutation(rows, path):
    found = [row for row in rows if row['path'] == path]
    require(len(found) == 1)
    return found[0]


def own_details(rows, after, before, user, snapshot, locked):
    found = [r for r in rows if r['path'] == '/session/player-details'
             and after < r['request_time'] and r['response_time'] < before]
    require(bool(found))
    detail(found[0], user, snapshot, locked)
    return found[0]


def ready_before(rows, time):
    require(any(row['path'] == '/session/join-room' and row['response_time'] < time for row in rows))


def phase_refresh(rows, events, selected, upper):
    # Keep the following event as the native response boundary. Reusing an
    # earlier retained startup invalidation cannot certify a mutation phase.
    selected_events = [e for e in events if selected['time'] <= e['time'] < upper]
    event, trades, details = event_refresh(rows, selected_events, selected['event'], 'cancellation')
    require(event is selected and max(trades['response_time'], details['response_time']) < upper)
    ready_before(rows, event['time'])
    return trades, details


def validate(primary_rows, primary_events, first_rows, first_events, second_rows, second_events,
             documents, zeros=(0, 0, 0)):
    users, snapshots, parent, first, second, publications = fixture_states(documents)
    owner, peer_before, peer_after = users[0]['PMTrade01'], users[1]['PMTrade02'], users[3]['PMTrade02']
    for rows, events, user in ((primary_rows, primary_events, owner),
                               (first_rows, first_events, peer_before), (second_rows, second_events, peer_after)):
        capture_identity(rows, events, user)
    require([r['path'] for r in primary_rows if r['path'] in MUTATIONS] ==
            ['/trading/request-morty', '/trading/cancel-trade'])
    require([r['path'] for r in first_rows if r['path'] in MUTATIONS] ==
            ['/trading/offer-morty', '/trading/cancel-trade-offer'])
    require([r['path'] for r in second_rows if r['path'] in MUTATIONS] == ['/trading/offer-morty'])
    create = one_mutation(primary_rows, '/trading/request-morty')
    cancel_parent = one_mutation(primary_rows, '/trading/cancel-trade')
    offer_first = one_mutation(first_rows, '/trading/offer-morty')
    cancel_offer = one_mutation(first_rows, '/trading/cancel-trade-offer')
    offer_second = one_mutation(second_rows, '/trading/offer-morty')
    for rows, mutation in ((primary_rows, create), (first_rows, offer_first), (second_rows, offer_second)):
        ready_before(rows, mutation['request_time'])
    require(create['request'] == dict(session_id=owner['session_id'], player_id=owner['player_id'],
        owned_morty_id=parent['morty_trade_id'], requested_morty_id='any', request_variant='Normal', is_free_trade=True))
    require(create['request']['is_free_trade'] is True)
    require(create['response']['error'] == 'None')
    returned_parent(create['response']['trade'], {'parent': parent})
    for row, user, offer, snapshot in ((offer_first, peer_before, first, snapshots[1]),
                                       (offer_second, peer_after, second, snapshots[3])):
        require(row['request'] == dict(session_id=user['session_id'], player_id=user['player_id'],
            offered_morty_id=offer['morty_offer_id'], trade_request_id=parent['trade_id']))
        require(set(row['response']) == {'error', 'offer'} and row['response']['error'] == 'None')
        returned_offer(row['response']['offer'], parent, offer, users[0], snapshot)
    require(cancel_offer['request'] == {'trade_offer_id': first['trade_offer_id']})
    require(cancel_parent['request'] == {'trade_id': parent['trade_id']})
    require(cancel_offer['response'] == cancel_parent['response'] == {'error': 'None'})
    require(offer_first['response_time'] < cancel_offer['request_time'])

    actual_primary = [e for e in primary_events if e['time'] > create['request_time']]
    require([e['event'] for e in actual_primary] == ['trade:offer-submit'] * 3)
    require(create['response_time'] < actual_primary[0]['time'])
    actual_second = [e for e in second_events if e['time'] > offer_second['request_time']]
    require([e['event'] for e in actual_second] == ['trade:offer-rejected'])
    require(offer_second['response_time'] < actual_second[0]['time'])
    require(not [e for e in first_events if e['time'] > offer_first['request_time']])
    # Only retained baseline notifications may precede each phase's mutation.
    for events, before, allowed in ((primary_events, create['request_time'], {'trade:offer-accepted'}),
                                   (first_events, offer_first['request_time'], {'trade:offer-submit'}),
                                   (second_events, offer_second['request_time'], {'trade:offer-submit'})):
        require(all(e['event'] in allowed | {'session:start'} for e in events if e['time'] < before))
        require(len([e for e in events if e['time'] < before and e['event'] != 'session:start']) <= 1)

    projections, timeline = [], []
    for i, (event, offer, snapshot, present) in enumerate(zip(actual_primary,
            (first, first, second), snapshots[1:4], (True, False, True))):
        bound = actual_primary[i+1]['time'] if i < 2 else cancel_parent['request_time']
        trades, details = phase_refresh(primary_rows, primary_events, event, bound)
        projections.append(cancellation_listing(trades, owner, parent, offer, users[0], snapshot, present))
        detail(details, owner, snapshot, {parent['morty_trade_id']})
        timeline.append(('primary', f'counterpart_refresh_{i+1}', event['time'],
                         trades['request_time'], details['request_time']))
    require(actual_primary[-1]['time'] < cancel_parent['request_time'])
    rejection = actual_second[0]
    trades, details = phase_refresh(second_rows, second_events, rejection, float('inf'))
    projections.append(cancellation_listing(trades, peer_after, None, second, users[3], snapshots[4], False))
    detail(details, peer_after, snapshots[4], set())
    timeline.append(('peer_second', 'parent_cancel_refresh', rejection['time'],
                     trades['request_time'], details['request_time']))
    own_details(primary_rows, create['response_time'], actual_primary[0]['time'], owner,
                snapshots[0], {parent['morty_trade_id']})
    own_details(first_rows, offer_first['response_time'], cancel_offer['request_time'], peer_before,
                snapshots[1], {first['morty_offer_id']})
    own_details(second_rows, offer_second['response_time'], rejection['time'], peer_after,
                snapshots[3], {second['morty_offer_id']})
    own_details(primary_rows, cancel_parent['response_time'], float('inf'), owner, snapshots[4], set())
    require(not [r for r in first_rows if r['path'] == '/session/player-details'
                 and r['request_time'] > cancel_offer['response_time']])
    startup = [r for r in second_rows if r['path'] == '/session/player-details'
               and r['response_time'] < offer_second['request_time']]
    require(bool(startup))
    cold = startup[0]
    require(cold['request']['session_id'] == peer_after['session_id'])
    include = cold['request']['include']
    require(type(include) is list and len(include) == len(set(include)) == 11 and set(INCLUDE) <= set(include))
    normalized = copy.deepcopy(cold)
    normalized['request']['include'] = INCLUDE
    detail(normalized, peer_after, snapshots[2], set())
    return dict(schema_version=1,
        evidence_kind='Live replacement-server Android 2.41.0 own-offer and parent cancellation counterparts',
        actual_native_own_offer_cancellation_proved=True, actual_native_parent_cancellation_proved=True,
        counterpart_native_trade_and_details_refresh_proved=True,
        parent_cancel_offerer_details_unlocked=True, request_owner_details_stayed_reserved_after_offer_withdrawal=True,
        actor_trade_event_absent_in_supplied_phase=True, self_cancel_immediate_owned_refresh_observed=False,
        peer_cold_login_boundary_proved=True, uninterrupted_peer_session_proved=False,
        self_cancel_cached_memory_unlock_proved=False, selector_eligibility_proved=False,
        parent_cancel_incoming_ui_button_proved=False, original_service_behavior_proved=False,
        cross_capture_clock_order_proved=False, mutation_to_sse_latency_proved=False,
        exact_sse_frame_trade_id_binding_proved=False,
        sse_correlation_scope='Phase correlation using native HTTP IDs and exact recipient revision changes; SSE payloads are empty objects',
        timing_scope='Only each capture clock is used; peer cold login is a separate capture and session',
        details_include=INCLUDE, details_mask='0x78', notifications=publications,
        both_existing_completions_preserved=True, listing_classification=projections,
        capture_timelines=[dict(capture=name, phase=phase, frame_seconds=round(stamp-zeros[0 if name == 'primary' else 2], 6),
            trades_request_seconds=round(trades_stamp-zeros[0 if name == 'primary' else 2], 6),
            details_request_seconds=round(details_stamp-zeros[0 if name == 'primary' else 2], 6))
            for name, phase, stamp, trades_stamp, details_stamp in timeline])


def inspect(primary_pcap, peer_first_pcap, peer_second_pcap, document_paths):
    require(__debug__ and len(document_paths) == 5)
    require(len({p.resolve() for p in (primary_pcap, peer_first_pcap, peer_second_pcap)}) == 3)
    captures = [wire_observations(path, allowed_paths=ALLOWED_PATHS)
                for path in (primary_pcap, peer_first_pcap, peer_second_pcap)]
    require(len({p.parent.resolve() for p in document_paths}) == 1)
    directory = document_paths[0].parent
    baseline_path = directory / 'baseline.json'
    baseline = strict_json(baseline_path.read_text(encoding='utf-8'))
    require(baseline['accepted_anchor']['sha256'] == digest(ANCHOR))
    require(baseline['accepted_anchor']['document'] == strict_json(ANCHOR.read_text(encoding='utf-8')))
    entries, attempts, receipts = [], set(), set()
    for path in directory.glob('observe-*.json'):
        doc = strict_json(path.read_text(encoding='utf-8'))
        if path.name.endswith('-attempt.json'):
            require(doc == {'action': 'observe', 'private': True})
            attempts.add(path.name.removesuffix('-attempt.json') + '.json')
        else:
            require(path.name == 'observe-' + doc['label'] + '.json')
            receipts.add(path.name)
            entries.append(dict(document=doc, sha256=digest(path)))
    require(receipts == attempts)
    entries.sort(key=lambda entry: entry['document']['sequence'])
    final, _ = verify_history(baseline, digest(baseline_path), entries)
    require(final['stage'] == 'parent-cancelled')
    docs = [strict_json(path.read_text(encoding='utf-8')) for path in document_paths]
    require(all(any(entry['document'] == doc for entry in entries) for doc in docs))
    require(all(a['sequence'] < b['sequence'] for a, b in zip(docs, docs[1:])))
    result = validate(captures[0][0], captures[0][1], captures[1][0], captures[1][1],
                      captures[2][0], captures[2][1], docs, tuple(c[2] for c in captures))
    result.update(protected_fixture_history_revalidated=True, baseline_sha256=digest(baseline_path),
        accepted_anchor_sha256=digest(ANCHOR), fixture_history_sha256=[e['sha256'] for e in entries],
        input_sha256={name: digest(path) for name, path in zip(
            ('parent', 'first_offer', 'offer_cancelled', 'second_offer', 'parent_cancelled'), document_paths)},
        capture_sha256={name: digest(path) for name, path in zip(('primary', 'peer_first', 'peer_second'),
            (primary_pcap, peer_first_pcap, peer_second_pcap))})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    names = ('primary-pcap', 'peer-first-pcap', 'peer-second-pcap', 'parent', 'offer',
             'offer-cancelled', 'second-offer', 'parent-cancelled', 'output')
    for name in names:
        parser.add_argument('--' + name, required=True, type=Path)
    args = parser.parse_args()
    require(all(getattr(args, n.replace('-', '_')).resolve().is_relative_to((ROOT / '.research').resolve()) for n in names))
    require(not args.output.exists())
    try:
        result = inspect(args.primary_pcap, args.peer_first_pcap, args.peer_second_pcap,
            [args.parent, args.offer, args.offer_cancelled, args.second_offer, args.parent_cancelled])
        with args.output.open('x', encoding='utf-8') as output:
            json.dump(result, output, indent=2)
            output.write('\n')
    except Exception as error:
        raise SystemExit('Native cancellation refresh proof failed: ' + type(error).__name__) from None
    print('Sanitized native cancellation refresh proof written.')


if __name__ == '__main__':
    main()

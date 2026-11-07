"""Read-only, fail-closed native offer-cycle proof; emits no private payload values.

Inputs and fresh output belong under ignored .research. Exact TCP ACK pairing
and packet order reuse the classic-PCAP parser. No database/device/network use.
"""
import argparse
from http.cookies import SimpleCookie
import json
from pathlib import Path
import re

from capture_friend_battle_http import ROOT, message, packets, runs
from sanitize_native_trade_cancellation import require, digest
from native_trade_offer_fixture import baseline_identity, identity


def exchanges(pcap):
    flows, positions = {}, {}
    for ordinal, (key, seq, ack, payload) in enumerate(packets(pcap)):
        flows.setdefault(key, []).append((seq, ack, payload))
        positions.setdefault((key, seq), ordinal)

    def packet_index(key, absolute):
        found = [positions[(key, seq)] for seq, _, body in flows[key]
                 if seq <= absolute < seq + len(body)]
        require(bool(found))
        return min(found)

    selected = {'/trading/offer-morty', '/trading/cancel-trade-offer',
                '/trading/get-trades', '/session/player-details'}
    result = []
    other_trading = 0
    for key, segments in flows.items():
        if key[3] != 8087:
            continue
        for start, stream, _ in runs(segments):
            for match in re.finditer(rb'POST /[^ ?\r\n]+ HTTP/1\.1\r\n', stream):
                line, headers, body, finish = message(stream, match.start())
                path = line.split()[1]
                if path.startswith('/trading/') and path not in selected:
                    other_trading += 1
                if path not in selected:
                    continue
                require(headers.get('user-agent') == 'UnityApp/2.41.0 (Android)')
                require(isinstance(headers.get('x-pmclient'), str) and bool(headers['x-pmclient']))
                reverse = (key[2], key[3], key[0], key[1])
                replies = []
                for rstart, response_stream, spans in runs(flows.get(reverse, [])):
                    for hit in re.finditer(rb'HTTP/1\.[01] [0-9]{3} [^\r\n]*\r\n', response_stream):
                        absolute = rstart + hit.start()
                        acks = {ack for lo, hi, ack in spans if lo <= absolute < hi}
                        if start + finish not in acks:
                            continue
                        require(acks == {start + finish})
                        status, _, reply, _ = message(response_stream, hit.start())
                        require(status.split()[1] == '200')
                        replies.append((json.loads(reply), packet_index(reverse, absolute)))
                require(len(replies) == 1)
                response, response_index = replies[0]
                request_index = packet_index(key, start + match.start())
                require(response_index > request_index)
                result.append(dict(path=path, headers=headers, request=json.loads(body),
                                   response=response, request_packet_index=request_index,
                                   response_packet_index=response_index))
    require(other_trading == 0)
    return sorted(result, key=lambda row: row['request_packet_index'])



def read_fixture(directory, prefix=''):
    names = ['before-offer-create', 'offer-created', 'before-offer-cancel', 'offer-cancelled']
    documents, hashes = {}, {}
    for label in ['baseline'] + ['observe-' + prefix + n for n in names]:
        path = directory / (label + '.json')
        document = json.loads(path.read_text(encoding='utf-8'))
        require(document['private'] is True)
        documents[label] = document
        hashes[label] = digest(path)
    baseline = documents['baseline']
    anchor = baseline_identity(baseline)
    snapshots = [documents['observe-' + prefix + n]['snapshot'] for n in names]
    before, created, pre_cancel, cancelled = snapshots
    for snapshot in snapshots:
        require(identity(snapshot) == anchor)
        require(len(snapshot['users']) == 2 and len(snapshot['owned_morties']) == 4)
    primary = next(u for u in before['users'] if u['username'] == 'PMTrade01')
    peer = next(u for u in before['users'] if u['username'] == 'PMTrade02')
    require(primary['session_id'] and primary['session_id'] != peer['session_id'])
    require(len(before['trades']) == 1 and not before['trade_offers'])
    parent = before['trades'][0]
    require(parent['player_id'] == peer['player_id'])
    require(parent['requested_morty_id'] == 'any' and parent['request_variant'] == 'Normal')
    require(type(parent['is_free_trade']) is int and parent['is_free_trade'] == 1)
    require(len(created['trade_offers']) == 1)
    offer = created['trade_offers'][0]
    require(offer['player_id'] == primary['player_id'] and offer['trade_id'] == parent['trade_id'])
    require(isinstance(offer['trade_offer_id'], str) and bool(offer['trade_offer_id']))
    spare = next(m for m in before['owned_morties'] if m['owned_morty_id'] == offer['morty_offer_id'])
    requested = next(m for m in before['owned_morties'] if m['owned_morty_id'] == parent['morty_trade_id'])
    require(spare['player_id'] == primary['player_id'] and requested['player_id'] == peer['player_id'])
    require(spare['is_locked'] == 'false' and spare['is_trading_locked'] == 'false')
    active = [d for d in before['decks'] if d['player_id'] == primary['player_id']
              and d['deck_id'] == primary['active_deck_id']]
    require(len(active) == 1)
    party = json.loads(active[0]['owned_morty_ids'])
    require(isinstance(party, list) and bool(party) and spare['owned_morty_id'] not in party)
    require(pre_cancel['trade_offers'] == created['trade_offers'] and not cancelled['trade_offers'])
    # Ignore only the ordinary heartbeat timestamp; all other user columns,
    # including both expiries, currencies and current sessions, remain exact.
    stable_users = lambda s: [{k: v for k, v in u.items() if k != 'last_seen'} for u in s['users']]
    for snapshot in snapshots:
        require(stable_users(snapshot) == stable_users(before))
        require(snapshot['trades'] == before['trades'])
        require(not snapshot['completed_trades'] and not snapshot['friend_battle_memberships'])
        for table in ('owned_morties', 'owned_attacks', 'owned_items', 'decks', 'friend_list', 'event_queue'):
            require(snapshot[table] == before[table])
    for table in ('owned_morties', 'owned_attacks', 'owned_items', 'decks'):
        require(before[table] == baseline['snapshot'][table])
    require(isinstance(peer['expiry_trade'], str) and bool(peer['expiry_trade']))
    return dict(primary=primary, peer=peer, spare=spare, requested=requested,
                parent=parent, offer=offer, before=before, hashes=hashes)


def authenticate(row, primary):
    cookie = SimpleCookie()
    raw = row['headers'].get('cookie', '')
    # SimpleCookie accepts duplicate names; reject them before parsing.
    require(len(re.findall(r'(?:^|;)\s*session_id\s*=', raw)) == 1)
    cookie.load(raw)
    require('session_id' in cookie and cookie['session_id'].value == primary['session_id'])


def check_offer(returned, fixture, fixed):
    primary, peer = fixture['primary'], fixture['peer']
    offer, parent = fixture['offer'], fixture['parent']
    core = {'trade_offer_id': offer['trade_offer_id'], 'player_id': primary['player_id'],
            'morty_offer_id': fixture['spare']['owned_morty_id'], 'trade_id': parent['trade_id']}
    require(all(returned.get(k) == v for k, v in core.items()))
    metadata = dict(request_user_name=peer['username'],
                    offering_morty_id=fixture['spare']['morty_id'],
                    request_morty_id=fixture['requested']['morty_id'])
    if not fixed:
        metadata.update(request_user_name=peer['player_id'], request_morty_id=parent['morty_trade_id'])
    require(all(returned.get(k) == v for k, v in metadata.items()))
    require(set(returned) == set(core) | set(metadata) | {'_created'})
    require(isinstance(returned['_created'], str) and bool(returned['_created']))


def inspect(pcap, fixture_dir, fixed=False, prefix=''):
    require(__debug__)
    fixture = read_fixture(fixture_dir, prefix)
    primary, spare = fixture['primary'], fixture['spare']
    observed = exchanges(pcap)
    def one(path):
        rows = [r for r in observed if r['path'] == path]
        require(len(rows) == 1)
        return rows[0]
    create = one('/trading/offer-morty')
    cancel = one('/trading/cancel-trade-offer')
    require(create['request'] == dict(session_id=primary['session_id'], player_id=primary['player_id'],
        offered_morty_id=spare['owned_morty_id'], trade_request_id=fixture['parent']['trade_id']))
    require(set(create['response']) == {'error', 'offer'} and create['response']['error'] == 'None')
    check_offer(create['response']['offer'], fixture, fixed)
    require(cancel['request'] == {'trade_offer_id': fixture['offer']['trade_offer_id']})
    require(cancel['response'] == {'error': 'None'})
    require(create['response_packet_index'] < cancel['request_packet_index'])
    authenticate(cancel, primary)
    for row in observed:
        if 'cookie' in row['headers']:
            authenticate(row, primary)
    details = [r for r in observed if r['path'] == '/session/player-details']
    between = [r for r in details if create['response_packet_index'] < r['request_packet_index']
               and r['response_packet_index'] < cancel['request_packet_index']]
    require(len(between) >= 1)
    owned = [m for m in fixture['before']['owned_morties'] if m['player_id'] == primary['player_id']]
    ids = {m['owned_morty_id'] for m in owned}
    for row in details:
        require(set(row['request']) == {'include', 'session_id'})
        require(row['request']['session_id'] == primary['session_id'])
        require(isinstance(row['request']['include'], list) and bool(row['request']['include']))
        payload = row['response']
        require(payload['player_id'] == primary['player_id'])
        for resource in ('coins', 'coupons', 'permits'):
            require(payload[resource] == primary[resource])
        inventory = payload['owned_morties']
        require(len(inventory) == len(ids) and {m['owned_morty_id'] for m in inventory} == ids)
        require(all(type(m['is_locked']) is bool and type(m['is_trading_locked']) is bool for m in inventory))
        selected = next(m for m in inventory if m['owned_morty_id'] == spare['owned_morty_id'])
        require(selected['is_locked'] is False)
        if row in between:
            require(selected['is_trading_locked'] is True)
    listings = [r for r in observed if r['path'] == '/trading/get-trades']
    persisted = 0
    for row in listings:
        require(row['request'] == dict(session_id=primary['session_id'], player_id=primary['player_id']))
        payload = row['response']
        require(not payload['completed_trades'])
        require(len(payload['trade_requests']) == 1)
        require(payload['trade_requests'][0]['trade_id'] == fixture['parent']['trade_id'])
        if create['response_packet_index'] < row['request_packet_index'] and row['response_packet_index'] < cancel['request_packet_index']:
            require(len(payload['trade_offers']) == 1)
            check_offer(payload['trade_offers'][0], fixture, fixed)
            persisted += 1
        elif (cancel['response_packet_index'] < row['request_packet_index']
              or row['response_packet_index'] < create['request_packet_index']):
            require(payload['trade_offers'] == [])
        else:
            require(False)
    if fixed:
        require(persisted >= 1)
    safe = [dict(path=r['path'], request_body_keys=sorted(r['request']), status=200,
                 request_packet_index=r['request_packet_index'], response_packet_index=r['response_packet_index'],
                 native_headers_present=True, exact_tcp_ack_pair=True) for r in observed]
    return dict(pcap_sha256=digest(pcap), fixture_sha256=fixture['hashes'], exchanges=safe,
        proof=dict(authenticated_four_field_creation_and_id_only_cookie_cancel=True,
            returned_core_ids_match_database=True, primary_spare_outside_party=True,
            database_offer_counts=[0, 1, 1, 0], database_parent_counts=[1, 1, 1, 1],
            both_expiries_resources_owned_raw_flags_decks_attacks_items_preserved=True,
            parent_and_friendship_preserved=True, no_completed_transfer=True,
            owned_details_after_create_boolean_lock_true=True,
            owned_details_after_cancel_count=sum(cancel['response_packet_index'] < r['request_packet_index'] for r in details),
            immediate_native_unlock_proved=False, metadata_display_semantics_correct=fixed,
            metadata_retaining_get_trades_count=persisted),
        gaps=dict(baseline_username_is_peer_player_id=not fixed,
                  baseline_requested_species_is_owned_instance_id=not fixed,
                  baseline_get_trades_metadata_unobserved=not fixed and persisted == 0,
                  cancellation_alone_proves_inventory_refresh=False))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline-pcap', type=Path, required=True)
    parser.add_argument('--fixed-pcap', type=Path)
    parser.add_argument('--fixture-dir', type=Path, required=True)
    parser.add_argument('--fixed-label-prefix', default='fixed-')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        private = (ROOT / '.research').resolve()
        paths = [args.baseline_pcap, args.fixture_dir, args.output]
        if args.fixed_pcap is not None:
            paths.append(args.fixed_pcap)
        require(all(p.resolve().is_relative_to(private) for p in paths))
        require(re.fullmatch(r'[a-zA-Z0-9_-]*', args.fixed_label_prefix) is not None)
        require(not args.output.exists())
        baseline_fixture = read_fixture(args.fixture_dir)
        result = dict(schema_version=1, native_replacement_server_only=True,
                      baseline=inspect(args.baseline_pcap, args.fixture_dir),
                      two_cycles_same_peer_parent_proved=False,
                      gui_selector_availability_proved=False)
        if args.fixed_pcap is not None:
            fixed_fixture = read_fixture(args.fixture_dir, args.fixed_label_prefix)
            require(fixed_fixture['parent'] == baseline_fixture['parent'])
            require(fixed_fixture['spare'] == baseline_fixture['spare'])
            require(fixed_fixture['peer']['player_id'] == baseline_fixture['peer']['player_id'])
            result['fixed'] = inspect(args.fixed_pcap, args.fixture_dir, True, args.fixed_label_prefix)
            result['two_cycles_same_peer_parent_proved'] = True
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2)
            handle.write('\n')
    except Exception as error:
        raise SystemExit('Native offer proof failed: ' + type(error).__name__) from None
    print('Sanitized native offer proof written; cycles: ' + str(1 + int(args.fixed_pcap is not None)))


if __name__ == '__main__':
    main()

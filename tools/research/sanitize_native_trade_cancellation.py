"""Read-only, fail-closed proof of one native replacement-server create/cancel.

Private inputs and fresh output must remain under ignored .research. Reuses the
classic-PCAP contiguous-TCP/Content-Length parser and exact response ACK pairing.
Never contacts a database/device/server or emits reconstructed payload values.
"""
import argparse
import hashlib
from http.cookies import SimpleCookie
import json
from pathlib import Path
import re

from capture_friend_battle_http import ROOT, message, packets, runs


def require(condition):
    if not condition:
        raise ValueError()


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_fixture(directory):
    names = ['prepared', 'observe-before-create', 'observe-request-created',
             'observe-before-cancel', 'observe-request-cancelled', 'verified-cancelled']
    documents = {}
    hashes = {}
    for name in names:
        path = directory / (name + '.json')
        documents[name] = json.loads(path.read_text(encoding='utf-8'))
        require(documents[name]['private'] is True)
        hashes[name] = digest(path)
    prepared = documents['prepared']
    spare = prepared['synthetic_uuid']
    require(isinstance(spare, str) and bool(spare))
    snapshots = [documents[name]['snapshot'] for name in names[1:]]
    before, created, pre_cancel, cancelled, verified = snapshots
    require(len(before['users']) == 1)
    user = before['users'][0]
    require(all(isinstance(user[k], str) and user[k] for k in ('player_id', 'session_id')))
    require(len([m for m in before['owned_morties'] if m['owned_morty_id'] == spare]) == 1)
    spare_row = next(m for m in before['owned_morties'] if m['owned_morty_id'] == spare)
    require(spare_row['player_id'] == user['player_id'])
    require(spare_row['is_locked'] == 'false' and spare_row['is_trading_locked'] == 'false')
    active = [d for d in before['decks'] if d['deck_id'] == user['active_deck_id']]
    require(len(active) == 1 and active[0]['player_id'] == user['player_id'])
    party = json.loads(active[0]['owned_morty_ids'])
    require(isinstance(party, list) and len(party) > 0 and spare not in party)
    require(not before['trades'] and not cancelled['trades'] and not verified['trades'])
    require(len(created['trades']) == 1 and pre_cancel['trades'] == created['trades'])
    trade = created['trades'][0]
    require(trade['player_id'] == user['player_id'] and trade['morty_trade_id'] == spare)
    require(trade['requested_morty_id'] == 'any' and trade['request_variant'] == 'Normal')
    require(type(trade['is_free_trade']) is int and trade['is_free_trade'] == 1)
    require(isinstance(trade['trade_id'], str) and bool(trade['trade_id']))
    resources = ('id', 'player_id', 'session_id', 'secret', 'level', 'xp', 'xp_lower',
                 'xp_upper', 'coins', 'coupons', 'permits', 'wins', 'losses', 'streak',
                 'active_deck_id', 'decks_owned')
    expiry = created['users'][0]['expiry_trade']
    require(before['users'][0]['expiry_trade'] is None)
    require(isinstance(expiry, str) and bool(expiry))
    for snapshot in snapshots:
        require(len(snapshot['users']) == 1)
        require(all(snapshot['users'][0][k] == user[k] for k in resources))
        for table in ('decks', 'owned_morties', 'owned_attacks', 'owned_items'):
            require(snapshot[table] == before[table])
        require(not snapshot['trade_offers'] and not snapshot['completed_trades'])
        require(all(m['player_id'] == user['player_id'] for m in snapshot['owned_morties']))
    require(all(s['users'][0]['expiry_trade'] == expiry for s in snapshots[1:]))
    require(prepared['snapshot']['owned_morties'] == before['owned_morties'])
    require(prepared['snapshot']['owned_attacks'] == before['owned_attacks'])
    require(prepared['snapshot']['decks'] == before['decks'])
    return user, spare, trade, before, hashes


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

    selected = {'/trading/request-morty', '/trading/cancel-trade',
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


def inspect(pcap, fixture_dir):
    # The shared strict parser uses assertions; disallow optimized Python.
    require(__debug__)
    user, spare, trade, before, hashes = read_fixture(fixture_dir)
    observed = exchanges(pcap)

    def one(path):
        matches = [row for row in observed if row['path'] == path]
        require(len(matches) == 1)
        return matches[0]

    create = one('/trading/request-morty')
    cancel = one('/trading/cancel-trade')
    listing = one('/trading/get-trades')
    expected = dict(session_id=user['session_id'], player_id=user['player_id'],
                    owned_morty_id=spare, requested_morty_id='any',
                    request_variant='Normal', is_free_trade=True)
    require(create['request'] == expected and type(create['request']['is_free_trade']) is bool)
    response = create['response']
    require(set(response) == {'error', 'trade', 'coupons'} and response['error'] == 'None')
    require(response['coupons'] == user['coupons'])
    returned = response['trade']
    require(set(returned) == {'trade_id', 'player_id', 'morty_trade_id', 'morty_request',
                              '_created', 'is_free_trade', 'request_variant'})
    require(returned['trade_id'] == trade['trade_id'] and returned['player_id'] == user['player_id'])
    require(returned['morty_trade_id'] == spare and returned['morty_request'] == 'any')
    require(returned['request_variant'] == 'Normal' and returned['is_free_trade'] is True)
    require(cancel['request'] == {'trade_id': trade['trade_id']})
    require(cancel['response'] == {'error': 'None'})
    require(create['response_packet_index'] < cancel['request_packet_index'])
    for row in (create, cancel, listing):
        cookie = SimpleCookie()
        cookie.load(row['headers'].get('cookie', ''))
        require('session_id' in cookie and cookie['session_id'].value == user['session_id'])
    require(listing['request'] == {'session_id': user['session_id'], 'player_id': user['player_id']})
    require(cancel['response_packet_index'] < listing['request_packet_index'])
    listed = listing['response']
    require(set(listed) == {'completed_trades', 'player_cooldown_data', 'trade_attacks',
                           'trade_mortys', 'trade_offers', 'trade_requests'})
    for key in ('completed_trades', 'trade_attacks', 'trade_mortys', 'trade_offers', 'trade_requests'):
        require(listed[key] == [])
    # Preserve the observed pre-fix defect explicitly; do not certify this as correct cooldown behavior.
    require(listed['player_cooldown_data'] == {'expiry': None, 'trades': 0})
    details = [row for row in observed if row['path'] == '/session/player-details']
    require(len(details) == 2)
    details.sort(key=lambda row: row['response_packet_index'])
    inventory_ids = {m['owned_morty_id'] for m in before['owned_morties']}
    require(len(inventory_ids) == len(before['owned_morties']))
    for row, lock in zip(details, (True, False)):
        require(set(row['request']) == {'include', 'session_id'})
        require(row['request']['session_id'] == user['session_id'])
        require(isinstance(row['request']['include'], list) and bool(row['request']['include']))
        payload = row['response']
        require(payload['player_id'] == user['player_id'])
        require(payload['coupons'] == user['coupons'])
        morties = payload['owned_morties']
        require(isinstance(morties, list) and len(morties) == len(inventory_ids))
        require({m['owned_morty_id'] for m in morties} == inventory_ids)
        selected = [m for m in morties if m['owned_morty_id'] == spare]
        require(len(selected) == 1)
        require(selected[0]['is_locked'] is False and selected[0]['is_trading_locked'] is lock)
        require(all(type(m['is_locked']) is bool and type(m['is_trading_locked']) is bool for m in morties))
    require(create['response_packet_index'] < details[0]['request_packet_index'])
    require(details[0]['response_packet_index'] < cancel['request_packet_index'])
    require(cancel['response_packet_index'] < details[1]['response_packet_index'])
    safe_exchanges = [dict(path=row['path'], status=200,
        request_packet_index=row['request_packet_index'], response_packet_index=row['response_packet_index'],
        native_headers_present=True, exact_tcp_ack_pair=True,
        request_body_keys=sorted(row['request'])) for row in observed]
    return dict(schema_version=1,
        evidence_kind='Observed native Android create/cancel on isolated replacement server; not original-service evidence',
        pcap_sha256=digest(pcap), fixture_sha256=hashes, exchanges=safe_exchanges,
        proof=dict(authenticated_creation_matches_fixture=True, creation_return_matches_db=True,
            id_only_cancel_matches_created_trade=True, cancellation_cookie_matches_creation_session=True,
            spare_outside_active_deck=True, trading_lock_details_response_sequence=[True, False],
            known_spare_details_occurrences=len(details), inventory_count=len(inventory_ids),
            decks_resources_coupons_ownership_attacks_raw_flags_unchanged=True,
            no_offers_or_completed_transfer=True, db_trade_counts=[0, 1, 1, 0, 0],
            db_expiry_created_nonempty_and_retained_on_cancel=True),
        confirmed_pre_fix_gap=dict(native_get_trades_expiry_is_null=True,
            native_get_trades_cooldown_count_is_zero=True, db_expiry_retained=True,
            captured_response_proves_fixed_query=False),
        redaction='Only allowlisted shapes, booleans, counts, packet indices and whole-input hashes; no IDs, credentials, header values or nested payloads')


def inspect_cooldown(pcap, fixture_dir):
    """Prove only the post-fix native wire projection, not GUI behavior."""
    require(__debug__)
    user, _, _, _, hashes = read_fixture(fixture_dir)
    created = json.loads((fixture_dir / 'observe-request-created.json').read_text(encoding='utf-8'))
    expiry = created['snapshot']['users'][0]['expiry_trade']
    require(isinstance(expiry, str) and bool(expiry))
    observed = exchanges(pcap)
    require(len(observed) == 1 and observed[0]['path'] == '/trading/get-trades')
    row = observed[0]
    require(row['request'] == {'session_id': user['session_id'], 'player_id': user['player_id']})
    cookie = SimpleCookie()
    cookie.load(row['headers'].get('cookie', ''))
    require('session_id' in cookie and cookie['session_id'].value == user['session_id'])
    payload = row['response']
    require(set(payload) == {'completed_trades', 'player_cooldown_data', 'trade_attacks',
                            'trade_mortys', 'trade_offers', 'trade_requests'})
    for key in ('completed_trades', 'trade_attacks', 'trade_mortys', 'trade_offers', 'trade_requests'):
        require(payload[key] == [])
    cooldown = payload['player_cooldown_data']
    require(set(cooldown) == {'expiry', 'trades'})
    require(cooldown['expiry'] == expiry)
    require(type(cooldown['trades']) is int and cooldown['trades'] == 1)
    return dict(pcap_sha256=digest(pcap), fixture_sha256=hashes,
                native_get_trades_count=1, status=200,
                request_packet_index=row['request_packet_index'],
                response_packet_index=row['response_packet_index'],
                native_headers_present=True, exact_tcp_ack_pair=True,
                authenticated_body_and_cookie_match_before_create=True,
                lists_remain_empty=True, cooldown_expiry_equals_retained_db_expiry=True,
                cooldown_count_is_integer_one=True, gui_behavior_proved=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pcap', type=Path, required=True)
    parser.add_argument('--fixture-dir', type=Path, required=True)
    parser.add_argument('--cooldown-pcap', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        private = (ROOT / '.research').resolve()
        require(all(path.resolve().is_relative_to(private) for path in
                    (args.pcap, args.fixture_dir, args.output)))
        if args.cooldown_pcap is not None:
            require(args.cooldown_pcap.resolve().is_relative_to(private))
        require(not args.output.exists())
        result = inspect(args.pcap.resolve(), args.fixture_dir.resolve())
        if args.cooldown_pcap is not None:
            result['post_fix_read'] = inspect_cooldown(args.cooldown_pcap.resolve(), args.fixture_dir.resolve())
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2)
            handle.write('\n')
    except Exception as error:
        # Even parser exception messages can contain credentials or raw JSON.
        raise SystemExit('Native trade proof failed: ' + type(error).__name__) from None
    print('Sanitized native create/cancel proof written; exchanges: ' + str(len(result['exchanges'])))


if __name__ == '__main__':
    main()

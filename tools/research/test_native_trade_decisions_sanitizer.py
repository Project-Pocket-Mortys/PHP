"""Pure synthetic decision proof tests; no DB, device, network, or git calls."""
import base64
import copy
import json
import socket
import struct
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import native_trade_decision_fixture as receipts
import native_trade_offer_fixture as original
import sanitize_native_trade_decisions as proof


class DecisionProofTests(unittest.TestCase):
    def setUp(self):
        self.users = [dict(id=i, username='PMTrade0' + str(i), player_id='secret-player-' + str(i),
            session_id='secret-session-' + str(i), secret='secret-login-' + str(i),
            active_deck_id='0', coins=10, coupons=3, permits=2, expiry_trade=None)
            for i in (1, 2)]
        morties = [dict(id=i, owned_morty_id='secret-morty-' + str(i),
                       player_id=self.users[(i-1)//2]['player_id'], morty_id='MortyDefault',
                       hp=20, xp=125, is_locked='false', is_trading_locked='false')
                   for i in range(1, 5)]
        initial = dict(users=self.users, owned_morties=morties,
            decks=[dict(id=i, player_id=u['player_id'], deck_id='0',
                        owned_morty_ids=json.dumps(['secret-morty-' + str(i*2-1)]))
                   for i, u in enumerate(self.users, 1)],
            owned_attacks=[], owned_items=[], trades=[], trade_offers=[], completed_trades=[],
            friend_list=[], event_queue=[], friend_battle_memberships=[])
        self.parent = dict(id=1, trade_id='secret-parent', player_id=self.users[1]['player_id'],
            morty_trade_id='secret-morty-4', requested_morty_id='any', request_variant='Normal',
            is_free_trade=1, created_at='2026-11-06 10:00:00')
        parent = copy.deepcopy(initial)
        parent['trades'] = [self.parent]
        parent['users'][1]['expiry_trade'] = '2026-11-06T11:00:00.000Z'
        self.offers = {name: dict(id=i, trade_offer_id='secret-offer-' + name,
            trade_id='secret-parent', player_id=self.users[0]['player_id'], morty_offer_id='secret-morty-2')
            for i, name in enumerate(('reject', 'accept'), 1)}
        reject, accept = copy.deepcopy(parent), copy.deepcopy(parent)
        reject['trade_offers'] = [self.offers['reject']]
        accept['trade_offers'] = [self.offers['accept']]
        final = copy.deepcopy(parent)
        final['trades'] = []
        final['owned_morties'][1]['player_id'] = self.users[1]['player_id']
        final['owned_morties'][3]['player_id'] = self.users[0]['player_id']
        final['completed_trades'] = [dict(id=1, completed_trade_id='secret-complete',
            request_player_id=self.users[1]['player_id'], offer_player_id=self.users[0]['player_id'],
            morty_request_id='secret-morty-4', morty_offer_id='secret-morty-2',
            trade_request_id='secret-parent', trade_offer_id='secret-offer-accept',
            is_free_trade=1, fulfilled_at='2026-11-06 10:01:00')]
        self.snapshots = dict(zip(proof.STAGES, map(copy.deepcopy,
            [initial, parent, reject, reject, parent, accept, accept, final])))
        self.fixture = proof.validate_snapshots(self.snapshots)
        self.fixture['hashes'] = {}
        self.rows = []
        def add(path, request, response, actor=None, response_headers=None):
            index = len(self.rows)*2
            headers = {'cookie': 'session_id=' + actor['session_id']} if actor else {}
            row = dict(path=path, request=request, response=response, headers=headers,
                response_headers=response_headers or {}, request_packet_index=index,
                response_packet_index=index+1, request_time=index, response_time=index+1)
            self.rows.append(row)
            return row
        for user in self.users:
            claims = {k: user[k] for k in ('player_id', 'username', 'session_id')}
            encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
            add('/user/login', dict(secret=user['secret'], consent_identifier='synthetic'),
                dict(session_url='https://example.invalid/sse/?token=a.' + encoded + '.b'),
                response_headers={'set-cookie': 'session_id=' + user['session_id'] +
                                  '; Path=/trading/; HttpOnly; SameSite=Lax'})
        p = self.users[1]
        returned_parent = dict(trade_id='secret-parent', player_id=p['player_id'],
            morty_trade_id='secret-morty-4', morty_request='any', request_variant='Normal',
            is_free_trade=True, _created='synthetic-time')
        add('/trading/request-morty', dict(session_id=p['session_id'], player_id=p['player_id'],
            owned_morty_id='secret-morty-4', requested_morty_id='any', request_variant='Normal',
            is_free_trade=True), dict(error='None', trade=returned_parent, coupons=3), p)
        for name in ('reject', 'accept'):
            o = self.users[0]
            returned_offer = {k: v for k, v in self.offers[name].items() if k != 'id'}
            returned_offer.update(_created='synthetic-time', request_user_name='PMTrade02',
                                  offering_morty_id='MortyDefault', request_morty_id='MortyDefault')
            add('/trading/offer-morty', dict(session_id=o['session_id'], player_id=o['player_id'],
                offered_morty_id='secret-morty-2', trade_request_id='secret-parent'),
                dict(error='None', offer=returned_offer), o)
            add('/trading/get-trades', dict(session_id=p['session_id'], player_id=p['player_id']),
                dict(trade_requests=[returned_parent], trade_offers=[returned_offer], completed_trades=[]), p)
            add('/trading/offer-response', dict(trade_request_id='secret-parent',
                trade_offer_id=self.offers[name]['trade_offer_id'], request_accepted=name == 'accept'), [None, None], p)
        for user in self.users:
            add('/session/player-details', dict(session_id=user['session_id'], include=['morties']),
                dict(player_id=user['player_id'], coins=10, coupons=3, permits=2, active_deck_id=0,
                    decks=[dict(deck_id=0, owned_morty_ids=['secret-morty-' + str(user['id']*2-1)])],
                    owned_morties=[dict(owned_morty_id=m['owned_morty_id'], is_locked=False, is_trading_locked=False)
                                   for m in final['owned_morties'] if m['player_id'] == user['player_id']]))

    def inspect(self, rows=None, bounded=False):
        with patch.object(proof, 'read_fixture', return_value=self.fixture), \
             patch.object(proof, 'exchanges', return_value=copy.deepcopy(self.rows if rows is None else rows)), \
             patch.object(proof, 'digest', return_value='0'*64):
            return proof.inspect([Path('synthetic.pcap')], Path('unused'), bounded)

    def test_full_and_bounded_claims_are_redacted(self):
        result = self.inspect()
        self.assertTrue(result['full_native_decision_cycle_proved'])
        self.assertNotIn('secret-', json.dumps(result))
        one_actor = self.rows[:-1]
        with self.assertRaises(ValueError): self.inspect(one_actor)
        bounded = self.inspect(one_actor, True)
        self.assertFalse(bounded['full_native_decision_cycle_proved'])
        self.assertTrue(bounded['bounded_stage_only'])
        self.assertEqual(bounded['proof']['post_accept_native_owned_refresh_actor_count'], 1)
        rows = copy.deepcopy(self.rows)
        rows[0]['request']['secret-private-key'] = 'private-value'
        self.assertNotIn('secret-private-key', json.dumps(self.inspect(rows)))

    def test_multi_capture_phase_order_uses_packet_time_not_input_position(self):
        early, late = copy.deepcopy(self.rows[:6]), copy.deepcopy(self.rows[6:])
        with patch.object(proof, 'read_fixture', return_value=self.fixture), \
             patch.object(proof, 'exchanges', side_effect=[late, early]), \
             patch.object(proof, 'digest', return_value='0'*64):
            result = proof.inspect([Path('late.pcap'), Path('early.pcap')], Path('unused'))
        self.assertTrue(result['full_native_decision_cycle_proved'])
        self.assertEqual(result['exchanges'][0]['capture_index'], 1)

    def test_latest_native_login_rotation_invalidates_earlier_cookie(self):
        rows = copy.deepcopy(self.rows)
        rotated = copy.deepcopy(rows[0])
        rotated.update(request_packet_index=99, response_packet_index=100,
                       request_time=11.1, response_time=11.2)
        rotated['response_headers']['set-cookie'] = (
            'session_id=secret-new-session; Path=/trading/; HttpOnly; SameSite=Lax')
        claims = dict(player_id=self.users[0]['player_id'], username='PMTrade01', session_id='secret-new-session')
        encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
        rotated['response']['session_url'] = 'https://example.invalid/sse/?token=a.' + encoded + '.b'
        rows.append(rotated)
        with self.assertRaises(ValueError): self.inspect(rows)

    def test_native_completion_alias_is_optional_but_must_equal_legacy_with_exact_types(self):
        result = self.inspect()
        self.assertFalse(result['proof']['all_get_trades_responses_have_native_completion_alias'])
        rows = copy.deepcopy(self.rows)
        for row in rows:
            if row['path'] == '/trading/get-trades':
                row['response']['competed_trades'] = []
        fixed = self.inspect(rows)
        self.assertTrue(fixed['proof']['all_get_trades_responses_have_native_completion_alias'])
        self.assertTrue(all(r['native_completed_count'] == r['legacy_completed_count'] == 0
                            for r in fixed['proof']['completion_projection_observations']))
        for legacy, native in (([], [{}]), ([], False), ([{'flag':True}], [{'flag':1}])):
            with self.subTest(legacy=legacy, native=native):
                with self.assertRaises(ValueError):
                    proof.completion_alias(dict(completed_trades=legacy, competed_trades=native))

    def test_exact_wire_identity_auth_types_and_order_fail_closed(self):
        mutations = [
            lambda r: r[5]['request'].update(session_id='secret-session-2'),
            lambda r: r[5]['request'].update(request_accepted='false'),
            lambda r: r[5]['request'].update(request_accepted=0),
            lambda r: r[8]['request'].update(request_accepted=1),
            lambda r: r[5]['request'].update(trade_offer_id='other'),
            lambda r: r[5]['request'].update(trade_request_id='other'),
            lambda r: r[5]['headers'].update(cookie='session_id=secret-session-1'),
            lambda r: r[5]['headers'].update(cookie='session_id=secret-session-2; session_id=secret-session-2'),
            lambda r: r[5]['headers'].update(authorization='synthetic'),
            lambda r: r[1]['response_headers'].update({'set-cookie':'session_id=secret-session-2; Path=/; HttpOnly; SameSite=Lax'}),
            lambda r: r[1]['response_headers'].update({'set-cookie':'session_id=secret-session-2; Path=/trading/; SameSite=Lax'}),
            lambda r: r[1]['request'].update(secret='other'),
            lambda r: r[2]['response']['trade'].update(trade_id='other'),
            lambda r: r[4]['response']['trade_offers'][0].update(trade_offer_id='other'),
            lambda r: r[4].update(response_time=50),
            lambda r: r[8].update(response=[None]),
            lambda r: r[9]['response']['owned_morties'][0].update(is_trading_locked='false'),
            lambda r: r[9]['response']['owned_morties'][0].update(is_locked=0),
            lambda r: r[9]['response']['decks'][0].update(owned_morty_ids=[]),
            lambda r: r[9]['response'].update(owned_morties=[]),
        ]
        for number, mutate in enumerate(mutations):
            with self.subTest(case=number):
                rows = copy.deepcopy(self.rows)
                mutate(rows)
                with self.assertRaises((ValueError, KeyError)): self.inspect(rows)
        for path in ('/trading/offer-response', '/trading/request-morty', '/trading/get-trades', '/user/login'):
            with self.subTest(missing=path):
                with self.assertRaises(ValueError): self.inspect([r for r in self.rows if r['path'] != path], True)

    def test_database_ownership_completion_and_protected_rows(self):
        mutations = [
            ('after-reject', lambda s: s['trades'].clear()),
            ('after-reject', lambda s: s['owned_morties'][0].update(hp=19)),
            ('after-reject', lambda s: s['users'][0].update(coins=11)),
            ('after-accept', lambda s: s['completed_trades'].clear()),
            ('after-accept', lambda s: s['completed_trades'].append(copy.deepcopy(s['completed_trades'][0]))),
            ('after-accept', lambda s: s['completed_trades'][0].update(trade_offer_id='other')),
            ('after-accept', lambda s: s['owned_morties'][1].update(player_id='secret-player-1')),
            ('after-accept', lambda s: s['owned_morties'][0].update(player_id='secret-player-2')),
            ('after-accept', lambda s: s['owned_morties'][3].update(xp=126)),
            ('after-accept', lambda s: s['owned_items'].append(dict(id=1))),
            ('after-accept', lambda s: s['users'][1].update(expiry_trade=None)),
            ('before-accept', lambda s: s['decks'][0].update(owned_morty_ids='["secret-morty-2"]')),
        ]
        for label, mutate in mutations:
            with self.subTest(label=label):
                snapshots = copy.deepcopy(self.snapshots)
                mutate(snapshots[label])
                with self.assertRaises((ValueError, KeyError)): proof.validate_snapshots(snapshots)

    def test_acceptance_query_row_order_preserves_physical_attack_rows(self):
        snapshots = copy.deepcopy(self.snapshots)
        attacks = [dict(id=i, owned_morty_id='secret-morty-' + str(i), pp=12) for i in range(1, 5)]
        for snapshot in snapshots.values():
            snapshot['owned_attacks'] = copy.deepcopy(attacks)
        snapshots['after-accept']['owned_attacks'].reverse()
        proof.validate_snapshots(snapshots)
        snapshots['after-accept']['owned_attacks'][0]['pp'] = 11
        with self.assertRaises(ValueError): proof.validate_snapshots(snapshots)

    def write_receipts(self, directory, extended=False):
        initial = self.snapshots['before-parent']
        old = dict(version=1, private=True, accounts=['PMTrade01', 'PMTrade02'],
                   snapshot=initial, identity=original.identity(initial))
        baseline = dict(old, action='snapshot', created_utc='2026-11-06T10:00:00+00:00', identity=receipts.pair_anchor(initial),
            old_pair_baseline=dict(document=old, identity=old['identity'], sha256='0'*64))
        path = directory / 'baseline.json'
        path.write_text(json.dumps(baseline), encoding='utf-8')
        prior, prior_hash = None, proof.digest(path)
        baseline_hash = prior_hash
        specs = [(label, stage, self.snapshots[alias or 'after-reject'], False)
                 for label, stage, alias in proof.RECEIPTS]
        if extended:
            gap = copy.deepcopy(self.snapshots['accept-offer-created'])
            gap['trade_offers'][0]['trade_offer_id'] = 'secret-offer-gap'
            specs = specs[:7] + [
                ('accept-offer-created', 'offer', gap, False),
                ('capture-gap-before-reject', 'offer', gap, False),
                ('capture-gap-offer-rejected', 'rejected', gap, True),
                ('capture-gap-retry-before-reject', 'offer', gap, False),
                ('capture-gap-retry-rejected', 'rejected', self.snapshots['after-reject'], False)] + [
                ('verified-' + label, stage, self.snapshots[alias or 'after-reject'], False)
                for label, stage, alias in proof.RECEIPTS[5:]]
        successful_hash = baseline_hash
        for sequence, (label, stage, snapshot, failed) in enumerate(specs, 1):
            document = dict(version=1, private=True, accounts=['PMTrade01', 'PMTrade02'],
                action='observe', stage=stage, label=label, sequence=sequence,
                created_utc='2026-11-06T10:00:' + str(sequence).zfill(2) + '+00:00',
                snapshot=snapshot, identity=baseline['identity'], baseline_sha256=baseline_hash,
                previous_sha256=prior_hash,
                comparison={'passed':False, 'private_details_suppressed':True} if failed else
                receipts.compare_snapshot(baseline, snapshot, stage, prior))
            path = directory / ('observe-' + label + '.json')
            path.write_text(json.dumps(document), encoding='utf-8')
            captured_hash = proof.digest(path)
            if failed:
                resumption = receipts.recovery_document(baseline, baseline_hash, document,
                    captured_hash, prior, successful_hash)
                resumption['created_utc'] = '2026-11-06T10:00:' + str(sequence).zfill(2) + '.500000+00:00'
                (directory / ('resume-' + label + '.json')).write_text(json.dumps(resumption), encoding='utf-8')
            else:
                prior, successful_hash = document, captured_hash
            prior_hash = captured_hash

    def test_complete_append_only_receipts_and_hash_chain(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.write_receipts(directory)
            self.assertEqual(len(proof.read_fixture(directory)['hashes']), 11)
            path = directory / 'observe-accept-before-decision.json'
            document = proof.strict_json(path.read_text())
            document['previous_sha256'] = 'f'*64
            path.write_text(json.dumps(document), encoding='utf-8')
            with self.assertRaises(ValueError): proof.read_fixture(directory)

    def test_accept_prefix_validates_all_intermediate_history_and_discloses_capture_gap(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self.write_receipts(directory, extended=True)
            fixture = proof.read_fixture(directory, 'verified-accept')
            history = fixture['history']
            self.assertEqual(history['observation_count'], 17)
            self.assertEqual(history['intermediate_offer_count'], 1)
            self.assertTrue(history['intermediate_offer_capture_gap_disclosed'])
            self.assertFalse(history['continuous_native_observation_of_all_history_proved'])
            self.assertEqual(history['resumed_failed_unchanged_offer_observations'][0]['sequence'], 10)
            self.assertNotIn('secret-', json.dumps(history))
            with self.assertRaises(ValueError): proof.read_fixture(directory)
            with patch.object(proof, 'read_fixture', return_value=fixture), \
                 patch.object(proof, 'exchanges', return_value=copy.deepcopy(self.rows)), \
                 patch.object(proof, 'digest', return_value='0'*64):
                result = proof.inspect([Path('synthetic')], directory, accept_prefix='verified-accept')
            self.assertTrue(result['selected_native_decisions_and_refreshes_proved'])
            self.assertFalse(result['full_native_decision_cycle_proved'])

    def test_unselected_intermediate_tampering_or_missing_strict_resume_is_rejected(self):
        for target, change in (
                ('observe-accept-offer-created.json', lambda d: d['snapshot']['owned_morties'][0].update(hp=19)),
                ('observe-capture-gap-offer-rejected.json', lambda d: d['snapshot']['users'][0].update(coins=11)),
                ('resume-capture-gap-offer-rejected.json', lambda d: d.update(failed_sequence=9)),
                ('resume-capture-gap-offer-rejected.json', None)):
            with self.subTest(target=target, delete=change is None), tempfile.TemporaryDirectory() as temp:
                directory = Path(temp)
                self.write_receipts(directory, extended=True)
                path = directory / target
                if change is None:
                    path.unlink()
                else:
                    document = proof.strict_json(path.read_text())
                    change(document)
                    path.write_text(json.dumps(document), encoding='utf-8')
                with self.assertRaises(ValueError): proof.read_fixture(directory, 'verified-accept')

    def wire_packets(self, body=b'{}'):
        request = (b'POST /trading/offer-response HTTP/1.1\r\nUser-Agent: UnityApp/2.41.0 (Android)\r\n'
                   b'X-PMClient: synthetic\r\nContent-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body)
        response = b'HTTP/1.1 200 OK\r\nContent-Length: 11\r\n\r\n[null,null]'
        key = ('192.0.2.1', 50000, '192.0.2.2', 8087)
        reverse = (key[2], key[3], key[0], key[1])
        return [(key, 100, 1, request), (reverse, 200, 100+len(request), response)]

    def test_parser_exact_ack_native_headers_json_types_and_order(self):
        packets = self.wire_packets()
        with patch.object(proof, 'packets', return_value=packets), \
             patch.object(proof, 'capture_packet_times', return_value=list(range(len(packets)))):
            self.assertEqual(len(proof.exchanges(Path('unused'))), 1)
        key, seq, ack, body = packets[1]
        bad = [packets[:1] + [(key, seq, ack+1, body)],
               packets + [(key, seq, ack+1, body)],
               packets + [(key, seq+len(body), ack, body)],
               list(reversed(packets)),
               self.wire_packets(b'{"request_accepted":false,"request_accepted":true}'),
               self.wire_packets(b'{"value":NaN}')]
        split = len(packets[0][3]) // 2
        qkey, qseq, qack, qbody = packets[0]
        bad.append([(qkey, qseq, qack, qbody[:split]), packets[1],
                    (qkey, qseq+split, qack, qbody[split:])])
        for number, changed in enumerate(bad):
            with self.subTest(case=number):
                with patch.object(proof, 'packets', return_value=changed), \
                     patch.object(proof, 'capture_packet_times', return_value=list(range(len(changed)))):
                    with self.assertRaises((ValueError, AssertionError)): proof.exchanges(Path('unused'))

    def test_unrelated_chunked_response_is_ignored_before_target_body_parser(self):
        packets = self.wire_packets()
        key, seq, ack, response = packets[1]
        chunked = b'HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n'
        unrelated = [packets[0], (key, seq, ack-1, chunked),
                     (key, seq+len(chunked), ack, response)]
        with patch.object(proof, 'packets', return_value=unrelated), \
             patch.object(proof, 'capture_packet_times', return_value=[1, 2, 3]):
            self.assertEqual(len(proof.exchanges(Path('unused'))), 1)
        selected = [packets[0], (key, seq, ack, chunked)]
        with patch.object(proof, 'packets', return_value=selected), \
             patch.object(proof, 'capture_packet_times', return_value=[1, 2]):
            with self.assertRaises(AssertionError): proof.exchanges(Path('unused'))

    def test_known_native_startup_config_allowed_unknown_trading_path_rejected(self):
        for path, accepted in ((b'/trading/config', True), (b'/trading/unknown-mutation', False)):
            with self.subTest(accepted=accepted):
                packets = self.wire_packets()
                key, seq, ack, body = packets[0]
                request = body.replace(b'/trading/offer-response', path)
                reverse, rseq, _, reply = packets[1]
                changed = [(key, seq, ack, request), (reverse, rseq, seq+len(request), reply)]
                with patch.object(proof, 'packets', return_value=changed), \
                     patch.object(proof, 'capture_packet_times', return_value=[1, 2]):
                    if accepted:
                        self.assertEqual(proof.exchanges(Path('unused'))[0]['path'], path.decode())
                    else:
                        with self.assertRaises(ValueError): proof.exchanges(Path('unused'))

    def write_pcap(self, path, timestamps, nano=False):
        header = struct.pack('<IHHIIII', 0xa1b23c4d if nano else 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1)
        frames = []
        for (key, seq, ack, body), (seconds, fraction) in zip(self.wire_packets(), timestamps):
            tcp = struct.pack('!HHIIBBHHH', key[1], key[3], seq, ack, 0x50, 0x18, 65535, 0, 0) + body
            ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20+len(tcp), 1, 0, 64, 6, 0,
                             socket.inet_aton(key[0]), socket.inet_aton(key[2])) + tcp
            frame = b'\0'*12 + b'\x08\x00' + ip
            frames.append(struct.pack('<IIII', seconds, fraction, len(frame), len(frame)) + frame)
        path.write_bytes(header + b''.join(frames))

    def test_real_pcap_timestamp_alignment_precision_and_regression(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'synthetic.pcap'
            for nano, fraction, expected in ((False, 123456, 123456000), (True, 123456789, 123456789)):
                with self.subTest(nano=nano):
                    self.write_pcap(path, [(1, fraction), (2, fraction)], nano)
                    rows = proof.exchanges(path)
                    self.assertEqual(rows[0]['request_time'], 10**9 + expected)
                    self.assertEqual(rows[0]['response_time'], 2*10**9 + expected)
            self.write_pcap(path, [(2, 0), (1, 0)])
            with self.assertRaises(ValueError): proof.exchanges(path)
            self.write_pcap(path, [(1, 10**6), (2, 0)])
            with self.assertRaises(ValueError): proof.exchanges(path)


if __name__ == '__main__':
    unittest.main()

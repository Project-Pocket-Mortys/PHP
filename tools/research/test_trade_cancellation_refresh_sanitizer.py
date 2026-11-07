"""Pure fail-closed cancellation evidence checks; no database or device access."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sanitize_trade_cancellation_refresh as proof
from test_cancel_trade_refresh_fixture import fixture, states
from cancel_trade_refresh_fixture import compare_snapshot


class CancellationProofTests(unittest.TestCase):
    def setUp(self):
        self.baseline = fixture()
        for snapshot in (self.baseline['snapshot'], self.baseline['accepted_anchor']['document']['snapshot']):
            for user in snapshot['users']:
                user['secret'] = 'private-secret-' + user['username']
        self.docs = []
        for index, (stage, snapshot) in enumerate(states(self.baseline), 1):
            self.docs.append(dict(private=True, stage=stage, snapshot=snapshot, sequence=index))
        self.users = [proof.accounts(d) for d in self.docs]
        self.parent = self.docs[0]['snapshot']['trades'][0]
        self.first = self.docs[1]['snapshot']['trade_offers'][0]
        self.second = self.docs[3]['snapshot']['trade_offers'][0]
        self.rows, self.events = [], []
        for name, user, snapshot, offset in (
                ('PMTrade01', self.users[0]['PMTrade01'], self.docs[0]['snapshot'], 0),
                ('PMTrade02', self.users[1]['PMTrade02'], self.docs[1]['snapshot'], 100000),
                ('PMTrade02', self.users[3]['PMTrade02'], self.docs[2]['snapshot'], -200000)):
            token = 'a.' + base64.urlsafe_b64encode(json.dumps(user).encode()).decode().rstrip('=') + '.b'
            login = self.row(user, '/user/login', {'secret': user['secret']},
                {'session_url': 'https://example.invalid/sse/?token=' + token}, offset)
            login['response_headers'] = {'set-cookie': 'session_id=' + user['session_id'] + '; Path=/trading/; HttpOnly; SameSite=Lax'}
            self.rows.append([login, self.row(user, '/session/join-room', {'session_id': user['session_id']}, {}, offset+3)])
            self.events.append([dict(event='session:start', payload=user, token=token,
                time=offset+2, client='private-client-' + name, request_time=offset+1.5)])
        owner, peer, peer2 = self.users[0]['PMTrade01'], self.users[1]['PMTrade02'], self.users[3]['PMTrade02']
        parent_response = {key: self.parent[key] for key in ('trade_id', 'player_id', 'morty_trade_id', 'request_variant')}
        parent_response.update(morty_request='any', is_free_trade=True, _created='2026-11-07T12:00:00Z')
        self.rows[0] += [self.row(owner, '/trading/request-morty', dict(session_id=owner['session_id'],
            player_id=owner['player_id'], owned_morty_id=self.parent['morty_trade_id'], requested_morty_id='any',
            request_variant='Normal', is_free_trade=True), {'error': 'None', 'trade': parent_response}, 20),
            self.detail(owner, 22, self.docs[0]['snapshot'], {self.parent['morty_trade_id']})]
        for time, snapshot, offer, present in ((40, self.docs[1]['snapshot'], self.first, True),
                (80, self.docs[2]['snapshot'], self.first, False), (120, self.docs[3]['snapshot'], self.second, True)):
            self.event(0, 'trade:offer-submit', time)
            self.rows[0] += [self.listing(owner, time+1, snapshot, offer, present),
                self.detail(owner, time+1.1, snapshot, {self.parent['morty_trade_id']})]
        self.rows[0] += [self.row(owner, '/trading/cancel-trade', {'trade_id': self.parent['trade_id']},
            {'error': 'None'}, 150), self.detail(owner, 152, self.docs[4]['snapshot'], set())]
        self.rows[1] += [self.offer(peer, 100020, self.docs[1]['snapshot'], self.first),
            self.detail(peer, 100022, self.docs[1]['snapshot'], {self.first['morty_offer_id']}),
            self.row(peer, '/trading/cancel-trade-offer', {'trade_offer_id': self.first['trade_offer_id']},
                {'error': 'None'}, 100060)]
        startup = self.detail(peer2, -199995, self.docs[2]['snapshot'], set())
        startup['request']['include'] = proof.INCLUDE + ['player', 'items', 'currency', 'avatars', 'badges', 'settings', 'dimensions']
        self.rows[2] += [startup, self.offer(peer2, -199980, self.docs[3]['snapshot'], self.second),
            self.detail(peer2, -199978, self.docs[3]['snapshot'], {self.second['morty_offer_id']}),
            self.listing(peer2, -199939, self.docs[4]['snapshot'], self.second, False, parent=False),
            self.detail(peer2, -199938.9, self.docs[4]['snapshot'], set())]
        self.event(2, 'trade:offer-rejected', -199940)

    def row(self, user, path, request, response, time):
        return dict(path=path, request=request, response=response, request_time=time, response_time=time+1,
            headers={'x-pmclient': 'private-client-' + user['username'], 'cookie': 'session_id=' + user['session_id']},
            response_headers={})

    def event(self, capture, name, time):
        start = self.events[capture][0]
        self.events[capture].append(dict(start, event=name, payload={}, time=time))

    def detail(self, user, time, snapshot, locked):
        return self.row(user, '/session/player-details', {'session_id': user['session_id'], 'include': proof.INCLUDE},
            dict(player_id=user['player_id'], username=user['username'], decks=[], mortydex=[],
                owned_morties=[dict(owned_morty_id=m['owned_morty_id'], is_locked=False,
                    is_trading_locked=m['owned_morty_id'] in locked) for m in snapshot['owned_morties']
                    if m['player_id'] == user['player_id']]), time)

    def projection(self, offer, snapshot):
        owned = {m['owned_morty_id']: m for m in snapshot['owned_morties']}
        value = {key: offer[key] for key in ('trade_offer_id', 'trade_id', 'player_id', 'morty_offer_id')}
        value.update(request_user_name='PMTrade01', request_morty_id=owned[self.parent['morty_trade_id']]['morty_id'],
            offering_morty_id=owned[offer['morty_offer_id']]['morty_id'], _created='2026-11-07T12:00:00Z')
        return value

    def offer(self, user, time, snapshot, offer):
        return self.row(user, '/trading/offer-morty', dict(session_id=user['session_id'], player_id=user['player_id'],
            offered_morty_id=offer['morty_offer_id'], trade_request_id=self.parent['trade_id']),
            {'error': 'None', 'offer': self.projection(offer, snapshot)}, time)

    def listing(self, user, time, snapshot, offer, present, parent=True):
        completed = [{key: value for key, value in row.items() if key not in ('id', 'fulfilled_at')}
                     for row in snapshot['completed_trades']]
        for row in completed:
            row['is_free_trade'] = bool(row['is_free_trade'])
        return self.row(user, '/trading/get-trades', {'session_id': user['session_id'], 'player_id': user['player_id']},
            dict(trade_requests=[copy.deepcopy(self.parent)] if parent else [],
                 trade_offers=[self.projection(offer, snapshot)] if present else [],
                 completed_trades=completed, competed_trades=copy.deepcopy(completed)), time)

    def validate(self):
        return proof.validate(self.rows[0], self.events[0], self.rows[1], self.events[1],
                              self.rows[2], self.events[2], self.docs, (0, 100000, -200000))

    def test_two_phase_counterpart_proof_is_redacted_and_discloses_cold_login(self):
        result = self.validate()
        for key in ('actual_native_own_offer_cancellation_proved', 'actual_native_parent_cancellation_proved',
                    'counterpart_native_trade_and_details_refresh_proved', 'peer_cold_login_boundary_proved'):
            self.assertTrue(result[key])
        for key in ('uninterrupted_peer_session_proved', 'self_cancel_cached_memory_unlock_proved',
                    'selector_eligibility_proved', 'parent_cancel_incoming_ui_button_proved',
                    'cross_capture_clock_order_proved', 'exact_sse_frame_trade_id_binding_proved',
                    'self_cancel_immediate_owned_refresh_observed', 'original_service_behavior_proved'):
            self.assertFalse(result[key])
        serialized = json.dumps(result)
        for private in ('private-secret-', 'private-client-', self.parent['trade_id'],
                        self.first['trade_offer_id'], self.second['trade_offer_id'], 'peer-cold-login', 'player-0', 'morty-0-1'):
            self.assertNotIn(private, serialized)
        self.assertEqual([n['recipient'] for n in result['notifications']], ['PMTrade01'] * 3 + ['PMTrade02'])

    def test_id_only_cancellation_and_roles_are_strict(self):
        for capture, path in ((0, '/trading/cancel-trade'), (1, '/trading/cancel-trade-offer')):
            row = next(r for r in self.rows[capture] if r['path'] == path)
            original = copy.deepcopy(row)
            for change in (lambda r: r['request'].update(session_id='invented'),
                           lambda r: r['request'].update({next(iter(r['request'])): 'foreign'}),
                           lambda r: r.update(response={'error': {'code': 'FAILED'}})):
                row.clear(); row.update(copy.deepcopy(original)); change(row)
                with self.assertRaises(ValueError):
                    self.validate()
            row.clear(); row.update(original)
        self.rows[2].append(copy.deepcopy(self.rows[1][-1]))
        with self.assertRaises(ValueError):
            self.validate()

    def test_missing_duplicate_or_actor_trade_frames_fail(self):
        saved = copy.deepcopy(self.events)
        for change in (lambda: self.events[0].pop(), lambda: self.event(0, 'trade:offer-submit', 130),
                       lambda: self.event(1, 'trade:offer-submit', 100062),
                       lambda: self.event(2, 'trade:offer-accepted', -199930),
                       lambda: self.events[0][1].update(payload={'trade_id': 'invented'})):
            self.events = copy.deepcopy(saved); change()
            with self.assertRaises(ValueError):
                self.validate()

    def test_wrong_cookie_token_or_sse_reconnect_fail(self):
        saved_rows, saved_events = copy.deepcopy(self.rows), copy.deepcopy(self.events)
        for change in (lambda: self.rows[1][-1]['headers'].update(cookie='session_id=foreign'),
                       lambda: self.events[2][-1].update(token=self.events[1][0]['token']),
                       lambda: self.events[0][-1].update(request_time=1.8),
                       lambda: self.rows[0].insert(1, copy.deepcopy(self.rows[0][0]))):
            self.rows, self.events = copy.deepcopy(saved_rows), copy.deepcopy(saved_events); change()
            with self.assertRaises(ValueError):
                self.validate()

    def test_missing_or_ambiguous_refresh_and_wrong_include_fail(self):
        saved = copy.deepcopy(self.rows)
        for change in (lambda: self.rows[0].pop(4),
                       lambda: self.rows[0][4]['request'].update(include=proof.INCLUDE + ['currency']),
                       lambda: self.rows[0].insert(5, dict(copy.deepcopy(self.rows[0][4]), request_time=41.2)),
                       lambda: self.rows[2][-1]['request'].update(include=proof.INCLUDE[:3]),
                       lambda: self.rows[2][2]['request'].update(include=proof.INCLUDE)):
            self.rows = copy.deepcopy(saved); change()
            with self.assertRaises(ValueError):
                self.validate()

    def test_derived_reservations_and_native_completion_alias_are_checked(self):
        saved = copy.deepcopy(self.rows)
        for change in (lambda: self.rows[2][-1]['response']['owned_morties'][1].update(is_trading_locked=True),
                       lambda: self.rows[0][5]['response']['owned_morties'][1].update(is_trading_locked=False),
                       lambda: self.rows[2][-2]['response'].pop('competed_trades'),
                       lambda: self.rows[0][4]['response']['trade_offers'][0].update(request_user_name='PMTrade02'),
                       lambda: self.rows[0][4]['response']['completed_trades'].pop()):
            self.rows = copy.deepcopy(saved); change()
            with self.assertRaises(ValueError):
                self.validate()

    def test_snapshot_roles_notification_recipient_and_completions_fail_closed(self):
        saved = copy.deepcopy(self.docs)
        for change in (lambda: self.docs[2]['snapshot']['trade_refresh_notifications'][1].update(revision='9'),
                       lambda: self.docs[4]['snapshot']['completed_trades'].pop(),
                       lambda: self.docs[3]['snapshot']['trade_offers'][0].update(trade_offer_id=self.first['trade_offer_id']),
                       lambda: self.docs[4]['snapshot']['users'][1].update(session_id='other')):
            self.docs = copy.deepcopy(saved); change()
            with self.assertRaises(ValueError):
                self.validate()

    def test_peer_cold_login_rotation_is_required_even_with_other_valid_identity(self):
        # A capture with one continuous peer session must never be described
        # as the explicitly observed cold-login workaround used by this proof.
        session = self.users[1]['PMTrade02']['session_id']
        for document in self.docs[3:]:
            next(u for u in document['snapshot']['users'] if u['username'] == 'PMTrade02')['session_id'] = session
        with self.assertRaises(ValueError):
            self.validate()

    def test_post_self_cancel_details_are_not_hidden_as_uninterrupted_gap(self):
        self.rows[1].append(self.detail(self.users[1]['PMTrade02'], 100065, self.docs[2]['snapshot'], set()))
        with self.assertRaises(ValueError):
            self.validate()

    def test_inspect_revalidates_actual_anchor_and_append_only_history(self):
        with tempfile.TemporaryDirectory() as directory:
            directory = Path(directory)
            anchor = directory / 'anchor.json'
            anchor.write_text(json.dumps(self.baseline['accepted_anchor']['document']), encoding='utf-8')
            self.baseline['accepted_anchor']['sha256'] = proof.digest(anchor)
            baseline_path = directory / 'baseline.json'
            baseline_path.write_text(json.dumps(self.baseline), encoding='utf-8')
            previous, previous_hash, paths = None, proof.digest(baseline_path), []
            for index, document in enumerate(self.docs, 1):
                document.update(version=1, accounts=self.baseline['accounts'], action='observe',
                    identity=self.baseline['identity'], label='step-' + str(index),
                    baseline_sha256=proof.digest(baseline_path), previous_sha256=previous_hash,
                    comparison=compare_snapshot(self.baseline, document['snapshot'], document['stage'], previous))
                path = directory / ('observe-' + document['label'] + '.json')
                path.write_text(json.dumps(document), encoding='utf-8')
                (directory / ('observe-' + document['label'] + '-attempt.json')).write_text(
                    json.dumps({'action': 'observe', 'private': True}), encoding='utf-8')
                paths.append(path)
                previous, previous_hash = document, proof.digest(path)
            pcaps = [directory / f'capture-{i}.pcap' for i in range(3)]
            for path in pcaps:
                path.write_bytes(b'private-pcap-placeholder')
            captures = {p: (self.rows[i], self.events[i], (0, 100000, -200000)[i]) for i, p in enumerate(pcaps)}
            with patch.object(proof, 'ANCHOR', anchor), patch.object(proof, 'wire_observations',
                    side_effect=lambda path, allowed_paths: captures[path]) as wire:
                result = proof.inspect(*pcaps, paths)
                self.assertTrue(result['protected_fixture_history_revalidated'])
                self.assertTrue(all(call.kwargs['allowed_paths'] == proof.ALLOWED_PATHS for call in wire.call_args_list))
                original_anchor = anchor.read_bytes()
                anchor.write_bytes(original_anchor + b' ')
                with self.assertRaises(ValueError):
                    proof.inspect(*pcaps, paths)
                anchor.write_bytes(original_anchor)
                pending = directory / 'observe-unresolved-attempt.json'
                pending.write_text(json.dumps({'action': 'observe', 'private': True}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    proof.inspect(*pcaps, paths)
                pending.unlink()
                paths[-1].write_text(paths[-1].read_text().replace('"ownership_unchanged": true', '"ownership_unchanged": false'))
                with self.assertRaises(ValueError):
                    proof.inspect(*pcaps, paths)


if __name__ == '__main__':
    unittest.main()

"""Pure fail-closed evidence tests; no database, emulator or network access."""
import base64
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sanitize_live_trade_refresh as proof
from test_live_trade_refresh_fixture import fixture, parent_state, offer_state, rejected_state, accepted_state_new
from live_trade_refresh_fixture import compare_snapshot
import test_trade_refresh_smoke_sanitizer as smoke_tests


class LiveTradeRefreshTests(unittest.TestCase):
    def setUp(self):
        baseline = fixture()
        self.docs = [dict(private=True, snapshot=state(baseline))
                     for state in (parent_state, offer_state, rejected_state)]
        for doc in self.docs:
            for user in doc['snapshot']['users']:
                user['secret'] = 'private-secret-'+user['username']
        self.users = proof.accounts(self.docs[1])
        self.parent = self.docs[0]['snapshot']['trades'][0]
        self.offer = self.docs[1]['snapshot']['trade_offers'][0]
        owned = {row['owned_morty_id']: row for row in self.docs[1]['snapshot']['owned_morties']}
        self.returned_offer = {key: self.offer[key] for key in ('trade_offer_id', 'trade_id', 'player_id', 'morty_offer_id')}
        self.returned_offer.update(request_user_name='PMTrade02',
            request_morty_id=owned[self.parent['morty_trade_id']]['morty_id'],
            offering_morty_id=owned[self.offer['morty_offer_id']]['morty_id'], _created='2026-11-07T00:00:00Z')
        self.rows, self.events = {}, {}
        for index, name in enumerate(('PMTrade01', 'PMTrade02')):
            user = self.users[name]
            offset = index * 100000  # Deliberately unrelated device clocks.
            token = 'a.' + base64.urlsafe_b64encode(json.dumps(user).encode()).decode().rstrip('=') + '.b'
            login = self.row(name, '/user/login', {'secret': user['secret']},
                             {'session_url': 'https://example.invalid/sse/?token='+token}, offset)
            login['response_headers'] = {'set-cookie': 'session_id='+user['session_id']+'; Path=/trading/; HttpOnly; SameSite=Lax'}
            self.rows[name] = [login]
            self.events[name] = [dict(event='session:start', payload=user, token=token,
                                     time=offset+2, client='private-client-'+name)]
        primary, peer = self.users['PMTrade01'], self.users['PMTrade02']
        self.rows['PMTrade01'] += [
            self.row('PMTrade01', '/trading/offer-morty', dict(session_id=primary['session_id'],
                player_id=primary['player_id'], offered_morty_id=self.offer['morty_offer_id'],
                trade_request_id=self.parent['trade_id']), {'error': 'None', 'offer': self.returned_offer}, 20),
            self.detail('PMTrade01', 22, {self.offer['morty_offer_id']}),
            self.listing('PMTrade01', 41, False), self.detail('PMTrade01', 41.1, set())]
        self.rows['PMTrade02'] += [self.listing('PMTrade02', 100031, True),
            self.detail('PMTrade02', 100031.1, {self.parent['morty_trade_id']}),
            self.row('PMTrade02', '/trading/offer-response', dict(trade_request_id=self.parent['trade_id'],
                trade_offer_id=self.offer['trade_offer_id'], request_accepted=False), [None, None], 100040)]
        for name, event, time in [('PMTrade01', 'trade:offer-submit', 4),
                                 ('PMTrade01', 'trade:offer-rejected', 40),
                                 ('PMTrade02', 'trade:offer-submit', 100030)]:
            self.events[name].append(dict(event=event, payload={}, time=time,
                token=self.events[name][0]['token'], client='private-client-'+name))

    def row(self, name, path, request, response, time):
        return dict(path=path, request=request, response=response, request_time=time,
            response_time=time+1, headers={'x-pmclient': 'private-client-'+name,
                'cookie': 'session_id='+self.users[name]['session_id']}, response_headers={})

    def detail(self, name, time, locked):
        user = self.users[name]
        response = dict(player_id=user['player_id'], username=name, decks=[], mortydex=[],
            owned_morties=[dict(owned_morty_id=row['owned_morty_id'], is_locked=False,
                is_trading_locked=row['owned_morty_id'] in locked)
                for row in self.docs[1]['snapshot']['owned_morties'] if row['player_id'] == user['player_id']])
        return self.row(name, '/session/player-details', dict(session_id=user['session_id'], include=proof.INCLUDE), response, time)

    def listing(self, name, time, offered):
        completed = [{key: value for key, value in row.items() if key not in ('id', 'fulfilled_at')}
                     for row in self.docs[1]['snapshot']['completed_trades']]
        for row in completed:
            row['is_free_trade'] = bool(row['is_free_trade'])
        return self.row(name, '/trading/get-trades', dict(session_id=self.users[name]['session_id'],
            player_id=self.users[name]['player_id']), dict(trade_requests=[copy.deepcopy(self.parent)],
            trade_offers=[copy.deepcopy(self.returned_offer)] if offered else [],
            completed_trades=completed, competed_trades=copy.deepcopy(completed)), time)

    def validate(self):
        return proof.validate(self.rows['PMTrade01'], self.events['PMTrade01'],
            self.rows['PMTrade02'], self.events['PMTrade02'], *self.docs)

    def test_live_offer_reject_claims_are_bounded_and_redacted(self):
        result = self.validate()
        self.assertTrue(result['actual_native_offer_and_owner_rejection_proved'])
        for key in ('acceptance_proved', 'original_service_behavior_proved', 'cross_device_clock_order_proved',
                    'mutation_to_sse_latency_proved', 'exact_sse_frame_trade_id_binding_proved'):
            self.assertFalse(result[key])
        text = json.dumps(result)
        for value in ('private-client-', self.offer['trade_offer_id'], self.parent['trade_id'], self.users['PMTrade01']['secret']):
            self.assertNotIn(value, text)

    def test_platform_header_may_match_across_distinct_native_accounts(self):
        for rows in self.rows.values():
            for row in rows:
                row['headers']['x-pmclient'] = 'Android/2.41.0'
        for events in self.events.values():
            for event in events:
                event['client'] = 'Android/2.41.0'
        self.assertTrue(self.validate()['separate_native_client_identities_proved'])

    def test_startup_static_config_null_session_is_cookie_bound_and_cannot_authorize_refresh(self):
        config = self.row('PMTrade01', '/trading/config', {'session_id': None}, {}, 1.5)
        self.rows['PMTrade01'].insert(1, config)
        self.assertTrue(self.validate()['separate_native_client_identities_proved'])
        for change in (lambda: config['headers'].update(cookie='session_id=wrong'),
                       lambda: config['request'].update(session_id='wrong'),
                       lambda: config.update(request_time=25, response_time=26)):
            original = copy.deepcopy(config)
            change()
            with self.assertRaises(ValueError):
                self.validate()
            config.clear()
            config.update(original)

    def test_identity_fields_cookie_mask_metadata_and_alias_fail_closed(self):
        changes = [
            lambda: self.rows['PMTrade01'][1]['headers'].update(cookie='session_id=wrong'),
            lambda: self.rows['PMTrade02'][1]['request'].update(player_id='wrong'),
            lambda: self.rows['PMTrade01'][1]['request'].update(trade_request_id='wrong'),
            lambda: self.rows['PMTrade02'][3]['request'].update(request_accepted=0),
            lambda: self.rows['PMTrade02'][3]['request'].update(extra=True),
            lambda: self.rows['PMTrade01'][2]['request'].update(include=['morties']),
            lambda: self.rows['PMTrade01'][2]['response']['owned_morties'][-1].update(is_trading_locked=False),
            lambda: self.rows['PMTrade02'][1]['response']['trade_offers'][0].update(request_user_name=self.users['PMTrade02']['player_id']),
            lambda: self.rows['PMTrade02'][1]['response'].pop('competed_trades'),
            lambda: self.events['PMTrade02'][-1].update(payload={'trade_id': self.parent['trade_id']}),
            lambda: self.events['PMTrade02'][-1].update(token='other'),
            lambda: self.rows['PMTrade01'][0]['request'].update(secret='wrong'),
        ]
        for number, change in enumerate(changes):
            with self.subTest(number=number):
                self.setUp()
                change()
                with self.assertRaises((ValueError, KeyError)):
                    self.validate()

    def test_competing_refresh_duplicate_event_and_same_device_order_fail(self):
        for change in (
            lambda: self.events['PMTrade02'].append(copy.deepcopy(self.events['PMTrade02'][-1])),
            lambda: self.rows['PMTrade02'].insert(2, copy.deepcopy(self.rows['PMTrade02'][1])),
            lambda: self.rows['PMTrade01'][2].update(request_time=19),
            lambda: self.rows['PMTrade02'][3].update(request_time=100031.5),
        ):
            self.setUp()
            change()
            with self.assertRaises((ValueError, KeyError)):
                self.validate()

    def test_db_recipient_revision_parent_offer_and_physical_drift_fail(self):
        for change in (
            lambda: self.docs[1]['snapshot']['trade_refresh_notifications'][1].update(revision='2'),
            lambda: self.docs[2]['snapshot']['trade_refresh_notifications'][0].update(event_name='trade:offer-accepted'),
            lambda: self.docs[2]['snapshot']['trades'].clear(),
            lambda: self.docs[2]['snapshot']['owned_morties'][0].update(player_id='wrong'),
            lambda: self.docs[1]['snapshot']['trade_offers'][0].update(trade_id='wrong'),
        ):
            self.setUp()
            change()
            with self.assertRaises((ValueError, KeyError)):
                self.validate()

    def test_native_wire_parser_handles_chunked_sse_and_rejects_overlap(self):
        helper = smoke_tests.TradeRefreshSmokeTests()
        for bad_json, bad_overlap in ((False, False), (True, False), (False, True)):
            with self.subTest(bad_json=bad_json, bad_overlap=bad_overlap), \
                 patch.object(proof, 'capture_packet_times', return_value=[]), \
                 patch.object(proof, 'flows', return_value=(helper.wire(bad_json, bad_overlap), 1)):
                if bad_json or bad_overlap:
                    with self.assertRaises((ValueError, AssertionError)):
                        proof.wire_observations(Path('unused'))
                else:
                    rows, events, _ = proof.wire_observations(Path('unused'))
                    self.assertEqual(rows, [])
                    self.assertEqual(events[0]['time'], 2)

    def test_later_phase_is_bounded_by_independent_device_markers(self):
        primary, peer = self.rows['PMTrade01'], self.rows['PMTrade02']
        later = copy.deepcopy(primary[1])
        later.update(request_time=60, response_time=61)
        primary.append(later)
        event = copy.deepcopy(self.events['PMTrade02'][-1])
        event['time'] = 100060
        self.events['PMTrade02'].append(event)
        p, pe, q, qe, bounded = proof.bounded_rejection_prefix(primary, self.events['PMTrade01'], peer, self.events['PMTrade02'])
        self.assertTrue(bounded)
        self.assertTrue(proof.validate(p, pe, q, qe, *self.docs)['actual_native_offer_and_owner_rejection_proved'])
        # A missing peer-side phase marker cannot be replaced by the other
        # device's timestamp, even if that would make the chronology fit.
        self.events['PMTrade02'].pop()
        with self.assertRaises(ValueError):
            proof.bounded_rejection_prefix(primary, self.events['PMTrade01'], peer, self.events['PMTrade02'])

    def acceptance_inputs(self):
        offered = copy.deepcopy(self.docs[1])
        offered['snapshot']['trade_offers'][0].update(trade_offer_id='offer-3', id=3)
        offered['snapshot']['trade_refresh_notifications'][0].update(revision='2', event_name='trade:offer-rejected')
        offered['snapshot']['trade_refresh_notifications'][1]['revision'] = '2'
        accepted = dict(private=True, snapshot=accepted_state_new(fixture()))
        for user in accepted['snapshot']['users']:
            user['secret'] = 'private-secret-'+user['username']
        accepted['snapshot']['completed_trades'][-1]['trade_offer_id'] = 'offer-3'
        accepted['snapshot']['trade_refresh_notifications'][0]['revision'] = '3'
        accepted['snapshot']['trade_refresh_notifications'][1]['revision'] = '2'
        create = copy.deepcopy(self.rows['PMTrade01'][1])
        create.update(request_time=60, response_time=61)
        create['response']['offer']['trade_offer_id'] = 'offer-3'
        self.rows['PMTrade01'] += [create, self.detail('PMTrade01', 62, {self.offer['morty_offer_id']})]
        second_listing = self.listing('PMTrade02', 100061, True)
        second_listing['response']['trade_offers'][0]['trade_offer_id'] = 'offer-3'
        accept = copy.deepcopy(self.rows['PMTrade02'][-1])
        accept.update(request_time=100070, response_time=100071)
        accept['request'].update(trade_offer_id='offer-3', request_accepted=True)
        self.rows['PMTrade02'] += [second_listing,
            self.detail('PMTrade02', 100061.1, {self.parent['morty_trade_id']}), accept]
        old = self.docs[1]
        self.docs[1] = accepted
        accepted_listing = self.listing('PMTrade01', 81, False)
        accepted_listing['response']['trade_requests'] = []
        self.rows['PMTrade01'] += [accepted_listing, self.detail('PMTrade01', 81.1, set())]
        self.rows['PMTrade02'].append(self.detail('PMTrade02', 100072, set()))
        self.docs[1] = old
        for name, event, time in [('PMTrade01', 'trade:offer-accepted', 80),
                                 ('PMTrade02', 'trade:offer-submit', 100060)]:
            self.events[name].append(dict(event=event, payload={}, time=time,
                token=self.events[name][0]['token'], client='private-client-'+name))
        return offered, accepted

    def test_acceptance_requires_true_exact_offer_and_both_native_inventory_refreshes(self):
        offered, accepted = self.acceptance_inputs()
        result = proof.validate_acceptance(self.rows['PMTrade01'], self.events['PMTrade01'],
            self.rows['PMTrade02'], self.events['PMTrade02'], self.docs[2], offered, accepted)
        self.assertTrue(result['acceptance_proved'])
        self.assertTrue(result['acceptance_both_clients_owned_refresh_proved'])
        for change in (lambda: self.rows['PMTrade02'][-2]['request'].update(request_accepted=1),
                       lambda: self.rows['PMTrade02'].pop(),
                       lambda: self.rows['PMTrade01'][-1]['response']['owned_morties'].pop(),
                       lambda: accepted['snapshot']['trade_refresh_notifications'][0].update(revision='4')):
            self.setUp()
            offered, accepted = self.acceptance_inputs()
            change()
            with self.assertRaises((ValueError, KeyError)):
                proof.validate_acceptance(self.rows['PMTrade01'], self.events['PMTrade01'],
                    self.rows['PMTrade02'], self.events['PMTrade02'], self.docs[2], offered, accepted)

    def test_inspect_revalidates_receipt_hash_chain_and_does_not_trust_passed_flag(self):
        baseline = fixture()
        for snapshot in (baseline['snapshot'], baseline['accepted_anchor']['document']['snapshot']):
            for user in snapshot['users']:
                user['secret'] = 'private-secret-'+user['username']
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            baseline_path = directory / 'baseline.json'
            baseline_path.write_text(json.dumps(baseline), encoding='utf-8')
            baseline_hash = proof.digest(baseline_path)
            previous, previous_hash, paths = None, baseline_hash, []
            for sequence, (stage, doc) in enumerate(zip(('parent', 'offer', 'rejected'), self.docs), 1):
                document = dict(version=1, accounts=baseline['accounts'], private=True, action='observe',
                    identity=baseline['identity'], sequence=sequence, label='step-'+str(sequence),
                    baseline_sha256=baseline_hash, previous_sha256=previous_hash, stage=stage,
                    snapshot=doc['snapshot'], comparison=compare_snapshot(baseline, doc['snapshot'], stage, previous))
                path = directory / ('observe-step-'+str(sequence)+'.json')
                path.write_text(json.dumps(document), encoding='utf-8')
                marker = directory / ('observe-step-'+str(sequence)+'-attempt.json')
                marker.write_text(json.dumps({'action': 'observe', 'private': True}), encoding='utf-8')
                previous, previous_hash = document, proof.digest(path)
                paths.append(path)
            observations = [(self.rows[name], self.events[name], 0, []) for name in ('PMTrade01', 'PMTrade02')]
            with patch.object(proof, 'device_observations', side_effect=observations):
                result = proof.inspect(Path('primary'), Path('peer'), *paths)
            self.assertTrue(result['protected_fixture_history_revalidated'])
            bad = json.loads(paths[-1].read_text(encoding='utf-8'))
            bad['comparison']['notification']['revision'] = '900'
            paths[-1].write_text(json.dumps(bad), encoding='utf-8')
            with patch.object(proof, 'device_observations', side_effect=observations):
                with self.assertRaises(ValueError):
                    proof.inspect(Path('primary'), Path('peer'), *paths)


if __name__ == '__main__':
    unittest.main()

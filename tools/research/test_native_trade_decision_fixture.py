"""Pure decision observation checks; no database, device, or network access."""
import copy
import hashlib
import json
import unittest

from native_trade_offer_fixture import identity
from native_trade_decision_fixture import compare_snapshot, pair_anchor, validate_baseline, verify_history


def fixture():
    users = [{'id': i, 'username': account, 'player_id': f'player-{i}',
              'session_id': f'session-{i}', 'active_deck_id': 0, 'coins': 10,
              'coupons': 3, 'permits': 2, 'expiry_trade': None, 'last_seen': None,
              'room_id': None, 'state': 'WORLD', 'last_event_id': 0,
              'room_membership_generation': 0} for i, account in enumerate(('PMTrade01', 'PMTrade02'))]
    morties = [{'id': i * 2 + j, 'owned_morty_id': f'morty-{i}-{j}', 'player_id': f'player-{i}',
                'morty_id': 'MortyDefault', 'is_locked': 'false', 'is_trading_locked': 'false',
                'level': 5, 'hp': 20} for i in range(2) for j in range(2)]
    snapshot = {'users': users, 'owned_morties': morties,
                'owned_attacks': [{'id': m['id'], 'owned_morty_id': m['owned_morty_id'],
                                  'attack_id': 'AttackOutburst', 'pp': 12} for m in morties],
                'owned_items': [{'id': i, 'player_id': f'player-{i}', 'quantity': 2} for i in range(2)],
                'decks': [{'id': i, 'player_id': f'player-{i}', 'deck_id': 0,
                           'owned_morty_ids': f'["morty-{i}-0"]'} for i in range(2)],
                'friend_list': [{'id': 1, 'player_id_a': 'player-0', 'player_id_b': 'player-1'}],
                'trades': [], 'trade_offers': [], 'completed_trades': [], 'event_queue': [],
                'friend_battle_memberships': []}
    old = {'version': 1, 'accounts': ['PMTrade01', 'PMTrade02'],
           'snapshot': copy.deepcopy(snapshot), 'identity': identity(snapshot)}
    return {'version': 1, 'accounts': ['PMTrade01', 'PMTrade02'], 'private': True, 'action': 'snapshot',
            'identity': pair_anchor(snapshot), 'snapshot': snapshot,
            'old_pair_baseline': {'document': old, 'identity': identity(snapshot), 'sha256': 'a' * 64}}


def parent_state(baseline):
    snapshot = copy.deepcopy(baseline['snapshot'])
    snapshot['trades'] = [{'id': 1, 'trade_id': 'parent-1', 'player_id': 'player-1',
                           'morty_trade_id': 'morty-1-1', 'requested_morty_id': 'any',
                           'request_variant': 'Normal', 'is_free_trade': 1,
                           'created_at': '2026-11-06 12:00:00'}]
    snapshot['users'][1]['expiry_trade'] = '2026-11-06T13:00:00.000Z'
    return snapshot


def offer_state(baseline):
    snapshot = parent_state(baseline)
    snapshot['trade_offers'] = [{'id': 1, 'trade_offer_id': 'offer-1', 'trade_id': 'parent-1',
                                 'player_id': 'player-0', 'morty_offer_id': 'morty-0-1'}]
    return snapshot


def accepted_state(baseline):
    snapshot = offer_state(baseline)
    snapshot['trades'] = []
    snapshot['trade_offers'] = []
    snapshot['owned_morties'][1]['player_id'] = 'player-1'
    snapshot['owned_morties'][3]['player_id'] = 'player-0'
    snapshot['completed_trades'] = [{'id': 1, 'completed_trade_id': 'completion-1',
        'request_player_id': 'player-1', 'offer_player_id': 'player-0',
        'morty_request_id': 'morty-1-1', 'morty_offer_id': 'morty-0-1',
        'trade_request_id': 'parent-1', 'trade_offer_id': 'offer-1', 'is_free_trade': 1,
        'fulfilled_at': '2026-11-06 12:10:00'}]
    return snapshot


class NativeTradeDecisionFixtureTests(unittest.TestCase):
    def test_fixed_roles_and_baseline_anchor(self):
        baseline = fixture()
        anchor = validate_baseline(baseline)
        self.assertEqual(anchor['roles'], {'requester': 'PMTrade02', 'offerer': 'PMTrade01'})
        self.assertEqual(anchor['accounts']['PMTrade01']['spare_owned_morty_id'], 'morty-0-1')
        baseline['snapshot']['owned_morties'][0]['hp'] = 19
        with self.assertRaises(ValueError):
            validate_baseline(baseline)

    def test_full_reject_then_accept_with_same_parent(self):
        baseline = fixture()
        previous = None
        stages = [('initial', baseline['snapshot']), ('parent', parent_state(baseline)),
                  ('offer', offer_state(baseline)), ('offer', offer_state(baseline)),
                  ('rejected', parent_state(baseline)), ('parent', parent_state(baseline)),
                  ('parent', parent_state(baseline)), ('offer', offer_state(baseline)),
                  ('accepted', accepted_state(baseline))]
        for stage, snapshot in stages:
            report = compare_snapshot(baseline, snapshot, stage, previous)
            self.assertTrue(report['passed'])
            previous = {'stage': stage, 'snapshot': snapshot}
        self.assertTrue(report['exact_spare_swap'])

    def test_reject_never_transfers_and_accept_requires_exact_spares(self):
        baseline = fixture()
        previous = {'stage': 'offer', 'snapshot': offer_state(baseline)}
        mutations = [lambda s: s['owned_morties'][1].update(player_id='player-0'),
                     lambda s: s['owned_morties'][0].update(player_id='player-1'),
                     lambda s: s['owned_morties'][1].update(hp=19),
                     lambda s: s['owned_morties'][1].update(is_trading_locked='true'),
                     lambda s: s['owned_morties'][1].update(id=99),
                     lambda s: s['owned_morties'][1].update(owned_morty_id='other')]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                snapshot = accepted_state(baseline)
                mutation(snapshot)
                with self.assertRaises(ValueError):
                    compare_snapshot(baseline, snapshot, 'accepted', previous)
        snapshot = parent_state(baseline)
        snapshot['owned_morties'][1]['player_id'] = 'player-1'
        with self.assertRaises(ValueError):
            compare_snapshot(baseline, snapshot, 'rejected', previous)

    def test_all_other_state_preserved(self):
        baseline = fixture()
        previous = {'stage': 'offer', 'snapshot': offer_state(baseline)}
        mutations = [lambda s: s['owned_attacks'][0].update(pp=11),
                     lambda s: s['owned_items'][0].update(quantity=3),
                     lambda s: s['users'][0].update(coupons=2),
                     lambda s: s['users'][1].update(coins=11),
                     lambda s: s['users'][0].update(expiry_trade='changed'),
                     lambda s: s['friend_list'][0].update(player_id_a='other'),
                     lambda s: s['decks'][0].update(owned_morty_ids='[]'),
                     lambda s: s['friend_battle_memberships'].append({'player_id': 'player-0'}),
                     lambda s: s.update(unexpected_table=[]),
                     lambda s: s['completed_trades'][0].update(trade_offer_id='other'),
                     lambda s: s['event_queue'].append({'id': 1, 'event_name': 'battle:start'})]
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                snapshot = accepted_state(baseline)
                mutation(snapshot)
                with self.assertRaises(ValueError):
                    compare_snapshot(baseline, snapshot, 'accepted', previous)

    def test_dynamic_user_and_controlled_presence_reported(self):
        baseline = fixture()
        snapshot = parent_state(baseline)
        snapshot['users'][0].update(session_id='new-session', last_seen='new-time', room_id=22)
        snapshot['event_queue'] = [{'id': 1, 'event_name': 'room:user-added', 'player_id': 'player-0',
                                   'room_id': 22, 'state': 'WORLD', 'zone_id': '[1,1]',
                                   'shiny_if_potion': 0, 'battle_start': None,
                                   'updated': '2026-11-06 12:00:00'}]
        report = compare_snapshot(baseline, snapshot, 'parent')
        self.assertEqual(report['user_dynamic_columns_changed']['PMTrade01'], ['last_seen', 'room_id', 'session_id'])
        self.assertEqual(report['presence_event_counts'], [0, 1])
        snapshot['event_queue'][0]['battle_start'] = '{}'
        with self.assertRaises(ValueError):
            compare_snapshot(baseline, snapshot, 'parent')

    def test_foreign_or_extra_listings_and_wrong_roles_rejected(self):
        baseline = fixture()
        for mutation in (lambda s: s['trades'][0].update(player_id='player-0'),
                         lambda s: s['trades'][0].update(morty_trade_id='morty-1-0'),
                         lambda s: s['trades'].append(dict(s['trades'][0], id=2)),
                         lambda s: s['trade_offers'][0].update(player_id='other'),
                         lambda s: s['trade_offers'].append(dict(s['trade_offers'][0], id=2))):
            snapshot = offer_state(baseline)
            mutation(snapshot)
            with self.assertRaises(ValueError):
                compare_snapshot(baseline, snapshot, 'offer', {'stage': 'parent', 'snapshot': parent_state(baseline)})

    def test_expiry_change_is_one_hour_only_and_retained(self):
        baseline = fixture()
        snapshot = parent_state(baseline)
        snapshot['users'][1]['expiry_trade'] = '2026-11-06T14:00:00.000Z'
        with self.assertRaises(ValueError):
            compare_snapshot(baseline, snapshot, 'parent')
        snapshot = accepted_state(baseline)
        snapshot['users'][1]['expiry_trade'] = None
        with self.assertRaises(ValueError):
            compare_snapshot(baseline, snapshot, 'accepted', {'stage': 'offer', 'snapshot': offer_state(baseline)})

    def test_no_accept_without_observed_offer_or_unexpected_transition(self):
        baseline = fixture()
        with self.assertRaises(ValueError):
            compare_snapshot(baseline, accepted_state(baseline), 'accepted')
        with self.assertRaises(ValueError):
            compare_snapshot(baseline, baseline['snapshot'], 'initial',
                             {'stage': 'offer', 'snapshot': offer_state(baseline)})

    def test_row_order_does_not_change_physical_identity(self):
        baseline = fixture()
        snapshot = accepted_state(baseline)
        snapshot['owned_morties'].reverse()
        snapshot['owned_attacks'].reverse()
        snapshot['users'].reverse()
        compare_snapshot(baseline, snapshot, 'accepted', {'stage': 'offer', 'snapshot': offer_state(baseline)})

    def missed_decision_history(self):
        baseline = fixture()
        baseline_hash = 'a' * 64
        entries, previous, prior_hash = [], None, baseline_hash
        for sequence, (stage, snapshot, failed) in enumerate([
                ('parent', parent_state(baseline), False),
                ('offer', offer_state(baseline), False),
                ('rejected', offer_state(baseline), True)], 1):
            document = {'version': 1, 'accounts': baseline['accounts'], 'private': True, 'action': 'observe',
                        'identity': baseline['identity'], 'stage': stage, 'label': f'capture-{sequence}',
                        'sequence': sequence, 'baseline_sha256': baseline_hash, 'previous_sha256': prior_hash,
                        'snapshot': snapshot, 'comparison': {'passed': False, 'private_details_suppressed': True}
                        if failed else compare_snapshot(baseline, snapshot, stage, previous)}
            prior_hash = hashlib.sha256(json.dumps(document, sort_keys=True).encode()).hexdigest()
            entries.append({'document': document, 'sha256': prior_hash})
            if not failed:
                previous = document
        return baseline, baseline_hash, entries

    def test_offline_resume_preserves_failed_sequence_hash_and_logical_offer(self):
        baseline, baseline_hash, entries = self.missed_decision_history()
        with self.assertRaises(ValueError):
            verify_history(baseline, baseline_hash, entries)
        state = verify_history(baseline, baseline_hash, entries, resumable_label='capture-3')
        self.assertEqual(state['last_sequence'], 3)
        self.assertEqual(state['previous']['sequence'], 2)
        self.assertEqual(state['previous_sha256'], entries[-1]['sha256'])
        resumption = dict(state['pending_resumption'], created_utc='2026-11-06T12:01:00+00:00')
        resumptions = {'capture-3': {'document': resumption, 'sha256': 'b' * 64}}
        snapshot = parent_state(baseline)
        document = dict(entries[-1]['document'], label='actual-rejection', sequence=4,
                        previous_sha256=entries[-1]['sha256'], snapshot=snapshot,
                        comparison=compare_snapshot(baseline, snapshot, 'rejected', state['previous']))
        entries.append({'document': document, 'sha256': 'c' * 64})
        verified = verify_history(baseline, baseline_hash, entries, resumptions)
        self.assertEqual(verified['previous']['stage'], 'rejected')
        self.assertEqual(verified['last_sequence'], 4)
        self.assertEqual(verified['failed_observations'], [{'label': 'capture-3', 'sequence': 3,
                          'sha256': resumption['failed_sha256'], 'resumption_sha256': 'b' * 64}])

    def test_offline_resume_rejects_hidden_protected_mutations(self):
        for mutate in (lambda s: s['owned_morties'][0].update(hp=19),
                       lambda s: s['owned_morties'][1].update(player_id='player-1'),
                       lambda s: s['users'][0].update(coins=22),
                       lambda s: s['decks'][0].update(owned_morty_ids='[]'),
                       lambda s: s['trade_offers'][0].update(trade_offer_id='different-offer')):
            baseline, baseline_hash, entries = self.missed_decision_history()
            mutate(entries[-1]['document']['snapshot'])
            with self.assertRaises(ValueError):
                verify_history(baseline, baseline_hash, entries, resumable_label='capture-3')

    def test_offline_resume_rejects_forged_failure_and_history_links(self):
        baseline, baseline_hash, entries = self.missed_decision_history()
        state = verify_history(baseline, baseline_hash, entries, resumable_label='capture-3')
        resumption = dict(state['pending_resumption'], created_utc='2026-11-06T12:01:00+00:00')
        for field, value in (('failed_sha256', 'd' * 64), ('failed_sequence', 2),
                             ('previous_successful_sha256', 'd' * 64), ('resume_stage', 'accepted')):
            bad = dict(resumption, **{field: value})
            with self.assertRaises(ValueError):
                verify_history(baseline, baseline_hash, entries,
                               {'capture-3': {'document': bad, 'sha256': 'b' * 64}})
        tampered = copy.deepcopy(entries)
        tampered[-1]['document']['previous_sha256'] = baseline_hash
        with self.assertRaises(ValueError):
            verify_history(baseline, baseline_hash, tampered, resumable_label='capture-3')
        tampered = copy.deepcopy(entries)
        tampered[-1]['document']['snapshot'] = parent_state(baseline)
        with self.assertRaises(ValueError):
            verify_history(baseline, baseline_hash, tampered, resumable_label='capture-3')
        with self.assertRaises(ValueError):
            verify_history(baseline, baseline_hash, entries, resumable_label='capture-2')


if __name__ == '__main__':
    unittest.main()

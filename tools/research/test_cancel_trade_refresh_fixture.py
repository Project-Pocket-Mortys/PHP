"""Pure cancellation observer checks; no database, device, or network access."""
import copy
import unittest

from test_live_trade_refresh_fixture import fixture as live_fixture, accepted_state_new
from cancel_trade_refresh_fixture import compare_snapshot, pair_anchor, validate_baseline, verify_history


def fixture():
    snapshot = accepted_state_new(live_fixture())
    snapshot['trade_refresh_notifications'][0].update(revision='3', event_name='trade:offer-accepted')
    snapshot['trade_refresh_notifications'][1].update(revision='2', event_name='trade:offer-submit')
    snapshot['users'][0]['expiry_trade'] = '2026-11-06T13:00:00.000Z'
    source = {'private': True, 'snapshot': copy.deepcopy(snapshot),
              'comparison': {'passed': True, 'stage': 'accepted', 'exact_spare_swap': True,
                             'existing_completion_preserved': True, 'protected_raw_rows_preserved': True}}
    return {'version': 1, 'accounts': ['PMTrade01', 'PMTrade02'], 'private': True,
            'action': 'snapshot', 'snapshot': snapshot, 'identity': pair_anchor(snapshot),
            'accepted_anchor': {'sha256': 'a' * 64, 'document': source}}


def states(baseline):
    parent = copy.deepcopy(baseline['snapshot'])
    parent['trades'] = [{'id': 3, 'trade_id': 'parent-3', 'player_id': 'player-0',
                        'morty_trade_id': 'morty-0-1', 'requested_morty_id': 'any',
                        'request_variant': 'Normal', 'is_free_trade': 1,
                        'created_at': '2026-11-07 12:00:00'}]
    parent['users'][0]['expiry_trade'] = '2026-11-07T13:00:00.000Z'
    offer = copy.deepcopy(parent)
    offer['trade_offers'] = [{'id': 3, 'trade_offer_id': 'offer-3', 'trade_id': 'parent-3',
                             'player_id': 'player-1', 'morty_offer_id': 'morty-1-1'}]
    offer['trade_refresh_notifications'][0].update(revision='4', event_name='trade:offer-submit')
    cancelled = copy.deepcopy(offer)
    cancelled['trade_offers'] = []
    cancelled['trade_refresh_notifications'][0]['revision'] = '5'
    second = copy.deepcopy(cancelled)
    second['users'][1].update(session_id='peer-cold-login', room_id=22, last_seen='later')
    second['trade_offers'] = [dict(offer['trade_offers'][0], id=4, trade_offer_id='offer-4')]
    second['trade_refresh_notifications'][0]['revision'] = '6'
    final = copy.deepcopy(second)
    final['trades'], final['trade_offers'] = [], []
    final['trade_refresh_notifications'][1].update(revision='3', event_name='trade:offer-rejected')
    return [('parent', parent), ('offer', offer), ('offer-cancelled', cancelled),
            ('offer', second), ('parent-cancelled', final)]


class CancelTradeRefreshFixtureTests(unittest.TestCase):
    def test_fixed_accepted_anchor_and_reversed_roles(self):
        baseline = fixture()
        anchor = validate_baseline(baseline)
        self.assertEqual(anchor['roles'], {'requester': 'PMTrade01', 'offerer': 'PMTrade02'})
        self.assertEqual(anchor['accounts']['PMTrade01']['spare_owned_morty_id'], 'morty-0-1')
        self.assertEqual(anchor['accounts']['PMTrade02']['spare_owned_morty_id'], 'morty-1-1')

    def test_complete_native_cancellation_cycle_with_peer_cold_login(self):
        baseline = fixture()
        previous, publications = None, []
        for stage, snapshot in states(baseline):
            report = compare_snapshot(baseline, snapshot, stage, previous)
            self.assertTrue(report['ownership_unchanged'])
            self.assertTrue(report['both_existing_completions_preserved'])
            publications.append(report['notification'])
            previous = {'stage': stage, 'snapshot': snapshot}
        self.assertEqual([p['revision'] for p in publications if p], ['4', '5', '6', '3'])
        self.assertEqual(publications[2]['event_name'], 'trade:offer-submit')
        self.assertEqual(publications[4]['event_name'], 'trade:offer-rejected')
        self.assertEqual(publications[2]['actor'], 'player-1')
        self.assertEqual(publications[4]['actor'], 'player-0')
        self.assertIsNone(compare_snapshot(baseline, previous['snapshot'], 'parent-cancelled', previous)['notification'])

    def test_baseline_rejects_resets_and_anchor_drift(self):
        changes = [lambda b: b['snapshot']['completed_trades'].pop(),
                   lambda b: b['snapshot']['owned_morties'][1].update(player_id='player-1'),
                   lambda b: b['snapshot']['users'][0].update(expiry_trade=None),
                   lambda b: b['snapshot']['trade_refresh_notifications'][0].update(revision='2'),
                   lambda b: b['accepted_anchor']['document']['comparison'].update(existing_completion_preserved=False),
                   lambda b: b['accepted_anchor']['document']['snapshot']['completed_trades'].pop()]
        for change in changes:
            baseline = fixture()
            change(baseline)
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_baseline(baseline)

    def test_each_notification_is_exact_recipient_only(self):
        baseline = fixture()
        chain = states(baseline)
        for index in range(1, len(chain)):
            stage, snapshot = chain[index]
            prior_stage, prior = chain[index - 1]
            recipient = 1 if stage == 'parent-cancelled' else 0
            actor = 1 - recipient
            changes = [lambda s: s['trade_refresh_notifications'].pop(recipient),
                       lambda s: s['trade_refresh_notifications'][actor].update(revision='9'),
                       lambda s: s['trade_refresh_notifications'][recipient].update(revision='99'),
                       lambda s: s['trade_refresh_notifications'][recipient].update(revision=4),
                       lambda s: s['trade_refresh_notifications'][recipient].update(event_name='trade:offer-accepted'),
                       lambda s: s['trade_refresh_notifications'].append(dict(s['trade_refresh_notifications'][recipient]))]
            for change in changes:
                mutated = copy.deepcopy(snapshot)
                change(mutated)
                with self.subTest(stage=stage, change=change), self.assertRaises(ValueError):
                    compare_snapshot(baseline, mutated, stage, {'stage': prior_stage, 'snapshot': prior})

    def test_all_protected_rows_never_change_at_any_stage(self):
        baseline = fixture()
        changes = [lambda s: s['owned_morties'][1].update(player_id='player-1'),
                   lambda s: s['owned_morties'][0].update(hp=19),
                   lambda s: s['owned_morties'][1].update(is_trading_locked='true'),
                   lambda s: s['owned_attacks'][0].update(pp=11),
                   lambda s: s['owned_items'][0].update(quantity=1),
                   lambda s: s['decks'][0].update(owned_morty_ids='[]'),
                   lambda s: s['friend_list'][0].update(player_id_a='other'),
                   lambda s: s['users'][0].update(coins=11),
                   lambda s: s['users'][1].update(coupons=0),
                   lambda s: s['completed_trades'][0].update(trade_offer_id='other'),
                   lambda s: s['completed_trades'].pop(),
                   lambda s: s['friend_battle_memberships'].append({'id': 1}),
                   lambda s: s['event_queue'].append({'id': 3, 'event_name': 'battle:start'}),
                   lambda s: s.update(unexpected=[])]
        previous = None
        for stage, snapshot in states(baseline):
            for change in changes:
                mutated = copy.deepcopy(snapshot)
                change(mutated)
                with self.subTest(stage=stage, change=change), self.assertRaises(ValueError):
                    compare_snapshot(baseline, mutated, stage, previous)
            previous = {'stage': stage, 'snapshot': snapshot}

    def test_expiry_natural_expiration_one_hour_and_retention(self):
        baseline = fixture()
        parent = states(baseline)[0][1]
        for account, value in [(0, '2026-11-07T14:00:00.000Z'), (1, None)]:
            mutated = copy.deepcopy(parent)
            mutated['users'][account]['expiry_trade'] = value
            with self.assertRaises(ValueError):
                compare_snapshot(baseline, mutated, 'parent')
        future = fixture()
        for s in (future['snapshot'], future['accepted_anchor']['document']['snapshot']):
            s['users'][0]['expiry_trade'] = '2026-11-07T14:00:00.000Z'
        with self.assertRaises(ValueError):
            compare_snapshot(future, states(future)[0][1], 'parent')
        chain = states(baseline)
        for index in range(1, len(chain)):
            stage, snapshot = copy.deepcopy(chain[index])
            snapshot['users'][0]['expiry_trade'] = None
            with self.assertRaises(ValueError):
                compare_snapshot(baseline, snapshot, stage,
                                 {'stage': chain[index - 1][0], 'snapshot': chain[index - 1][1]})

    def test_parent_and_offer_links_roles_and_removals(self):
        baseline = fixture()
        chain = states(baseline)
        for change in [lambda s: s['trades'][0].update(player_id='player-1'),
                       lambda s: s['trades'][0].update(morty_trade_id='morty-0-0'),
                       lambda s: s['trades'][0].update(is_free_trade=True),
                       lambda s: s['trade_offers'][0].update(player_id='player-0'),
                       lambda s: s['trade_offers'][0].update(morty_offer_id='morty-1-0'),
                       lambda s: s['trade_offers'][0].update(trade_id='other'),
                       lambda s: s['trade_offers'].append(dict(s['trade_offers'][0], id=9))]:
            snapshot = copy.deepcopy(chain[1][1])
            change(snapshot)
            with self.subTest(change=change), self.assertRaises(ValueError):
                compare_snapshot(baseline, snapshot, 'offer', {'stage': 'parent', 'snapshot': chain[0][1]})
        for index, table in [(2, 'trade_offers'), (4, 'trades'), (4, 'trade_offers')]:
            stage, snapshot = copy.deepcopy(chain[index])
            snapshot[table] = copy.deepcopy(chain[index - 1][1][table])
            with self.assertRaises(ValueError):
                compare_snapshot(baseline, snapshot, stage,
                                 {'stage': chain[index - 1][0], 'snapshot': chain[index - 1][1]})

    def test_only_bounded_presence_and_session_dynamics_allowed(self):
        baseline = fixture()
        snapshot = states(baseline)[0][1]
        snapshot['users'][1].update(session_id='cold-login', room_id=22, last_seen='later')
        snapshot['event_queue'] = [{'id': 7, 'event_name': 'room:user-added', 'player_id': 'player-1',
                                    'room_id': 22, 'zone_id': '[1,1]', 'battle_start': None}]
        compare_snapshot(baseline, snapshot, 'parent')
        snapshot['event_queue'][0]['battle_start'] = '{}'
        with self.assertRaises(ValueError):
            compare_snapshot(baseline, snapshot, 'parent')

    def test_append_only_chain_rejects_failures_forgery_and_terminal_restart(self):
        baseline = fixture()
        previous, prior_hash, entries = None, 'b' * 64, []
        for sequence, (stage, snapshot) in enumerate(states(baseline), 1):
            d = {'version': 1, 'accounts': baseline['accounts'], 'private': True, 'action': 'observe',
                 'identity': baseline['identity'], 'sequence': sequence, 'label': f'step-{sequence}',
                 'baseline_sha256': 'b' * 64, 'previous_sha256': prior_hash, 'snapshot': snapshot,
                 'stage': stage, 'comparison': compare_snapshot(baseline, snapshot, stage, previous)}
            prior_hash = str(sequence) * 64
            entries.append({'document': d, 'sha256': prior_hash})
            previous = d
        self.assertEqual(verify_history(baseline, 'b' * 64, entries)[0]['stage'], 'parent-cancelled')
        for change in [lambda e: e[1]['document'].update(previous_sha256='x' * 64),
                       lambda e: e[1]['document'].update(sequence=3),
                       lambda e: e[1]['document'].update(label='step-1'),
                       lambda e: e[1]['document'].update(comparison={'passed': False}),
                       lambda e: e[-1]['document']['comparison'].update(ownership_unchanged=False)]:
            mutated = copy.deepcopy(entries)
            change(mutated)
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_history(baseline, 'b' * 64, mutated)
        with self.assertRaises(ValueError):
            compare_snapshot(baseline, states(baseline)[0][1], 'parent', previous)


if __name__ == '__main__':
    unittest.main()

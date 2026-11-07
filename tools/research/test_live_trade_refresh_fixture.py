"""Pure live-refresh observer tests: never connects to a database or device."""
import copy
import unittest

from test_native_trade_decision_fixture import fixture as old_fixture, accepted_state
from live_trade_refresh_fixture import (compare_snapshot, pair_anchor, validate_baseline,
                                        verify_history)


def fixture():
    snapshot = accepted_state(old_fixture())
    source = {'private': True, 'snapshot': copy.deepcopy(snapshot),
              'comparison': {'passed': True, 'stage': 'accepted',
                             'exact_spare_swap': True, 'protected_raw_rows_preserved': True}}
    snapshot['trade_refresh_notifications'] = [{'player_id': 'player-0', 'revision': '1',
                                               'event_name': 'trade:offer-submit'}]
    return {'version': 1, 'accounts': ['PMTrade01', 'PMTrade02'], 'private': True,
            'action': 'snapshot', 'snapshot': snapshot, 'identity': pair_anchor(snapshot),
            'accepted_anchor': {'sha256': 'a' * 64, 'document': source}}


def parent_state(baseline):
    s = copy.deepcopy(baseline['snapshot'])
    s['trades'] = [{'id': 2, 'trade_id': 'parent-2', 'player_id': 'player-1',
                    'morty_trade_id': 'morty-0-1', 'requested_morty_id': 'any',
                    'request_variant': 'Normal', 'is_free_trade': 1,
                    'created_at': '2026-11-07 12:00:00'}]
    s['users'][1]['expiry_trade'] = '2026-11-07T13:00:00.000Z'
    return s


def offer_state(baseline):
    s = parent_state(baseline)
    s['trade_offers'] = [{'id': 2, 'trade_offer_id': 'offer-2', 'trade_id': 'parent-2',
                         'player_id': 'player-0', 'morty_offer_id': 'morty-1-1'}]
    s['trade_refresh_notifications'].append({'player_id': 'player-1', 'revision': '1',
                                            'event_name': 'trade:offer-submit'})
    return s


def rejected_state(baseline):
    s = offer_state(baseline)
    s['trade_offers'] = []
    s['trade_refresh_notifications'][0].update(revision='2', event_name='trade:offer-rejected')
    return s


def accepted_state_new(baseline):
    s = offer_state(baseline)
    s['trades'], s['trade_offers'] = [], []
    s['owned_morties'][1]['player_id'] = 'player-0'
    s['owned_morties'][3]['player_id'] = 'player-1'
    s['completed_trades'].append({'id': 2, 'completed_trade_id': 'completion-2',
        'request_player_id': 'player-1', 'offer_player_id': 'player-0',
        'morty_request_id': 'morty-0-1', 'morty_offer_id': 'morty-1-1',
        'trade_request_id': 'parent-2', 'trade_offer_id': 'offer-2', 'is_free_trade': 1,
        'fulfilled_at': '2026-11-07 12:10:00'})
    s['trade_refresh_notifications'][0].update(revision='2', event_name='trade:offer-accepted')
    return s


class LiveTradeRefreshFixtureTests(unittest.TestCase):
    def test_baseline_uses_current_spares_after_previous_swap(self):
        baseline = fixture()
        anchor = validate_baseline(baseline)
        self.assertEqual(anchor['accounts']['PMTrade01']['spare_owned_morty_id'], 'morty-1-1')
        self.assertEqual(anchor['accounts']['PMTrade02']['spare_owned_morty_id'], 'morty-0-1')

    def test_anchor_rejects_reset_or_protected_drift(self):
        for change in (lambda s: s['completed_trades'].clear(),
                       lambda s: s['owned_morties'][1].update(player_id='player-0'),
                       lambda s: s['users'][0].update(coins=11),
                       lambda s: s['users'][1].update(expiry_trade=None),
                       lambda s: s['owned_attacks'][0].update(pp=11),
                       lambda s: s['decks'][0].update(owned_morty_ids='[]'),
                       lambda s: s['trade_refresh_notifications'][0].update(revision='2')):
            baseline = fixture()
            change(baseline['snapshot'])
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate_baseline(baseline)

    def test_parent_offer_reject_preserve_old_completion_and_actor_notification(self):
        baseline = fixture()
        previous = None
        for stage, s in [('parent', parent_state(baseline)), ('offer', offer_state(baseline)),
                         ('offer', offer_state(baseline)), ('rejected', rejected_state(baseline)),
                         ('rejected', rejected_state(baseline))]:
            report = compare_snapshot(baseline, s, stage, previous)
            self.assertTrue(report['passed'])
            previous = {'stage': stage, 'snapshot': s}

    def test_second_offer_increments_peer_and_accept_swaps_exact_current_spares(self):
        baseline = fixture()
        p = {'stage': 'parent', 'snapshot': parent_state(baseline)}
        offer = offer_state(baseline)
        compare_snapshot(baseline, offer, 'offer', p)
        rejected = rejected_state(baseline)
        compare_snapshot(baseline, rejected, 'rejected', {'stage': 'offer', 'snapshot': offer})
        second = offer_state(baseline)
        second['trade_offers'][0].update(id=3, trade_offer_id='offer-3')
        second['trade_refresh_notifications'] = copy.deepcopy(rejected['trade_refresh_notifications'])
        second['trade_refresh_notifications'][1]['revision'] = '2'
        compare_snapshot(baseline, second, 'offer', {'stage': 'rejected', 'snapshot': rejected})
        accepted = accepted_state_new(baseline)
        accepted['completed_trades'][1]['trade_offer_id'] = 'offer-3'
        accepted['trade_refresh_notifications'][0]['revision'] = '3'
        accepted['trade_refresh_notifications'][1]['revision'] = '2'
        report = compare_snapshot(baseline, accepted, 'accepted', {'stage': 'offer', 'snapshot': second})
        self.assertTrue(report['exact_spare_swap'])
        self.assertEqual(report['notification']['previous_revision'], '2')

    def test_notification_delta_rejects_missing_duplicate_actor_wrong_event_and_skips(self):
        baseline = fixture()
        for change in (lambda s: s['trade_refresh_notifications'].pop(),
                       lambda s: s['trade_refresh_notifications'][0].update(revision='2'),
                       lambda s: s['trade_refresh_notifications'][1].update(event_name='trade:offer-accepted'),
                       lambda s: s['trade_refresh_notifications'][1].update(revision='2'),
                       lambda s: s['trade_refresh_notifications'][1].update(revision=1),
                       lambda s: s['trade_refresh_notifications'].append(dict(s['trade_refresh_notifications'][1]))):
            s = offer_state(baseline)
            change(s)
            with self.subTest(change=change), self.assertRaises(ValueError):
                compare_snapshot(baseline, s, 'offer', {'stage': 'parent', 'snapshot': parent_state(baseline)})

    def test_protected_rows_and_existing_completion_never_change(self):
        baseline = fixture()
        for change in (lambda s: s['completed_trades'][0].update(trade_offer_id='other'),
                       lambda s: s['owned_morties'][0].update(hp=19),
                       lambda s: s['owned_morties'][1].update(is_trading_locked='true'),
                       lambda s: s['owned_items'][0].update(quantity=3),
                       lambda s: s['friend_list'][0].update(player_id_a='other'),
                       lambda s: s['users'][0].update(coupons=0),
                       lambda s: s['users'][1].update(expiry_trade=None)):
            s = accepted_state_new(baseline)
            change(s)
            with self.subTest(change=change), self.assertRaises(ValueError):
                compare_snapshot(baseline, s, 'accepted', {'stage': 'offer', 'snapshot': offer_state(baseline)})

    def test_only_controlled_presence_and_session_changes_are_permitted(self):
        baseline = fixture()
        s = parent_state(baseline)
        s['users'][0].update(session_id='new', room_id=22, last_seen='now')
        s['event_queue'] = [{'id': 7, 'event_name': 'room:user-added', 'player_id': 'player-0',
                             'room_id': 22, 'zone_id': '[1,1]', 'battle_start': None}]
        compare_snapshot(baseline, s, 'parent')
        s['event_queue'][0]['battle_start'] = '{}'
        with self.assertRaises(ValueError):
            compare_snapshot(baseline, s, 'parent')

    def test_history_links_labels_and_failures_are_fail_closed(self):
        baseline = fixture()
        previous, previous_hash, entries = None, 'b' * 64, []
        for sequence, (stage, s) in enumerate([('parent', parent_state(baseline)),
                ('offer', offer_state(baseline)), ('rejected', rejected_state(baseline))], 1):
            d = {'version': 1, 'accounts': baseline['accounts'], 'private': True, 'action': 'observe',
                 'identity': baseline['identity'], 'sequence': sequence, 'label': f'step-{sequence}',
                 'baseline_sha256': 'b' * 64, 'previous_sha256': previous_hash,
                 'snapshot': s, 'stage': stage, 'comparison': compare_snapshot(baseline, s, stage, previous)}
            previous_hash = str(sequence) * 64
            entries.append({'document': d, 'sha256': previous_hash})
            previous = d
        self.assertEqual(verify_history(baseline, 'b' * 64, entries)[0]['stage'], 'rejected')
        for change in (lambda e: e[1]['document'].update(previous_sha256='x' * 64),
                       lambda e: e[1]['document'].update(sequence=3),
                       lambda e: e[1]['document'].update(label='step-1'),
                       lambda e: e[1]['document'].update(comparison={'passed': False})):
            bad = copy.deepcopy(entries)
            change(bad)
            with self.subTest(change=change), self.assertRaises(ValueError):
                verify_history(baseline, 'b' * 64, bad)


if __name__ == '__main__':
    unittest.main()

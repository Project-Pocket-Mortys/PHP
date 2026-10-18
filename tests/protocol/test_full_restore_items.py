"""Full revive/AP restore contracts using disposable, account-local fixtures."""
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
import uuid

import test_use_item as use_item
from test_http import post, sql


REVIVE = 'ItemPureHalzinger'
ROCK = 'ItemPurePlutonicRock'
# Pinned MP AttackInfo maxima; persisted pp_stat may be stale.
ATTACK_MAX_AP = {'AttackLick': 18, 'AttackFlail': 10, 'AttackOutburst': 12}


class FullRestoreItemTests(unittest.TestCase):
    def setUp(self):
        # Compose the fixture helper so its healing tests are not inherited/run again.
        self.fixture = use_item.UseItemTests()
        self.addCleanup(lambda: self.assertTrue(self.fixture.doCleanups(),
                                                'Disposable item fixture cleanup failed'))
        self.fixture.setUp()
        self.player = self.fixture.players[0]
        self.morty = self.fixture.morties[0]
        sql(f"UPDATE owned_attacks SET pp_stat=18 WHERE owned_morty_id='{self.morty}' AND attack_id='AttackLick'")
        for item in (REVIVE, ROCK):
            sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.player}','{item}',1)")

    def request(self, item, **overrides):
        return self.fixture.request(item_id=item, **overrides)

    def assert_success(self, response, item, hp, quantity=0):
        status, body = response
        self.assertEqual(status, 200, body)
        self.assertEqual(set(body), {'owned_morty_id', 'item_id', 'is_success', 'effect_value',
                                     'owned_morties', 'owned_items', 'attacks_to_learn'})
        self.assertEqual(body['owned_morty_id'], self.morty)
        self.assertEqual(body['item_id'], item)
        self.assertIs(body['is_success'], True)
        self.assertEqual(body['effect_value'], 100)
        self.assertIs(type(body['effect_value']), int)
        self.assertEqual(body['attacks_to_learn'], [])
        self.assertEqual(body['owned_items'], [{'item_id': item, 'quantity': quantity}])
        self.assertIs(type(body['owned_items'][0]['quantity']), int)
        details_status, details = post('/session/player-details', {'session_id': self.player})
        self.assertEqual(details_status, 200)
        morty = next(m for m in details['owned_morties'] if m['owned_morty_id'] == self.morty)
        self.assertEqual(body['owned_morties'], [morty])
        self.assertEqual(morty['hp'], hp)
        return body

    def assert_failure_unchanged(self, item, **overrides):
        before = self.fixture.snapshot()
        self.fixture.assert_failed(self.request(item, **overrides))
        self.assertEqual(self.fixture.snapshot(), before)

    def expected_change(self, before, item, hp=None, restore_ap=False):
        if hp is not None:
            next(m for m in before['morties'] if m['owned_morty_id'] == self.morty)['hp'] = hp
        if restore_ap:
            for attack in before['attacks']:
                if attack['owned_morty_id'] == self.morty:
                    attack['pp'] = ATTACK_MAX_AP[attack['attack_id']]
                    attack['pp_stat'] = ATTACK_MAX_AP[attack['attack_id']]
        next(i for i in before['items'] if i['player_id'] == self.player and i['item_id'] == item)['quantity'] -= 1
        return before

    def test_revive_restores_full_hp_preserves_ap_and_retains_zero_item_row(self):
        sql(f"UPDATE owned_morties SET hp=0,hp_stat=537 WHERE owned_morty_id='{self.morty}'")
        before = self.fixture.snapshot()
        self.assert_success(self.request(REVIVE), REVIVE, 537)
        self.assertEqual(self.fixture.snapshot(), self.expected_change(before, REVIVE, hp=537))
        self.assert_failure_unchanged(REVIVE)

    def test_revive_requires_fainted_target_and_positive_maximum(self):
        for hp, maximum in ((1, 100), (100, 100), (-1, 100), ('NULL', 100),
                            (0, 0), (0, -10), (0, 'NULL')):
            with self.subTest(hp=hp, maximum=maximum):
                sql(f"UPDATE owned_morties SET hp={hp},hp_stat={maximum} WHERE owned_morty_id='{self.morty}'")
                self.assert_failure_unchanged(REVIVE)

    def test_rock_restores_each_maximum_preserves_positions_hp_and_other_morties(self):
        sql(f"UPDATE owned_attacks SET position=7,pp=2 WHERE owned_morty_id='{self.morty}' AND attack_id='AttackLick'")
        sql(f"UPDATE owned_attacks SET position=2,pp=0 WHERE owned_morty_id='{self.morty}' AND attack_id='AttackFlail'")
        before = self.fixture.snapshot()
        body = self.assert_success(self.request(ROCK), ROCK, 35)
        self.assertEqual(self.fixture.snapshot(), self.expected_change(before, ROCK, restore_ap=True))
        self.assertEqual([(a['position'], a['pp'], a['pp_stat']) for a in body['owned_morties'][0]['owned_attacks']],
                         [(2, 10, 10), (7, 18, 18)])
        self.assert_failure_unchanged(ROCK)

    def test_rock_can_restore_ap_at_full_hp_with_one_attack_already_full(self):
        sql(f"UPDATE owned_morties SET hp=100 WHERE owned_morty_id='{self.morty}'")
        sql(f"UPDATE owned_attacks SET pp=pp_stat WHERE owned_morty_id='{self.morty}' AND position=0")
        before = self.fixture.snapshot()
        self.assert_success(self.request(ROCK), ROCK, 100)
        self.assertEqual(self.fixture.snapshot(), self.expected_change(before, ROCK, restore_ap=True))

    def test_rock_rejects_fainted_or_negative_hp_without_charge(self):
        for hp in (0, -1):
            with self.subTest(hp=hp):
                sql(f"UPDATE owned_morties SET hp={hp} WHERE owned_morty_id='{self.morty}'")
                self.assert_failure_unchanged(ROCK)

    def test_rock_rejects_full_ap_and_no_attacks_without_charge(self):
        sql(f"UPDATE owned_attacks SET pp=pp_stat WHERE owned_morty_id='{self.morty}'")
        self.assert_failure_unchanged(ROCK)
        # Stale metadata alone is not an AP deficit and must not spend an item.
        sql(f"UPDATE owned_attacks SET pp_stat=8 WHERE owned_morty_id='{self.morty}'")
        self.assert_failure_unchanged(ROCK)
        sql(f"DELETE FROM owned_attacks WHERE owned_morty_id='{self.morty}'")
        self.assert_failure_unchanged(ROCK)

    def test_rock_repairs_stale_null_or_negative_saved_maximum_from_client_catalog(self):
        sql(f"UPDATE owned_attacks SET attack_id='AttackOutburst' WHERE owned_morty_id='{self.morty}' AND position=1")
        for maximum in (8, 'NULL', 0, -10):
            with self.subTest(maximum=maximum):
                sql(f"UPDATE owned_items SET quantity=1 WHERE player_id='{self.player}' AND item_id='{ROCK}'")
                sql(f"UPDATE owned_attacks SET pp=2,pp_stat={maximum} WHERE owned_morty_id='{self.morty}' AND position=1")
                before = self.fixture.snapshot()
                self.assert_success(self.request(ROCK), ROCK, 35)
                self.assertEqual(self.fixture.snapshot(), self.expected_change(before, ROCK, restore_ap=True))

    def test_rock_unknown_or_unlimited_attack_fails_atomically(self):
        for attack_id in ('AttackUnknown', 'AttackStruggle'):
            with self.subTest(attack_id=attack_id):
                sql(f"UPDATE owned_attacks SET attack_id='{attack_id}' WHERE owned_morty_id='{self.morty}' AND position=1")
                self.assert_failure_unchanged(ROCK)

    def test_rock_invalid_current_ap_fails_atomically(self):
        for pp in ('NULL', -1, 11):
            with self.subTest(pp=pp):
                sql(f"UPDATE owned_attacks SET pp={pp} WHERE owned_morty_id='{self.morty}' AND position=1")
                self.assert_failure_unchanged(ROCK)

    def test_invalid_session_foreign_and_missing_morties_are_not_charged(self):
        for item in (REVIVE, ROCK):
            sql(f"UPDATE owned_morties SET hp={0 if item == REVIVE else 35} WHERE owned_morty_id='{self.morty}'")
            for override in ({'session_id': str(uuid.uuid4())},
                             {'owned_morty_id': self.fixture.morties[1]},
                             {'owned_morty_id': str(uuid.uuid4())}):
                with self.subTest(item=item, override=override):
                    self.assert_failure_unchanged(item, **override)

    def test_missing_or_zero_stock_is_not_charged(self):
        for item in (REVIVE, ROCK):
            sql(f"UPDATE owned_morties SET hp={0 if item == REVIVE else 35} WHERE owned_morty_id='{self.morty}'")
            sql(f"UPDATE owned_items SET quantity=0 WHERE player_id='{self.player}' AND item_id='{item}'")
            self.assert_failure_unchanged(item)
            sql(f"DELETE FROM owned_items WHERE player_id='{self.player}' AND item_id='{item}'")
            self.assert_failure_unchanged(item)

    def test_concurrent_requests_spend_last_item_only_once(self):
        for item in (REVIVE, ROCK):
            with self.subTest(item=item):
                hp = 0 if item == REVIVE else 35
                sql(f"UPDATE owned_morties SET hp={hp} WHERE owned_morty_id='{self.morty}'")
                before = self.fixture.snapshot()
                barrier = threading.Barrier(2)

                def use():
                    barrier.wait(timeout=5)
                    return self.request(item)

                with ThreadPoolExecutor(max_workers=2) as pool:
                    responses = list(pool.map(lambda _: use(), range(2)))
                successes = [response for response in responses if response[0] == 200]
                self.assertEqual(len(successes), 1, responses)
                self.assert_success(successes[0], item, 100 if item == REVIVE else hp)
                for response in responses:
                    if response[0] != 200:
                        self.fixture.assert_failed(response)
                self.assertEqual(self.fixture.snapshot(), self.expected_change(
                    before, item, hp=100 if item == REVIVE else None, restore_ap=item == ROCK))


if __name__ == '__main__':
    unittest.main()

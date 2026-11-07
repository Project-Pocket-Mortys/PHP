"""Native four-slot attack edits with additive UUID fixtures; never reseed."""
import unittest

import test_battle_items as battle_items
import test_mutation_morty_flags as mutation_flags
from test_http import post, sql


ROCK = 'ItemPurePlutonicRock'


class LearnAttackSlotTests(unittest.TestCase):
    def setUp(self):
        # Compose the fixture without inheriting or rediscovering its tests.
        self.f = mutation_flags.MutationMortyFlagsTests(methodName='runTest')
        self.addCleanup(lambda: self.assertTrue(self.f.doCleanups(),
                                                'Disposable mutation fixture cleanup failed'))
        self.f.setUp()
        self.addCleanup(lambda: sql(f"DELETE FROM owned_items WHERE player_id IN ('{self.f.a}','{self.f.b}')"))
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.f.a}','{ROCK}',2)")

    def snapshot(self):
        result = self.f.snapshot()
        result['items'] = sql(f"SELECT * FROM owned_items WHERE player_id IN ('{self.f.a}','{self.f.b}') ORDER BY id")
        return result

    def learn(self, slots, morty=None, extra=()):
        return post('/session/owned_morties/learn-attacks', {
            'session_id': self.f.a,
            'morty_labs': True,
            'owned_morties': [{'owned_morty_id': morty or self.f.morty,
                               'attack_ids': slots}, *extra],
        })

    def expected_replacement(self, before, attacks):
        before['attacks'] = [a for a in before['attacks']
                             if a['owned_morty_id'] != self.f.morty]
        before['attacks'].extend(dict(owned_morty_id=self.f.morty, **attack)
                                 for attack in attacks)
        before['attacks'].sort(key=lambda a: (a['owned_morty_id'], a['position']))
        return before

    def assert_learned(self, response, attacks):
        status, body = response
        self.assertEqual(status, 200, body)
        self.assertEqual((body['coins'], body['coupons'], body['permits']), (123, 4, 5))
        self.assertEqual(len(body['owned_morties']), 1)
        morty = body['owned_morties'][0]
        self.assertEqual(morty['owned_morty_id'], self.f.morty)
        self.assertEqual(morty['owned_attacks'], attacks)
        self.assertIs(morty['is_locked'], False)
        self.assertIs(morty['is_trading_locked'], False)
        self.assertIs(morty['is_poisoned'], True)
        self.assertIs(morty['is_paralysed'], False)
        status, details = post('/session/player-details', {'session_id': self.f.a})
        self.assertEqual(status, 200, details)
        self.assertEqual(morty, next(m for m in details['owned_morties']
                                     if m['owned_morty_id'] == self.f.morty))

    def assert_ignored(self, response, before):
        status, body = response
        self.assertEqual(status, 200, body)
        self.assertEqual(body['owned_morties'], [])
        self.assertEqual((body['coins'], body['coupons'], body['permits']), (123, 4, 5))
        self.assertEqual(self.snapshot(), before)

    def test_native_one_move_and_three_null_slots_persist_one_attack(self):
        before = self.snapshot()
        expected = [{'attack_id': 'AttackLick', 'position': 0, 'pp': 8, 'pp_stat': 8}]
        self.assert_learned(self.learn(['AttackLick', None, None, None]), expected)
        self.assertEqual(self.snapshot(), self.expected_replacement(before, expected))

    def test_interleaved_holes_preserve_native_positions_in_storage_and_response(self):
        before = self.snapshot()
        expected = [{'attack_id': 'AttackLick', 'position': 1, 'pp': 8, 'pp_stat': 8},
                    {'attack_id': 'AttackFlail', 'position': 3, 'pp': 8, 'pp_stat': 8}]
        self.assert_learned(self.learn([None, 'AttackLick', None, 'AttackFlail']), expected)
        self.assertEqual(self.snapshot(), self.expected_replacement(before, expected))

    def test_two_three_and_four_move_layouts_keep_each_slot(self):
        layouts = [
            (['AttackLick', 'AttackFlail', None, None], [(0, 'AttackLick'), (1, 'AttackFlail')]),
            (['AttackLick', None, 'AttackOutburst', 'AttackFlail'],
             [(0, 'AttackLick'), (2, 'AttackOutburst'), (3, 'AttackFlail')]),
            (['AttackLick', 'AttackFlail', 'AttackOutburst', 'AttackSlam'],
             [(0, 'AttackLick'), (1, 'AttackFlail'), (2, 'AttackOutburst'), (3, 'AttackSlam')]),
        ]
        for slots, positions in layouts:
            with self.subTest(slots=slots):
                before = self.snapshot()
                expected = [dict(attack_id=attack, position=position, pp=8, pp_stat=8)
                            for position, attack in positions]
                self.assert_learned(self.learn(slots), expected)
                self.assertEqual(self.snapshot(), self.expected_replacement(before, expected))

    def test_forget_then_fill_hole_keeps_later_attacks_in_their_slots(self):
        for slots, positions in (
            (['AttackLick', 'AttackFlail', 'AttackOutburst', 'AttackSlam'],
             [(0, 'AttackLick'), (1, 'AttackFlail'), (2, 'AttackOutburst'), (3, 'AttackSlam')]),
            (['AttackLick', None, 'AttackOutburst', 'AttackSlam'],
             [(0, 'AttackLick'), (2, 'AttackOutburst'), (3, 'AttackSlam')]),
            (['AttackLick', 'AttackFlail', 'AttackOutburst', 'AttackSlam'],
             [(0, 'AttackLick'), (1, 'AttackFlail'), (2, 'AttackOutburst'), (3, 'AttackSlam')]),
        ):
            with self.subTest(slots=slots):
                before = self.snapshot()
                expected = [dict(attack_id=attack, position=position, pp=8, pp_stat=8)
                            for position, attack in positions]
                self.assert_learned(self.learn(slots), expected)
                self.assertEqual(self.snapshot(), self.expected_replacement(before, expected))

    def test_rock_after_native_learn_restores_real_maxima_once_without_blank_attacks(self):
        status, body = self.learn([None, 'AttackLick', None, 'AttackFlail'])
        self.assertEqual(status, 200, body)
        before = self.snapshot()
        request = {'session_id': self.f.a, 'owned_morty_id': self.f.morty, 'item_id': ROCK}
        status, body = post('/session/use-item', request)
        # The unfixed endpoint creates blank rows, making this valid AP restore return 409.
        self.assertEqual(status, 200, body)
        expected = [{'attack_id': 'AttackLick', 'position': 1, 'pp': 18, 'pp_stat': 18},
                    {'attack_id': 'AttackFlail', 'position': 3, 'pp': 10, 'pp_stat': 10}]
        self.assertIs(body['is_success'], True)
        self.assertEqual(body['effect_value'], 100)
        self.assertEqual(body['owned_items'], [{'item_id': ROCK, 'quantity': 1}])
        self.assertEqual(body['attacks_to_learn'], [])
        self.assertEqual(body['owned_morties'][0]['owned_attacks'], expected)
        self.assertEqual(body['owned_morties'][0]['hp'], 42)
        self.expected_replacement(before, expected)
        next(i for i in before['items'] if i['item_id'] == ROCK)['quantity'] = 1
        self.assertEqual(self.snapshot(), before)
        # Stock remains, so this retry proves a no-effect request cannot charge again.
        self.assertEqual(post('/session/use-item', request), (409, {'error': {'code': 'FAILED'}}))
        self.assertEqual(self.snapshot(), before)

    def test_battle_rock_after_native_learn_restores_ap_in_original_slots(self):
        untouched = self.snapshot()
        battle = battle_items.BattleItemTests(methodName='runTest')
        self.addCleanup(lambda: self.assertTrue(battle.doCleanups(),
                                                'Disposable battle item fixture cleanup failed'))
        battle.setUp()
        status, body = post('/session/owned_morties/learn-attacks', {
            'session_id': battle.f.session,
            'morty_labs': True,
            'owned_morties': [{'owned_morty_id': battle.f.morty,
                               'attack_ids': [None, 'AttackLick', None, 'AttackFlail']}],
        })
        self.assertEqual(status, 200, body)
        learned = [{'attack_id': 'AttackLick', 'position': 1, 'pp': 8, 'pp_stat': 8},
                   {'attack_id': 'AttackFlail', 'position': 3, 'pp': 8, 'pp_stat': 8}]
        self.assertEqual(body['owned_morties'][0]['owned_attacks'], learned)
        query = (f"SELECT attack_id,position,pp,pp_stat FROM owned_attacks "
                 f"WHERE owned_morty_id='{battle.f.morty}' ORDER BY position")
        self.assertEqual(sql(query), learned)
        battle.stock(ROCK, 2)
        battle.f.begin()
        self.assertEqual(battle.item(ROCK), (200, {'success': True}))
        morty = battle.assert_item(ROCK, battle.f.morty, 100, 100, quantity=1)
        restored = [{'attack_id': 'AttackLick', 'position': 1, 'pp': 18, 'pp_stat': 18},
                    {'attack_id': 'AttackFlail', 'position': 3, 'pp': 10, 'pp_stat': 10}]
        self.assertEqual(morty['owned_attacks'], restored)
        self.assertEqual(sql(query), restored)
        self.assertEqual(self.snapshot(), untouched)

    def test_all_null_slots_ignore_entry_and_preserve_existing_attacks(self):
        before = self.snapshot()
        self.assert_ignored(self.learn([None, None, None, None]), before)

    def test_empty_attack_array_retains_existing_skip_behavior(self):
        before = self.snapshot()
        self.assert_ignored(self.learn([]), before)

    def test_four_slot_limit_does_not_compact_in_a_fifth_attack(self):
        before = self.snapshot()
        expected = [{'attack_id': 'AttackLick', 'position': 1, 'pp': 8, 'pp_stat': 8}]
        self.assert_learned(self.learn([None, 'AttackLick', None, None, 'AttackFlail']), expected)
        self.assertEqual(self.snapshot(), self.expected_replacement(before, expected))
        # An attack outside the native slots cannot turn an all-null entry into a replacement.
        before = self.snapshot()
        self.assert_ignored(self.learn([None, None, None, None, 'AttackFlail']), before)

    def test_foreign_morty_slots_cannot_replace_its_attacks(self):
        before = self.snapshot()
        self.assert_ignored(self.learn([None, 'AttackLick', None, 'AttackFlail'],
                                       morty=self.f.foreign), before)

    def test_duplicate_logical_morty_id_is_ignored_without_changing_other_attacks(self):
        sql(f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,hp,hp_stat) VALUES ('{self.f.b}','{self.f.bench}','MortyDefault',100,100)")
        before = self.snapshot()
        self.assert_ignored(self.learn([None, 'AttackLick', None, 'AttackFlail'],
                                       morty=self.f.bench), before)

    def test_mixed_batch_only_updates_target_and_preserves_flags_decks_and_resources(self):
        before = self.snapshot()
        expected = [{'attack_id': 'AttackLick', 'position': 1, 'pp': 8, 'pp_stat': 8},
                    {'attack_id': 'AttackFlail', 'position': 3, 'pp': 8, 'pp_stat': 8}]
        response = self.learn([None, 'AttackLick', None, 'AttackFlail'], extra=[
            {'owned_morty_id': self.f.foreign, 'attack_ids': ['AttackSlam', None, None, None]},
            {'owned_morty_id': self.f.bench, 'attack_ids': [None, None, None, None]},
        ])
        self.assert_learned(response, expected)
        self.assertEqual(self.snapshot(), self.expected_replacement(before, expected))


if __name__ == '__main__':
    unittest.main()

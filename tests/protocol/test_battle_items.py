"""UUID-isolated native battle ITEM regressions; never reseed shared accounts."""
import json
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

from test_http import sql
import test_battle_lifecycle


class BattleItemTests(unittest.TestCase):
    def setUp(self):
        self.f = test_battle_lifecycle.BattleLifecycleTests(methodName='runTest')
        self.f.setUp()
        self.addCleanup(lambda: self.assertTrue(self.f.doCleanups()))
        self.bench, self.storage = str(uuid.uuid4()), str(uuid.uuid4())
        self.addCleanup(lambda: sql(f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.bench}','{self.storage}')"))
        self.f.execute([
            f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat) VALUES ('{self.bench}','{self.f.player}','Morty',100,100),('{self.storage}','{self.f.player}','Morty',100,100)",
            f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{self.bench}','AttackLick',0,5,18),('{self.storage}','AttackLick',0,5,18)",
            f"UPDATE owned_attacks SET pp_stat=18 WHERE owned_morty_id='{self.f.morty}'",
            f"UPDATE decks SET owned_morty_ids='[\"{self.f.morty}\",\"{self.bench}\"]' WHERE player_id='{self.f.player}'",
        ])

    def stock(self, item='ItemSerum', quantity=1):
        sql(f"DELETE FROM owned_items WHERE player_id='{self.f.player}' AND item_id='{item}'")
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.f.player}','{item}',{quantity})")

    def hp(self, target, hp, maximum=100):
        sql(f"UPDATE owned_morties SET hp={hp},hp_stat={maximum} WHERE owned_morty_id='{target}'")

    def snapshot(self):
        result = self.f.snapshot()
        result['bench_attacks'] = sql(f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.bench}','{self.storage}') ORDER BY id")
        return result

    def item(self, item='ItemSerum', target=None, **changes):
        return self.f.move('ITEM', move_id=item, owned_morty_id=target or self.f.morty, **changes)

    def rejected(self, action, status=409):
        before = self.snapshot()
        response = action()
        self.assertEqual(response[0], status, response)
        self.assertIs(response[1]['success'], False)
        self.assertEqual(self.snapshot(), before)

    def result(self, count=1):
        events = [e for e in self.snapshot()['events'] if e['event_name'] == 'battle:turn-result']
        self.assertEqual(len(events), count)
        for event in events:
            self.assertEqual((event['room_id'], event['player_id'], event['only_show_to_player_id']),
                             (self.f.room, self.f.player, self.f.player))
        return json.loads(events[-1]['battle_turn_result'])

    def assert_item(self, item, target, effect, hp, quantity=0, count=1):
        result = self.result(count)
        action, ai = result['turn_datas']
        for key, value in dict(type='ITEM', item_id=item, owned_morty_id=target,
                               success=True, effect_value=effect).items():
            self.assertEqual(action[key], value)
        self.assertEqual(action['attacker_player_id'], self.f.player)
        self.assertEqual(action['defender_player_id'], self.snapshot()['battles'][0]['opponent_id'])
        self.assertEqual(action['defender_morty_datas'], [])
        self.assertIs(action['success'], True)
        self.assertIs(type(action['effect_value']), int)
        self.assertEqual(len(action['attacker_morty_datas']), 1)
        morty = action['attacker_morty_datas'][0]
        self.assertEqual((morty['owned_morty_id'], morty['hp']), (target, hp))
        self.assertIs(type(morty['is_poisoned']), bool)
        self.assertIs(type(morty['is_paralysed']), bool)
        self.assertEqual(result['player_datas']['player']['owned_items'], [{'item_id': item, 'quantity': quantity}])
        self.assertEqual(ai['type'], 'ATTACK')
        self.assertIn(ai['effect_datas'][0]['damage'], (1, 2, 3))
        battle = self.snapshot()['battles'][0]
        self.assertEqual(ai['effect_datas'][0]['defender_morty_datas'],
                         [{'owned_morty_id': battle['player_active_morty'], 'hp': battle['player_hp']}])
        self.assertEqual(battle['opponent_hp'], 1)
        return morty

    def test_native_active_serum(self):
        self.hp(self.f.morty, 10)
        self.stock()
        self.f.begin()
        before = self.snapshot()
        initial = next(e for e in before['events'] if e['event_name'] == 'battle:start')
        initial_player = json.loads(initial['battle_start'])['player']
        self.assertEqual(next(m for m in initial_player['owned_morties'] if m['owned_morty_id'] == self.f.morty)['hp'], 10)
        self.assertEqual(self.item(), (200, {'success': True}))
        self.assert_item('ItemSerum', self.f.morty, 20, 30)
        after = self.snapshot()
        self.assertIn(after['battles'][0]['player_hp'], (27, 28, 29))
        self.assertEqual(initial, next(e for e in after['events'] if e['event_name'] == 'battle:start'))
        self.assertEqual(before['attacks'], after['attacks'])
        self.assertEqual(next(i for i in after['items'] if i['item_id'] == 'ItemSerum')['quantity'], 0)

    def test_heal_caps_and_snapshot_precedes_ai(self):
        self.hp(self.f.morty, 95)
        self.stock()
        self.f.begin()
        self.assertEqual(self.item()[0], 200)
        self.assert_item('ItemSerum', self.f.morty, 5, 100)
        self.assertIn(self.snapshot()['battles'][0]['player_hp'], (97, 98, 99))

    def test_bench_heal_attacks_only_active_and_preserves_ap(self):
        self.hp(self.bench, 10)
        self.stock()
        self.f.begin()
        before = self.snapshot()
        self.assertEqual(self.item(target=self.bench)[0], 200)
        self.assert_item('ItemSerum', self.bench, 20, 30)
        after = self.snapshot()
        self.assertEqual(next(m for m in after['morties'] if m['owned_morty_id'] == self.bench)['hp'], 30)
        self.assertIn(after['battles'][0]['player_hp'], (97, 98, 99))
        self.assertEqual((before['attacks'], before['bench_attacks']), (after['attacks'], after['bench_attacks']))

    def test_all_supported_healing_amounts(self):
        self.f.begin()
        for item, effect in [('ItemSerum', 20), ('ItemGreatSerum', 50), ('ItemSensationalSerum', 200),
                             ('ItemPureSerum', 490), ('ItemEasterEgg', 30), ('ItemPumpkin', 30),
                             ('ItemSpicyBBQPizza', 200), ('ItemBreakfastMedley', 200)]:
            with self.subTest(item=item):
                self.hp(self.bench, 10, 500)
                self.stock(item)
                self.assertEqual(self.item(item, self.bench)[0], 200)
                count = len([e for e in self.snapshot()['events'] if e['event_name'] == 'battle:turn-result'])
                self.assert_item(item, self.bench, effect, 10 + effect, count=count)

    def test_cures_clear_only_matching_flag_and_preserve_hp_ap(self):
        self.hp(self.bench, 45)
        self.f.begin()
        for count, (item, cleared, kept) in enumerate([
                ('ItemPoisonCure', 'is_poisoned', 'is_paralysed'),
                ('ItemParalysisCure', 'is_paralysed', 'is_poisoned')], 1):
            sql(f"UPDATE owned_morties SET is_poisoned=1,is_paralysed=1 WHERE owned_morty_id='{self.bench}'")
            self.stock(item, 2)
            before = self.snapshot()['bench_attacks']
            self.assertEqual(self.item(item, self.bench)[0], 200)
            morty = self.assert_item(item, self.bench, 0, 45, quantity=1, count=count)
            self.assertFalse(morty[cleared])
            self.assertTrue(morty[kept])
            self.assertEqual(before, self.snapshot()['bench_attacks'])
            self.rejected(lambda: self.item(item, self.bench))

    def test_revived_bench_is_live_replacement_after_ai_faints_active(self):
        self.hp(self.f.morty, 1)
        self.hp(self.bench, 0)
        self.stock('ItemPureHalzinger', 2)
        self.f.begin()
        self.assertEqual(self.item('ItemPureHalzinger', self.bench)[0], 200)
        self.assert_item('ItemPureHalzinger', self.bench, 100, 100, quantity=1)
        self.assertEqual(self.result()['outcome'], 'FORCE_SWITCH')
        self.assertEqual(self.snapshot()['battles'][0]['player_hp'], 0)
        self.rejected(lambda: self.item('ItemPureHalzinger', self.bench))

    def test_ap_restores_catalog_maxima_and_preserves_attack_positions(self):
        self.stock('ItemPurePlutonicRock', 2)
        self.hp(self.bench, 45)
        sql(f"UPDATE owned_attacks SET position=7,pp=2,pp_stat=690 WHERE owned_morty_id='{self.bench}'")
        sql(f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{self.bench}','AttackOutburst',2,0,690)")
        self.f.begin()
        self.assertEqual(self.item('ItemPurePlutonicRock', self.bench)[0], 200)
        morty = self.assert_item('ItemPurePlutonicRock', self.bench, 100, 45, quantity=1)
        self.assertEqual([(a['attack_id'], a['position'], a['pp'], a['pp_stat']) for a in morty['owned_attacks']],
                         [('AttackOutburst', 2, 12, 12), ('AttackLick', 7, 18, 18)])
        self.rejected(lambda: self.item('ItemPurePlutonicRock', self.bench))

    def test_invalid_ap_identity_and_positions_are_atomic(self):
        self.stock('ItemPurePlutonicRock', 5)
        self.f.begin()
        for attack, position in [('AttackLick', 1), ('AttackOutburst', 0), ('AttackMissing', 2)]:
            with self.subTest(attack=attack, position=position):
                sql(f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{self.bench}','{attack}',{position},0,18)")
                self.rejected(lambda: self.item('ItemPurePlutonicRock', self.bench))
                sql(f"DELETE FROM owned_attacks WHERE owned_morty_id='{self.bench}' AND id=(SELECT id FROM (SELECT MAX(id) id FROM owned_attacks WHERE owned_morty_id='{self.bench}') latest)")

    def test_full_hp_living_revive_and_uncured_noops_do_not_advance_turn(self):
        self.f.begin()
        for item in ('ItemSerum', 'ItemPureHalzinger', 'ItemPoisonCure', 'ItemParalysisCure'):
            with self.subTest(item=item):
                self.stock(item)
                self.rejected(lambda: self.item(item, self.bench))

    def test_concurrent_last_item_commits_one_result_and_one_spend(self):
        self.hp(self.bench, 10)
        self.stock()
        self.f.begin()
        barrier = threading.Barrier(2)
        def request():
            barrier.wait()
            return self.item(target=self.bench)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: request(), range(2)))
        self.assertEqual(sorted(r[0] for r in responses), [200, 409])
        self.assert_item('ItemSerum', self.bench, 20, 30)
        self.assertIn(self.snapshot()['battles'][0]['player_hp'], (97, 98, 99))

    def test_repeated_effective_requests_are_distinct_turns(self):
        self.hp(self.bench, 10)
        self.stock(quantity=2)
        self.f.begin()
        for count in (1, 2):
            self.assertEqual(self.item(target=self.bench)[0], 200)
            self.assert_item('ItemSerum', self.bench, 20, 10 + 20 * count, quantity=2-count, count=count)

    def test_targets_outside_initial_party_foreign_and_changed_deck(self):
        self.hp(self.storage, 10)
        self.hp(self.f.other_morty, 10)
        self.stock(quantity=3)
        self.f.begin()
        self.rejected(lambda: self.item(target=self.f.other_morty), 403)
        self.rejected(lambda: self.item(target=self.storage), 403)
        sql(f"UPDATE decks SET owned_morty_ids='[\"{self.f.morty}\",\"{self.storage}\"]' WHERE player_id='{self.f.player}'")
        self.rejected(lambda: self.item(target=self.storage), 403)

    def test_missing_and_globally_ambiguous_party_ids_fail_closed(self):
        self.hp(self.bench, 10)
        self.stock()
        self.f.begin()
        sql(f"DELETE FROM owned_morties WHERE owned_morty_id='{self.bench}'")
        self.rejected(lambda: self.item(target=self.bench))
        sql(f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat) VALUES ('{self.bench}','{self.f.player}','Morty',10,100),('{self.bench}','{self.f.other_player}','Morty',10,100)")
        self.rejected(lambda: self.item(target=self.bench))

    def test_active_cache_mismatch_and_pending_switch_reject_items(self):
        self.hp(self.bench, 10)
        self.stock()
        self.f.begin()
        self.hp(self.f.morty, 90)
        self.rejected(lambda: self.item(target=self.bench))
        self.hp(self.f.morty, 0)
        sql(f"UPDATE battles SET player_hp=0 WHERE battle_id='{self.f.battle}'")
        self.rejected(lambda: self.item(target=self.bench))

    def test_session_room_and_closed_battle_guards_leave_everything_unchanged(self):
        self.hp(self.bench, 10)
        self.stock()
        self.f.begin()
        self.rejected(lambda: self.item(target=self.bench, session_id=str(uuid.uuid4())), 401)
        self.rejected(lambda: self.item(target=self.bench, battle_id=str(uuid.uuid4())), 404)
        sql(f"UPDATE users SET room_id='{self.f.other_room}' WHERE player_id='{self.f.player}'")
        self.rejected(lambda: self.item(target=self.bench))
        sql(f"UPDATE users SET room_id='{self.f.room}' WHERE player_id='{self.f.player}'")
        sql(f"UPDATE battles SET state='COMPLETED' WHERE battle_id='{self.f.battle}'")
        self.rejected(lambda: self.item(target=self.bench))

    def test_unsupported_and_legacy_without_roster_do_not_mutate(self):
        self.hp(self.f.morty, 10)
        self.stock()
        self.f.begin()
        for item in ('ItemMortyChip', 'ItemAttackMegaSeed', 'ItemMrMeeseeksBox'):
            self.rejected(lambda: self.item(item), 501)
        sql(f"UPDATE event_queue SET battle_start=JSON_REMOVE(battle_start,'$.player.owned_morties') WHERE event_name='battle:start' AND player_id='{self.f.player}'")
        self.rejected(lambda: self.item())
        self.rejected(lambda: self.item('ItemMortyChip'), 501)

    def test_run_after_item_and_item_after_switch_use_native_target(self):
        self.hp(self.f.morty, 10)
        self.stock(quantity=2)
        self.f.begin()
        self.assertEqual(self.f.move('SWITCH', move_id=self.bench)[0], 200)
        self.assertEqual(self.item(target=self.f.morty)[0], 200)
        self.assert_item('ItemSerum', self.f.morty, 20, 30, quantity=1, count=2)
        self.assertEqual(self.snapshot()['battles'][0]['player_active_morty'], self.bench)
        self.assertEqual(self.f.move('RUN', owned_morty_id=self.bench, move_id=None)[0], 200)
        self.assertEqual(self.result(count=3)['outcome'], 'RUN')
        self.rejected(lambda: self.item(target=self.f.morty))

    def test_missing_zero_negative_and_duplicate_stock_are_atomic(self):
        self.hp(self.bench, 10)
        self.f.begin()
        self.rejected(lambda: self.item(target=self.bench))
        for quantity in (0, -1):
            self.stock(quantity=quantity)
            self.rejected(lambda: self.item(target=self.bench))
        self.stock()
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.f.player}','ItemSerum',1)")
        self.rejected(lambda: self.item(target=self.bench))

    def test_supported_item_requires_native_string_identifiers(self):
        self.stock()
        self.f.begin()
        self.rejected(lambda: self.f.move('ITEM', owned_morty_id=None, move_id='ItemSerum'), 400)
        self.rejected(lambda: self.f.move('ITEM', owned_morty_id=self.bench, move_id=None), 400)
        self.rejected(lambda: self.f.move('ITEM', owned_morty_id=[], move_id='ItemSerum'), 400)


    def test_private_event_failure_rolls_back_item_ai_and_terminal_writes(self):
        from test_http import php
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.hp(self.f.morty, 1)
        self.hp(self.bench, 0)
        self.stock('ItemPurePlutonicRock')
        self.f.begin()
        # Fail the final private result after AP/inventory, AI damage and the
        # terminal world events have been written, only for this fresh UUID.
        trigger = 'research_battle_item_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON event_queue FOR EACH ROW "
            f"BEGIN IF NEW.player_id = '{self.f.player}' AND NEW.event_name = 'battle:turn-result' THEN "
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Research battle item fault'; END IF; END")
        try:
            self.rejected(lambda: self.item('ItemPurePlutonicRock'), 500)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')

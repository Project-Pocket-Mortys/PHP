"""Additive Full Recover regressions using disposable UUID fixtures only."""
import threading
import unittest
import uuid
from concurrent.futures import ThreadPoolExecutor

from test_http import post, sql
import test_use_item
import test_battle_items


ITEM = 'ItemFullRecover'


class FullRecoverWorldTests(unittest.TestCase):
    def setUp(self):
        self.f = test_use_item.UseItemTests(methodName='runTest')
        self.f.setUp()
        self.addCleanup(lambda: self.assertTrue(self.f.doCleanups()))
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.f.players[0]}','{ITEM}',10)")

    def configure(self, hp=35, poison=0, paralysis=0):
        sql(f"UPDATE owned_morties SET hp={hp},is_poisoned={poison},is_paralysed={paralysis} WHERE owned_morty_id='{self.f.morties[0]}'")

    def use(self, **changes):
        return self.f.request(item_id=ITEM, **changes)

    def reject(self, status=409, **changes):
        before = self.f.snapshot()
        response = self.use(**changes)
        self.assertEqual(response, (status, {'error': {'code': 'FAILED'}}))
        self.assertEqual(self.f.snapshot(), before)

    def test_damage_and_each_ailment_combination_restore_hp_and_both_flags_only(self):
        for hp, poison, paralysis in [(35, 0, 0), (35, 1, 1), (100, 1, 0), (100, 0, 1), (100, 1, 1)]:
            with self.subTest(hp=hp, poison=poison, paralysis=paralysis):
                self.configure(hp, poison, paralysis)
                before = self.f.snapshot()
                status, body = self.use()
                self.assertEqual(status, 200, body)
                self.assertEqual((body['item_id'], body['owned_morty_id']), (ITEM, self.f.morties[0]))
                self.assertIs(body['is_success'], True)
                self.assertIs(type(body['effect_value']), int)
                self.assertEqual(body['effect_value'], 0)
                self.assertEqual(body['attacks_to_learn'], [])
                expected = next(m for m in before['morties'] if m['owned_morty_id'] == self.f.morties[0])
                expected.update(hp=100, is_poisoned=0, is_paralysed=0)
                stock = next(i for i in before['items'] if i['item_id'] == ITEM)
                stock['quantity'] -= 1
                self.assertEqual(body['owned_items'], [{'item_id': ITEM, 'quantity': stock['quantity']}])
                changed = body['owned_morties'][0]
                self.assertEqual(changed['hp'], 100)
                self.assertIs(changed['is_poisoned'], False)
                self.assertIs(changed['is_paralysed'], False)
                self.assertEqual([(a['pp'], a['pp_stat']) for a in changed['owned_attacks']], [(3, 10), (0, 10)])
                _, details = post('/session/player-details', {'session_id': self.f.players[0]})
                self.assertEqual(changed, next(m for m in details['owned_morties'] if m['owned_morty_id'] == self.f.morties[0]))
                self.assertEqual(self.f.snapshot(), before)

    def test_fainted_even_with_ailments_and_full_hp_ap_deficit_are_noops(self):
        for hp, poison, paralysis in [(0, 1, 1), (0, 0, 0), (100, 0, 0)]:
            self.configure(hp, poison, paralysis)
            self.reject()

    def test_invalid_or_stale_ap_never_blocks_recovery_or_changes_attacks(self):
        sql(f"UPDATE owned_attacks SET attack_id='AttackMissing',pp=-1,pp_stat=690 WHERE owned_morty_id='{self.f.morties[0]}'")
        before = self.f.snapshot()['attacks']
        self.assertEqual(self.use()[0], 200)
        self.assertEqual(self.f.snapshot()['attacks'], before)

    def test_stock_owner_session_and_world_guards_are_atomic(self):
        self.reject(401, session_id=str(uuid.uuid4()))
        self.reject(404, owned_morty_id=self.f.morties[1])
        for quantity in (0, -1):
            sql(f"UPDATE owned_items SET quantity={quantity} WHERE player_id='{self.f.players[0]}' AND item_id='{ITEM}'")
            self.reject()
        sql(f"UPDATE owned_items SET quantity=2 WHERE player_id='{self.f.players[0]}' AND item_id='{ITEM}'")
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.f.players[0]}','{ITEM}',1)")
        self.reject()
        sql(f"DELETE FROM owned_items WHERE player_id='{self.f.players[0]}' AND item_id='{ITEM}'")
        self.reject()
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.f.players[0]}','{ITEM}',1)")
        sql(f"UPDATE users SET state='BATTLE' WHERE player_id='{self.f.players[0]}'")
        self.reject()
        sql(f"UPDATE users SET state='WORLD' WHERE player_id='{self.f.players[0]}'")
        sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,player_active_morty,state) VALUES ('{uuid.uuid4()}','{self.f.players[0]}','{self.f.players[1]}','{self.f.morties[0]}','ACTIVE')")
        self.reject()

    def test_concurrent_last_stock_spends_once(self):
        self.configure(35, 1, 1)
        sql(f"UPDATE owned_items SET quantity=1 WHERE player_id='{self.f.players[0]}' AND item_id='{ITEM}'")
        before = self.f.snapshot()['attacks']
        barrier = threading.Barrier(2)
        def request():
            barrier.wait(timeout=5)
            return self.use()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: request(), range(2)))
        self.assertEqual(sorted(r[0] for r in responses), [200, 409])
        self.assertEqual(sql(f"SELECT quantity FROM owned_items WHERE player_id='{self.f.players[0]}' AND item_id='{ITEM}'"), [{'quantity': 0}])
        self.assertEqual(self.f.snapshot()['attacks'], before)

    def test_inventory_failure_rolls_back_hp_and_both_cures(self):
        self.configure(35, 1, 1)
        trigger = 'full_recover_world_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE UPDATE ON owned_items FOR EACH ROW BEGIN IF OLD.player_id='{self.f.players[0]}' AND OLD.item_id='{ITEM}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Full Recover fault'; END IF; END")
        try:
            self.reject(500)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')


class FullRecoverBattleTests(unittest.TestCase):
    def setUp(self):
        self.f = test_battle_items.BattleItemTests(methodName='runTest')
        self.f.setUp()
        self.addCleanup(lambda: self.assertTrue(self.f.doCleanups()))
        self.f.stock(ITEM, 10)

    def configure(self, target, hp=35, poison=1, paralysis=1):
        sql(f"UPDATE owned_morties SET hp={hp},is_poisoned={poison},is_paralysed={paralysis} WHERE owned_morty_id='{target}'")

    def use(self, target=None, **changes):
        return self.f.item(ITEM, target, **changes)

    def assert_result(self, target, count=1, quantity=9):
        morty = self.f.assert_item(ITEM, target, 0, 100, quantity=quantity, count=count)
        self.assertEqual(morty, {'owned_morty_id': target, 'hp': 100, 'is_poisoned': False, 'is_paralysed': False})
        return self.f.result(count)

    def test_active_snapshot_precedes_ai_and_preserves_ap(self):
        target = self.f.f.morty
        self.configure(target)
        self.f.f.begin()
        before = self.f.snapshot()
        self.assertEqual(self.use(), (200, {'success': True}))
        self.assert_result(target)
        after = self.f.snapshot()
        self.assertIn(after['battles'][0]['player_hp'], (97, 98, 99))
        self.assertEqual(before['attacks'], after['attacks'])

    def test_bench_damage_and_full_hp_ailment_combinations_preserve_invalid_ap(self):
        self.f.f.begin()
        sql(f"UPDATE owned_attacks SET attack_id='AttackMissing',pp=-1,pp_stat=690 WHERE owned_morty_id='{self.f.bench}'")
        before = self.f.snapshot()['bench_attacks']
        for count, (hp, poison, paralysis) in enumerate([(35, 0, 0), (35, 1, 1), (100, 1, 0), (100, 0, 1), (100, 1, 1)], 1):
            self.configure(self.f.bench, hp, poison, paralysis)
            self.assertEqual(self.use(self.f.bench)[0], 200)
            self.assert_result(self.f.bench, count=count, quantity=10-count)
            self.assertEqual(self.f.snapshot()['bench_attacks'], before)

    def test_faint_and_full_hp_ap_only_noops_do_not_advance_turn(self):
        self.f.f.begin()
        for hp, poison, paralysis in [(0, 1, 1), (0, 0, 0), (100, 0, 0)]:
            self.configure(self.f.bench, hp, poison, paralysis)
            self.f.rejected(lambda: self.use(self.f.bench))

    def test_healed_survivor_allows_force_switch_after_ai_faints_active(self):
        self.configure(self.f.f.morty, 1, 0, 0)
        self.configure(self.f.bench, 1)
        self.f.f.begin()
        self.assertEqual(self.use(self.f.bench)[0], 200)
        self.assertEqual(self.assert_result(self.f.bench)['outcome'], 'FORCE_SWITCH')
        self.f.rejected(lambda: self.use(self.f.bench))

    def test_concurrent_last_stock_commits_one_turn(self):
        self.configure(self.f.bench)
        self.f.stock(ITEM)
        self.f.f.begin()
        barrier = threading.Barrier(2)
        def request():
            barrier.wait(timeout=5)
            return self.use(self.f.bench)
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: request(), range(2)))
        self.assertEqual(sorted(r[0] for r in responses), [200, 409])
        self.assert_result(self.f.bench, quantity=0)

    def test_stock_owner_session_room_and_world_battle_isolation(self):
        self.configure(self.f.bench)
        self.f.f.begin()
        self.f.rejected(lambda: self.use(self.f.f.other_morty), 403)
        self.f.rejected(lambda: self.use(self.f.storage), 403)
        self.f.rejected(lambda: self.use(self.f.bench, session_id=str(uuid.uuid4())), 401)
        sql(f"UPDATE users SET room_id='{self.f.f.other_room}' WHERE player_id='{self.f.f.player}'")
        self.f.rejected(lambda: self.use(self.f.bench))
        sql(f"UPDATE users SET room_id='{self.f.f.room}',state='WORLD' WHERE player_id='{self.f.f.player}'")
        before = self.f.snapshot()
        self.assertEqual(post('/session/use-item', dict(session_id=self.f.f.session, owned_morty_id=self.f.bench, item_id=ITEM))[0], 409)
        self.assertEqual(self.f.snapshot(), before)
        sql(f"UPDATE users SET state='BATTLE' WHERE player_id='{self.f.f.player}'")
        for quantity in (0, -1):
            self.f.stock(ITEM, quantity)
            self.f.rejected(lambda: self.use(self.f.bench))
        self.f.stock(ITEM)
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.f.f.player}','{ITEM}',1)")
        self.f.rejected(lambda: self.use(self.f.bench))
        sql(f"DELETE FROM owned_items WHERE player_id='{self.f.f.player}' AND item_id='{ITEM}'")
        self.f.rejected(lambda: self.use(self.f.bench))

    def test_private_result_failure_rolls_back_hp_flags_inventory_and_ai(self):
        self.configure(self.f.bench)
        self.f.f.begin()
        trigger = 'full_recover_battle_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON event_queue FOR EACH ROW BEGIN IF NEW.player_id='{self.f.f.player}' AND NEW.event_name='battle:turn-result' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Full Recover fault'; END IF; END")
        try:
            self.f.rejected(lambda: self.use(self.f.bench), 500)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')


if __name__ == '__main__':
    unittest.main()

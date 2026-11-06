"""Crafting and pickup preparation guards, using only UUID-owned fixtures."""
from concurrent.futures import ThreadPoolExecutor
import json
import unittest
import uuid

import test_start_context_writer_guards as context_guards
from test_http import post, sql


class CraftingPickupPreparationGuardTests(unittest.TestCase):
    def setUp(self):
        self.context = context_guards.StartContextWriterGuardTests(methodName='runTest')
        self.addCleanup(self.context.doCleanups)
        self.context.setUp()
        self.f = self.context.f
        self.pickups = {}
        for player, _, _ in self.context.participants():
            pickup = str(uuid.uuid4())
            self.pickups[player] = pickup
            contents = json.dumps([{'type': 'ITEM', 'item_id': 'ItemMortyChip', 'amount': 2},
                                   {'type': 'COIN', 'amount': 7}])
            self.f.execute([
                f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{player}','ItemBattery',2),('{player}','ItemFleeb',2)",
                f"INSERT INTO event_queue (room_id,event_name,pickup_id,placement,pick_up_contents) VALUES ('{self.f.room}','room:pickup-added','{pickup}','2,79','{contents}')",
            ])

    def actions(self, player, session):
        return [('/session/recipe/use', {'session_id': session, 'recipe_id': 'RecipeSerum'}),
                ('/session/collect-pickup', {'session_id': session, 'pickup_id': self.pickups[player]})]

    def blocked(self):
        before = self.context.snapshot()
        for player, session, _ in self.context.participants():
            for route, request in self.actions(player, session):
                with self.subTest(route=route, player=player):
                    expected = {'error': 'FAILED'} if route.endswith('collect-pickup') else {'error': {'code': 'FAILED'}}
                    self.assertEqual(post(route, request), (409, expected))
                    self.assertEqual(self.context.snapshot(), before)

    def success(self):
        for player, session, _ in self.context.participants():
            actions = self.actions(player, session)
            response = post(*actions[0])
            self.assertEqual(response[0], 200, response)
            self.assertEqual(response[1]['result'], {'type': 3, 'item_id': 'ItemSerum', 'quantity': 1, 'amount': 1, 'amount_received': 1})
            self.assertEqual(post(*actions[1]), (200, {'pickup_id': self.pickups[player], 'contents': [
                {'type': 'ITEM', 'item_id': 'ItemMortyChip', 'quantity': 4, 'amount_received': 2, 'amount': 2},
                {'type': 'COIN', 'quantity': 30, 'amount_received': 7, 'amount': 7}]}))
            items = sql(f"SELECT item_id,quantity FROM owned_items WHERE player_id='{player}'")
            self.assertEqual({r['item_id']: int(r['quantity']) for r in items},
                             {'ItemBattery': 1, 'ItemFleeb': 1, 'ItemMortyChip': 4, 'ItemSerum': 1})

    def test_both_roles_blocked_then_success_after_cancellation(self):
        self.context.claim()
        self.blocked()
        self.context.cancel()
        self.success()

    def test_orphan_claim_blocks_crafting_and_pickup(self):
        for player, _, _ in self.context.participants():
            sql(f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{player}','{self.context.battle}')")
        self.blocked()

    def test_claim_committed_during_user_lock_wait_is_observed(self):
        for route, request in self.actions(self.f.player, self.f.session):
            with self.subTest(route=route):
                before = self.context.snapshot()
                process = self.context.lock_user(self.f.player)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(post, route, request)
                    self.context.wait_for_user_lock(self.f.player, future)
                    self.context.release_user(process, [f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{self.f.player}','{self.context.battle}')"])
                    self.assertEqual(future.result(timeout=10)[0], 409)
                sql(f"DELETE FROM friend_battle_memberships WHERE player_id='{self.f.player}'")
                self.assertEqual(self.context.snapshot(), before)

    def test_revoked_session_after_user_lock_wait_cannot_write(self):
        for route, request in self.actions(self.f.player, self.f.session):
            with self.subTest(route=route):
                before = self.context.snapshot()
                process = self.context.lock_user(self.f.player)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(post, route, request)
                    self.context.wait_for_user_lock(self.f.player, future)
                    self.context.release_user(process, [f"UPDATE users SET session_id='{uuid.uuid4()}',last_seen=last_seen WHERE player_id='{self.f.player}'"])
                    self.assertEqual(future.result(timeout=10)[0], 401)
                sql(f"UPDATE users SET session_id='{self.f.session}',last_seen=last_seen WHERE player_id='{self.f.player}'")
                self.assertEqual(self.context.snapshot(), before)

    def test_pickup_publication_fault_rolls_back_rewards_and_collected_marker(self):
        trigger = 'context_pickup_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON event_queue FOR EACH ROW BEGIN IF NEW.room_id='{self.f.room}' AND NEW.event_name='room:pickup-removed' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID pickup failure'; END IF; END")
        before = self.context.snapshot()
        self.assertEqual(post(*self.actions(self.f.player, self.f.session)[1]), (500, {'error': 'Server error'}))
        self.assertEqual(self.context.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

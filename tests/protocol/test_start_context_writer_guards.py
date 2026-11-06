"""Resource/profile preparation guards: additive UUID fixtures, no purchases."""
from concurrent.futures import ThreadPoolExecutor
import json
import unittest
import uuid

import test_battle_lifecycle as lifecycle
from test_http import post, sql
import test_party_writer_guards as party_helpers


class StartContextWriterGuardTests(unittest.TestCase):
    participants = party_helpers.PartyWriterGuardTests.participants
    claim = party_helpers.PartyWriterGuardTests.claim
    cancel = party_helpers.PartyWriterGuardTests.cancel
    lock_user = party_helpers.PartyWriterGuardTests.lock_user
    release_user = party_helpers.PartyWriterGuardTests.release_user
    wait_for_user_lock = party_helpers.PartyWriterGuardTests.wait_for_user_lock

    def setUp(self):
        self.f = lifecycle.BattleLifecycleTests(methodName='runTest')
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.battle, self.invite, self.avatar, self.active = [str(uuid.uuid4()) for _ in range(4)]
        self.players = f"'{self.f.player}','{self.f.other_player}'"
        self.addCleanup(self.cleanup_context)
        self.f.execute([
            f"UPDATE users SET decks_owned=0,coupons=100,coins=23,player_avatar_id='initial' WHERE player_id IN ({self.players})",
            f"UPDATE owned_items SET quantity=2 WHERE player_id IN ({self.players}) AND item_id='ItemMortyChip'",
            *[f"INSERT INTO owned_avatars (player_id,player_avatar_id) VALUES ('{player}','[]')" for player, _, _ in self.participants()],
        ])

    def cleanup_context(self):
        self.f.execute([
            *[f"DELETE FROM {table} WHERE player_id IN ({self.players})" for table in ('friend_battle_memberships', 'owned_avatars', 'trades')],
            f"DELETE FROM friend_battle_sessions WHERE battle_id='{self.battle}'",
        ])

    def actions(self, session, morty):
        return [
            ('/session/buy-item', {'session_id': session, 'item_id': 'ItemMortyChip'}),
            ('/session/player-avatar/buy', {'session_id': session, 'player_avatar_id': self.avatar}),
            ('/session/player-avatar/set-active', {'session_id': session, 'player_avatar_id': self.active}),
            ('/session/decks/slots/buy', {'session_id': session}),
            ('/trading/request-morty', {'session_id': session, 'owned_morty_id': morty, 'is_free_trade': False}),
        ]

    def snapshot(self):
        result = self.f.snapshot()
        for table in ('owned_avatars', 'trades', 'friend_battle_memberships'):
            result[table] = sql(f"SELECT * FROM {table} WHERE player_id IN ({self.players}) ORDER BY player_id")
        return result

    def blocked(self):
        before = self.snapshot()
        for _, session, morty in self.participants():
            for route, request in self.actions(session, morty):
                with self.subTest(route=route, session=session):
                    expected = ({'success': False, 'error': 'FAILED'} if route.endswith('set-active') else
                                {'error': 'FAILED'} if route.endswith('avatar/buy') else {'error': {'code': 'FAILED'}})
                    self.assertEqual(post(route, request), (409, expected))
                    self.assertEqual(self.snapshot(), before)
            request = self.actions(session, morty)[-1][1] | {'is_free_trade': True}
            self.assertEqual(post('/trading/request-morty', request), (409, {'error': {'code': 'FAILED'}}))
            self.assertEqual(self.snapshot(), before)

    def success(self):
        config = sql('SELECT cost_additional_slot FROM deck_config LIMIT 1')[0]
        for player, session, morty in self.participants():
            responses = [post(route, request) for route, request in self.actions(session, morty)]
            self.assertTrue(all(status == 200 for status, _ in responses), responses)
            self.assertEqual(responses[0][1], {'coins': 3205915, 'coupons': 1,
                'result': {'type': 'ITEM', 'item_id': 'ItemMortyChip', 'quantity': 3, 'amount_received': 1, 'amount': 1}})
            self.assertEqual(responses[1][1]['coins_deducted'], 0)
            user = sql(f"SELECT coins,coupons,decks_owned,player_avatar_id FROM users WHERE player_id='{player}'")[0]
            self.assertEqual((int(user['coins']), int(user['coupons']), int(user['decks_owned']), user['player_avatar_id']),
                             (23, 99 - int(config['cost_additional_slot']), 1, self.active))
            self.assertEqual(json.loads(sql(f"SELECT player_avatar_id FROM owned_avatars WHERE player_id='{player}'")[0]['player_avatar_id']), [self.avatar])
            self.assertEqual(len(sql(f"SELECT * FROM trades WHERE player_id='{player}'")), 1)

    def test_both_roles_blocked_then_success_after_cancellation(self):
        self.claim()
        self.blocked()
        self.cancel()
        self.success()

    def test_orphan_claim_blocks_every_writer_and_free_trade(self):
        for player, _, _ in self.participants():
            sql(f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{player}','{self.battle}')")
        self.blocked()

    def test_unclaimed_success_preserves_costs_and_legacy_responses(self):
        self.success()

    def test_unclaimed_item_cap_and_coupon_checks_preserve_resources(self):
        sql(f"UPDATE owned_items SET quantity=10 WHERE player_id='{self.f.player}' AND item_id='ItemMortyChip'")
        sql(f"UPDATE users SET coupons=0 WHERE player_id='{self.f.player}'")
        before = self.snapshot()
        actions = self.actions(self.f.session, self.f.morty)
        self.assertEqual(post(*actions[0]), (409, {'error': {'code': 'ITEM_LIMIT'}}))
        self.assertEqual(post(*actions[-1]), (409, {'error': {'code': 'NOT_ENOUGH_COUPONS'}}))
        self.assertEqual(self.snapshot(), before)

    def test_claim_committed_during_user_lock_wait_is_observed(self):
        for route, request in self.actions(self.f.session, self.f.morty):
            with self.subTest(route=route):
                before = self.snapshot()
                process = self.lock_user(self.f.player)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(post, route, request)
                    self.wait_for_user_lock(self.f.player, future)
                    self.release_user(process, [f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{self.f.player}','{self.battle}')"])
                    self.assertEqual(future.result(timeout=10)[0], 409)
                sql(f"DELETE FROM friend_battle_memberships WHERE player_id='{self.f.player}'")
                self.assertEqual(self.snapshot(), before)

    def test_session_revoked_during_user_lock_wait_cannot_write(self):
        for route, request in self.actions(self.f.session, self.f.morty):
            with self.subTest(route=route):
                before = self.snapshot()
                process = self.lock_user(self.f.player)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(post, route, request)
                    self.wait_for_user_lock(self.f.player, future)
                    self.release_user(process, [f"UPDATE users SET session_id='{uuid.uuid4()}',last_seen=last_seen WHERE player_id='{self.f.player}'"])
                    self.assertEqual(future.result(timeout=10)[0], 401)
                sql(f"UPDATE users SET session_id='{self.f.session}',last_seen=last_seen WHERE player_id='{self.f.player}'")
                self.assertEqual(self.snapshot(), before)

    def test_avatar_equip_fault_rolls_back_owned_avatar_change(self):
        trigger = 'context_avatar_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE UPDATE ON users FOR EACH ROW BEGIN IF NEW.player_id='{self.f.player}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID profile failure'; END IF; END")
        before = self.snapshot()
        response = post(*self.actions(self.f.session, self.f.morty)[1])
        self.assertEqual(response, (500, {'error': 'SERVER_ERROR'}))
        self.assertEqual(self.snapshot(), before)

    def test_trade_insert_fault_rolls_back_coupon_and_expiry_changes(self):
        trigger = 'context_trade_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON trades FOR EACH ROW BEGIN IF NEW.player_id='{self.f.player}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID trade failure'; END IF; END")
        for free in (False, True):
            with self.subTest(free=free):
                before = self.snapshot()
                route, request = self.actions(self.f.session, self.f.morty)[-1]
                self.assertEqual(post(route, request | {'is_free_trade': free}), (500, {'error': {'code': 'SERVER_ERROR'}}))
                self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

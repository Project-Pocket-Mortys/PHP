"""Party writers serialize with shared reservations; additive UUID fixtures only."""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import time
import unittest
import uuid

import test_battle_lifecycle as lifecycle
from test_http import COMPOSE, ROOT, php, post, sql


class PartyWriterGuardTests(unittest.TestCase):
    def setUp(self):
        self.f = lifecycle.BattleLifecycleTests(methodName='runTest')
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.battle, self.invite, self.gacha, self.promo = [str(uuid.uuid4()) for _ in range(4)]
        self.players = f"'{self.f.player}','{self.f.other_player}'"
        self.addCleanup(self.cleanup_party)
        self.f.execute([
            f"UPDATE users SET decks_owned=3,coupons=20 WHERE player_id IN ({self.players})",
            f"UPDATE owned_items SET quantity=2 WHERE player_id IN ({self.players}) AND item_id='ItemMortyChip'",
            f"INSERT INTO gachas (gacha_id,cost,lvl_min,lvl_max) VALUES ('{self.gacha}',2,1,1)",
            f"INSERT INTO gacha_contents (gacha_id,reward,quantity) VALUES ('{self.gacha}','ITEM',1)",
            f"INSERT INTO gacha_content_items (gacha_content_id,item_id) SELECT id,'ItemMortyChip' FROM gacha_contents WHERE gacha_id='{self.gacha}'",
            # The endpoint requires an active promo even for its ITEM-only path.
            # Every catalog write and cleanup is restricted to our UUID catalog IDs.
            f"INSERT INTO gacha_promos (gacha_promo_id,period_start,period_end) VALUES ('{self.promo}',UNIX_TIMESTAMP()-60,UNIX_TIMESTAMP()+3600)",
        ])

    def cleanup_party(self):
        self.f.execute([
            f"DELETE FROM friend_battle_memberships WHERE player_id IN ({self.players})",
            f"DELETE FROM friend_battle_sessions WHERE battle_id='{self.battle}'",
            f"DELETE FROM gacha_content_items WHERE gacha_content_id IN (SELECT id FROM gacha_contents WHERE gacha_id='{self.gacha}')",
            f"DELETE FROM gacha_contents WHERE gacha_id='{self.gacha}'",
            f"DELETE FROM gachas WHERE gacha_id='{self.gacha}'",
            f"DELETE FROM gacha_promos WHERE gacha_promo_id='{self.promo}'",
        ])

    def participants(self):
        return ((self.f.player, self.f.session, self.f.morty),
                (self.f.other_player, self.f.other_session, self.f.other_morty))

    def actions(self, session, morty):
        return [
            ('deck/edit', {'session_id': session, 'deck_id': 2, 'owned_morty_ids': [morty]}),
            ('deck/set-active', {'session_id': session, 'deck_id': 1}),
            ('owned_morties/learn-attacks', {'session_id': session, 'owned_morties': [
                {'owned_morty_id': morty, 'attack_ids': ['AttackLick', 'AttackLick']}]}),
            ('gacha', {'session_id': session, 'gacha_id': self.gacha}),
        ]

    def snapshot(self):
        result = self.f.snapshot()
        result['claims'] = sql(f"SELECT * FROM friend_battle_memberships WHERE player_id IN ({self.players}) ORDER BY player_id")
        result['shared'] = sql(f"SELECT * FROM friend_battle_sessions WHERE battle_id='{self.battle}'")
        result['catalog'] = sql(f"SELECT * FROM gachas WHERE gacha_id='{self.gacha}'")
        return result

    def claim(self):
        self.f.execute([
            f"INSERT INTO friend_battle_sessions (battle_id,invite_id,sender_id,recipient_id,state,created_at,updated_at,prepare_deadline) VALUES ('{self.battle}','{self.invite}','{self.f.player}','{self.f.other_player}','PREPARING',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6),UTC_TIMESTAMP(6)+INTERVAL 60 SECOND)",
            *[f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{player}','{self.battle}')"
              for player, _, _ in self.participants()],
        ])

    def cancel(self):
        php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "require '/var/www/html/lib/friend_battle_membership.php';"
            f"friend_battle_cancel_reservation($pdo,'{self.f.session}','{self.battle}');")

    def assert_blocked(self):
        before = self.snapshot()
        for _, session, morty in self.participants():
            actions = self.actions(session, morty) + [
                ('deck/edit', {'session_id': session, 'deck_id': 1, 'owned_morty_ids': []})]
            for route, request in actions:
                with self.subTest(route=route, session=session):
                    response = post('/session/' + route, request)
                    expected = ({'error': {'code': 'FAILED'}} if route.endswith('learn-attacks') else
                                {'error': 'FAILED'} if route == 'gacha' else
                                {'success': False, 'error': 'FAILED'})
                    self.assertEqual(response, (409, expected))
                    self.assertEqual(self.snapshot(), before)

    def assert_success(self):
        for player, session, morty in self.participants():
            for route, request in self.actions(session, morty):
                with self.subTest(route=route, player=player):
                    response = post('/session/' + route, request)
                    self.assertEqual(response[0], 200, response)
            decks = sql(f"SELECT deck_id,owned_morty_ids FROM decks WHERE player_id='{player}' ORDER BY deck_id")
            self.assertEqual([(int(d['deck_id']), json.loads(d['owned_morty_ids'])) for d in decks],
                             [(1, [morty]), (2, [morty])])
            user = sql(f"SELECT active_deck_id,coupons FROM users WHERE player_id='{player}'")[0]
            self.assertEqual((int(user['active_deck_id']), int(user['coupons'])), (1, 18))
            attacks = sql(f"SELECT attack_id,position,pp,pp_stat FROM owned_attacks WHERE owned_morty_id='{morty}' ORDER BY position")
            self.assertEqual([(a['attack_id'], int(a['position']), int(a['pp']), int(a['pp_stat'])) for a in attacks],
                             [('AttackLick', 0, 8, 8), ('AttackLick', 1, 8, 8)])
            items = sql(f"SELECT quantity FROM owned_items WHERE player_id='{player}' AND item_id='ItemMortyChip'")
            self.assertEqual(int(items[0]['quantity']), 3)

    def test_both_roles_blocked_then_success_after_cancellation(self):
        self.claim()
        self.assert_blocked()
        self.cancel()
        self.assertEqual(sql(f"SELECT * FROM friend_battle_memberships WHERE player_id IN ({self.players})"), [])
        self.assert_success()

    def test_unclaimed_party_writers_preserve_success_paths(self):
        self.assert_success()

    def test_orphaned_claim_is_busy(self):
        for player, _, _ in self.participants():
            sql(f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{player}','{self.battle}')")
        self.assert_blocked()

    def test_duplicate_morty_id_cannot_replace_claimed_players_attacks(self):
        sql(f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{self.f.other_player}','{self.battle}')")
        sql(f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat) VALUES ('{self.f.other_morty}','{self.f.player}','Morty',100,100)")
        before = self.snapshot()
        response = post('/session/owned_morties/learn-attacks', {
            'session_id': self.f.session, 'owned_morties': [
                {'owned_morty_id': self.f.other_morty, 'attack_ids': ['AttackLick', 'AttackLick']}]})
        self.assertEqual(response[0], 200, response)
        self.assertEqual(response[1]['owned_morties'], [])
        self.assertEqual(self.snapshot(), before)

    def wait_for_user_lock(self, player, future):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            self.assertFalse(future.done(), 'Writer returned while the user lock was held')
            waiting = sql("SELECT ID FROM information_schema.PROCESSLIST WHERE ID<>CONNECTION_ID() "
                          f"AND INFO LIKE '%FOR UPDATE%' AND INFO LIKE '%{player}%'")
            if waiting:
                return
            time.sleep(0.05)
        self.fail('Writer did not wait for the authenticated user row lock')

    def lock_user(self, player):
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
                "$pdo->beginTransaction();"
                f"$pdo->query(\"SELECT id FROM users WHERE player_id='{player}' FOR UPDATE\")->fetchAll();"
                "echo \"LOCKED\\n\"; flush(); fgets(STDIN);"
                "foreach(json_decode(base64_decode(trim(fgets(STDIN))),true) as $q) $pdo->exec($q);"
                "$pdo->commit();")
        process = subprocess.Popen(COMPOSE + ['exec', '-T', 'web', 'php', '-r', code],
                                   cwd=ROOT, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE)
        self.addCleanup(lambda: process.poll() is None and process.kill())
        self.assertEqual(process.stdout.readline().strip(), 'LOCKED')
        return process

    def release_user(self, process, queries):
        import base64
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        out, err = process.communicate('\n' + encoded + '\n', timeout=10)
        self.assertEqual(process.returncode, 0, (out, err))

    def test_claim_committed_while_writer_waits_is_observed(self):
        # Each route starts with no claim. A concurrent holder inserts the claim
        # before releasing its user lock. Any earlier snapshot would miss it.
        for route, request in self.actions(self.f.session, self.f.morty):
            with self.subTest(route=route):
                before = self.f.snapshot()
                process = self.lock_user(self.f.player)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(post, '/session/' + route, request)
                    self.wait_for_user_lock(self.f.player, future)
                    self.release_user(process, [f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{self.f.player}','{self.battle}')"])
                    self.assertEqual(future.result(timeout=10)[0], 409)
                sql(f"DELETE FROM friend_battle_memberships WHERE player_id='{self.f.player}'")
                self.assertEqual(self.f.snapshot(), before)

    def test_revoked_session_after_user_lock_wait_cannot_write(self):
        for route, request in self.actions(self.f.session, self.f.morty):
            with self.subTest(route=route):
                before = self.f.snapshot()
                process = self.lock_user(self.f.player)
                with ThreadPoolExecutor(max_workers=1) as pool:
                    future = pool.submit(post, '/session/' + route, request)
                    self.wait_for_user_lock(self.f.player, future)
                    self.release_user(process, [f"UPDATE users SET session_id='{uuid.uuid4()}',last_seen=last_seen WHERE player_id='{self.f.player}'"])
                    self.assertEqual(future.result(timeout=10)[0], 401)
                sql(f"UPDATE users SET session_id='{self.f.session}',last_seen=last_seen WHERE player_id='{self.f.player}'")
                self.assertEqual(self.f.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

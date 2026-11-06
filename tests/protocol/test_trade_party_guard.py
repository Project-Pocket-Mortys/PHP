"""Trade ownership guard with additive UUID fixtures; no account reseeding."""
from concurrent.futures import ThreadPoolExecutor
import subprocess
import time
import unittest
import uuid

import test_friend_battle_invites as invitations
from test_http import COMPOSE, ROOT, post, sql


class TradePartyGuardTests(unittest.TestCase):
    def setUp(self):
        self.f = invitations.FriendBattleInviteTests(methodName='runTest')
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.a, self.b, self.c, self.d = self.f.players
        self.trade, self.offer, self.claim = [str(uuid.uuid4()) for _ in range(3)]
        self.addCleanup(self.cleanup_trade)
        self.f.execute([
            f"INSERT INTO trades (trade_id,player_id,morty_trade_id,is_free_trade) VALUES ('{self.trade}','{self.a}','{self.a}',1)",
            f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{self.offer}','{self.trade}','{self.b}','{self.b}')",
        ])

    def cleanup_trade(self):
        self.f.execute([
            f"DELETE FROM completed_trades WHERE trade_request_id='{self.trade}' OR trade_offer_id='{self.offer}'",
            f"DELETE FROM trade_offers WHERE trade_offer_id='{self.offer}'",
            f"DELETE FROM trades WHERE trade_id='{self.trade}'",
            f"DELETE FROM friend_battle_memberships WHERE player_id IN ('{self.f.ids}')",
        ])

    def call(self, accept=True):
        return post('/trading/offer-response', dict(trade_request_id=self.trade,
                    trade_offer_id=self.offer, request_accepted=accept))

    def snapshot(self):
        return dict(gameplay=self.f.snapshot(),
                    trades=sql(f"SELECT * FROM trades WHERE trade_id='{self.trade}' ORDER BY id"),
                    offers=sql(f"SELECT * FROM trade_offers WHERE trade_offer_id='{self.offer}' ORDER BY id"),
                    completed=sql(f"SELECT * FROM completed_trades WHERE trade_request_id='{self.trade}' ORDER BY id"),
                    claims=sql(f"SELECT * FROM friend_battle_memberships WHERE player_id IN ('{self.f.ids}') ORDER BY player_id"))

    def assert_blocked(self, accept=True):
        before = self.snapshot()
        self.assertEqual(self.call(accept), (409, {'error': 'FAILED'}))
        self.assertEqual(self.snapshot(), before)

    def test_declared_and_actual_owners_all_block_transfer_and_decline(self):
        # Old trade rows can name targets different from current ownership.
        # The guard covers both sides without claiming to recover trade policy.
        self.f.execute([
            f"UPDATE owned_morties SET player_id='{self.c}' WHERE owned_morty_id='{self.a}'",
            f"UPDATE owned_morties SET player_id='{self.d}' WHERE owned_morty_id='{self.b}'",
        ])
        for player in self.f.players:
            with self.subTest(player=player):
                sql(f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{player}','{self.claim}')")
                self.assert_blocked()
                self.assert_blocked(False)
                sql(f"DELETE FROM friend_battle_memberships WHERE player_id='{player}'")

    def test_unreserved_accept_preserves_legacy_success_and_transfer(self):
        before = sql(f"SELECT owned_morty_id,player_id FROM owned_morties WHERE owned_morty_id IN ('{self.a}','{self.b}') ORDER BY owned_morty_id")
        self.assertEqual(self.call(), (200, [None, None]))
        after = sql(f"SELECT owned_morty_id,player_id FROM owned_morties WHERE owned_morty_id IN ('{self.a}','{self.b}') ORDER BY owned_morty_id")
        expected = [dict(row, player_id=self.b if row['player_id'] == self.a else self.a) for row in before]
        self.assertEqual(after, expected)
        state = self.snapshot()
        self.assertEqual(state['trades'], [])
        self.assertEqual(state['offers'], [])
        self.assertEqual(len(state['completed']), 1)

    def test_unreserved_decline_preserves_legacy_success_and_party(self):
        before = self.f.snapshot()
        self.assertEqual(self.call(False), (200, [None, None]))
        self.assertEqual(self.f.snapshot(), before)
        state = self.snapshot()
        self.assertEqual(len(state['trades']), 1)
        self.assertEqual(state['offers'], [])
        self.assertEqual(state['completed'], [])

    def test_ambiguous_global_morty_or_user_fails_without_mutation(self):
        sql(f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id) VALUES ('{self.a}','{self.c}','Morty')")
        self.assert_blocked()
        sql(f"DELETE FROM owned_morties WHERE owned_morty_id='{self.a}' AND player_id='{self.c}'")
        sql(f"INSERT INTO users (secret,player_id,session_id) VALUES ('{self.c}','{self.c}','{uuid.uuid4()}')")
        sql(f"UPDATE owned_morties SET player_id='{self.c}' WHERE owned_morty_id='{self.a}'")
        self.assert_blocked()

    def test_completion_fault_rolls_back_both_ownership_changes(self):
        trigger = 'trade_party_fault_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON completed_trades FOR EACH ROW BEGIN IF NEW.trade_request_id='{self.trade}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID trade completion failure'; END IF; END")
        before = self.snapshot()
        try:
            self.assertEqual(self.call(), (500, {'error': 'SERVER_ERROR'}))
            self.assertEqual(self.snapshot(), before)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')

    def test_waiting_trade_observes_newly_committed_membership(self):
        # Preflight may see no claim; the first membership read after the user
        # lock must observe a reservation committed while that lock was held.
        player = min(self.a, self.b)
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
                "$pdo->beginTransaction();"
                f"$pdo->query(\"SELECT id FROM users WHERE player_id='{player}' FOR UPDATE\")->fetchAll();"
                "echo \"locked\\n\"; flush(); fgets(STDIN);"
                f"$pdo->exec(\"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{player}','{self.claim}')\");"
                "$pdo->commit(); echo \"committed\\n\";")
        blocker = subprocess.Popen(COMPOSE + ['exec', '-T', 'web', 'php', '-r', code],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, cwd=ROOT)
        try:
            self.assertEqual(blocker.stdout.readline().strip(), 'locked')
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(self.call)
                try:
                    time.sleep(0.5)
                    self.assertFalse(pending.done(), 'Trade did not wait for the affected user lock')
                finally:
                    blocker.stdin.write('release\n')
                    blocker.stdin.flush()
                self.assertEqual(pending.result(timeout=10), (409, {'error': 'FAILED'}))
            self.assertEqual(blocker.wait(timeout=10), 0, blocker.stderr.read())
            self.assertEqual(len(sql(f"SELECT * FROM trades WHERE trade_id='{self.trade}'")), 1)
            self.assertEqual(len(sql(f"SELECT * FROM trade_offers WHERE trade_offer_id='{self.offer}'")), 1)
            self.assertEqual(sql(f"SELECT * FROM completed_trades WHERE trade_request_id='{self.trade}'"), [])
            self.assertEqual(sql(f"SELECT player_id FROM owned_morties WHERE owned_morty_id='{self.a}'"), [{'player_id': self.a}])
        finally:
            if blocker.poll() is None:
                blocker.kill()
                blocker.wait(timeout=10)
            for stream in (blocker.stdin, blocker.stdout, blocker.stderr):
                stream.close()


if __name__ == '__main__':
    unittest.main()

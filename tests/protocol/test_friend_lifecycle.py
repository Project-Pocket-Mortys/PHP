"""Friend lifecycle contracts using isolated UUID accounts, without reseeding."""
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import threading
import unittest
import uuid
import urllib.request
import urllib.error

from test_http import COMPOSE, ROOT, php, post, sql


class FriendLifecycleTests(unittest.TestCase):
    def test_auth_errors_use_a_member_of_every_native_friend_enum(self):
        for action in ('list','search','request','response','remove'):
            with self.subTest(action=action):
                status, body = self.call(action, target=self.b, session_id=str(uuid.uuid4()),
                                         query=self.b, approve=True)
                self.assertEqual(status, 401)
                self.assertEqual(body, {'error': {'code': 'FAILED'}})

    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.players = [str(uuid.uuid4()) for _ in range(3)]
        self.a, self.b, self.c = self.players
        self.addCleanup(self.cleanup)
        for player in self.players:
            sql(f"INSERT INTO users (secret,player_id,session_id,username,state,tags,level,wins,losses) "
                f"VALUES ('{player}','{player}','{player}','{player}','WORLD','[]',7,2,1)")
            sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{player}','ItemSerum',3)")

    def cleanup(self):
        for player in self.players:
            sql(f"DELETE FROM friend_list WHERE player_id_a='{player}' OR player_id_b='{player}'")
            for table in ('owned_items', 'users'):
                sql(f"DELETE FROM {table} WHERE player_id='{player}'")

    def call(self, action, actor=None, target=None, **extra):
        body = dict(session_id=actor or self.a)
        if target is not None:
            body['player_id'] = target
        body.update(extra)
        return post('/session/friend/' + action, body)

    def rows(self):
        return sql(f"SELECT * FROM friend_list WHERE player_id_a IN ('{self.a}','{self.b}','{self.c}') ORDER BY id")

    def stock(self):
        ids = "','".join(self.players)
        return [sql(f"SELECT * FROM {table} WHERE player_id IN ('{ids}') ORDER BY id")
                for table in ('users', 'owned_items', 'owned_morties', 'decks', 'event_queue')]

    def test_sender_cannot_approve_or_decline_own_request(self):
        before = self.stock()
        self.assertEqual(self.call('request', target=self.b)[0], 200)
        pending = self.rows()
        for approve in (True, False):
            status, _ = self.call('response', target=self.b, approve=approve)
            self.assertGreaterEqual(status, 400)
            self.assertLess(status, 500)
            self.assertEqual(self.rows(), pending)
        self.assertEqual(self.stock(), before)

    def test_accept_replay_privacy_and_symmetric_removal(self):
        before = self.stock()
        status, request = self.call('request', target=self.b)
        self.assertEqual(status, 200)
        self.assertEqual((request['player_id_a'], request['player_id_b']), (self.a, self.b))
        self.assertIs(request['pending'], True)
        self.assertEqual(self.call('request', target=self.b)[0], 400)
        self.assertEqual(self.call('request', self.b, self.a)[0], 400)
        for actor, sent, received in ((self.a, [self.b], []), (self.b, [], [self.a]), (self.c, [], [])):
            status, body = self.call('list', actor)
            self.assertEqual(status, 200)
            self.assertEqual([r['player_id'] for r in body['requests_sent']], sent)
            self.assertEqual([r['player_id'] for r in body['requests_received']], received)
            self.assertEqual(body['friends'], [])
            for row in body['requests_sent'] + body['requests_received']:
                self.assertIs(type(row['level']), int)
            self.assertEqual(body['poll_period'], 5)
            self.assertEqual(body['limit_friends'], 30)
            self.assertEqual(body['donation_request'],
                             {'morty_id': None, 'next_countdown': 0, 'donation': None})
        self.assertGreaterEqual(self.call('response', self.c, self.a, approve=True)[0], 400)
        pending = self.rows()
        self.assertEqual(self.call('remove', self.c, self.a)[0], 404)
        self.assertEqual(self.rows(), pending)
        self.assertEqual(self.call('response', self.b, self.a, approve=True), (200, 1))
        self.assertGreaterEqual(self.call('response', self.b, self.a, approve=True)[0], 400)
        for actor, other in ((self.a, self.b), (self.b, self.a)):
            body = self.call('list', actor)[1]
            self.assertEqual([r['player_id'] for r in body['friends']], [other])
            for key in ('level', 'wins', 'losses'):
                self.assertIs(type(body['friends'][0][key]), int)
        self.assertEqual(self.call('remove', self.b, self.a)[0], 200)
        self.assertEqual(self.call('remove', self.a, self.b)[0], 404)
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.stock(), before)

    def test_decline_and_cancel_both_orientations(self):
        before = self.stock()
        for sender, recipient in ((self.a, self.b), (self.b, self.a)):
            self.assertEqual(self.call('request', sender, recipient)[0], 200)
            self.assertEqual(self.call('response', recipient, sender, approve=False), (200, 1))
            self.assertEqual(self.rows(), [])
            self.assertEqual(self.call('request', sender, recipient)[0], 200)
            self.assertEqual(self.call('remove', sender, recipient)[0], 200)
            self.assertEqual(self.rows(), [])
        self.assertEqual(self.stock(), before)

    def test_crossed_concurrent_requests_create_one_pair(self):
        barrier = threading.Barrier(2)
        def send(pair):
            barrier.wait(timeout=5)
            return self.call('request', *pair)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, [(self.a, self.b), (self.b, self.a)]))
        self.assertEqual(sorted(r[0] for r in results), [200, 400], results)
        self.assertEqual(len(self.rows()), 1)

    def test_concurrent_accept_and_remove_cannot_restore_deleted_pair(self):
        self.call('request', target=self.b)
        barrier = threading.Barrier(2)
        def mutate(action):
            barrier.wait(timeout=5)
            return self.call(action, self.b, self.a, approve=True)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(mutate, ['response', 'remove']))
        self.assertEqual(results[1][0], 200, results)
        self.assertIn(results[0][0], (200, 400), results)
        self.assertEqual(self.rows(), [])

    def test_database_failures_rollback_and_hide_internals(self):
        before = self.stock()
        for operation, action, actor, target, extra in (
                ('INSERT', 'request', self.a, self.b, {}),
                ('UPDATE', 'response', self.b, self.a, {'approve': True}),
                ('DELETE', 'response', self.b, self.a, {'approve': False}),
                ('DELETE', 'remove', self.a, self.b, {})):
            if operation == 'INSERT':
                self.assertEqual(self.rows(), [])
            elif not self.rows():
                self.assertEqual(self.call('request', target=self.b)[0], 200)
            pending = self.rows()
            trigger = 'friend_fault_' + uuid.uuid4().hex
            self.addCleanup(lambda name=trigger: sql(f'DROP TRIGGER IF EXISTS {name}'))
            source = 'NEW' if operation != 'DELETE' else 'OLD'
            sql(f"CREATE TRIGGER {trigger} BEFORE {operation} ON friend_list FOR EACH ROW "
                f"BEGIN IF {source}.player_id_a='{self.a}' THEN SIGNAL SQLSTATE '45000' "
                "SET MESSAGE_TEXT='UUID friend rollback private'; END IF; END")
            try:
                status, body = self.call(action, actor, target, **extra)
                self.assertEqual(status, 500)
                self.assertEqual(body, {'error': {'code': 'FAILED'}})
                self.assertEqual(self.rows(), pending)
                self.assertEqual(self.stock(), before)
            finally:
                sql(f'DROP TRIGGER IF EXISTS {trigger}')

    def test_ambiguous_pair_fails_closed(self):
        self.call('request', target=self.b)
        sql(f"INSERT INTO friend_list (player_id_a,player_id_b,pending,direction,created,modified) VALUES ('{self.b}','{self.a}','true','false',NOW(),NOW())")
        before = self.rows()
        for action, actor, target, extra in (
                ('request', self.a, self.b, {}), ('response', self.b, self.a, {'approve': True}),
                ('remove', self.a, self.b, {})):
            status, _ = self.call(action, actor, target, **extra)
            self.assertGreaterEqual(status, 400)
            self.assertLess(status, 500)
            self.assertEqual(self.rows(), before)

    def test_invalid_revoked_and_ambiguous_sessions(self):
        for action in ('request', 'response', 'remove', 'list', 'search'):
            extra = dict(approve=True, query=self.b)
            for session in ([], {}, 1, '', str(uuid.uuid4())):
                status, body = self.call(action, target=self.b, session_id=session, **extra)
                self.assertGreaterEqual(status, 400)
                self.assertLess(status, 500)
                self.assertIn('error', body)
        sql(f"UPDATE users SET session_id='{self.a}' WHERE player_id='{self.c}'")
        self.assertEqual(self.call('request', target=self.b)[0], 401)
        sql(f"UPDATE users SET session_id=NULL WHERE player_id='{self.a}'")
        sql(f"UPDATE users SET session_id=NULL WHERE player_id='{self.c}'")
        self.assertEqual(self.call('request', target=self.b)[0], 401)

    def test_session_revoked_while_waiting_for_pair_lock(self):
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                "$pdo->beginTransaction(); "
                f"$pdo->query(\"SELECT id FROM users WHERE player_id='{self.a}' FOR UPDATE\")->fetchAll(); "
                "echo 'locked\\n'; flush(); sleep(2); "
                f"$pdo->exec(\"UPDATE users SET session_id=NULL WHERE player_id='{self.a}'\"); "
                "$pdo->commit();")
        # An independent connection revokes the token while the HTTP request waits.
        with subprocess.Popen(COMPOSE + ['exec', '-T', 'web', 'php', '-r', code],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                              text=True, cwd=ROOT) as locker:
            self.assertEqual(locker.stdout.read(8), 'locked\\n')
            status, body = self.call('request', target=self.b)
            self.assertEqual(status, 401, body)
            self.assertEqual(locker.wait(timeout=10), 0, locker.stderr.read())
        self.assertEqual(self.rows(), [])

    def test_malformed_targets_and_approve_are_clean_errors(self):
        before = self.rows()
        for target in ([], {}, 1, '', str(uuid.uuid4()), self.a):
            for action in ('request', 'response', 'remove'):
                status, body = self.call(action, target=target, approve=True)
                self.assertGreaterEqual(status, 400)
                self.assertLess(status, 500)
                self.assertIsInstance(body['error']['code'], str)
                self.assertEqual(self.rows(), before)
        self.call('request', target=self.b)
        before = self.rows()
        for approve in (None, 'true', 1, [], {}):
            status, body = self.call('response', self.b, self.a, approve=approve)
            self.assertEqual(status, 400)
            self.assertEqual(body['error']['code'], 'APPROVE_INVALID')
            self.assertEqual(self.rows(), before)

    def test_ambiguous_player_identity_fails_closed(self):
        duplicate = str(uuid.uuid4())
        sql(f"INSERT INTO users (secret,player_id,session_id,username) "
            f"VALUES ('{duplicate}','{self.a}','{duplicate}','{duplicate}')")
        for action in ('request', 'response', 'remove', 'list', 'search'):
            status, _ = self.call(action, target=self.b, approve=True, query=self.b)
            self.assertEqual(status, 401)
        self.assertEqual(self.call('request', self.b, self.a)[0], 400)
        self.assertEqual(self.rows(), [])

    def test_search_existing_no_result_and_invalid_fields(self):
        status, body = self.call('search', query=self.b)
        self.assertEqual(status, 200)
        self.assertEqual(body['player_id'], self.b)
        self.assertIs(type(body['level']), int)
        request = urllib.request.Request('http://127.0.0.1:8087/session/friend/search/',
            json.dumps(dict(session_id=self.a, query=str(uuid.uuid4()))).encode(),
            {'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.read(), b'')
        self.assertEqual(self.call('search', query=[])[0], 400)


if __name__ == '__main__':
    unittest.main()

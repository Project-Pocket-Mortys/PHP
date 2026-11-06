"""Friend battle invitations against additive UUID fixtures; never reseed accounts."""
from concurrent.futures import ThreadPoolExecutor
import base64
import json
import threading
import unittest
import urllib.error
import urllib.request
import uuid

from test_http import php, post, sql


class FriendBattleInviteTests(unittest.TestCase):
    def setUp(self):
        self.players = [str(uuid.uuid4()) for _ in range(4)]
        self.a, self.b, self.c, self.d = self.players
        self.ids = "','".join(self.players)
        self.addCleanup(self.cleanup)
        queries = []
        for player in self.players:
            queries.extend([
                f"INSERT INTO users (secret,player_id,session_id,username,state,tags,level,wins,losses) VALUES ('{player}','{player}','{player}','{player}','WORLD','[]',7,2,1)",
                f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{player}','ItemSerum',3)",
                f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat) VALUES ('{player}','{player}','Morty',100,100)",
                f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{player}','AttackLick',0,5,5)",
                f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{player}',1,'[\"{player}\"]')",
            ])
        self.execute(queries)
        self.befriend(self.a, self.b)

    def execute(self, queries):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        return php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; $pdo->beginTransaction(); foreach(json_decode(base64_decode('" + encoded + "'),true) as $q) $pdo->exec($q); $pdo->commit();")

    def cleanup(self):
        self.execute([
            f"DELETE FROM friend_battle_invites WHERE sender_id IN ('{self.ids}') OR recipient_id IN ('{self.ids}')",
            f"DELETE FROM friend_list WHERE player_id_a IN ('{self.ids}') OR player_id_b IN ('{self.ids}')",
            f"DELETE FROM battles WHERE player_id IN ('{self.ids}') OR opponent_id IN ('{self.ids}')",
            f"DELETE FROM event_queue WHERE player_id IN ('{self.ids}') OR only_show_to_player_id IN ('{self.ids}')",
            f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.ids}')",
            *[f"DELETE FROM {table} WHERE player_id IN ('{self.ids}')" for table in ('owned_items', 'owned_morties', 'decks', 'users')],
        ])

    def befriend(self, sender, recipient, pending='false'):
        sql(f"INSERT INTO friend_list (player_id_a,player_id_b,pending,direction,created,modified) VALUES ('{sender}','{recipient}','{pending}','true',NOW(),NOW())")

    def call(self, action, actor=None, **changes):
        request = {'session_id': actor or self.a}
        request.update(changes)
        return post('/session/battle-invite/' + action, request)

    def create(self, actor=None, target=None, **changes):
        request = dict(opponent_player_id=target or self.b, battle_type='PvF')
        request.update(changes)
        return self.call('create', actor, **request)

    def rows(self):
        return sql(f"SELECT * FROM friend_battle_invites WHERE sender_id IN ('{self.ids}') OR recipient_id IN ('{self.ids}') ORDER BY invite_id")

    def snapshot(self):
        queries = {table: f"SELECT * FROM {table} WHERE player_id IN ('{self.ids}') ORDER BY id"
                   for table in ('users', 'owned_items', 'owned_morties', 'decks', 'event_queue')}
        queries['attacks'] = f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.ids}') ORDER BY id"
        queries['battles'] = f"SELECT * FROM battles WHERE player_id IN ('{self.ids}') OR opponent_id IN ('{self.ids}') ORDER BY battle_id"
        queries['friends'] = f"SELECT * FROM friend_list WHERE player_id_a IN ('{self.ids}') OR player_id_b IN ('{self.ids}') ORDER BY id"
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        return json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; $out=[]; foreach(json_decode(base64_decode('" + encoded + "'),true) as $key=>$q) $out[$key]=$pdo->query($q)->fetchAll(); echo json_encode($out);"))

    def error(self, result, status, code):
        self.assertEqual(result, (status, {'error': {'code': code}}))

    def pending(self):
        status, body = self.create()
        self.assertEqual(status, 200, body)
        rows = self.rows()
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row['state'], 'PENDING')
        self.assertEqual((row['sender_id'], row['recipient_id']), (self.a, self.b))
        self.assertEqual(body['battle_invite_id'], row['invite_id'])
        self.assertEqual(body['token'], row['sender_token'])
        self.assertNotEqual(row['sender_token'], row['recipient_token'])
        return body, row

    def test_create_replay_shape_and_preserves_gameplay(self):
        before = self.snapshot()
        body, row = self.pending()
        self.assertEqual(set(body), {'battle_invite_id', 'battle_type', 'battle_invite_ttl', 'token'})
        self.assertEqual(str(uuid.UUID(body['battle_invite_id'])), body['battle_invite_id'])
        self.assertEqual(body['battle_type'], 'PvF')
        self.assertIn(type(body['battle_invite_ttl']), (int, float))
        self.assertGreater(body['battle_invite_ttl'], 0)
        self.assertRegex(body['token'], r'^[0-9a-f]{64}$')
        status, replay = self.create()
        self.assertEqual(status, 200)
        self.assertEqual(replay['battle_invite_id'], body['battle_invite_id'])
        self.assertEqual(replay['token'], body['token'])
        self.assertGreater(replay['battle_invite_ttl'], 0)
        self.assertLessEqual(replay['battle_invite_ttl'], body['battle_invite_ttl'])
        self.assertEqual(self.rows(), [row])
        self.assertEqual(self.snapshot(), before)

    def test_recipient_decline_and_sender_revoke_are_idempotent(self):
        before = self.snapshot()
        for action, actor, key, state in (('response', self.b, 'recipient_token', 'DECLINED'),
                                          ('revoke', self.a, 'sender_token', 'REVOKED')):
            with self.subTest(action=action):
                _, row = self.pending()
                extra = {'accept': False} if action == 'response' else {}
                self.assertEqual(self.call(action, actor, token=row[key], **extra), (200, {'success': True}))
                terminal = self.rows()
                self.assertEqual(next(r for r in terminal if r['invite_id'] == row['invite_id'])['state'], state)
                self.assertEqual(self.call(action, actor, token=row[key], **extra), (200, {'success': True}))
                self.assertEqual(self.rows(), terminal)
                sql(f"DELETE FROM friend_battle_invites WHERE invite_id='{row['invite_id']}'")
        self.assertEqual(self.snapshot(), before)

    def test_accept_unavailable_preserves_pending_invite(self):
        _, row = self.pending()
        before = self.snapshot()
        self.error(self.call('response', self.b, token=row['recipient_token'], accept=True), 501, 'FAILED')
        self.assertEqual(self.rows(), [row])
        self.assertEqual(self.snapshot(), before)

    def test_tokens_are_role_and_account_scoped(self):
        _, row = self.pending()
        for action, actor, key in (('response', self.a, 'sender_token'),
                                   ('response', self.a, 'recipient_token'),
                                   ('response', self.c, 'recipient_token'),
                                   ('revoke', self.b, 'recipient_token'),
                                   ('revoke', self.b, 'sender_token'),
                                   ('revoke', self.c, 'sender_token')):
            with self.subTest(action=action, actor=actor, token=key):
                self.error(self.call(action, actor, token=row[key], accept=False), 403, 'TOKEN_NOTVALID')
                self.assertEqual(self.rows(), [row])
        for action in ('response', 'revoke'):
            self.error(self.call(action, self.b, token='a' * 64, accept=False), 400, 'TOKEN_INVALID')
        self.assertEqual(self.rows(), [row])

    def test_expired_tokens_cannot_decline_accept_or_revoke(self):
        _, row = self.pending()
        sql(f"UPDATE friend_battle_invites SET expires_at=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE invite_id='{row['invite_id']}'")
        before = self.snapshot()
        for action, actor, key, accept in (('response', self.b, 'recipient_token', False),
                                           ('response', self.b, 'recipient_token', True),
                                           ('revoke', self.a, 'sender_token', False)):
            self.error(self.call(action, actor, token=row[key], accept=accept), 410, 'TOKEN_EXPIRED')
        self.assertEqual(self.rows()[0]['state'], 'EXPIRED')
        self.assertEqual(self.snapshot(), before)

    def test_create_requires_accepted_unambiguous_friendship(self):
        for pending in (None, 'true'):
            if pending:
                self.befriend(self.a, self.c, pending)
            self.error(self.create(target=self.c), 400, 'OPPONENT_PLAYER_ID_INVALID')
            self.assertEqual(self.rows(), [])
        self.befriend(self.b, self.a)
        self.error(self.create(), 409, 'FAILED')
        self.assertEqual(self.rows(), [])

    def test_both_users_must_be_in_world(self):
        for actor, code in ((self.a, 'FAILED'), (self.b, 'OPPONENT_STATE_INVALID')):
            sql(f"UPDATE users SET state='BATTLE' WHERE player_id='{actor}'")
            self.error(self.create(), 409, code)
            self.assertEqual(self.rows(), [])
            sql(f"UPDATE users SET state='WORLD' WHERE player_id='{actor}'")

    def test_active_battle_in_either_column_blocks_either_user(self):
        for player, code in ((self.a, 'FAILED'), (self.b, 'OPPONENT_STATE_INVALID')):
            for column in ('player_id', 'opponent_id'):
                with self.subTest(player=player, column=column):
                    battle = str(uuid.uuid4())
                    owner, opponent = (player, self.c) if column == 'player_id' else (self.c, player)
                    sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,state) VALUES ('{battle}','{owner}','{opponent}','ACTIVE')")
                    self.error(self.create(), 409, code)
                    self.assertEqual(self.rows(), [])
                    sql(f"DELETE FROM battles WHERE battle_id='{battle}'")

    def test_one_outgoing_invite_allows_crossed_incoming(self):
        self.befriend(self.a, self.c)
        body, _ = self.pending()
        self.error(self.create(target=self.c), 409, 'SENT_INVITE_PENDING')
        status, reverse = self.create(self.b, self.a)
        self.assertEqual(status, 200, reverse)
        self.assertNotEqual(reverse['battle_invite_id'], body['battle_invite_id'])
        self.assertEqual(len(self.rows()), 2)

    def test_concurrent_same_create_returns_one_pending_row(self):
        barrier = threading.Barrier(2)
        def send(_):
            barrier.wait(timeout=5)
            return self.create()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, range(2)))
        self.assertEqual([r[0] for r in results], [200, 200], results)
        self.assertEqual(results[0][1]['battle_invite_id'], results[1][1]['battle_invite_id'])
        self.assertEqual(results[0][1]['token'], results[1][1]['token'])
        self.assertEqual(len(self.rows()), 1)

    def test_invalid_sessions_types_and_boolean_are_clean_native_errors(self):
        for session in (None, [], {}, 1, '', str(uuid.uuid4())):
            self.error(self.create(session_id=session), 401, 'SESSION_ID_INVALID')
            for action in ('response', 'revoke'):
                self.error(self.call(action, session_id=session, token='a' * 64, accept=False), 401, 'FAILED')
        for kind in (None, [], {}, 1, '', 'PvP', 'PvE'):
            self.error(self.create(battle_type=kind), 400, 'FAILED')
        for target in (None, [], {}, 1, '', self.a, str(uuid.uuid4())):
            self.error(self.create(opponent_player_id=target), 400, 'OPPONENT_PLAYER_ID_INVALID')
        _, row = self.pending()
        for accept in (None, 'true', 'false', 1, 0, [], {}):
            self.error(self.call('response', self.b, token=row['recipient_token'], accept=accept), 400, 'ACCEPT_INVALID')
            self.assertEqual(self.rows(), [row])

    def test_database_insert_failure_rolls_back_and_hides_internals(self):
        before = self.snapshot()
        trigger = 'invite_fault_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON friend_battle_invites FOR EACH ROW BEGIN IF NEW.sender_id='{self.a}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID invite rollback private'; END IF; END")
        try:
            self.error(self.create(), 500, 'FAILED')
            self.assertEqual(self.rows(), [])
            self.assertEqual(self.snapshot(), before)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')

    def test_revoked_and_ambiguous_sessions_cannot_mutate_invite(self):
        _, row = self.pending()
        sql(f"UPDATE users SET session_id='{self.a}' WHERE player_id='{self.c}'")
        self.error(self.create(), 401, 'SESSION_ID_INVALID')
        self.error(self.call('revoke', token=row['sender_token']), 401, 'FAILED')
        self.assertEqual(self.rows(), [row])
        sql(f"UPDATE users SET session_id=NULL WHERE player_id IN ('{self.a}','{self.c}')")
        self.error(self.create(), 401, 'SESSION_ID_INVALID')
        self.error(self.call('revoke', token=row['sender_token']), 401, 'FAILED')
        sql(f"UPDATE users SET session_id=NULL WHERE player_id='{self.b}'")
        self.error(self.call('response', self.b, token=row['recipient_token'], accept=False), 401, 'FAILED')
        self.assertEqual(self.rows(), [row])

    def test_unrelated_concurrent_creates_both_succeed(self):
        self.befriend(self.c, self.d)
        before = self.snapshot()
        barrier = threading.Barrier(2)
        def send(pair):
            barrier.wait(timeout=5)
            return self.create(*pair)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, [(self.a, self.b), (self.c, self.d)]))
        self.assertEqual([r[0] for r in results], [200, 200], results)
        self.assertNotEqual(results[0][1]['battle_invite_id'], results[1][1]['battle_invite_id'])
        self.assertEqual({(r['sender_id'], r['recipient_id'], r['state']) for r in self.rows()},
                         {(self.a, self.b, 'PENDING'), (self.c, self.d, 'PENDING')})
        self.assertEqual(self.snapshot(), before)

    def test_friend_removal_revokes_both_directions_without_changing_saves(self):
        self.pending()
        self.assertEqual(self.create(self.b, self.a)[0], 200)
        before = self.snapshot()
        before.pop('friends')
        status, body = post('/session/friend/remove', {'session_id': self.a, 'player_id': self.b})
        self.assertEqual(status, 200, body)
        terminal = self.rows()
        self.assertEqual(len(terminal), 2)
        self.assertEqual([r['state'] for r in terminal], ['REVOKED', 'REVOKED'])
        after = self.snapshot()
        self.assertEqual(after.pop('friends'), [])
        self.assertEqual(after, before)
        self.error(post('/session/friend/remove', {'session_id': self.b, 'player_id': self.a}),
                   404, 'PLAYER_ID_INVALID')
        self.assertEqual(self.rows(), terminal)
        after = self.snapshot()
        self.assertEqual(after.pop('friends'), [])
        self.assertEqual(after, before)

    def test_concurrent_create_and_friend_remove_cannot_leave_pending_invite(self):
        before = self.snapshot()
        before.pop('friends')
        barrier = threading.Barrier(2)
        def mutate(action):
            barrier.wait(timeout=5)
            if action == 'create':
                return self.create()
            return post('/session/friend/remove', {'session_id': self.b, 'player_id': self.a})
        with ThreadPoolExecutor(max_workers=2) as pool:
            created, removed = list(pool.map(mutate, ['create', 'remove']))
        self.assertEqual(removed[0], 200, removed)
        self.assertIn(created[0], (200, 400), created)
        rows = self.rows()
        if created[0] == 200:
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]['invite_id'], created[1]['battle_invite_id'])
            self.assertEqual(rows[0]['state'], 'REVOKED')
        else:
            self.error(created, 400, 'OPPONENT_PLAYER_ID_INVALID')
            self.assertEqual(rows, [])
        after = self.snapshot()
        self.assertEqual(after.pop('friends'), [])
        self.assertEqual(after, before)

    def test_invite_update_failure_rolls_back_friend_removal_and_decline(self):
        _, row = self.pending()
        before = self.snapshot()
        trigger = 'invite_update_fault_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE UPDATE ON friend_battle_invites FOR EACH ROW BEGIN IF OLD.sender_id='{self.a}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID invitation update rollback private'; END IF; END")
        try:
            self.error(post('/session/friend/remove', {'session_id': self.a, 'player_id': self.b}),
                       500, 'FAILED')
            self.assertEqual(self.rows(), [row])
            self.assertEqual(self.snapshot(), before)
            self.error(self.call('response', self.b, token=row['recipient_token'], accept=False),
                       500, 'FAILED')
            self.assertEqual(self.rows(), [row])
            self.assertEqual(self.snapshot(), before)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')

    def test_slashless_native_posts_preserve_body_without_redirect(self):
        def request(action, body=None, method='POST'):
            url = 'http://127.0.0.1:8087/session/battle-invite/' + action
            req = urllib.request.Request(url, None if body is None else json.dumps(body).encode(),
                                         {'Content-Type': 'application/json'}, method=method)
            try:
                response = urllib.request.urlopen(req, timeout=10)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                self.assertEqual(response.geturl(), url)
                return response.status, json.loads(response.read())

        before = self.snapshot()
        payload = dict(session_id=self.a, opponent_player_id=self.b, battle_type='PvF')
        for terminal in ('response', 'revoke'):
            status, created = request('create', payload)
            self.assertEqual(status, 200, created)
            self.assertEqual(set(created), {'battle_invite_id', 'battle_type', 'battle_invite_ttl', 'token'})
            row = next(r for r in self.rows() if r['invite_id'] == created['battle_invite_id'])
            if terminal == 'response':
                reply = dict(session_id=self.b, token=row['recipient_token'], accept=False)
            else:
                reply = dict(session_id=self.a, token=created['token'])
            self.assertEqual(request(terminal, reply), (200, {'success': True}))
            self.assertEqual(next(r for r in self.rows() if r['invite_id'] == row['invite_id'])['state'],
                             'DECLINED' if terminal == 'response' else 'REVOKED')
        terminal_rows = self.rows()
        for action in ('create', 'response', 'revoke'):
            self.error(request(action, method='GET'), 405, 'FAILED')
        self.assertEqual(self.rows(), terminal_rows)
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

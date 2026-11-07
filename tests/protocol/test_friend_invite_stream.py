"""Global invitation SSE using additive UUID fixtures; never reseeds data."""
import base64
import json
import unittest
import urllib.request
import uuid

from test_http import php, sql


class FriendInviteStreamTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.players = [str(uuid.uuid4()) for _ in range(3)]
        self.a, self.b, self.c = self.players
        self.invite = str(uuid.uuid4())
        self.battle = str(uuid.uuid4())
        self.sender_token, self.recipient_token = uuid.uuid4().hex * 2, uuid.uuid4().hex * 2
        self.addCleanup(self.cleanup)
        for player in self.players:
            sql(f"INSERT INTO users (secret,player_id,session_id,username,state,tags,room_id,level,player_avatar_id) "
                f"VALUES ('{player}','{player}','{player}','InviteStream','WORLD','[]','0',7,'RickDefault')")
        sql(f"INSERT INTO friend_list (player_id_a,player_id_b,pending,direction,created,modified) "
            f"VALUES ('{self.a}','{self.b}','false','true',NOW(),NOW())")
        sql(f"INSERT INTO friend_battle_invites (invite_id,sender_id,recipient_id,sender_token,recipient_token,state,created_at,expires_at,updated_at) "
            f"VALUES ('{self.invite}','{self.a}','{self.b}','{self.sender_token}','{self.recipient_token}',"
            "'PENDING',UTC_TIMESTAMP(6),DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 60 SECOND),UTC_TIMESTAMP(6))")

    def cleanup(self):
        sql(f"DELETE FROM battles WHERE battle_id='{self.battle}'")
        sql(f"DELETE FROM friend_battle_invites WHERE invite_id='{self.invite}'")
        for player in self.players:
            sql(f"DELETE FROM friend_list WHERE player_id_a='{player}' OR player_id_b='{player}'")
            sql(f"DELETE FROM users WHERE player_id='{player}'")

    def invoke(self, code):
        return json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                              "require '/var/www/html/lib/friend_invite_stream.php'; $seen=[]; " + code))

    def poll(self, player):
        return self.invoke(f"echo json_encode(friend_battle_invite_events($pdo,'{player}','{player}',$seen));")

    def test_recipient_rehydrates_once_per_connection_without_sender_token(self):
        first, second = self.invoke(f"$a=friend_battle_invite_events($pdo,'{self.b}','{self.b}',$seen); "
                                   f"$b=friend_battle_invite_events($pdo,'{self.b}','{self.b}',$seen); echo json_encode([$a,$b]);")
        self.assertEqual(second, [])
        self.assertEqual(self.poll(self.a), [])
        self.assertEqual(self.poll(self.c), [])
        self.assertEqual(first[0]['event'], 'battle-invite:received')
        payload = first[0]['payload']
        self.assertEqual(set(payload), {'battle_invite_id', 'battle_type', 'battle_invite_ttl', 'from_player', 'token'})
        self.assertEqual(payload['battle_invite_id'], self.invite)
        self.assertEqual(payload['battle_type'], 'PvF')
        self.assertGreater(payload['battle_invite_ttl'], 0)
        self.assertLessEqual(payload['battle_invite_ttl'], 60)
        self.assertEqual(payload['token'], self.recipient_token)
        self.assertNotIn(self.sender_token, json.dumps(first))
        self.assertEqual(payload['from_player'], {'player_id': self.a, 'username': 'InviteStream',
                                                'player_avatar_id': 'RickDefault', 'level': 7})
        self.assertEqual(len(self.poll(self.b)), 1)

    def test_terminals_repeat_only_once_per_second_and_never_start_battle(self):
        for state in ('DECLINED', 'REVOKED', 'EXPIRED'):
            sql(f"UPDATE friend_battle_invites SET state='{state}',updated_at=UTC_TIMESTAMP(6) WHERE invite_id='{self.invite}'")
            for actor, event in ((self.a, 'battle-invite:declined'), (self.b, 'battle-invite:revoked')):
                result = self.invoke(f"$a=friend_battle_invite_events($pdo,'{actor}','{actor}',$seen); "
                                     f"$b=friend_battle_invite_events($pdo,'{actor}','{actor}',$seen); "
                                     "usleep(1050000); "
                                     f"$c=friend_battle_invite_events($pdo,'{actor}','{actor}',$seen); echo json_encode([$a,$b,$c]);")
                expected = [{'event': event, 'payload': {'battle_invite_id': self.invite}}]
                self.assertEqual(result, [expected, [], expected])

    def test_effective_expiry_is_read_only_and_recent_terminal_prunes(self):
        sql(f"UPDATE friend_battle_invites SET expires_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 1 SECOND),"
            f"updated_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 60 SECOND) WHERE invite_id='{self.invite}'")
        self.assertEqual(self.poll(self.b), [{'event': 'battle-invite:revoked', 'payload': {'battle_invite_id': self.invite}}])
        self.assertEqual(sql(f"SELECT state FROM friend_battle_invites WHERE invite_id='{self.invite}'")[0]['state'], 'PENDING')
        sql(f"UPDATE friend_battle_invites SET expires_at=DATE_SUB(UTC_TIMESTAMP(6),INTERVAL 10 SECOND) WHERE invite_id='{self.invite}'")
        result = self.invoke(f"$seen['{self.invite}']=['received'=>true,'until'=>microtime(true)-1]; "
                             f"$events=friend_battle_invite_events($pdo,'{self.b}','{self.b}',$seen); echo json_encode([$events,$seen]);")
        self.assertEqual(result, [[], []])

    def test_friend_removal_and_world_state_suppress_pending_received(self):
        sql(f"UPDATE users SET state='BATTLE' WHERE player_id='{self.a}'")
        self.assertEqual(self.poll(self.b), [])
        sql(f"UPDATE users SET state='WORLD' WHERE player_id='{self.a}'")
        sql(f"DELETE FROM friend_list WHERE player_id_a='{self.a}' AND player_id_b='{self.b}'")
        self.assertEqual(self.poll(self.b), [])

    def test_active_battle_claim_on_either_side_suppresses_received(self):
        for participant in (self.a, self.b):
            for owner, opponent in ((participant, self.c), (self.c, participant)):
                sql(f"DELETE FROM battles WHERE battle_id='{self.battle}'")
                sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,state) "
                    f"VALUES ('{self.battle}','{owner}','{opponent}','ACTIVE')")
                self.assertEqual(self.poll(self.b), [])

    def test_roomless_stream_delivers_after_session_start_without_room_cursor(self):
        token = base64.urlsafe_b64encode(json.dumps({'session_id': self.b}).encode()).decode().rstrip('=')
        events = []
        with urllib.request.urlopen(f'http://127.0.0.1:8087/sse/?token=e30.{token}.test', timeout=5) as stream:
            event = None
            for _ in range(12):
                line = stream.readline().decode().strip()
                if line.startswith('event: '):
                    event = line[7:]
                elif line.startswith('data: '):
                    events.append((event, json.loads(line[6:])))
                    if event == 'battle-invite:received':
                        break
        self.assertEqual([event for event, _ in events], ['session:start', 'battle-invite:received'])
        self.assertEqual(events[-1][1]['battle_invite_id'], self.invite)
        self.assertEqual(sql(f"SELECT COALESCE(last_event_id,0) AS event_cursor FROM users WHERE player_id='{self.b}'")[0]['event_cursor'], 0)

    def test_session_is_revalidated_on_every_poll(self):
        result = self.invoke(f"friend_battle_invite_events($pdo,'{self.b}','{self.b}',$seen); "
                             f"$pdo->exec(\"UPDATE users SET session_id='revoked-{self.b}' WHERE player_id='{self.b}'\"); "
                             f"try {{ friend_battle_invite_events($pdo,'{self.b}','{self.b}',$seen); echo 'false'; }} "
                             "catch (FriendError $error) { echo json_encode($error->status); }")
        self.assertEqual(result, 401)

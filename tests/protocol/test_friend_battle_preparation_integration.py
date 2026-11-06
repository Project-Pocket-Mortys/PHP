"""Roomless SSE and optional CLI preparation expiry with additive UUID fixtures."""
import base64
import json
import subprocess
import time
import unittest
import urllib.error
import urllib.request
import uuid

from test_http import COMPOSE, ROOT, php, sql


class FriendBattlePreparationIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_DB_NAME');"), 'db:pocket_mortys')
        self.a, self.b = str(uuid.uuid4()), str(uuid.uuid4())
        self.invite = str(uuid.uuid4())
        self.invites = [self.invite]
        self.sender_token, self.recipient_token = uuid.uuid4().hex * 2, uuid.uuid4().hex * 2
        self.addCleanup(self.cleanup)
        for player in (self.a, self.b):
            sql(f"INSERT INTO users (secret,player_id,session_id,username,state,tags,room_id,level,player_avatar_id) "
                f"VALUES ('{player}','{player}','{player}','PreparationIntegration','WORLD','[]','0',7,'RickDefault')")
        sql(f"INSERT INTO friend_list (player_id_a,player_id_b,pending,direction,created,modified) "
            f"VALUES ('{self.a}','{self.b}','false','true',NOW(),NOW())")
        sql("INSERT INTO friend_battle_invites "
            "(invite_id,sender_id,recipient_id,sender_token,recipient_token,state,created_at,expires_at,updated_at) "
            f"VALUES ('{self.invite}','{self.a}','{self.b}','{self.sender_token}','{self.recipient_token}',"
            "'PENDING',UTC_TIMESTAMP(6),DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 60 SECOND),UTC_TIMESTAMP(6))")
        self.battle = php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                          "require '/var/www/html/lib/friend_battle_membership.php'; "
                          f"echo friend_battle_reserve($pdo,'{self.b}','{self.recipient_token}');")

    def cleanup(self):
        sql(f"DELETE FROM friend_battle_memberships WHERE player_id IN ('{self.a}','{self.b}')")
        for invite in self.invites:
            sql(f"DELETE FROM friend_battle_sessions WHERE invite_id='{invite}'")
            sql(f"DELETE FROM friend_battle_invites WHERE invite_id='{invite}'")
        sql(f"DELETE FROM friend_list WHERE player_id_a IN ('{self.a}','{self.b}') OR player_id_b IN ('{self.a}','{self.b}')")
        sql(f"DELETE FROM users WHERE player_id IN ('{self.a}','{self.b}')")

    def due(self):
        sql(f"UPDATE friend_battle_sessions SET prepare_deadline=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE battle_id='{self.battle}'")

    def session(self):
        return sql(f"SELECT * FROM friend_battle_sessions WHERE battle_id='{self.battle}'")[0]

    def claims(self):
        return sql(f"SELECT * FROM friend_battle_memberships WHERE player_id IN ('{self.a}','{self.b}') ORDER BY player_id")

    def stream(self, session):
        token = base64.urlsafe_b64encode(json.dumps({'session_id': session}).encode()).decode().rstrip('=')
        return urllib.request.urlopen(f'http://127.0.0.1:8087/sse/?token=e30.{token}.test', timeout=5)

    def next_event(self, stream):
        event = None
        while True:
            line = stream.readline()
            if not line:
                return None
            line = line.decode().strip()
            if line.startswith('event: '):
                event = line[7:]
            elif line.startswith('data: '):
                return event, json.loads(line[6:])

    def assert_cancelled(self):
        self.assertEqual(self.session()['state'], 'CANCELLED')
        self.assertEqual(self.session()['cancel_reason'], 'PREPARATION_TIMEOUT')
        self.assertEqual(self.claims(), [])
        self.assertEqual(sql(f"SELECT state,room_id FROM users WHERE player_id IN ('{self.a}','{self.b}')"),
                         [{'state': 'WORLD', 'room_id': '0'}] * 2)
        self.assertEqual(sql(f"SELECT battle_id FROM battles WHERE battle_id='{self.battle}'"), [])
        self.assertEqual(sql(f"SELECT id FROM event_queue WHERE player_id IN ('{self.a}','{self.b}')"), [])

    def test_waiting_room_cleanup_precedes_invitation_projection(self):
        # No room/world loop is entered. A pending invitation becomes eligible
        # only after this connection releases the expired shared claims.
        with self.stream(self.b) as stream:
            self.assertEqual(self.next_event(stream)[0], 'session:start')
            # Let the initial poll complete while the deadline is still future,
            # then exercise cleanup from the waiting-room polling loop.
            time.sleep(1.1)
            self.due()
            event, payload = self.next_event(stream)
            self.assertEqual(event, 'battle-invite:received')
            self.assertEqual(payload['battle_invite_id'], self.invite)
            self.assert_cancelled()
            sql(f"UPDATE users SET session_id='{uuid.uuid4()}' WHERE player_id='{self.b}'")

    def test_revoked_waiting_stream_cannot_release_newer_session_claims(self):
        with self.stream(self.b) as stream:
            self.assertEqual(self.next_event(stream)[0], 'session:start')
            newer = str(uuid.uuid4())
            sql(f"UPDATE users SET session_id='{newer}' WHERE player_id='{self.b}'")
            # Replace the old preparation through its normal internal cancel
            # and reserve operations after the new session takes ownership.
            php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                "require '/var/www/html/lib/friend_battle_membership.php'; "
                f"friend_battle_cancel_reservation($pdo,'{newer}','{self.battle}');")
            fresh_invite, fresh_token = str(uuid.uuid4()), uuid.uuid4().hex * 2
            self.invites.append(fresh_invite)
            sql("INSERT INTO friend_battle_invites "
                "(invite_id,sender_id,recipient_id,sender_token,recipient_token,state,created_at,expires_at,updated_at) "
                f"VALUES ('{fresh_invite}','{self.a}','{self.b}','{uuid.uuid4().hex * 2}','{fresh_token}',"
                "'PENDING',UTC_TIMESTAMP(6),DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 60 SECOND),UTC_TIMESTAMP(6))")
            self.battle = php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                              "require '/var/www/html/lib/friend_battle_membership.php'; "
                              f"echo friend_battle_reserve($pdo,'{newer}','{fresh_token}');")
            self.due()
            before = self.session(), self.claims()
            self.assertIsNone(self.next_event(stream))
            self.assertEqual((self.session(), self.claims()), before)
        # The new session retains authority to clear its own due reservation.
        with self.stream(newer) as stream:
            self.assertEqual(self.next_event(stream)[0], 'session:start')
            self.assertEqual(self.next_event(stream)[0], 'battle-invite:received')
            self.assert_cancelled()
            sql(f"UPDATE users SET session_id='{uuid.uuid4()}' WHERE player_id='{self.b}'")

    def test_optional_cli_once_cleans_without_protocol_or_http_exposure(self):
        self.due()
        result = subprocess.run(COMPOSE + ['exec', '-T', 'web', 'php',
            '/var/www/html/tools/research/server/friend-battle-preparations.php', '--once'],
            cwd=ROOT, text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'Expired 1 friend battle preparations\n')
        self.assertEqual(result.stderr, '')
        self.assert_cancelled()
        try:
            response = urllib.request.urlopen(
                'http://127.0.0.1:8087/tools/research/server/friend-battle-preparations.php', timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            self.assertIn(response.status, (403, 404))


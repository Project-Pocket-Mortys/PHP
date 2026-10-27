"""Session revocation on live streams, using only disposable accounts."""
import base64
import json
import unittest
import urllib.request
import uuid

from test_http import php, sql


class SessionStreamTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.player, self.session, self.room = [str(uuid.uuid4()) for _ in range(3)]
        self.addCleanup(self.cleanup)
        sql(f"INSERT INTO users (secret, player_id, session_id, username, room_id, state, tags) "
            f"VALUES ('{self.player}', '{self.player}', '{self.session}', 'SessionTest', '{self.room}', 'WORLD', '[]')")

    def cleanup(self):
        sql(f"DELETE FROM event_queue WHERE room_id='{self.room}'")
        sql(f"DELETE FROM users WHERE player_id='{self.player}'")

    def connect(self, session):
        payload = base64.urlsafe_b64encode(json.dumps({'session_id': session}).encode()).decode().rstrip('=')
        stream = urllib.request.urlopen(
            f'http://127.0.0.1:8087/sse/?since=0&token=e30.{payload}.synthetic', timeout=3)
        self.addCleanup(stream.close)
        self.assertEqual(stream.readline().strip(), b'event: session:start')
        self.assertEqual(json.loads(stream.readline()[6:])['session_id'], session)
        self.assertEqual(stream.readline().strip(), b'')
        return stream

    def revoke(self, waiting, delete):
        if waiting:
            sql(f"UPDATE users SET room_id=NULL WHERE player_id='{self.player}'")
        stream = self.connect(self.session)
        replacement = str(uuid.uuid4())
        if delete:
            sql(f"DELETE FROM users WHERE player_id='{self.player}'")
        else:
            sql(f"UPDATE users SET session_id='{replacement}' WHERE player_id='{self.player}'")
        sql(f"INSERT INTO event_queue (room_id, event_name, player_id) "
            f"VALUES ('{self.room}', 'room:user-removed', '{self.player}')")
        # EOF, not another keepalive or an application-specific invented error.
        self.assertEqual(stream.readline(), b'')
        if not delete:
            sql(f"DELETE FROM event_queue WHERE room_id='{self.room}'")
            fresh = self.connect(replacement)
            sql(f"DELETE FROM users WHERE player_id='{self.player}'")
            self.assertEqual(fresh.readline(), b'')

    def test_rotation_closes_room_stream_and_new_session_connects(self):
        self.revoke(waiting=False, delete=False)

    def test_deletion_closes_room_stream(self):
        self.revoke(waiting=False, delete=True)

    def test_rotation_closes_waiting_stream_and_new_session_connects(self):
        self.revoke(waiting=True, delete=False)

    def test_deletion_closes_waiting_stream(self):
        self.revoke(waiting=True, delete=True)


if __name__ == '__main__':
    unittest.main()

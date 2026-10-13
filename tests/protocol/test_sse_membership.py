"""Isolated room fixtures: never reseed or modify the emulator account."""
import base64
import json
import unittest
import urllib.request
import uuid

from test_http import php, sql


class MembershipTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.room = str(uuid.uuid4())
        self.a, self.b = str(uuid.uuid4()), str(uuid.uuid4())
        self.addCleanup(self.cleanup)
        for player, name, level in ((self.a, 'Observer', 2), (self.b, 'Visitor', 7)):
            sql(f"INSERT INTO users (secret, player_id, session_id, username, room_id, level, state, tags) "
                f"VALUES ('{player}', '{player}', '{player}', '{name}', '{self.room}', {level}, 'WORLD', '[]')")

    def cleanup(self):
        sql(f"DELETE FROM event_queue WHERE room_id='{self.room}'")
        sql(f"DELETE FROM users WHERE player_id IN ('{self.a}', '{self.b}')")

    def publish(self, event):
        php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
            "require '/var/www/html/lib/events.php'; "
            f"publish_event($pdo, '{self.room}', '{event}', "
            f"['room_id'=>'{self.room}', 'player_id'=>'{self.b}', 'state'=>'WORLD']);")
        return sql(f"SELECT MAX(id) AS id FROM event_queue WHERE room_id='{self.room}'")[0]['id']

    def read_events(self, terminal, since=0):
        payload = base64.urlsafe_b64encode(json.dumps({'session_id': self.a}).encode()).decode().rstrip('=')
        url = f'http://127.0.0.1:8087/sse/?since={since}&token=e30.{payload}.synthetic'
        events = []
        with urllib.request.urlopen(url, timeout=5) as stream:
            event = None
            for _ in range(60):
                line = stream.readline().decode().strip()
                if line.startswith('event: '):
                    event = line[7:]
                elif line.startswith('data: '):
                    events.append((event, json.loads(line[6:])))
                    if event == terminal:
                        return events
        self.fail('Expected SSE event was not received')

    def test_arrival_describes_subject_not_subscriber(self):
        self.publish('room:user-added')
        events = self.read_events('room:user-added')
        self.assertEqual(events[0][0], 'session:start')
        self.assertEqual(events[0][1]['player_id'], self.a)
        body = events[-1][1]
        self.assertEqual((body['player_id'], body['username'], body['level']), (self.b, 'Visitor', 7))
        self.assertEqual(body['owned_morties'], [])

    def test_departure_describes_subject_even_after_account_removed(self):
        self.publish('room:user-removed')
        sql(f"DELETE FROM users WHERE player_id='{self.b}'")
        self.assertEqual(self.read_events('room:user-removed')[-1][1], {'player_id': self.b})

    def test_explicit_cursor_replays_only_later_membership_event(self):
        cursor = self.publish('room:user-added')
        self.publish('room:user-removed')
        events = self.read_events('room:user-removed', cursor)
        self.assertEqual([event for event, _ in events], ['session:start', 'room:user-removed'])
        self.assertEqual(events[-1][1], {'player_id': self.b})

    def test_deleted_arrival_subject_does_not_impersonate_subscriber(self):
        self.publish('room:user-added')
        self.publish('room:user-removed')
        sql(f"DELETE FROM users WHERE player_id='{self.b}'")
        events = self.read_events('room:user-removed')
        self.assertEqual([event for event, _ in events], ['session:start', 'room:user-removed'])


if __name__ == '__main__':
    unittest.main()

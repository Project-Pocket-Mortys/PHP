"""Room transitions on one live stream; additive isolated fixtures only."""
import base64
import json
import queue
import threading
import time
import unittest
import urllib.request
import uuid

from test_http import php, post, sql


class RoomStreamTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.player, self.session = str(uuid.uuid4()), str(uuid.uuid4())
        self.rooms = [str(uuid.uuid4()) for _ in range(2)]
        self.worlds = [str(uuid.uuid4()) for _ in range(2)]
        self.events = queue.Queue()
        self.reader = None
        self.addCleanup(self.cleanup)
        for room, world in zip(self.rooms, self.worlds):
            sql(f"INSERT INTO room_ids (room_id, world_id, zone_id) VALUES ('{room}', '{world}', '[1,1]')")
        sql(f"INSERT INTO users (secret, player_id, session_id, username, room_id, state, tags) "
            f"VALUES ('{self.player}', '{self.player}', '{self.session}', 'RoomTest', '{self.rooms[0]}', 'WORLD', '[]')")
        token = base64.urlsafe_b64encode(json.dumps({'session_id': self.session}).encode()).decode().rstrip('=')
        self.stream = urllib.request.urlopen(
            f'http://127.0.0.1:8087/sse/?since=0&token=e30.{token}.synthetic', timeout=5)
        self.reader = threading.Thread(target=self.read_stream, daemon=True)
        self.reader.start()
        self.assertEqual(self.next_event()[0], 'session:start')
        self.marker(self.rooms[0], 'initial')
        self.assertEqual(self.next_event(), ('room:user-removed', {'player_id': 'initial'}))

    def read_stream(self):
        try:
            event = None
            for line in self.stream:
                line = line.decode().strip()
                if line.startswith('event: '):
                    event = line[7:]
                elif line.startswith('data: '):
                    self.events.put((event, json.loads(line[6:])))
        except Exception as error:
            self.events.put(('reader-error', type(error).__name__))

    def cleanup(self):
        sql(f"DELETE FROM users WHERE player_id='{self.player}'")
        if self.reader:
            self.reader.join(timeout=6)
            self.stream.close()
        for room in self.rooms:
            sql(f"DELETE FROM event_queue WHERE room_id='{room}'")
            sql(f"DELETE FROM room_ids WHERE room_id='{room}'")

    def marker(self, room, subject):
        sql(f"INSERT INTO event_queue (room_id, event_name, player_id) "
            f"VALUES ('{room}', 'room:user-removed', '{subject}')")

    def next_event(self):
        return self.events.get(timeout=3)

    def join(self, index):
        status, body = post('/session/join-room', {'session_id': self.session, 'world_id': self.worlds[index]})
        self.assertEqual(status, 200)
        self.assertEqual(body['room_id'], self.rooms[index])
        event, payload = self.next_event()
        self.assertEqual((event, payload.get('player_id')), ('room:user-added', self.player))

    def test_leave_suspends_old_room_and_join_rebinds_same_stream(self):
        self.assertEqual(post('/session/leave-room', {'session_id': self.session}), (200, {'success': True}))
        time.sleep(0.6)
        self.marker(self.rooms[0], 'old-room-private-marker')
        with self.assertRaises(queue.Empty):
            self.events.get(timeout=0.7)
        self.marker(self.rooms[1], 'historical-destination-marker')
        self.join(1)
        self.marker(self.rooms[1], 'new-room-marker')
        self.assertEqual(self.next_event(), ('room:user-removed', {'player_id': 'new-room-marker'}))

    def test_direct_room_change_uses_destination_baseline(self):
        self.marker(self.rooms[1], 'historical-destination-marker')
        self.join(1)
        self.marker(self.rooms[0], 'old-room-private-marker')
        self.marker(self.rooms[1], 'new-room-marker')
        self.assertEqual(self.next_event(), ('room:user-removed', {'player_id': 'new-room-marker'}))

    def test_return_to_previous_room_does_not_replay_history(self):
        self.join(1)
        self.marker(self.rooms[0], 'while-away-marker')
        self.join(0)
        self.marker(self.rooms[0], 'returned-marker')
        self.assertEqual(self.next_event(), ('room:user-removed', {'player_id': 'returned-marker'}))


if __name__ == '__main__':
    unittest.main()

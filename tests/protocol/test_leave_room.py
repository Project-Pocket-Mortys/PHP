"""Additive room-leave regressions; keep emulator accounts intact."""
from concurrent.futures import ThreadPoolExecutor
import unittest
import uuid

from test_http import php, post, sql


class LeaveRoomTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.room, self.player, self.session = [str(uuid.uuid4()) for _ in range(3)]
        self.addCleanup(self.cleanup)
        sql(f"INSERT INTO users (secret, player_id, session_id, username, room_id, state, tags) "
            f"VALUES ('{self.session}', '{self.player}', '{self.session}', 'LeaveTest', '{self.room}', 'WORLD', '[]')")

    def cleanup(self):
        sql(f"DELETE FROM event_queue WHERE player_id='{self.player}'")
        sql(f"DELETE FROM users WHERE player_id='{self.player}'")

    def leave(self):
        return post('/session/leave-room', {'session_id': self.session})

    def rows(self):
        return sql(f"SELECT room_id, player_id, event_name FROM event_queue WHERE player_id='{self.player}'")

    def test_leave_clears_membership_and_emits_subject_in_old_room(self):
        self.assertEqual(self.leave(), (200, {'success': True}))
        self.assertEqual(sql(f"SELECT room_id FROM users WHERE player_id='{self.player}'"), [{'room_id': None}])
        self.assertEqual(self.rows(), [{'room_id':self.room,'player_id':self.player,'event_name':'room:user-removed'}])

    def test_concurrent_retries_emit_only_one_departure(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self.leave(), range(2)))
        self.assertEqual(results, [(200, {'success':True})] * 2)
        self.assertEqual(len(self.rows()), 1)

    def test_already_outside_room_acknowledges_without_event(self):
        sql(f"UPDATE users SET room_id=NULL WHERE player_id='{self.player}'")
        self.assertEqual(self.leave(), (200, {'success':True}))
        self.assertEqual(self.rows(), [])

    def test_invalid_session_does_not_change_room_or_emit_event(self):
        status, _ = post('/session/leave-room', {'session_id': str(uuid.uuid4())})
        self.assertEqual(status, 404)
        self.assertEqual(sql(f"SELECT room_id FROM users WHERE player_id='{self.player}'"), [{'room_id':self.room}])
        self.assertEqual(self.rows(), [])

    def test_event_insert_failure_rolls_back_membership_change(self):
        # A temporary fault scoped to this synthetic player; never affects the emulator.
        trigger = 'research_leave_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON event_queue FOR EACH ROW "
            f"BEGIN IF NEW.player_id = '{self.player}' THEN "
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Research fault injection'; END IF; END")
        self.assertEqual(self.leave(), (500, {'success':False, 'error':'Unable to leave room'}))
        self.assertEqual(sql(f"SELECT room_id FROM users WHERE player_id='{self.player}'"), [{'room_id':self.room}])
        self.assertEqual(self.rows(), [])


if __name__ == '__main__':
    unittest.main()

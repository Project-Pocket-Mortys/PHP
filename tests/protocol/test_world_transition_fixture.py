"""Additive world-transition fixture checks; never reseed or touch client accounts."""
import subprocess
import unittest
import uuid

from test_http import COMPOSE, ROOT, php, sql


class WorldTransitionFixtureTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_DB_NAME').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:pocket_mortys:http://localhost:8087')
        if php("echo file_exists('/tmp/pm-world-transition.json') ? 'yes' : 'no';") == 'yes':
            self.skipTest('An existing transition snapshot must be restored before these checks')
        if sql("SELECT id FROM room_ids WHERE world_id='2'"):
            self.skipTest('An existing world-2 room prevents isolated fixture checks')
        self.players = [str(uuid.uuid4()) for _ in range(2)]
        self.names = ['Transition_' + player.replace('-', '') for player in self.players]
        self.guard_room = str(uuid.uuid4())
        self.addCleanup(self.cleanup)
        for name, player in zip(self.names, self.players):
            sql("INSERT INTO users (secret, player_id, session_id, username, level, xp, coins) "
                f"VALUES ('{player}', '{player}', '{player}', '{name}', 1, 17, 23)")

    def command(self, mode):
        return subprocess.run(COMPOSE + ['exec', '-T', 'web', 'php',
                              '/var/www/html/tools/research/server/seed-world-transition.php',
                              mode, '--players=' + ','.join(self.names)],
                              cwd=ROOT, text=True, capture_output=True)

    def cleanup(self):
        # If a test failed after apply, leave only these synthetic players and restore.
        for player in self.players:
            sql(f"UPDATE users SET room_id=NULL WHERE player_id='{player}'")
        result = self.command('--restore')
        self.assertEqual(result.returncode, 0, result.stderr)
        sql(f"DELETE FROM room_ids WHERE room_id='{self.guard_room}' AND world_id='2'")
        sql(f"DELETE FROM event_queue WHERE room_id='{self.guard_room}'")
        for player in self.players:
            sql(f"DELETE FROM users WHERE player_id='{player}'")

    def levels(self):
        return [row['level'] for row in sql(
            "SELECT level FROM users WHERE player_id IN ('" + "','".join(self.players) + "') ORDER BY id")]

    def test_apply_repeat_guard_and_restore(self):
        baseline = sql("SELECT id, player_id, username, level, xp, coins, session_id, last_seen FROM users "
                       "WHERE player_id IN ('" + "','".join(self.players) + "') ORDER BY id")
        result = self.command('--apply')
        self.assertEqual(result.returncode, 0, result.stderr)
        rooms = sql("SELECT * FROM room_ids WHERE world_id='2'")
        self.assertEqual(len(rooms), 1)
        room = rooms[0]
        self.assertEqual((room['room_udp_host'], room['room_udp_port'], room['zone_id']),
                         ('10.0.2.2', '5055', '[1,1]'))
        self.assertEqual(uuid.UUID(room['room_id']).version, 4)
        self.assertEqual(self.levels(), [5, 5])
        self.assertEqual(self.command('--apply').returncode, 0)
        self.assertEqual(sql("SELECT * FROM room_ids WHERE world_id='2'"), rooms)
        sql(f"INSERT INTO event_queue (room_id, event_name) VALUES ('{room['room_id']}', 'fixture:test'), "
            f"('{self.guard_room}', 'fixture:unrelated')")
        sql(f"UPDATE users SET room_id='{room['room_id']}' WHERE player_id='{self.players[0]}'")
        result = self.command('--restore')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('still in the fixture room', result.stderr)
        self.assertEqual(self.levels(), [5, 5])
        sql(f"UPDATE users SET room_id=NULL, last_seen=last_seen WHERE player_id='{self.players[0]}'")
        result = self.command('--restore')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.levels(), [1, 1])
        self.assertEqual(sql("SELECT * FROM room_ids WHERE world_id='2'"), [])
        self.assertEqual(sql(f"SELECT id FROM event_queue WHERE room_id='{room['room_id']}'"), [])
        self.assertEqual(len(sql(f"SELECT id FROM event_queue WHERE room_id='{self.guard_room}'")), 1)
        # Ignore last_seen here because the simulated room entry above legitimately updates it.
        restored = sql("SELECT id, player_id, username, level, xp, coins, session_id, last_seen FROM users "
                       "WHERE player_id IN ('" + "','".join(self.players) + "') ORDER BY id")
        self.assertEqual([{k: v for k, v in row.items() if k != 'last_seen'} for row in restored],
                         [{k: v for k, v in row.items() if k != 'last_seen'} for row in baseline])
        self.assertEqual(self.command('--restore').returncode, 0)

    def test_refuses_existing_world_two_and_noninitial_level(self):
        sql(f"INSERT INTO room_ids (room_id, world_id, zone_id) VALUES ('{self.guard_room}', '2', '[1,1]')")
        result = self.command('--apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('existing world-2 room', result.stderr)
        self.assertEqual(self.levels(), [1, 1])
        sql(f"DELETE FROM room_ids WHERE room_id='{self.guard_room}' AND world_id='2'")
        sql(f"UPDATE users SET level=2 WHERE player_id='{self.players[0]}'")
        result = self.command('--apply')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('original level exactly 1', result.stderr)
        self.assertEqual(sql("SELECT id FROM room_ids WHERE world_id='2'"), [])


if __name__ == '__main__':
    unittest.main()

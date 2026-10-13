"""Research-only heartbeat persistence and additive migration checks."""
import subprocess
import unittest
import uuid

from test_http import COMPOSE, ROOT, php, post, sql


class HeartbeatTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_RESEARCH_HEARTBEATS');"), 'db:1')
        self.player, self.session, self.room = [str(uuid.uuid4()) for _ in range(3)]
        self.addCleanup(self.cleanup)
        sql(f"INSERT INTO room_ids (room_id, world_id, zone_id) VALUES ('{self.room}', 'heartbeat-test', '[1,1]')")
        sql(f"INSERT INTO users (secret, player_id, session_id, room_id, state) "
            f"VALUES ('{self.player}', '{self.player}', '{self.session}', '{self.room}', 'WORLD')")

    def cleanup(self):
        sql(f"DELETE FROM users WHERE player_id='{self.player}'")
        sql(f"DELETE FROM room_ids WHERE room_id='{self.room}'")

    def rows(self):
        return sql(f"SELECT h.session_id, h.room_id FROM research_client_heartbeats h "
                   f"JOIN users u ON u.id=h.user_id WHERE u.player_id='{self.player}'")

    def ping(self, session=None):
        self.assertEqual(post('/session/ping-dynamic', {'session_id': session or self.session, 'type': 'DEFAULT'}),
                         (200, {'success': True}))

    def test_valid_ping_upserts_one_current_session_and_room(self):
        self.ping(); self.ping()
        self.assertEqual(self.rows(), [{'session_id': self.session, 'room_id': self.room}])

    def test_invalid_or_malformed_session_does_not_record_heartbeat(self):
        self.ping(str(uuid.uuid4()))
        for body in ({}, {'session_id': []}, {'session_id': 5}):
            self.assertEqual(post('/session/ping-dynamic', body), (200, {'success': True}))
        self.assertEqual(self.rows(), [])

    def test_rotated_session_cannot_refresh_previous_heartbeat(self):
        self.ping()
        sql(f"UPDATE research_client_heartbeats h JOIN users u ON u.id=h.user_id "
            f"SET h.received_at='2000-01-01' WHERE u.player_id='{self.player}'")
        replacement = str(uuid.uuid4())
        sql(f"UPDATE users SET session_id='{replacement}' WHERE player_id='{self.player}'")
        self.ping()
        self.assertEqual(sql(f"SELECT YEAR(h.received_at) AS year FROM research_client_heartbeats h "
                             f"JOIN users u ON u.id=h.user_id WHERE u.player_id='{self.player}'"), [{'year': 2000}])
        self.ping(replacement)
        self.assertEqual(self.rows(), [{'session_id': replacement, 'room_id': self.room}])

    def test_outside_room_or_non_world_ping_does_not_register(self):
        sql(f"UPDATE users SET state='BATTLE' WHERE player_id='{self.player}'")
        self.ping(); self.assertEqual(self.rows(), [])
        sql(f"UPDATE users SET state='WORLD', room_id=NULL WHERE player_id='{self.player}'")
        self.ping(); self.assertEqual(self.rows(), [])


class HeartbeatMigrationTests(unittest.TestCase):
    def test_migration_is_additive_repeatable_and_cascades_on_schema_copy(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_DB_NAME');"), 'db:pocket_mortys')
        database = 'research_migration_' + uuid.uuid4().hex
        def mysql(statement):
            return subprocess.check_output(COMPOSE + ['exec', '-T', 'db', 'sh', '-c',
                'exec mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --batch --skip-column-names'],
                input=statement, text=True, cwd=ROOT)
        mysql(f'CREATE DATABASE {database};')
        try:
            mysql(f'USE {database};\n' + (ROOT/'pocket_mortys.sql').read_text())
            before = mysql(f'USE {database}; SHOW CREATE TABLE users;')
            migration = (ROOT/'tools/research/server/migrations/001-client-heartbeats.sql').read_text()
            mysql(f'USE {database};\n' + migration + '\n' + migration)
            self.assertEqual(mysql(f'USE {database}; SHOW CREATE TABLE users;'), before)
            self.assertEqual(mysql(f"USE {database}; INSERT INTO users (secret) VALUES ('migration-test'); "
                "SET @test_user=LAST_INSERT_ID(); INSERT INTO research_client_heartbeats (user_id, session_id, room_id) "
                "VALUES (@test_user, 'session', 'room'); DELETE FROM users WHERE id=@test_user; "
                "SELECT COUNT(*) FROM research_client_heartbeats;" ).strip(), '0')
        finally:
            mysql(f'DROP DATABASE {database};')


if __name__ == '__main__':
    unittest.main()

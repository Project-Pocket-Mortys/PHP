"""Validate migration 002 against a connection-local synthetic schema copy."""
import json
import unittest

from test_http import php


class MembershipMigrationTests(unittest.TestCase):
    def test_repeatable_migration_preserves_existing_fields_and_generations(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        result = json.loads(php("""
require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';
$liveSchema = $pdo->query('SHOW COLUMNS FROM users')->fetchAll(PDO::FETCH_ASSOC);
$pdo->exec('CREATE TEMPORARY TABLE generation_fixture LIKE users');
try {
    // This test also works after migration 002 is already installed. Only the
    // connection-local copy is returned to its pre-migration shape.
    $pdo->exec('ALTER TABLE generation_fixture DROP COLUMN IF EXISTS room_membership_generation');
    $pdo->exec("INSERT INTO generation_fixture
        (secret, player_id, session_id, room_id, last_event_id, username)
        VALUES ('synthetic-one', 'migration-one', 'session-one', 'room-one', 12345, 'FixtureOne'),
               ('synthetic-two', 'migration-two', 'session-two', NULL, 67890, 'FixtureTwo')");
    $before = $pdo->query('SELECT * FROM generation_fixture ORDER BY id')->fetchAll(PDO::FETCH_ASSOC);
    $migration = str_replace('ALTER TABLE users', 'ALTER TABLE generation_fixture',
        file_get_contents('/var/www/html/tools/research/server/migrations/002-room-membership-generation.sql'), $count);
    if ($count !== 1) throw new RuntimeException('Unexpected migration target');
    $pdo->exec($migration);
    $after = $pdo->query('SELECT * FROM generation_fixture ORDER BY id')->fetchAll(PDO::FETCH_ASSOC);
    foreach ($after as &$row) {
        if ((string)$row['room_membership_generation'] !== '0') {
            throw new RuntimeException('Existing row did not receive generation zero');
        }
        unset($row['room_membership_generation']);
    }
    unset($row);
    if ($after !== $before) throw new RuntimeException('Existing fixture fields changed');
    $column = $pdo->query("SHOW COLUMNS FROM generation_fixture LIKE 'room_membership_generation'")->fetch(PDO::FETCH_ASSOC);
    if (!str_starts_with(strtolower($column['Type']), 'bigint')
        || !str_contains(strtolower($column['Type']), 'unsigned')
        || $column['Null'] !== 'NO' || (string)$column['Default'] !== '0') {
        throw new RuntimeException('Unexpected generation column definition');
    }
    $pdo->exec("UPDATE generation_fixture SET room_membership_generation=9223372036854775808 WHERE player_id='migration-one'");
    $once = $pdo->query('SELECT * FROM generation_fixture ORDER BY id')->fetchAll(PDO::FETCH_ASSOC);
    $pdo->exec($migration);
    $twice = $pdo->query('SELECT * FROM generation_fixture ORDER BY id')->fetchAll(PDO::FETCH_ASSOC);
    if ($once !== $twice) throw new RuntimeException('Repeat migration changed fixture data');
    if ($liveSchema !== $pdo->query('SHOW COLUMNS FROM users')->fetchAll(PDO::FETCH_ASSOC)) {
        throw new RuntimeException('Live users schema changed');
    }
    echo json_encode(['default_zero' => true, 'existing_fields_preserved' => true,
        'repeat_preserves_nonzero_generation' => true, 'live_schema_unchanged' => true]);
} finally {
    $pdo->exec('DROP TEMPORARY TABLE generation_fixture');
}
"""))
        self.assertEqual(result, {
            'default_zero': True,
            'existing_fields_preserved': True,
            'repeat_preserves_nonzero_generation': True,
            'live_schema_unchanged': True,
        })


if __name__ == '__main__':
    unittest.main()

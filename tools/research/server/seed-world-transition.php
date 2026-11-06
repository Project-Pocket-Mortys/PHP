<?php
declare(strict_types=1);
// Explicit, reversible fixture. Snapshot and lock live only in the web container's /tmp.
// Stop clients / leave the fixture room before restoring. No session or progress resets.
if (PHP_SAPI !== 'cli' || getenv('PM_DB_HOST') !== 'db'
    || getenv('PM_DB_NAME') !== 'pocket_mortys'
    || getenv('PM_PUBLIC_ORIGIN') !== 'http://localhost:8087') {
    fwrite(STDERR, "Isolated research web environment required.\n");
    exit(1);
}
$mode = null;
$names = ['PMResearch01', 'PMResearch02'];
foreach (array_slice($argv, 1) as $arg) {
    if (in_array($arg, ['--apply', '--restore'], true) && $mode === null) {
        $mode = $arg;
    } elseif (str_starts_with($arg, '--players=')) {
        $names = explode(',', substr($arg, 10));
    } else {
        fwrite(STDERR, "Usage: php seed-world-transition.php --apply|--restore [--players=name1,name2]\n");
        exit(1);
    }
}
if ($mode === null || count($names) !== 2 || $names[0] === $names[1]
    || !preg_match('/^[A-Za-z0-9_-]{1,64}$/', $names[0])
    || !preg_match('/^[A-Za-z0-9_-]{1,64}$/', $names[1])) {
    fwrite(STDERR, "An explicit --apply or --restore and two distinct player names are required.\n");
    exit(1);
}
$snapshotPath = '/tmp/pm-world-transition.json';
$lock = fopen('/tmp/pm-world-transition.lock', 'c');
if (!$lock || !flock($lock, LOCK_EX)) {
    fwrite(STDERR, "Cannot lock world-transition fixture.\n");
    exit(1);
}
require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';
function fixtureRequire(bool $ok, string $message): void {
    if (!$ok) {
        throw new RuntimeException($message);
    }
}
function fixtureQuery(PDO $pdo, string $query, array $args = []): array {
    $stmt = $pdo->prepare($query);
    $stmt->execute($args);
    return $stmt->fetchAll();
}
try {
    $snapshot = is_file($snapshotPath)
        ? json_decode(file_get_contents($snapshotPath), true, 512, JSON_THROW_ON_ERROR) : null;
    if ($snapshot !== null) {
        fixtureRequire(($snapshot['version'] ?? null) === 1 && ($snapshot['names'] ?? null) === $names,
            'Snapshot belongs to another player selection; restore it with its original --players.');
    }
    if ($mode === '--restore' && $snapshot === null) {
        echo "No world-transition snapshot to restore.\n";
        exit;
    }
    $pdo->beginTransaction();
    $players = [];
    foreach ($names as $name) {
        $rows = fixtureQuery($pdo, 'SELECT id, player_id, username, level FROM users WHERE username = ? FOR UPDATE', [$name]);
        fixtureRequire(count($rows) === 1 && $rows[0]['username'] === $name
            && is_string($rows[0]['player_id']) && $rows[0]['player_id'] !== '',
            'Each selected username must identify exactly one existing player.');
        $players[] = $rows[0];
    }
    fixtureRequire($players[0]['player_id'] !== $players[1]['player_id'], 'Player IDs must be distinct.');
    // Lock the room range as well as the selected accounts throughout each operation.
    $worldRooms = fixtureQuery($pdo, 'SELECT * FROM room_ids WHERE world_id = ? FOR UPDATE', ['2']);
    if ($snapshot !== null) {
        fixtureRequire(count($snapshot['players'] ?? []) === 2, 'Invalid fixture snapshot.');
        foreach ($players as $index => $player) {
            $original = $snapshot['players'][$index];
            fixtureRequire($player['id'] === $original['id'] && $player['player_id'] === $original['player_id']
                && $player['username'] === $original['username'] && (int)$original['level'] === 1,
                'Player identity changed; refusing fixture mutation.');
        }
        $room = $snapshot['room'];
        $owned = fixtureQuery($pdo, 'SELECT * FROM room_ids WHERE id = ? OR room_id = ? FOR UPDATE', [$room['id'], $room['room_id']]);
        $occupants = fixtureQuery($pdo, 'SELECT id FROM users WHERE room_id = ? FOR UPDATE', [$room['room_id']]);
        if (!$owned && $mode === '--restore' && !$occupants
            && (int)$players[0]['level'] === 1 && (int)$players[1]['level'] === 1) {
            // Recovery after a rolled-back apply or committed restore interrupted before unlink.
            $pdo->commit();
            fixtureRequire(unlink($snapshotPath), 'Recovery complete but snapshot removal failed.');
            echo "Fixture already absent; recovery snapshot removed.\n";
            exit;
        }
        fixtureRequire(count($owned) === 1 && $owned[0] === $room, 'Fixture room configuration changed; refusing mutation.');
        fixtureRequire((int)$players[0]['level'] === 5 && (int)$players[1]['level'] === 5,
            'Selected player level changed; refusing mutation.');
        if ($mode === '--apply') {
            fixtureRequire(count($worldRooms) === 1, 'Unexpected additional world-2 room.');
            $pdo->commit();
            echo "World-transition fixture already applied.\n";
            exit;
        }
        fixtureRequire(!$occupants, 'A player is still in the fixture room; leave it before restoring.');
        foreach ($players as $player) {
            $stmt = $pdo->prepare('UPDATE users SET level = 1, last_seen = last_seen WHERE id = ? AND player_id = ? AND level = 5');
            $stmt->execute([$player['id'], $player['player_id']]);
            fixtureRequire($stmt->rowCount() === 1, 'Player changed during restore.');
        }
        $stmt = $pdo->prepare('DELETE FROM room_ids WHERE id = ? AND room_id = ? AND world_id = ? AND zone_id = ? AND room_udp_host = ? AND room_udp_port = ?');
        $stmt->execute([$room['id'], $room['room_id'], '2', '[1,1]', '10.0.2.2', '5055']);
        fixtureRequire($stmt->rowCount() === 1, 'Fixture room changed during restore.');
        // Remove only events belonging to this verified, now-empty owned room.
        $stmt = $pdo->prepare('DELETE FROM event_queue WHERE room_id = ?');
        $stmt->execute([$room['room_id']]);
        $pdo->commit();
        fixtureRequire(unlink($snapshotPath), 'Restore committed but snapshot removal failed; rerun --restore.');
        echo "Original levels restored and empty fixture room removed.\n";
        exit;
    }
    fixtureRequire(!$worldRooms, 'An existing world-2 room prevents fixture creation.');
    fixtureRequire((int)$players[0]['level'] === 1 && (int)$players[1]['level'] === 1,
        'Both selected players must have original level exactly 1.');
    $bytes = random_bytes(16);
    $bytes[6] = chr((ord($bytes[6]) & 15) | 64);
    $bytes[8] = chr((ord($bytes[8]) & 63) | 128);
    $hex = bin2hex($bytes);
    $uuid = substr($hex, 0, 8).'-'.substr($hex, 8, 4).'-'.substr($hex, 12, 4).'-'.substr($hex, 16, 4).'-'.substr($hex, 20);
    $stmt = $pdo->prepare('INSERT INTO room_ids (room_id, room_udp_host, room_udp_port, world_id, zone_id) VALUES (?, ?, ?, ?, ?)');
    // Opaque required-schema fixture: Android RoomJoinedResponse has no zone_id field.
    $stmt->execute([$uuid, '10.0.2.2', '5055', '2', '[1,1]']);
    $room = fixtureQuery($pdo, 'SELECT * FROM room_ids WHERE id = ?', [$pdo->lastInsertId()])[0];
    $snapshot = ['version' => 1, 'names' => $names, 'players' => $players, 'room' => $room];
    // Persist recovery information before committing any database mutations.
    $file = fopen($snapshotPath, 'x');
    fixtureRequire($file !== false, 'Cannot create recovery snapshot.');
    chmod($snapshotPath, 0600);
    $json = json_encode($snapshot, JSON_THROW_ON_ERROR);
    fixtureRequire(fwrite($file, $json) === strlen($json) && fflush($file), 'Cannot persist recovery snapshot.');
    if (function_exists('fsync')) {
        fixtureRequire(fsync($file), 'Cannot sync recovery snapshot.');
    }
    fclose($file);
    foreach ($players as $player) {
        $stmt = $pdo->prepare('UPDATE users SET level = 5, last_seen = last_seen WHERE id = ? AND player_id = ? AND level = 1');
        $stmt->execute([$player['id'], $player['player_id']]);
        fixtureRequire($stmt->rowCount() === 1, 'Player changed during apply.');
    }
    $pdo->commit();
    echo "World-transition fixture applied; recovery snapshot saved in container /tmp.\n";
} catch (Throwable $error) {
    if ($pdo->inTransaction()) {
        $pdo->rollBack();
    }
    // Never print connection details, tokens, or arbitrary database exception text.
    fwrite(STDERR, ($error instanceof RuntimeException && !($error instanceof PDOException)
        ? $error->getMessage() : 'Fixture operation failed; database transaction rolled back when possible.')."\n");
    exit(1);
}

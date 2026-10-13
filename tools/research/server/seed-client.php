<?php
// Additive, synthetic room fixture for the isolated Android client smoke test.
if (getenv('PM_DB_HOST') !== 'db' || getenv('PM_PUBLIC_ORIGIN') !== 'http://localhost:8087') {
    throw new RuntimeException('Isolated research environment required');
}
require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';
$pdo->beginTransaction();
if (!$pdo->query('SELECT id FROM deck_config LIMIT 1')->fetch()) {
    // Use the checked-in schema's defaults (MP, 3, 9, 10), not guessed economy data.
    $pdo->exec('INSERT INTO deck_config () VALUES ()');
}
$room = '00000000-0000-4000-8000-000000000001';
$stmt = $pdo->prepare('SELECT id FROM room_ids WHERE room_id = ?');
$stmt->execute([$room]);
if (!$stmt->fetch()) {
    $stmt = $pdo->prepare('INSERT INTO room_ids (room_id, room_udp_host, room_udp_port, world_id, zone_id) VALUES (?, ?, ?, ?, ?)');
    // World 1 is observed in the client request. Zone follows the existing test
    // fixture convention. Port 5055 is reserved here; no UDP service is claimed.
    $stmt->execute([$room, 'localhost', '5055', '1', '[1,1]']);
}
$pdo->commit();
echo "Synthetic world-1 room ready; UDP service remains unimplemented.\n";

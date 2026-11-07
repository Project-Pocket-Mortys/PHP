<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('X-Powered-By: Express');
header('Access-Control-Allow-Origin: *');
header('Vary: Accept-Encoding');
header('Cache-Control: no-store');
require __DIR__ . '/../../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../../lib/friends.php';
try {
    $data = friend_input();
    $session = friend_string($data, 'session_id', 'NOT_AUTHENTICATED');
    $target = friend_string($data, 'player_id', 'PLAYER_ID_INVALID');
    [$actor, $other, $row] = friend_lock_pair($pdo, $session, $target);
    if ($row) friend_fail(400, 'FRIEND_DUPLICATE');
    $date = (new DateTimeImmutable('now', new DateTimeZone('UTC')))->format('Y-m-d\TH:i:s.v') . 'Z';
    $stmt = $pdo->prepare('INSERT INTO friend_list (player_id_a, player_id_b, pending, direction, created, modified) VALUES (?, ?, ?, ?, ?, ?)');
    $stmt->execute([$actor['player_id'], $target, 'true', 'false', $date, $date]);
    $response = json_encode([
        'player_id_a' => $actor['player_id'], 'player_id_b' => $target,
        'wins_a' => (int)$actor['wins'], 'wins_b' => (int)$other['wins'],
        'pending' => true, 'direction' => false, '_created' => $date, '_modified' => $date
    ], JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
    $pdo->commit();
    header('ETag: W/"' . md5($response) . '"');
    echo $response;
} catch (Throwable $error) {
    friend_error_response($pdo, $error);
}

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
    if (!isset($data['approve']) || !is_bool($data['approve'])) friend_fail(400, 'APPROVE_INVALID');
    [$actor, $other, $row] = friend_lock_pair($pdo, $session, $target);
    if (!$row || $row['pending'] !== 'true' || $row['player_id_a'] !== $target ||
        $row['player_id_b'] !== $actor['player_id']) friend_fail(400, 'PLAYER_ID_INVALID');
    if ($data['approve']) {
        $stmt = $pdo->prepare("UPDATE friend_list SET pending = 'false', modified = NOW() WHERE id = ?");
    } else {
        $stmt = $pdo->prepare('DELETE FROM friend_list WHERE id = ?');
    }
    $stmt->execute([$row['id']]);
    $pdo->commit();
    echo '1';
} catch (Throwable $error) {
    friend_error_response($pdo, $error);
}

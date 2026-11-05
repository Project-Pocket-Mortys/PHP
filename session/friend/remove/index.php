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
    if (!$row) friend_fail(404, 'PLAYER_ID_INVALID');
    $stmt = $pdo->prepare('DELETE FROM friend_list WHERE id = ?');
    $stmt->execute([$row['id']]);
    $pdo->commit();
    echo json_encode(['success' => true, 'message' => 'Friend removed successfully', 'removed_friend_id' => $target], JSON_UNESCAPED_SLASHES);
} catch (Throwable $error) {
    friend_error_response($pdo, $error);
}

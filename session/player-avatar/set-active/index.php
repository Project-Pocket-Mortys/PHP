<?php
// player-avatar/set-active

error_reporting(E_ALL);
ini_set('display_errors', 0);

header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");

require '../../../pocket_f4894h398r8h9w9er8he98he.php'; // provides $pdo
require_once __DIR__ . '/../../../lib/preparation_writer_guard.php';

$data = json_decode(file_get_contents("php://input"), true);

$session_id       = $data['session_id'] ?? '';
$player_avatar_id = $data['player_avatar_id'] ?? '';

if (!$session_id || !$player_avatar_id) {
    http_response_code(400);
    echo json_encode(["success" => false, "error" => "Missing parameters"]);
    exit;
}

try {
    $user = preparation_writer_lock($pdo, (string)$session_id);
    $stmt = $pdo->prepare('UPDATE users SET player_avatar_id = ? WHERE id = ?');
    $stmt->execute([$player_avatar_id, $user['id']]);
    // Preserve the legacy unchanged-avatar response.
    if ($stmt->rowCount() === 0) friend_fail(401, 'NOT_AUTHENTICATED');
    $pdo->commit();
    echo json_encode(['success' => true], JSON_UNESCAPED_SLASHES);
} catch (Throwable $e) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    http_response_code($e instanceof FriendError ? $e->status : 500);
    echo json_encode(['success' => false, 'error' => $e instanceof FriendError ?
        ($e->status === 401 ? 'Invalid session' : $e->getMessage()) : 'SERVER_ERROR']);
}

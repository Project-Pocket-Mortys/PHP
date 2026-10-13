<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require '../../../pocket_f4894h398r8h9w9er8he98he.php';

$input = file_get_contents('php://input');
$data = json_decode($input, true);

$session_id = $data['session_id'] ?? null;
$friend_id  = $data['player_id']   ?? null;  // the player_id of the friend to remove

if (empty($session_id) || empty($friend_id)) {
    http_response_code(400);
    echo json_encode(['error' => 'Missing session_id or friend_id']);
    exit;
}

// ─── Authenticate user ────────────────────────────────────────────────
try {
    $stmt = $pdo->prepare("SELECT player_id FROM users WHERE session_id = ?");
    $stmt->execute([$session_id]);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$user) {
        http_response_code(401);
        echo json_encode(['error' => 'Invalid session']);
        exit;
    }

    $my_player_id = $user['player_id'];

    if ($my_player_id === $friend_id) {
        http_response_code(400);
        echo json_encode(['error' => 'Cannot remove yourself']);
        exit;
    }

    // ─── Delete the friendship row ────────────────────────────────────────
    $deleteStmt = $pdo->prepare("
        DELETE FROM friend_list
        WHERE (player_id_a = ? AND player_id_b = ?)
           OR (player_id_a = ? AND player_id_b = ?)
        LIMIT 1
    ");

    $deleteStmt->execute([
        $my_player_id, $friend_id,
        $friend_id,    $my_player_id
    ]);

    $deletedRows = $deleteStmt->rowCount();

    if ($deletedRows === 0) {
        http_response_code(404);
        echo json_encode([
            'success' => false,
            'message' => 'No friendship found to delete'
        ]);
        exit;
    }

    // Optional: you could also delete any pending requests in the same direction
    // but usually one row represents the whole relationship

    echo json_encode([
        'success' => true,
        'message' => 'Friend removed successfully',
        'removed_friend_id' => $friend_id
    ]);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        'error'   => 'Server error',
        'message' => $e->getMessage()
    ]);
}

//echo '[null, null]';
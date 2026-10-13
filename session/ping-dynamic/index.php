<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

// Optional research relay liveness. Preserve the existing wire acknowledgement.
if (getenv('PM_RESEARCH_HEARTBEATS') === '1' && getenv('PM_DB_HOST') === 'db'
    && getenv('PM_DB_NAME') === 'pocket_mortys') {
    require __DIR__.'/../../pocket_f4894h398r8h9w9er8he98he.php';
    $body = json_decode(file_get_contents('php://input'), true);
    $session = is_array($body) ? ($body['session_id'] ?? null) : null;
    if (is_string($session) && $session !== '') {
        $ping = $pdo->prepare("INSERT INTO research_client_heartbeats (user_id, session_id, room_id, received_at)
            SELECT u.id, u.session_id, u.room_id, CURRENT_TIMESTAMP
            FROM users u WHERE u.session_id = ? AND u.state = 'WORLD'
              AND EXISTS (SELECT 1 FROM room_ids r WHERE r.room_id = u.room_id)
            ON DUPLICATE KEY UPDATE session_id = VALUES(session_id), room_id = VALUES(room_id), received_at = VALUES(received_at)");
        $ping->execute([$session]);
    }
}

echo '{"success": true}';

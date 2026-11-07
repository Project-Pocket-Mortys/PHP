<?php
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
require __DIR__ . '/../../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../../lib/battle_timeouts.php';
require_once __DIR__ . '/../../../lib/friend_battle_startup.php';

$body = json_input();
foreach (['session_id', 'battle_id'] as $key) {
    if (!is_string($body[$key] ?? null) || $body[$key] === '') respond(400, ['success' => false, 'error' => 'Error']);
}
// Research-only shared startup has no combat timer or public acceptance path.
if (friend_battle_transport_enabled()) {
    try {
    $query=$pdo->prepare('SELECT 1 FROM friend_battle_sessions WHERE battle_id=?');
    $query->execute([$body['battle_id']]);
    if ($query->fetchColumn()!==false) {
            friend_battle_startup_ready($pdo,$body['session_id'],$body['battle_id']);
            respond(200,['success'=>true]);
    }
    } catch (Throwable $error) {
            if ($pdo->inTransaction()) $pdo->rollBack();
            if (!$error instanceof FriendError) error_log('Shared readiness failed: '.get_class($error));
            respond($error instanceof FriendError ? $error->status : 500,['error'=>['code'=>'FAILED']]);
    }
}
$error_body = null;
try {
    $pdo->beginTransaction();
    $stmt = $pdo->prepare('SELECT player_id, room_id, state FROM users WHERE session_id=? LIMIT 1 FOR UPDATE');
    $stmt->execute([$body['session_id']]);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$user) battle_reject(401);
    $stmt = $pdo->prepare('SELECT * FROM battles WHERE battle_id=? FOR UPDATE');
    $stmt->execute([$body['battle_id']]);
    $battle = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$battle) battle_reject(404);
    if ((string)$battle['player_id'] !== (string)$user['player_id']) battle_reject(403);
    if ($battle['state'] !== 'ACTIVE') battle_reject(409);
    // Preserve the existing READY failure bodies for room validation.
    $current_room = (string)($user['room_id'] ?? '');
    if ($current_room === '' || $current_room === '0') {
        $error_body = ['success' => false, 'error' => 'Player is not in a room'];
        battle_reject(409);
    }
    $stmt = $pdo->prepare('SELECT 1 FROM room_ids WHERE room_id=? LIMIT 1');
    $stmt->execute([$current_room]);
    if (!$stmt->fetchColumn()) {
        $error_body = ['success' => false, 'error' => 'Room does not exist', 'room_id' => $current_room];
        battle_reject(409);
    }
    if (battle_timeout_expire_locked($pdo, $user, $battle)) {
        $pdo->commit();
        respond(409, ['success' => false]);
    }
    $room = battle_timeout_validate_locked($pdo, $user, $battle);
    if ($battle['move_deadline'] === null) {
        $pdo->prepare('UPDATE battles SET move_deadline=UTC_TIMESTAMP(6)+INTERVAL 30 SECOND WHERE battle_id=?')->execute([$battle['battle_id']]);
        publish_event($pdo, $room, 'battle:move-timer-started', [
            'battle_id' => (string)$battle['battle_id'], 'timeout' => 30,
        ], (string)$user['player_id']);
    }
    $pdo->commit();
    respond(200, ['success' => true]);
} catch (Throwable $error) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    $status = battle_error_status($error);
    if ($status === 500) error_log((string)$error);
    respond($status, $error_body ?? ($status === 401
        ? ['success' => false, 'error' => 'Not authenticated'] : ['success' => false]));
}

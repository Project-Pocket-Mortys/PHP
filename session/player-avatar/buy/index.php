<?php
// player-avatar/buy

error_reporting(E_ALL);
ini_set('display_errors', 0);

header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");

require '../../../pocket_f4894h398r8h9w9er8he98he.php'; // $pdo
require_once __DIR__ . '/../../../lib/preparation_writer_guard.php';

$data = json_decode(file_get_contents("php://input"), true);

$session_id       = $data['session_id'] ?? '';
$player_avatar_id = $data['player_avatar_id'] ?? '';

if (!$session_id || !$player_avatar_id) {
    http_response_code(400);
    echo json_encode(["error" => "Missing parameters"]);
    exit;
}

try {
$user = preparation_writer_lock($pdo, (string)$session_id);
$stmt = $pdo->prepare('SELECT player_avatar_id FROM owned_avatars WHERE player_id = ? FOR UPDATE');
$stmt->execute([$user['player_id']]);
$owned = $stmt->fetch(PDO::FETCH_ASSOC);
if (!$owned) friend_fail(401, 'NOT_AUTHENTICATED');
$player = ['player_id' => $user['player_id'], 'coins' => $user['coins'],
           'current_avatar' => $user['player_avatar_id'], 'owned_avatars' => $owned['player_avatar_id']];

/*
Decode owned avatars (JSON ARRAY)
*/
$owned_avatars = json_decode($player['owned_avatars'], true);
if (!is_array($owned_avatars)) {
    $owned_avatars = [];
}

/*
Add avatar if missing
*/
if (!in_array($player_avatar_id, $owned_avatars, true)) {
    $owned_avatars[] = $player_avatar_id;
}

/*
Write JSON ARRAY back to DB
*/
$stmt = $pdo->prepare("
    UPDATE owned_avatars
    SET player_avatar_id = ?
    WHERE player_id = ?
");
$stmt->execute([
    json_encode(array_values($owned_avatars), JSON_UNESCAPED_SLASHES),
    $player['player_id']
]);

/*
Equip avatar
*/
if ($player['current_avatar'] !== $player_avatar_id) {
    $stmt = $pdo->prepare("
        UPDATE users
        SET player_avatar_id = ?
        WHERE player_id = ?
    ");
    $stmt->execute([
        $player_avatar_id,
        $player['player_id']
    ]);
}

/*
Respond
*/
$pdo->commit();
echo json_encode([
    "coins" => (int)$player['coins'],
    "coins_deducted" => 0,
    "result" => [
        "type" => "AVATAR",
        "player_avatar_id" => $player_avatar_id
    ]
], JSON_UNESCAPED_SLASHES);

} catch (Throwable $e) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    http_response_code($e instanceof FriendError ? $e->status : 500);
    echo json_encode(['error' => $e instanceof FriendError ?
        ($e->status === 401 ? 'Invalid session' : $e->getMessage()) : 'SERVER_ERROR']);
}

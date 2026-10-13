<?php
// player-avatar/buy

error_reporting(E_ALL);
ini_set('display_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");

require '../../../pocket_f4894h398r8h9w9er8he98he.php'; // $pdo

$data = json_decode(file_get_contents("php://input"), true);

$session_id       = $data['session_id'] ?? '';
$player_avatar_id = $data['player_avatar_id'] ?? '';

if (!$session_id || !$player_avatar_id) {
    http_response_code(400);
    echo json_encode(["error" => "Missing parameters"]);
    exit;
}

/*
Get player by session_id
*/
$stmt = $pdo->prepare("
    SELECT 
        u.player_id,
        u.coins,
        u.player_avatar_id AS current_avatar,
        oa.player_avatar_id AS owned_avatars
    FROM users u
    JOIN owned_avatars oa ON oa.player_id = u.player_id
    WHERE u.session_id = ?
    LIMIT 1
");
$stmt->execute([$session_id]);
$player = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$player) {
    http_response_code(401);
    echo json_encode(["error" => "Invalid session"]);
    exit;
}

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
echo json_encode([
    "coins" => (int)$player['coins'],
    "coins_deducted" => 0,
    "result" => [
        "type" => "AVATAR",
        "player_avatar_id" => $player_avatar_id
    ]
], JSON_UNESCAPED_SLASHES);

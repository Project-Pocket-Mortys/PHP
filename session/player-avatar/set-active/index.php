<?php
// player-avatar/set-active

error_reporting(E_ALL);
ini_set('display_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");

require '../../../pocket_f4894h398r8h9w9er8he98he.php'; // provides $pdo

$data = json_decode(file_get_contents("php://input"), true);

$session_id       = $data['session_id'] ?? '';
$player_avatar_id = $data['player_avatar_id'] ?? '';

if (!$session_id || !$player_avatar_id) {
    http_response_code(400);
    echo json_encode(["success" => false, "error" => "Missing parameters"]);
    exit;
}

/*
Update active avatar by session_id
*/
$stmt = $pdo->prepare("
    UPDATE users
    SET player_avatar_id = ?
    WHERE session_id = ?
    LIMIT 1
");
$stmt->execute([
    $player_avatar_id,
    $session_id
]);

if ($stmt->rowCount() === 0) {
    http_response_code(401);
    echo json_encode(["success" => false, "error" => "Invalid session"]);
    exit;
}

/*
Respond
*/
echo json_encode([
    "success" => true
], JSON_UNESCAPED_SLASHES);
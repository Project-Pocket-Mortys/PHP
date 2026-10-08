<?php
// ready
header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");

error_reporting(E_ALL);
ini_set('display_errors', 1);

require __DIR__ . "/../../../pocket_f4894h398r8h9w9er8he98he.php";
require_once __DIR__ . "/../../../lib/events.php";

// Read body
$raw  = file_get_contents("php://input");
$body = json_decode($raw, true);

// Accept session_id from JSON body
$session_id = (string)($body["session_id"]);
if ($session_id === "") {
    http_response_code(400);
    echo json_encode(["success" => false, "error" => "Error"], JSON_UNESCAPED_SLASHES);
    exit;
}

// Accept battle_id from JSON body
$battle_id = (string)($body["session_id"]);
if ($battle_id === "") {
    http_response_code(400);
    echo json_encode(["success" => false, "error" => "Error"], JSON_UNESCAPED_SLASHES);
    exit;
}


// 1) Lookup player + current room from users
$stmt = $pdo->prepare("
  SELECT player_id, room_id
  FROM users
  WHERE session_id = ?
  LIMIT 1
");
$stmt->execute([$session_id]);
$u = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$u) {
    http_response_code(401);
    echo json_encode(["success" => false, "error" => "Not authenticated"], JSON_UNESCAPED_SLASHES);
    exit;
}

$player_id = (string)$u["player_id"];
$room_id   = (string)($u["room_id"] ?? "");

if ($room_id === "" || $room_id === "0") {
    http_response_code(409);
    echo json_encode(["success" => false, "error" => "Player is not in a room"], JSON_UNESCAPED_SLASHES);
    exit;
}

// 2) Verify room exists in room_ids
$chk = $pdo->prepare("SELECT 1 FROM room_ids WHERE room_id = ? LIMIT 1");
$chk->execute([$room_id]);
if (!$chk->fetchColumn()) {
    http_response_code(409);
    echo json_encode(["success" => false, "error" => "Room does not exist", "room_id" => $room_id], JSON_UNESCAPED_SLASHES);
    exit;
}

$battle_payload = [
    "battle_id"   => (string)$battle_id,
    "timeout" => (int)30
];

publish_event($pdo, $room_id, "battle:move-timer-started", $battle_payload, (string)$player_id);

echo '{"success":true}';
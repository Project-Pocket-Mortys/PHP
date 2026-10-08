<?php
// emote-room

error_reporting(E_ALL);
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");

require __DIR__ . "/../../../pocket_f4894h398r8h9w9er8he98he.php";
require __DIR__ . "/../../../lib/events.php";

$body = json_decode(file_get_contents("php://input"), true) ?: [];
$session_id = (string)($body["session_id"] ?? "");
$emote      = (string)($body["emote"] ?? "");

if ($session_id === "" || $emote === "") {
  http_response_code(400);
  echo json_encode(["error" => "Missing session_id or emote"], JSON_UNESCAPED_SLASHES);
  exit;
}

// Keep emote small + safe (matches your examples)
if (strlen($emote) > 24 || !preg_match('/^[a-zA-Z0-9]+$/', $emote)) {
  http_response_code(400);
  echo json_encode(["error" => "Invalid emote"], JSON_UNESCAPED_SLASHES);
  exit;
}

try {
  // Find the user and their room
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
    echo json_encode(["error" => "Not authenticated"], JSON_UNESCAPED_SLASHES);
    exit;
  }

  $player_id = (string)$u["player_id"];
  $room_id   = (string)($u["room_id"] ?? "");

  if ($room_id === "" || $room_id === "0") {
    http_response_code(409);
    echo json_encode(["error" => "Player is not in a room"], JSON_UNESCAPED_SLASHES);
    exit;
  }

  // Mark active
  $pdo->prepare("UPDATE users SET last_seen = NOW() WHERE session_id = ? LIMIT 1")
      ->execute([$session_id]);

  // ✅ Publish the exact event + payload shape your client expects
  publish_event($pdo, $room_id, "emote:room", [
    "player_id" => $player_id,
    "emote" => $emote
  ]);
  
// 🔥 SEND TO UDP SERVER (FIXED PORT 13000)
$socket = socket_create(AF_INET, SOCK_DGRAM, SOL_UDP);

$data = json_encode([
    "type" => "emote",
    "player_id" => $player_id,
    "room_id" => $room_id,
    "emote" => $emote
]);

socket_sendto(
    $socket,
    $data,
    strlen($data),
    0,
    "127.0.0.1",
    13000
);

socket_close($socket);

// Debug log (optional)
error_log("EMOTE SENT: " . $data);

  echo json_encode(["success" => true], JSON_UNESCAPED_SLASHES);
} catch (Throwable $e) {
  http_response_code(500);
  echo json_encode(["error" => "Server error", "detail" => $e->getMessage()], JSON_UNESCAPED_SLASHES);
}

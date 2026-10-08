<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require __DIR__ . "/../../pocket_f4894h398r8h9w9er8he98he.php";
require_once __DIR__ . "/../../lib/auth.php";
require_once __DIR__ . "/../../lib/events.php";

$body = json_decode(file_get_contents("php://input"), true) ?: [];
$session_id = (string)($body["session_id"] ?? "");

if ($session_id === "") {
    http_response_code(400);
    echo json_encode(["success" => false, "error" => "Missing session_id"], JSON_UNESCAPED_SLASHES);
    exit;
}

$stmt = $pdo->prepare("
    SELECT player_id, room_id
    FROM users
    WHERE session_id = ?
    LIMIT 1
");
$stmt->execute([$session_id]);
$session = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$session) {
    http_response_code(404);
    echo json_encode([
        "success" => false,
        "error" => "Invalid session"
    ]);
    exit;
}

$player_id = $session["player_id"];
$room_id   = $session["room_id"];

// ✅ Broadcast leave to everyone still in that room
publish_event($pdo, (string)$room_id, "room:user-removed", [
    "player_id" => $player_id
]);

echo json_encode([
    "success" => true
], JSON_UNESCAPED_SLASHES);

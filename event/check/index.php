<?php
// event/check  (raid test publisher)
header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");

require __DIR__ . "/../../pocket_f4894h398r8h9w9er8he98he.php";
require_once __DIR__ . "/../../lib/events.php";

// Read body
$raw  = file_get_contents("php://input");
$body = json_decode($raw, true);
if (!is_array($body)) $body = [];

// Accept session_id from JSON body (or GET for quick testing)
$session_id = (string)($body["session_id"] ?? ($_GET["session_id"] ?? ""));
if ($session_id === "") {
    http_response_code(400);
    echo json_encode(["success" => false, "error" => "Missing session_id"], JSON_UNESCAPED_SLASHES);
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

// You can also pass world_id or anything else you want
$world_id = (int)($body["world_id"] ?? ($_GET["world_id"] ?? 1));

$stmt = $pdo->prepare("
  SELECT *
  FROM events
  WHERE current_state IN ('build_up','active')
  ORDER BY
    CASE current_state
      WHEN 'active' THEN 0
      WHEN 'build_up' THEN 1
      ELSE 2
    END,
    event_state_next_timestamp ASC
  LIMIT 1
");
$stmt->execute();
$event = $stmt->fetch(PDO::FETCH_ASSOC);
if ($event) {
// If no event row, use empty array so $event['x'] won't throw warnings
$event = $event ?: [];

$payload = [
    "raid_event_id" => (string)($event["raid_event_id"]),
    "shard_id" => (string)($event["shard_id"]),
    "current_state" => (string)($event["current_state"]),
    "world_id" => (int)($event["world_id"]),
    "spawn_location" => (string)($event["spawn_location"]),
    "boss_id" => (string)($event["boss_id"]),
    "asset_id" => (string)($event["asset_id"]),
    "threat_lvl" => (int)($event["threat_lvl"]),
    "total_damage" => (string)($event["total_damage"]),
    "initial_health" => (int)($event["initial_health"]),
    "max_health_bars" => (int)($event["max_health_bars"]),
    "event_state_next_timestamp" => (string)($event["event_state_next_timestamp"]),
    "has_ran" => (bool)($event["has_ran"]),
    "permit_start" => (int)($event["permit_start"]),
    "permit_buy_in" => (int)($event["permit_buy_in"]),
    "ticket_buy_in" => (int)($event["ticket_buy_in"]),
];
}
/*
data: {"raid_event_id":"RaidBossKillerAsteroid_2025","shard_id":"78496e72-fb88-11f0-b2fd-8b24d97da62f","current_state":"active","world_id":1,"spawn_location":"37,58","boss_id":"killer_asteroid","asset_id":"RaidBossKillerAsteroid","threat_lvl":10,"total_damage":"1530524","initial_health":30860800,"max_health_bars":60275,"event_state_next_timestamp":"2026-02-02T08:30:00.000Z","has_ran":false,"permit_start":50,"permit_buy_in":1,"ticket_buy_in":0}
$payload_2 = $payload;
$payload_2["current_state"] = "active"; OR build_up
$payload_2["total_damage"]  = (string)($body["total_damage"] ?? "1530524");
$payload_2["event_state_next_timestamp"] = (string)($body["event_state_next_timestamp"] ?? "2026-02-02T08:30:00.000Z");
*/

// ✅ Publish into THIS player's current room stream (SSE will receive it)
$state = $event["current_state"] ?? null;
if ($state === "active" || $state === "build_up") {
publish_event($pdo, $room_id, "shard:raid-boss-state-changed", $payload);
}
 
// Optional: keep player online
$pdo->prepare("UPDATE users SET last_seen = NOW() WHERE player_id = ? LIMIT 1")->execute([$player_id]);

echo json_encode([
    "success" => true
], JSON_UNESCAPED_SLASHES);

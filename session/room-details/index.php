<?php
// room-details

header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

error_reporting(E_ALL);
ini_set('display_errors', 1);

require_once "../../pocket_f4894h398r8h9w9er8he98he.php";
require_once __DIR__ . "/../../lib/events.php";

function iso8601_z($date = null): string {
    $ts = $date ? strtotime($date) : time();
    return gmdate("Y-m-d\\TH:i:s.000\\Z", $ts);
}

$input = json_decode(file_get_contents("php://input"), true);

if (!isset($input["session_id"])) {
    echo json_encode(["error" => "Missing session_id"]);
    exit;
}

$session_id = $input["session_id"];

/*
|--------------------------------------------------------------------------
| 1. Get requesting player
|--------------------------------------------------------------------------
*/
$stmt = $pdo->prepare("
    SELECT player_id, room_id
    FROM users
    WHERE session_id = ?
    LIMIT 1
");
$stmt->execute([$session_id]);
$self = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$self) {
    echo json_encode(["error" => "Invalid session"]);
    exit;
}

$room_id = $self["room_id"];

/*
|--------------------------------------------------------------------------
| 2. Room metadata
|--------------------------------------------------------------------------
*/
$stmt = $pdo->prepare("
    SELECT *
    FROM room_ids
    WHERE room_id = ?
    LIMIT 1
");
$stmt->execute([$room_id]);
$room = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$room) {
    echo json_encode(["error" => "Room not found"]);
    exit;
}

/*
|--------------------------------------------------------------------------
| 3. USERS (real players only)
|--------------------------------------------------------------------------
*/
$userStmt = $pdo->prepare("
    SELECT player_id, username, player_avatar_id, level, active_deck_id, state
    FROM users
    WHERE room_id = ?
    AND last_seen >= (NOW() - INTERVAL 5 MINUTE)
");
$userStmt->execute([$room_id]);

$users = [];

while ($u = $userStmt->fetch(PDO::FETCH_ASSOC)) {

    $deckStmt = $pdo->prepare("
        SELECT owned_morty_ids
        FROM decks
        WHERE player_id = ?
        AND deck_id = ?
        LIMIT 1
    ");
    $deckStmt->execute([
        $u["player_id"],
        $u["active_deck_id"]
    ]);

    $deck = $deckStmt->fetch(PDO::FETCH_ASSOC);

    $deck_ids = [];

    if ($deck && !empty($deck["owned_morty_ids"])) {
        $decoded = json_decode($deck["owned_morty_ids"], true);

        if (is_array($decoded)) {
            $deck_ids = $decoded;
        }
    }

    $owned_morties = [];

    if (!empty($deck_ids)) {
        $placeholders = implode(",", array_fill(0, count($deck_ids), "?"));

        $params = $deck_ids;
        array_unshift($params, $u["player_id"]);

        $mortyStmt = $pdo->prepare("
            SELECT owned_morty_id, morty_id, hp, variant,
                   is_locked, is_trading_locked, fight_pit_id
            FROM owned_morties
            WHERE player_id = ?
            AND owned_morty_id IN ($placeholders)
        ");
        $mortyStmt->execute($params);

        while ($m = $mortyStmt->fetch(PDO::FETCH_ASSOC)) {
            $owned_morties[] = [
                "owned_morty_id" => $m["owned_morty_id"],
                "morty_id" => $m["morty_id"],
                "hp" => (int)$m["hp"],
                "variant" => $m["variant"] ?: "Normal",
                "is_locked" => (bool)$m["is_locked"],
                "is_trading_locked" => (bool)$m["is_trading_locked"],

                // must be real null, not "null"
                "fight_pit_id" => !empty($m["fight_pit_id"])
                    ? $m["fight_pit_id"]
                    : null
            ];
        }
    }

    $users[] = [
        "player_id" => $u["player_id"],
        "username" => $u["username"],
        "player_avatar_id" => $u["player_avatar_id"],
        "level" => (int)$u["level"],
        "owned_morties" => $owned_morties,
        "state" => $u["state"] ?: "WORLD"
    ];
}

/*
|--------------------------------------------------------------------------
| 4. PICKUPS
|--------------------------------------------------------------------------
*/
$pickupStmt = $pdo->prepare("
    SELECT pickup_id, placement, pick_up_contents
    FROM event_queue
    WHERE room_id = ?
    AND event_name = 'room:pickup-added'
    AND pickup_id_collected_by_player_id IS NULL
");
$pickupStmt->execute([$room_id]);

$pickups = [];

while ($p = $pickupStmt->fetch(PDO::FETCH_ASSOC)) {

    $pos = explode(",", $p["placement"]);

    if (count($pos) !== 2) continue;

    $contents = json_decode($p["pick_up_contents"], true);

    if (!is_array($contents)) {
        $contents = [];
    }

    // force original format:
    if (isset($contents["type"])) {
        $contents = [$contents];
    }

    $pickups[] = [
        "pickup_id" => $p["pickup_id"],
        "placement" => [
            (int)$pos[0],
            (int)$pos[1]
        ],
        "contents" => array_values($contents)
    ];
}

/*
|--------------------------------------------------------------------------
| 5. WILD MORTIES
|--------------------------------------------------------------------------
*/
$wildStmt = $pdo->prepare("
    SELECT wild_morty_id, morty_id, placement, state,
           division, variant, shiny_if_potion, created_at, updated
    FROM event_queue
    WHERE room_id = ?
    AND event_name = 'room:wild-morty-added'
");
$wildStmt->execute([$room_id]);

$wild_morties = [];

while ($w = $wildStmt->fetch(PDO::FETCH_ASSOC)) {

    $pos = explode(",", $w["placement"]);

    if (count($pos) !== 2) continue;

    $wild_morties[] = [
        "morty_id" => $w["morty_id"],
        "placement" => [
            (int)$pos[0],
            (int)$pos[1]
        ],
        "state" => $w["state"] ?: "WORLD",
        "division" => (int)$w["division"],
        "variant" => $w["variant"] ?: "Normal",
        "shiny_if_potion" => (bool)$w["shiny_if_potion"],
        "_created" => iso8601_z($w["created_at"]),
        "_updated" => iso8601_z($w["updated"]),
        "wild_morty_id" => $w["wild_morty_id"]
    ];
}

/*
|--------------------------------------------------------------------------
| 6. BOTS
|--------------------------------------------------------------------------
*/
$botStmt = $pdo->prepare("
    SELECT bot_id, username, player_avatar_id, placement, state, division, zone_id, shiny_if_potion, owned_morties
    FROM event_queue
    WHERE room_id = ?
    AND event_name = 'room:bot-added'
");

$botStmt->execute([$room_id]);

$bots = [];

while ($b = $botStmt->fetch(PDO::FETCH_ASSOC)) {

    $placement = isset($b["placement"]) ? explode(",", $b["placement"]) : [0, 0];

    $bots[] = [
        "username" => $b["username"],
        "player_avatar_id" => $b["player_avatar_id"],
		"state" => $b["state"],
		"level" => 1,
		"owned_morties" => json_decode($b["owned_morties"], true),
        "shiny_if_potion" => (bool)$b["shiny_if_potion"],
		"streak" => 0,
        "bot_id" => $b["bot_id"],
        "placement" => [(int)($placement[0] ?? 0),(int)($placement[1] ?? 0)]
    ];
}

/*
|--------------------------------------------------------------------------
| 7. baseline_event_id
|--------------------------------------------------------------------------
*/
$baselineStmt = $pdo->prepare("
    SELECT COALESCE(MAX(id),0)
    FROM event_queue
    WHERE room_id = ?
");
$baselineStmt->execute([$room_id]);

$baseline_event_id = (int)$baselineStmt->fetchColumn();

/*
|--------------------------------------------------------------------------
| FINAL RESPONSE
|--------------------------------------------------------------------------
*/
echo json_encode([
    "room_id" => $room["room_id"],
    "room_udp_host" => $room["room_udp_host"],
    "room_udp_port" => (string)$room["room_udp_port"],
    "world_id" => (string)$room["world_id"],
    "zone_id" => $room["zone_id"],
    "users" => $users,
    "pickups" => $pickups,
    "wild_morties" => $wild_morties,
    "bots" => $bots,
    //"baseline_event_id" => $baseline_event_id

], JSON_UNESCAPED_SLASHES | JSON_NUMERIC_CHECK | JSON_PRESERVE_ZERO_FRACTION);
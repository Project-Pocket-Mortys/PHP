<?php
// join-room

error_reporting(E_ALL);
ini_set('display_errors', 1);

header("Content-Type: application/json; charset=utf-8");

require __DIR__ . "/../../pocket_f4894h398r8h9w9er8he98he.php";
require_once __DIR__ . "/../../lib/events.php";
//require_once __DIR__ . "/../../lib/room_entities.php";

function iso8601_z($date = null): string {
    $ts = $date ? strtotime($date) : time();
    return gmdate("Y-m-d\\TH:i:s.000\\Z", $ts);
}

$body = json_decode(file_get_contents("php://input"), true) ?: [];

$session_id = (string)($body["session_id"] ?? "");
$world_id_in = (string)($body["world_id"] ?? "");

if (!$session_id || !$world_id_in) {
    http_response_code(400);
    echo json_encode([
        "error" => "Missing session_id or world_id"
    ]);
    exit;
}

/* ---------------- AUTH ---------------- */

$stmt = $pdo->prepare("
    SELECT player_id, username, player_avatar_id, level, active_deck_id
    FROM users
    WHERE session_id = ?
    LIMIT 1
");
$stmt->execute([$session_id]);

$me = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$me) {
    http_response_code(401);
    echo json_encode([
        "error" => "Not authenticated"
    ]);
    exit;
}

$player_id = $me["player_id"];

/* ---------------- ROOM PICK ---------------- */

$roomStmt = $pdo->prepare("
    SELECT room_id, room_udp_host, room_udp_port, world_id, zone_id
    FROM room_ids
    WHERE world_id = ?
    LIMIT 1
");
$roomStmt->execute([$world_id_in]);

$room = $roomStmt->fetch(PDO::FETCH_ASSOC);

if (!$room) {
    http_response_code(400);
    echo json_encode([
        "error" => "NO_ROOM_FOUND"
    ]);
    exit;
}

$room_id = $room["room_id"];

/* ---------------- UPDATE PLAYER ---------------- */

$update = $pdo->prepare("
    UPDATE users
    SET room_id = ?,
        state = 'WORLD',
        last_seen = NOW()
    WHERE player_id = ?
");
$update->execute([$room_id, $player_id]);

/* ---------------- BASELINE EVENT ---------------- */

$baselineStmt = $pdo->prepare("
    SELECT COALESCE(MAX(id),0)
    FROM event_queue
    WHERE room_id = ?
");
$baselineStmt->execute([$room_id]);

$baseline_event_id = (int)$baselineStmt->fetchColumn();

$pdo->prepare("
    UPDATE users
    SET last_event_id = ?
    WHERE player_id = ?
")->execute([$baseline_event_id, $player_id]);

/* ---------------- USERS ---------------- */
$usersStmt = $pdo->prepare("
    SELECT 
        player_id,
        username,
        player_avatar_id,
        level,
        state
    FROM users
    WHERE room_id = ?
      AND last_seen >= (NOW() - INTERVAL 1 MINUTE)
");
$usersStmt->execute([$room_id]);

$users = [];

while ($u = $usersStmt->fetch(PDO::FETCH_ASSOC)) {

    $deckStmt = $pdo->prepare("
        SELECT owned_morty_ids
        FROM decks
        WHERE player_id = ?
        AND deck_id = (
            SELECT active_deck_id
            FROM users
            WHERE player_id = ?
        )
        LIMIT 1
    ");
    $deckStmt->execute([$u["player_id"], $u["player_id"]]);

    $deck = $deckStmt->fetch(PDO::FETCH_ASSOC);

    $mortyIds = json_decode($deck["owned_morty_ids"] ?? "[]", true);

    $owned_morties = [];

    if (!empty($mortyIds)) {
        $placeholders = implode(",", array_fill(0, count($mortyIds), "?"));

        $mortyStmt = $pdo->prepare("
            SELECT *
            FROM owned_morties
            WHERE owned_morty_id IN ($placeholders)
        ");
        $mortyStmt->execute($mortyIds);

        while ($m = $mortyStmt->fetch(PDO::FETCH_ASSOC)) {
            $owned_morties[] = [
                "owned_morty_id" => $m["owned_morty_id"],
                "morty_id" => $m["morty_id"],
                "hp" => (int)$m["hp"],
                "variant" => $m["variant"] ?: "Normal",
                "is_locked" => (bool)$m["is_locked"],
                "is_trading_locked" => (bool)$m["is_trading_locked"],

                // IMPORTANT FIX
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

/* ---------------- PICKUPS ---------------- */

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

    $contents = json_decode($p["pick_up_contents"], true);

    if (!is_array($contents)) {
        $contents = [];
    }

    // force array format
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

/* ---------------- WILD MORTIES ---------------- */

$wildStmt = $pdo->prepare("
    SELECT *
    FROM event_queue
    WHERE room_id = ?
    AND event_name = 'room:wild-morty-added'
");
$wildStmt->execute([$room_id]);

$wild_morties = [];

while ($w = $wildStmt->fetch(PDO::FETCH_ASSOC)) {

    $pos = explode(",", $w["placement"]);

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
        "_updated" => iso8601_z($w["created_at"]),
        "wild_morty_id" => $w["wild_morty_id"]
    ];
}

/* ---------------- BOTS ---------------- */

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

/* ---------------- FINAL RESPONSE ---------------- */

echo json_encode([
    "room_id" => $room["room_id"],
    "room_udp_host" => $room["room_udp_host"],
    "room_udp_port" => (string)$room["room_udp_port"],
    "world_id" => (string)$room["world_id"],
    "zone_id" => $room["zone_id"],

    "incentive" => [
        "incentive_id" => "NPCAd",
        "rewards" => [
            [
                "type" => "ITEM",
                "amount" => 1,
                "item_id" => "ItemSerum",
                "rarity" => 100
            ],
            [
                "type" => "ITEM",
                "amount" => 1,
                "item_id" => "ItemParalysisCure",
                "rarity" => 75
            ],
            [
                "type" => "COIN",
                "amount" => 200
            ]
        ],
        "token" => ""
    ],

    "users" => $users,
    "pickups" => $pickups,
    "wild_morties" => $wild_morties,
    "bots" => $bots,
    //"baseline_event_id" => $baseline_event_id

], JSON_UNESCAPED_SLASHES | JSON_NUMERIC_CHECK | JSON_PRESERVE_ZERO_FRACTION);

/* ---------------- SEND TO SSE USER JOINED ROOM ---------------- */
$payload = [
"room_id" => $room_id,
"player_id" => $player_id,
"state" => "WORLD"
];
publish_event($pdo, $room_id, "room:user-added", $payload, $player_id);
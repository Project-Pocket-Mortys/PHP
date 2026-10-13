<?php
// battle wild morty
header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");

error_reporting(E_ALL);
ini_set('display_errors', 1);

require __DIR__ . "/../../pocket_f4894h398r8h9w9er8he98he.php";
require_once __DIR__ . "/../../lib/events.php";

// ------------------------
// Read input
// ------------------------
$raw  = file_get_contents("php://input");
$body = json_decode($raw, true);

$session_id    = (string)($body["session_id"] ?? "");
$wild_morty_id = (string)($body["wild_morty_id"] ?? "");

if ($session_id === "" || $wild_morty_id === "") {
    http_response_code(400);
    echo json_encode(["success" => false, "error" => "Missing session_id or wild_morty_id"], JSON_UNESCAPED_SLASHES);
    exit;
}

// ------------------------
// Helpers
// ------------------------
function uuidv4(): string {
    $data = random_bytes(16);
    $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
    $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
    return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
}

function to_bool($v): bool {
    if (is_bool($v)) return $v;
    if ($v === null) return false;
    $s = strtolower(trim((string)$v));
    return in_array($s, ['1','true','yes','y','on'], true);
}

function parse_id_list($raw): array {
    $raw = trim((string)$raw);
    $ids = json_decode($raw, true);
    if (is_array($ids)) return array_values(array_filter(array_map('trim', $ids)));
    return array_values(array_filter(array_map('trim', explode(',', $raw))));
}

// ------------------------
// Lookup player + room
// ------------------------
$stmt = $pdo->prepare("SELECT player_id, room_id FROM users WHERE session_id = ? LIMIT 1");
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

// ------------------------
// Verify room exists
// ------------------------
$chk = $pdo->prepare("SELECT 1 FROM room_ids WHERE room_id = ? LIMIT 1");
$chk->execute([$room_id]);
if (!$chk->fetchColumn()) {
    http_response_code(409);
    echo json_encode(["success" => false, "error" => "Room does not exist", "room_id" => $room_id], JSON_UNESCAPED_SLASHES);
    exit;
}

// New pulls directly from the db
function get_wild_morty_payload(PDO $pdo, string $room_id, string $wild_morty_id): ?array {
    $stmt = $pdo->prepare("
        SELECT 
            wild_morty_id,
            morty_id,
            placement,
            state,
            division,
            variant,
            shiny_if_potion,
            created_at,
            updated
        FROM event_queue
        WHERE room_id = ?
          AND event_name = 'room:wild-morty-added'
          AND wild_morty_id = ?
        ORDER BY id DESC
        LIMIT 1
    ");

    $stmt->execute([$room_id, $wild_morty_id]);

    $row = $stmt->fetch(PDO::FETCH_ASSOC);

    return $row ?: null;
}
$wildPayload = get_wild_morty_payload($pdo, $room_id, $wild_morty_id);
if (!$wildPayload) {
    http_response_code(409);
    echo json_encode(["success" => false, "error" => "Morty does not exist"], JSON_UNESCAPED_SLASHES);
    exit;
}
$wildMortyId = $wildPayload["morty_id"];


// ------------------------
// Load player and active deck
// ------------------------
$stmt = $pdo->prepare("
  SELECT player_id, username, player_avatar_id, level, xp, streak, coins, coupons, permits, xp_lower, xp_upper, active_deck_id
  FROM users
  WHERE player_id = ?
  LIMIT 1
");
$stmt->execute([$player_id]);
$playerRow = $stmt->fetch(PDO::FETCH_ASSOC);
if (!$playerRow) {
    http_response_code(404);
    echo json_encode(["success" => false, "error" => "Player not found"], JSON_UNESCAPED_SLASHES);
    exit;
}

// ------------------------
// Load owned morties and attacks
// ------------------------
$stmt = $pdo->prepare("
  SELECT owned_morty_id, morty_id, level, xp, hp, variant, hp_stat, xp_lower, xp_upper, is_locked, is_trading_locked
  FROM owned_morties
  WHERE player_id = ?
  ORDER BY created_at ASC
");
$stmt->execute([$player_id]);
$ownedMortiesRows = $stmt->fetchAll(PDO::FETCH_ASSOC);

$attacksByOwnedMorty = [];
$ownedMortyIds = array_map(fn($m) => $m["owned_morty_id"], $ownedMortiesRows);
if (!empty($ownedMortyIds)) {
    $ph = implode(",", array_fill(0, count($ownedMortyIds), "?"));
    $stmt = $pdo->prepare("
      SELECT owned_morty_id, attack_id, position, pp, pp_stat
      FROM owned_attacks
      WHERE owned_morty_id IN ($ph)
      ORDER BY owned_morty_id, position
    ");
    $stmt->execute($ownedMortyIds);
    foreach ($stmt->fetchAll(PDO::FETCH_ASSOC) as $a) {
        $oid = $a["owned_morty_id"];
        $attacksByOwnedMorty[$oid][] = [
            "attack_id" => $a["attack_id"],
            "position" => (int)$a["position"],
            "pp" => (int)$a["pp"],
            "pp_stat" => (int)$a["pp_stat"]
        ];
    }
}

// ------------------------
// Determine active morty
// ------------------------
$activeOwnedMorty = "";
$activeDeckId = $playerRow["active_deck_id"] ?? "";
$deckMortyIds = [];

if ($activeDeckId !== "" && $activeDeckId !== "0") {
    $stmt = $pdo->prepare("SELECT owned_morty_ids FROM decks WHERE deck_id = ? LIMIT 1");
    $stmt->execute([$activeDeckId]);
    $deckRow = $stmt->fetch(PDO::FETCH_ASSOC);
    if ($deckRow && isset($deckRow["owned_morty_ids"])) {
        $deckMortyIds = parse_id_list($deckRow["owned_morty_ids"]);
    }
}

$hpMap = [];
if (!empty($deckMortyIds)) {
    $ph = implode(",", array_fill(0, count($deckMortyIds), "?"));
    $stmt = $pdo->prepare("SELECT owned_morty_id, hp FROM owned_morties WHERE owned_morty_id IN ($ph)");
    $stmt->execute($deckMortyIds);
    foreach ($stmt->fetchAll(PDO::FETCH_ASSOC) as $r) {
        $hpMap[$r["owned_morty_id"]] = (int)$r["hp"];
    }
    foreach ($deckMortyIds as $oid) {
        if (($hpMap[$oid] ?? 0) > 0) {
            $activeOwnedMorty = $oid;
            break;
        }
    }
}

// ------------------------
// Build owned morties payload (only from active deck)
// ------------------------
$ownedMorties = [];
if (!empty($deckMortyIds)) {
    $deckMortyMap = array_flip($deckMortyIds); // quick lookup
    foreach ($ownedMortiesRows as $m) {
        if (!isset($deckMortyMap[$m["owned_morty_id"]])) continue; // skip if not in deck
        $oid = $m["owned_morty_id"];
        $ownedMorties[] = [
            "owned_morty_id" => $oid,
            "morty_id" => $m["morty_id"],
            "level" => (int)$m["level"],
            "xp_lower" => (int)($m["xp_lower"] ?? 0),
            "xp_upper" => (int)($m["xp_upper"] ?? 0),
            "xp" => (int)$m["xp"],
            "hp" => (int)$m["hp"],
            "variant" => $m["variant"],
            "hp_stat" => (int)$m["hp_stat"],
            "is_locked" => to_bool($m["is_locked"]),
            "is_trading_locked" => to_bool($m["is_trading_locked"]),
            "owned_attacks" => $attacksByOwnedMorty[$oid] ?? [],
        ];
    }
}

// ------------------------
// Player items
// ------------------------
$stmt = $pdo->prepare("SELECT item_id, quantity FROM owned_items WHERE player_id = ? ORDER BY item_id ASC");
$stmt->execute([$player_id]);
$ownedItems = array_map(fn($it) => [
    "item_id" => (string)$it["item_id"],
    "quantity" => (int)$it["quantity"]
], $stmt->fetchAll(PDO::FETCH_ASSOC));

// ------------------------
// Build player + opponent
// ------------------------
$moveLog = ["cooldown"=>new stdClass(),"count"=>new stdClass(),"cooldown_next"=>["ITEM"=>1],"last_move_type"=>new stdClass()];
$playerPayload = [
    "player_id"=>$playerRow["player_id"],
    "username"=>$playerRow["username"],
    "player_avatar_id"=>$playerRow["player_avatar_id"],
    "level"=>(int)$playerRow["level"],
    "xp"=>(int)$playerRow["xp"],
    "streak"=>(int)$playerRow["streak"],
    "coins"=>(int)$playerRow["coins"],
    "coupons"=>(int)$playerRow["coupons"],
    "permits"=>(int)$playerRow["permits"],
    "owned_morties"=>$ownedMorties,
    "owned_items"=>$ownedItems,
    "tags"=>[],
    "xp_lower"=>(int)($playerRow["xp_lower"]??0),
    "xp_upper"=>(int)($playerRow["xp_upper"]??0),
    "_meta"=>["session_id"=>$session_id,"isPlayerInDB"=>true,"isControlledByAI"=>false,"isRaidBoss"=>false],
    "active_owned_morty"=>$activeOwnedMorty,
    "move_log"=>$moveLog
];

$wild_owned_PlayerId = uuidv4();

// Make it based on player level
/*
$playerRow["level"]
function Disobedience(int $playerLevel): int {
    $maximum_obedient = $playerLevel * 2;
    if ($maximum_obedient > 100) {
        return 100;
    }
    return $maximum_obedient;
}

*/

$level = 999;
$xp = 1000000;
$opponentHP = rand(1, 1);

$opponentPayload = [
    "player_id"=>$wild_owned_PlayerId,
    "username"=>"AWILDMORTY",
    "player_avatar_id"=>"NOAVATAR",
    "owned_morties"=>[["owned_morty_id"=>$wild_morty_id,"morty_id"=>$wildMortyId,"level"=>$level,"xp"=>$xp,"hp"=>$opponentHP,"variant"=>$wildPayload["variant"]??"Normal","hp_stat"=>$opponentHP]],
    "streak"=>0,
    "shiny_if_potion"=>to_bool($wildPayload["shiny_if_potion"]??false),
    "_meta"=>["isPlayerInDB"=>false,"isControlledByAI"=>true,"isRaidBoss"=>false],
    "active_owned_morty"=>$wild_morty_id
];

// =========================
// 🔥 INSERT INTO BATTLES TABLE
// =========================
$battle_id = uuidv4(); // Generate a unique battle ID

$opponent_active_morty_id = $opponentPayload["active_owned_morty"];
$opponent_morty_id = $opponentPayload["owned_morties"][0]["morty_id"];
$opponent_hp = $opponentPayload["owned_morties"][0]["hp"];

$player_active_morty_id = $activeOwnedMorty;
$player_hp = 0;
// Find player's active morty HP
foreach ($ownedMorties as $m) {
    if ($m["owned_morty_id"] === $activeOwnedMorty) {
        $player_hp = $m["hp"];
        break;
    }
}

$stmt = $pdo->prepare("
    INSERT INTO battles (
        battle_id,
        player_id,
        opponent_id,
        wild_morty_id,
        opponent_active_morty,
        opponent_morty_id,
        opponent_hp,
        player_active_morty,
        player_hp,
        state,
        created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE', NOW())
");

$stmt->execute([
    $battle_id,
    $player_id,
    $opponentPayload["player_id"],
    $wildMortyId,
    $opponent_active_morty_id,
    $opponent_morty_id,
    $opponent_hp,
    $player_active_morty_id,
    $player_hp
]);

// ------------------------
// Build payload and publish
// ------------------------
$payload = ["battle_id"=>$battle_id,"battle_type"=>"PvWM","player"=>$playerPayload,"opponent"=>$opponentPayload,"meta"=>new stdClass()];
publish_event($pdo, $room_id, "battle:start", $payload, $player_id);
publish_event($pdo, $room_id, "room:wild-morty-state-changed", ["wild_morty_id"=>$wild_morty_id,"state"=>"BATTLE"]);
publish_event($pdo, $room_id, "room:user-state-changed", ["player_id"=>$player_id,"state"=>"BATTLE"]);

echo json_encode(["success"=>true], JSON_UNESCAPED_SLASHES);
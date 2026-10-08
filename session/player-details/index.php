<?php
// player-details (return ALL owned mortys, not just active deck)

error_reporting(E_ALL);
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require '../../pocket_f4894h398r8h9w9er8he98he.php';

function toBool($v) {
    if ($v === null) return false;
    if (is_bool($v)) return $v;
    $s = strtolower(trim((string)$v));
    return in_array($s, ["1","true","yes","y","on"], true);
}

function toNull($v) {
    if ($v === null) return null;
    $s = trim((string)$v);
    return ($s === '' || strtolower($s) === 'null') ? null : $s;
}

// decks.owned_morty_ids might be stored escaped like: [\"id1\",\"id2\"]
function decode_owned_ids(string $raw): array {
    $raw = trim($raw);
    if ($raw === '') return [];

    $decoded = json_decode($raw, true);
    if (is_array($decoded)) return array_values(array_filter(array_map('strval', $decoded)));

    $unescaped = stripcslashes($raw); // turns \" into "
    $decoded = json_decode($unescaped, true);
    if (is_array($decoded)) return array_values(array_filter(array_map('strval', $decoded)));

    $raw2 = trim($raw, "\"'");
    $raw2 = stripcslashes($raw2);
    $decoded = json_decode($raw2, true);
    if (is_array($decoded)) return array_values(array_filter(array_map('strval', $decoded)));

    return [];
}

$input = file_get_contents('php://input');
$data  = json_decode($input, true) ?: [];

$session_id = (string)($data['session_id'] ?? '');
if ($session_id === '') {
    http_response_code(401);
    echo json_encode(["error" => ["code" => "NOT_AUTHENTICATED"]], JSON_UNESCAPED_SLASHES);
    exit;
}

$stmt = $pdo->prepare("SELECT * FROM users WHERE session_id = ? LIMIT 1");
$stmt->execute([$session_id]);
$user = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$user) {
    http_response_code(401);
    echo json_encode(["error" => ["code" => "NOT_AUTHENTICATED"]], JSON_UNESCAPED_SLASHES);
    exit;
}

$player_id        = (string)$user['player_id'];
$player_avatar_id = (string)($user['player_avatar_id'] ?? 'AvatarRickDefault');

// ---------------- ACTIVE DECK IDS (for optional sorting) ----------------
$active_deck_id = (int)($user['active_deck_id'] ?? 0);

$stmt = $pdo->prepare("SELECT owned_morty_ids FROM decks WHERE player_id = ? AND deck_id = ? LIMIT 1");
$stmt->execute([$player_id, $active_deck_id]);
$deckRow = $stmt->fetch(PDO::FETCH_ASSOC);

$deckOwnedIds = decode_owned_ids((string)($deckRow['owned_morty_ids'] ?? ''));

// ---------------- OWNED MORTIES (ALL) + ATTACKS ----------------
$owned_morties = [];

$sql = "
    SELECT
        m.owned_morty_id,
        m.morty_id,
        m.level,
        m.xp,
        m.hp,
        m.hp_stat,
        m.attack_stat,
        m.defence_stat,
        m.variant,
        m.speed_stat,
        m.is_locked,
        m.is_trading_locked,
        m.fight_pit_id,
        m.evolution_points,
        m.xp_lower,
        m.xp_upper,

        a.attack_id,
        a.position,
        a.pp,
        a.pp_stat

    FROM owned_morties m
    LEFT JOIN owned_attacks a
        ON m.owned_morty_id = a.owned_morty_id

    WHERE m.player_id = ?

    ORDER BY m.owned_morty_id ASC, a.position ASC
";

$stmt = $pdo->prepare($sql);
$stmt->execute([$player_id]);
$rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

// Build morties keyed by owned_morty_id
$byId = [];
foreach ($rows as $row) {
    $id = (string)$row['owned_morty_id'];

    if (!isset($byId[$id])) {
        $byId[$id] = [
            "owned_morty_id"     => $id,
            "morty_id"           => (string)$row['morty_id'],
            "level"              => (int)$row['level'],
            "xp"                 => (int)$row['xp'],
            "hp"                 => (int)$row['hp'],
            "hp_stat"            => (int)$row['hp_stat'],
            "attack_stat"        => (int)$row['attack_stat'],
            "defence_stat"       => (int)$row['defence_stat'],
            "variant"            => (string)($row['variant'] ?? 'Normal'),
            "speed_stat"         => (int)$row['speed_stat'],
            "is_locked"          => toBool($row['is_locked']),
            "is_trading_locked"  => toBool($row['is_trading_locked']),
            "fight_pit_id"       => toNull($row['fight_pit_id']),
            "evolution_points"   => (int)$row['evolution_points'],
            "owned_attacks"      => [],
            "xp_lower"           => (int)($row['xp_lower'] ?? 0),
            "xp_upper"           => (int)($row['xp_upper'] ?? 0),
        ];
    }

    if (!empty($row['attack_id'])) {
        $byId[$id]['owned_attacks'][] = [
            "attack_id" => (string)$row['attack_id'],
            "position"  => (int)$row['position'],
            "pp"        => (int)$row['pp'],
            "pp_stat"   => (int)$row['pp_stat'],
        ];
    }
}

// OPTIONAL: return active-deck morties first (in deck order), then the rest
if (!empty($deckOwnedIds)) {
    $inDeck = [];
    foreach ($deckOwnedIds as $oid) {
        if (isset($byId[$oid])) {
            $inDeck[] = $byId[$oid];
            unset($byId[$oid]);
        }
    }
    // remaining morties (not in deck)
    $rest = array_values($byId);
    $owned_morties = array_merge($inDeck, $rest);
} else {
    $owned_morties = array_values($byId);
}

// ---------------- decks list ----------------
$stmt = $pdo->prepare("SELECT deck_id, owned_morty_ids FROM decks WHERE player_id = ?");
$stmt->execute([$player_id]);
$decks_raw = $stmt->fetchAll(PDO::FETCH_ASSOC);

$decks = [];
foreach ($decks_raw as $deck) {
    $decks[] = [
        "deck_id" => (int)$deck["deck_id"],
        "owned_morty_ids" => decode_owned_ids((string)$deck["owned_morty_ids"]),
    ];
}

// ---------------- owned_items ----------------
$stmt = $pdo->prepare("SELECT item_id, quantity FROM owned_items WHERE player_id = ?");
$stmt->execute([$player_id]);
$owned_items = $stmt->fetchAll(PDO::FETCH_ASSOC);

// ---------------- owned_avatars ----------------
$stmt = $pdo->prepare("SELECT player_avatar_id FROM owned_avatars WHERE player_id = ? LIMIT 1");
$stmt->execute([$player_id]);
$row = $stmt->fetch(PDO::FETCH_ASSOC);

$owned_avatars = [];
$raw = (string)($row['player_avatar_id'] ?? '');

if ($raw !== '') {
    $decoded = json_decode($raw, true);
    if (!is_array($decoded)) $decoded = json_decode(stripcslashes($raw), true);

    if (is_array($decoded)) {
        foreach ($decoded as $avatar) {
            $avatar = trim((string)$avatar);
            $avatar = trim($avatar, "\"' \t\r\n");
            if ($avatar !== '') {
                $owned_avatars[] = ["player_avatar_id" => $avatar];
            }
        }
    }
}

// ---------------- mortydex ----------------
$stmt = $pdo->prepare("SELECT morty_id, caught FROM mortydex WHERE player_id = ?");
$stmt->execute([$player_id]);
$rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

$mortydex = [];
foreach ($rows as $r) {
    $mortydex[] = [
        "morty_id" => (string)$r["morty_id"],
        "caught"   => filter_var($r["caught"], FILTER_VALIDATE_BOOLEAN),
    ];
}

// ---------------- response ----------------
$responseArray = [
    "player_id" => (string)($user["player_id"] ?? ""),
    "username" => (string)($user["username"] ?? ""),
    "player_avatar_id" => $player_avatar_id,

    "level" => (int)($user["level"] ?? 1),
    "xp" => (int)($user["xp"] ?? 0),
    "streak" => (int)($user["streak"] ?? 0),

    "coins" => (int)($user["coins"] ?? 0),
    "coupons" => (int)($user["coupons"] ?? 0),
    "permits" => (int)($user["permits"] ?? 0),

    "challenge_reward" => false,

    // ✅ NOW: ALL OWNED MORTIES
    "owned_morties" => array_values($owned_morties),

    "active_deck_id" => (int)($user["active_deck_id"] ?? 0),
    "decks_owned" => (int)($user["decks_owned"] ?? 0),
    "decks" => array_values($decks),

    "owned_items" => array_values($owned_items),
    "owned_avatars" => array_values($owned_avatars),
    "mortydex" => array_values($mortydex),

    "tags" => [],
    "play_shiny_potion" => null,

    "xp_lower" => (int)($user["xp_lower"] ?? 0),
    "xp_upper" => (int)($user["xp_upper"] ?? 0),
];

echo json_encode($responseArray, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
exit;

<?php
// /session/deck/set-active

error_reporting(E_ALL);
ini_set('display_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require __DIR__ . "/../../../pocket_f4894h398r8h9w9er8he98he.php"; // provides $pdo

function respond(int $code, array $data) {
    http_response_code($code);
    echo json_encode($data, JSON_UNESCAPED_SLASHES);
    exit;
}

$raw  = file_get_contents("php://input");
$data = json_decode($raw, true);
if (!is_array($data)) respond(400, ["success" => false, "error" => "Invalid JSON"]);

$session_id = $data["session_id"] ?? "";
$deck_id    = $data["deck_id"] ?? null;

if (!$session_id) respond(401, ["success" => false, "error" => "Not authenticated"]);
if (!is_int($deck_id)) respond(400, ["success" => false, "error" => "deck_id must be int"]);

// Load user
$u = $pdo->prepare("SELECT player_id, username, player_avatar_id, level, xp, streak, active_deck_id, decks_owned, xp_lower, xp_upper, tags
                    FROM users
                    WHERE session_id = ?
                    LIMIT 1");
$u->execute([$session_id]);
$user = $u->fetch(PDO::FETCH_ASSOC);
if (!$user) respond(401, ["success" => false, "error" => "Invalid session"]);

$player_id   = $user["player_id"];
$decks_owned = (int)($user["decks_owned"] ?? 0);

if ($deck_id < 0 || $deck_id >= $decks_owned) {
    respond(409, [
        "success" => false,
        "error" => "Invalid deck_id",
        "deck_id" => $deck_id,
        "decks_owned" => $decks_owned
    ]);
}

// Verify the deck exists and is not empty
$d = $pdo->prepare("SELECT owned_morty_ids
                    FROM decks
                    WHERE player_id = ? AND deck_id = ?
                    LIMIT 1");
$d->execute([$player_id, $deck_id]);
$deckRow = $d->fetch(PDO::FETCH_ASSOC);

if (!$deckRow) {
    respond(409, ["success" => false, "error" => "Deck does not exist", "deck_id" => $deck_id]);
}

$ids = json_decode($deckRow["owned_morty_ids"] ?? "[]", true);
if (!is_array($ids)) $ids = [];
if (count($ids) === 0) {
    respond(409, ["success" => false, "error" => "Cannot activate empty deck", "deck_id" => $deck_id]);
}

// Update active deck
$set = $pdo->prepare("UPDATE users SET active_deck_id = ? WHERE session_id = ?");
$set->execute([$deck_id, $session_id]);

$user["active_deck_id"] = $deck_id;

// Build decks list for response (only existing non-empty decks, like your sample)
$dq = $pdo->prepare("SELECT deck_id, owned_morty_ids
                     FROM decks
                     WHERE player_id = ?
                     ORDER BY deck_id ASC");
$dq->execute([$player_id]);

$decks = [];
while ($r = $dq->fetch(PDO::FETCH_ASSOC)) {
    $list = json_decode($r["owned_morty_ids"] ?? "[]", true);
    if (!is_array($list)) $list = [];
    if (count($list) === 0) continue;

    $decks[] = [
        "deck_id" => (int)$r["deck_id"],
        "owned_morty_ids" => array_values($list)
    ];
}

// tags stored as text; client expects []
$tags = [];
if (!empty($user["tags"])) {
    $maybe = json_decode($user["tags"], true);
    if (is_array($maybe)) $tags = $maybe;
}

echo json_encode([
    "player_id" => $player_id,
    "username" => $user["username"],
    "player_avatar_id" => $user["player_avatar_id"],
    "level" => (int)$user["level"],
    "xp" => (int)$user["xp"],
    "streak" => (int)$user["streak"],
    "active_deck_id" => (int)$user["active_deck_id"],
    "decks_owned" => $decks_owned,
    "decks" => $decks,
    "xp_lower" => (int)($user["xp_lower"] ?? 0),
    "xp_upper" => (int)($user["xp_upper"] ?? 0),
    "tags" => $tags
], JSON_UNESCAPED_SLASHES);

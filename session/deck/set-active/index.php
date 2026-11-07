<?php
// /session/deck/set-active

error_reporting(E_ALL);
ini_set('display_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require __DIR__ . "/../../../pocket_f4894h398r8h9w9er8he98he.php"; // provides $pdo
require_once __DIR__ . "/../../../lib/battle_membership_guard.php";
require_once __DIR__ . "/../../../lib/trade_party_transitions.php";


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

try {
    $pdo->beginTransaction();

    // Shared reservations and party writers serialize on the authenticated user.
    $lock = $pdo->prepare("SELECT * FROM users WHERE player_id = ? FOR UPDATE");
    $lock->execute([$player_id]);
    $lockedUsers = $lock->fetchAll(PDO::FETCH_ASSOC);
    $sessionCheck = $pdo->prepare("SELECT id, session_id FROM users WHERE session_id = ? ORDER BY id FOR UPDATE");
    $sessionCheck->execute([$session_id]);
    $sessionUsers = $sessionCheck->fetchAll(PDO::FETCH_ASSOC);
    if (count($lockedUsers) !== 1 || $lockedUsers[0]['player_id'] !== $player_id
        || $lockedUsers[0]['session_id'] !== $session_id || count($sessionUsers) !== 1
        || $sessionUsers[0]['id'] !== $lockedUsers[0]['id'] || $sessionUsers[0]['session_id'] !== $session_id) {
        $pdo->rollBack();
        respond(401, ["success" => false, "error" => "Invalid session"]);
    }
    $user = $lockedUsers[0];
    if (battle_has_shared_membership($pdo, $player_id)) {
        $pdo->rollBack();
        respond(409, ["success" => false, "error" => "FAILED"]);
    }
    $decks_owned = (int)($user["decks_owned"] ?? 0);
    if ($deck_id < 0 || $deck_id >= $decks_owned) {
        $pdo->rollBack();
        respond(409, ["success" => false, "error" => "Invalid deck_id", "deck_id" => $deck_id, "decks_owned" => $decks_owned]);
    }
    // Verify the deck exists and is not empty
    $deckRow = trade_party_transition_target($pdo, $user, $deck_id);

    if (!$deckRow) {
        $pdo->rollBack();
        respond(409, ["success" => false, "error" => "Deck does not exist", "deck_id" => $deck_id]);
    }

    $ids = trade_party_transition_decode($deckRow["owned_morty_ids"]);
    if (count($ids) === 0) {
        $pdo->rollBack();
        respond(409, ["success" => false, "error" => "Cannot activate empty deck", "deck_id" => $deck_id]);
    }

    trade_party_transition_ids($pdo, $user, $ids);

    // Update active deck
    $set = $pdo->prepare("UPDATE users SET active_deck_id = ? WHERE session_id = ?");
    $set->execute([$deck_id, $session_id]);

    $user["active_deck_id"] = $deck_id;

    $pdo->commit();
} catch (Throwable $e) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    if ($e instanceof TradePartyTransitionError) respond($e->status, ["success" => false, "error" => ["code" => "FAILED"]]);
    respond(500, ["success" => false, "error" => "Server error"]);
}

// Build decks list for response (only existing non-empty decks, like your sample)
$dq = $pdo->prepare("SELECT deck_id, owned_morty_ids
                     FROM decks
                     WHERE player_id = ?
                     ORDER BY deck_id ASC");
$dq->execute([$player_id]);

$decks = [];
while ($r = $dq->fetch(PDO::FETCH_ASSOC)) {
    $list = json_decode($r["owned_morty_ids"] ?? "[]", true);
    if (!is_array($list)) $list = json_decode(stripcslashes($r["owned_morty_ids"] ?? "[]"), true);
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

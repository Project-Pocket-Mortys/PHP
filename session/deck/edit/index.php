<?php
// /session/deck/edit

error_reporting(E_ALL);
ini_set('display_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require __DIR__ . "/../../../pocket_f4894h398r8h9w9er8he98he.php"; // must provide $pdo

function respond(int $code, array $data) {
    http_response_code($code);
    echo json_encode($data, JSON_UNESCAPED_SLASHES);
    exit;
}

function is_uuid(string $s): bool {
    return (bool)preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i', $s);
}

$raw = file_get_contents("php://input");
$data = json_decode($raw, true);
if (!is_array($data)) respond(400, ["success" => false, "error" => "Invalid JSON"]);

$session_id = $data["session_id"] ?? "";
$deck_id    = $data["deck_id"] ?? null;
$list       = $data["owned_morty_ids"] ?? null;

if (!$session_id) respond(401, ["success" => false, "error" => "Not authenticated"]);
if (!is_int($deck_id)) respond(400, ["success" => false, "error" => "deck_id must be int"]);
if (!is_array($list)) respond(400, ["success" => false, "error" => "owned_morty_ids must be array"]);

// Load user by session_id
$u = $pdo->prepare("SELECT player_id, username, player_avatar_id, level, xp, streak, active_deck_id, decks_owned, xp_lower, xp_upper, tags
                    FROM users
                    WHERE session_id = ?
                    LIMIT 1");
$u->execute([$session_id]);
$user = $u->fetch(PDO::FETCH_ASSOC);
if (!$user) respond(401, ["success" => false, "error" => "Invalid session"]);

$player_id   = $user["player_id"];
$decks_owned = (int)($user["decks_owned"] ?? 0);

if ($decks_owned <= 0) {
    respond(409, ["success" => false, "error" => "Player has no decks_owned set"]);
}

// Validate deck_id range
if ($deck_id < 0 || $deck_id >= $decks_owned) {
    respond(409, [
        "success" => false,
        "error" => "Invalid deck_id",
        "deck_id" => $deck_id,
        "decks_owned" => $decks_owned
    ]);
}

// Normalize list: strings only, trim, remove empties, dedupe (keep order)
$seen = [];
$owned_morty_ids = [];
foreach ($list as $id) {
    if (!is_string($id)) continue;
    $id = trim($id);
    if ($id === "") continue;
    if (isset($seen[$id])) continue;
    $seen[$id] = true;
    $owned_morty_ids[] = $id;
}

// Max deck size (Pocket Mortys uses 5 in your samples)
$MAX_DECK = 5;
if (count($owned_morty_ids) > $MAX_DECK) {
    respond(409, ["success" => false, "error" => "Deck too large", "max" => $MAX_DECK]);
}

$bad = [];
foreach ($owned_morty_ids as $id) {
    if (!is_uuid($id)) {
        $bad[] = [
            "raw" => $id,
            "len" => strlen($id),
            "hex" => bin2hex($id)
        ];
    }
}

if ($bad) {
    respond(409, [
        "success" => false,
        "error" => "Invalid owned_morty_id format",
        "invalid" => $bad
    ]);
}

try {
    $pdo->beginTransaction();

    // If empty list: delete deck row (matches your observed behavior)
    if (count($owned_morty_ids) === 0) {
        $del = $pdo->prepare("DELETE FROM decks WHERE player_id = ? AND deck_id = ?");
        $del->execute([$player_id, $deck_id]);

        // DO NOT change active_deck_id when empty (matches your sample)
    } else {
        // Verify ownership: every owned_morty_id must exist in owned_morties for this player
        $placeholders = implode(",", array_fill(0, count($owned_morty_ids), "?"));
        $params = array_merge([$player_id], $owned_morty_ids);

        $chk = $pdo->prepare("
            SELECT owned_morty_id
            FROM owned_morties
            WHERE player_id = ?
              AND owned_morty_id IN ($placeholders)
        ");
        $chk->execute($params);

        $found = $chk->fetchAll(PDO::FETCH_COLUMN, 0);
        $foundSet = array_fill_keys($found, true);

        $missing = [];
        foreach ($owned_morty_ids as $id) {
            if (!isset($foundSet[$id])) $missing[] = $id;
        }
        if ($missing) {
            $pdo->rollBack();
            respond(409, ["success" => false, "error" => "Owned morty not found for player", "missing" => $missing]);
        }

        // Store JSON array string exactly like your DB format
        $deck_json = json_encode(array_values($owned_morty_ids), JSON_UNESCAPED_SLASHES);

        // Upsert (since decks table has no unique key on player_id+deck_id)
        $exists = $pdo->prepare("SELECT id FROM decks WHERE player_id = ? AND deck_id = ? LIMIT 1");
        $exists->execute([$player_id, $deck_id]);
        $rowId = $exists->fetchColumn();

        if ($rowId) {
            $up = $pdo->prepare("UPDATE decks SET owned_morty_ids = ? WHERE id = ?");
            $up->execute([$deck_json, $rowId]);
        } else {
            $ins = $pdo->prepare("INSERT INTO decks (player_id, deck_id, owned_morty_ids) VALUES (?, ?, ?)");
            $ins->execute([$player_id, $deck_id, $deck_json]);
        }

        // Set active deck ONLY when non-empty (matches your sample behavior)
        $setActive = $pdo->prepare("UPDATE users SET active_deck_id = ? WHERE session_id = ?");
        $setActive->execute([$deck_id, $session_id]);

        $user["active_deck_id"] = $deck_id; // keep response consistent
    }

    $pdo->commit();
} catch (Throwable $e) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    respond(500, ["success" => false, "error" => "Server error", "detail" => $e->getMessage()]);
}

// Reload decks for response
$dq = $pdo->prepare("SELECT deck_id, owned_morty_ids
                     FROM decks
                     WHERE player_id = ?
                     ORDER BY deck_id ASC");
$dq->execute([$player_id]);

$decks = [];
while ($r = $dq->fetch(PDO::FETCH_ASSOC)) {
    $ids = json_decode($r["owned_morty_ids"] ?? "[]", true);
    if (!is_array($ids)) $ids = [];
    // Optional: filter out empty decks just in case
    if (count($ids) === 0) continue;

    $decks[] = [
        "deck_id" => (int)$r["deck_id"],
        "owned_morty_ids" => array_values($ids)
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
    "active_deck_id" => (int)($user["active_deck_id"] ?? 0),
    "decks_owned" => $decks_owned,
    "decks" => $decks,
    "xp_lower" => (int)($user["xp_lower"] ?? 0),
    "xp_upper" => (int)($user["xp_upper"] ?? 0),
    "tags" => $tags
], JSON_UNESCAPED_SLASHES);

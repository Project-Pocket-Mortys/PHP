<?php
// heal

error_reporting(E_ALL);
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");
header("Access-Control-Allow-Headers: Content-Type");
header("Access-Control-Allow-Methods: POST, OPTIONS");

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
  http_response_code(204);
  exit;
}

require __DIR__ . "/../../pocket_f4894h398r8h9w9er8he98he.php"; // $pdo

// ---------------- helpers ----------------
function json_out(array $arr, int $code = 200): void {
  http_response_code($code);
  echo json_encode($arr, JSON_UNESCAPED_SLASHES);
  exit;
}

function toBool($v): bool {
  if ($v === null) return false;
  if (is_bool($v)) return $v;
  $s = strtolower(trim((string)$v));
  return in_array($s, ["1", "true", "yes", "y", "on"], true);
}

function toNull($v) {
  if ($v === null) return null;
  $s = trim((string)$v);
  if ($s === "" || strtolower($s) === "null") return null;
  return $s;
}

/**
 * Your decks.owned_morty_ids are stored like:
 *   [\"id1\",\"id2\",...]
 * This safely converts to a PHP array of ids.
 */
function decode_owned_ids(string $raw): array {
  $raw = trim($raw);
  if ($raw === "") return [];

  // Attempt 1: decode as-is
  $decoded = json_decode($raw, true);
  if (is_array($decoded)) {
    return array_values(array_filter(array_map('strval', $decoded), fn($x) => $x !== ""));
  }

  // Attempt 2: remove escaping (\" -> ")
  $unescaped = stripcslashes($raw);
  $decoded = json_decode($unescaped, true);
  if (is_array($decoded)) {
    return array_values(array_filter(array_map('strval', $decoded), fn($x) => $x !== ""));
  }

  // Attempt 3: strip surrounding quotes then unescape
  $raw2 = trim($raw, "\"'");
  $raw2 = stripcslashes($raw2);
  $decoded = json_decode($raw2, true);
  if (is_array($decoded)) {
    return array_values(array_filter(array_map('strval', $decoded), fn($x) => $x !== ""));
  }

  return [];
}

// ---------------- main ----------------
$body = json_decode(file_get_contents("php://input"), true) ?: [];
$session_id = (string)($body["session_id"] ?? "");

if ($session_id === "") {
  json_out(["error" => ["code" => "NOT_AUTHENTICATED"]], 401);
}

try {
  $pdo->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);

  // 1) user by session_id
  $stmt = $pdo->prepare("SELECT * FROM users WHERE session_id = ? LIMIT 1");
  $stmt->execute([$session_id]);
  $user = $stmt->fetch(PDO::FETCH_ASSOC);

  if (!$user) {
    json_out(["error" => ["code" => "INVALID_SESSION"]], 401);
  }

  $player_id = (string)($user["player_id"] ?? "");
  if ($player_id === "") {
    json_out(["error" => ["code" => "NO_PLAYER_ID"]], 500);
  }

  $active_deck_id = (int)($user["active_deck_id"] ?? -1);
  if ($active_deck_id < 0) {
    json_out(["error" => ["code" => "NO_ACTIVE_DECK"]], 400);
  }

  // 2) deck -> owned ids
  $stmt = $pdo->prepare("
    SELECT owned_morty_ids
    FROM decks
    WHERE player_id = ?
      AND deck_id = ?
    LIMIT 1
  ");
  $stmt->execute([$player_id, $active_deck_id]);
  $deck = $stmt->fetch(PDO::FETCH_ASSOC);

  $ownedIds = decode_owned_ids((string)($deck["owned_morty_ids"] ?? ""));
  if (!$ownedIds) {
    // This is the reason you saw owned_morties: []
    json_out(["error" => ["code" => "DECK_EMPTY"]], 400);
  }

  // 3) heal HP + PP (transaction)
  $pdo->beginTransaction();

  $ph = implode(",", array_fill(0, count($ownedIds), "?"));

  // HP -> full
  $sqlHp = "
    UPDATE owned_morties
    SET hp = hp_stat
    WHERE player_id = ?
      AND owned_morty_id IN ($ph)
  ";
  $stmt = $pdo->prepare($sqlHp);
  $stmt->execute(array_merge([$player_id], $ownedIds));

  // PP -> full (owned_attacks table)
  $sqlPp = "
    UPDATE owned_attacks
    SET pp = pp_stat
    WHERE owned_morty_id IN ($ph)
  ";
  $stmt = $pdo->prepare($sqlPp);
  $stmt->execute($ownedIds);

  $pdo->commit();

  // 4) fetch morties in deck order (FIELD keeps exact order)
  $fieldList = implode(",", array_fill(0, count($ownedIds), "?"));
  $sqlMorties = "
    SELECT *
    FROM owned_morties
    WHERE player_id = ?
      AND owned_morty_id IN ($ph)
    ORDER BY FIELD(owned_morty_id, $fieldList)
  ";
  $stmt = $pdo->prepare($sqlMorties);
  $stmt->execute(array_merge([$player_id], $ownedIds, $ownedIds));
  $morties = $stmt->fetchAll(PDO::FETCH_ASSOC);

  // 5) fetch attacks
  $sqlAttacks = "
    SELECT owned_morty_id, attack_id, position, pp, pp_stat
    FROM owned_attacks
    WHERE owned_morty_id IN ($ph)
    ORDER BY owned_morty_id ASC, position ASC
  ";
  $stmt = $pdo->prepare($sqlAttacks);
  $stmt->execute($ownedIds);
  $attRows = $stmt->fetchAll(PDO::FETCH_ASSOC);

  $attByOwned = [];
  foreach ($attRows as $a) {
    $oid = (string)$a["owned_morty_id"];
    if (!isset($attByOwned[$oid])) $attByOwned[$oid] = [];
    $attByOwned[$oid][] = [
      "attack_id" => (string)$a["attack_id"],
      "position"  => (int)$a["position"],
      "pp"        => (int)$a["pp"],
      "pp_stat"   => (int)$a["pp_stat"],
    ];
  }

  // 6) build owned_morties output
  // (If a morty id from deck isn't found in owned_morties table, skip it safely)
  $mortyById = [];
  foreach ($morties as $m) {
    $mortyById[(string)$m["owned_morty_id"]] = $m;
  }

  $owned_morties = [];
  foreach ($ownedIds as $oid) {
    if (!isset($mortyById[$oid])) continue;
    $m = $mortyById[$oid];

    $owned_morties[] = [
      "owned_morty_id"    => (string)$m["owned_morty_id"],
      "morty_id"          => (string)$m["morty_id"],
      "level"             => (int)$m["level"],
      "xp"                => (int)$m["xp"],
      "hp"                => (int)$m["hp"],
      "hp_stat"           => (int)$m["hp_stat"],
      "attack_stat"       => (int)$m["attack_stat"],
      "defence_stat"      => (int)$m["defence_stat"],
      "variant"           => (string)($m["variant"] ?? "Normal"),
      "speed_stat"        => (int)$m["speed_stat"],
      "is_locked"         => toBool($m["is_locked"] ?? false),
      "is_trading_locked" => toBool($m["is_trading_locked"] ?? false),
      "fight_pit_id"      => toNull($m["fight_pit_id"] ?? null),
      "evolution_points"  => (int)($m["evolution_points"] ?? 0),
      "owned_attacks"     => $attByOwned[$oid] ?? [],
      "xp_lower"          => (int)($m["xp_lower"] ?? 0),
      "xp_upper"          => (int)($m["xp_upper"] ?? 0),
    ];
  }

  // 7) output EXACT key order like your example
  $player = [
    "player_id"        => (string)$user["player_id"],
    "username"         => (string)$user["username"],
    "player_avatar_id" => (string)$user["player_avatar_id"],
    "level"            => (int)$user["level"],
    "xp"               => (int)$user["xp"],
    "streak"           => (int)($user["streak"] ?? 0),
    "owned_morties"    => $owned_morties,
    "xp_lower"         => (int)($user["xp_lower"] ?? 0),
    "xp_upper"         => (int)($user["xp_upper"] ?? 0),
    "tags"             => []
  ];

  json_out($player, 200);

} catch (Throwable $e) {
  if (isset($pdo) && $pdo->inTransaction()) $pdo->rollBack();
  json_out(["error" => ["code" => "SERVER_ERROR", "message" => $e->getMessage()]], 500);
}
<?php
// session/gacha

error_reporting(E_ALL);
ini_set('display_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require __DIR__ . "/../../pocket_f4894h398r8h9w9er8he98he.php"; // must set $pdo (PDO)

// ---------------- CONFIG ----------------
const MAX_DECK_SIZE     = 5;
const MAX_ITEM_QUANTITY = 10;

// ---------------- HELPERS ----------------
function uuidv4(): string {
  $data = random_bytes(16);
  $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
  $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
  return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
}
function randInt(int $min, int $max): int { return random_int($min, $max); }

function jsonOut(int $code, array $payload): void {
  http_response_code($code);
  echo json_encode($payload, JSON_UNESCAPED_SLASHES);
  exit;
}

function playerIdFromSession(PDO $pdo, string $session_id): ?string {
  $st = $pdo->prepare("SELECT player_id FROM users WHERE session_id = ? LIMIT 1");
  $st->execute([$session_id]);
  $v = $st->fetchColumn();
  if ($v === false || $v === null || (string)$v === "") return null;
  return (string)$v;
}

function getActiveDeckId(PDO $pdo, string $player_id): int {
  $st = $pdo->prepare("SELECT active_deck_id FROM users WHERE player_id = ? LIMIT 1");
  $st->execute([$player_id]);
  $v = $st->fetchColumn();
  return ($v === false || $v === null) ? 0 : (int)$v;
}

// Deck JSON normalization
function decodeDeckIds(?string $raw): array {
  if ($raw === null || $raw === "") return [];
  $arr = json_decode($raw, true);
  if (is_array($arr)) return $arr;
  $fixed = stripslashes($raw);
  $arr2 = json_decode($fixed, true);
  if (is_array($arr2)) return $arr2;
  $fixed2 = str_replace('\\"', '"', $raw);
  $arr3 = json_decode($fixed2, true);
  if (is_array($arr3)) return $arr3;
  return [];
}
function loadDeckMortyIds(PDO $pdo, string $player_id, int $deck_id): array {
  $st = $pdo->prepare("SELECT owned_morty_ids FROM decks WHERE player_id = ? AND deck_id = ? LIMIT 1");
  $st->execute([$player_id, $deck_id]);
  $raw = $st->fetchColumn();
  $ids = decodeDeckIds($raw === false ? "" : (string)$raw);
  return array_values(array_filter($ids, fn($x) => is_string($x) && $x !== ""));
}
function saveDeckMortyIds(PDO $pdo, string $player_id, int $deck_id, array $ids): void {
  $json = json_encode(array_values($ids), JSON_UNESCAPED_SLASHES);
  $up = $pdo->prepare("UPDATE decks SET owned_morty_ids = ? WHERE player_id = ? AND deck_id = ?");
  $up->execute([$json, $player_id, $deck_id]);
  if ($up->rowCount() === 0) {
    $ins = $pdo->prepare("INSERT INTO decks (player_id, deck_id, owned_morty_ids) VALUES (?, ?, ?)");
    $ins->execute([$player_id, $deck_id, $json]);
  }
}
function maybeAddToActiveDeck(PDO $pdo, string $player_id, string $owned_morty_id): bool {
  $deck_id = getActiveDeckId($pdo, $player_id);
  $ids = loadDeckMortyIds($pdo, $player_id, $deck_id);
  if (in_array($owned_morty_id, $ids, true)) return true;
  if (count($ids) >= MAX_DECK_SIZE) return false;
  $ids[] = $owned_morty_id;
  saveDeckMortyIds($pdo, $player_id, $deck_id, $ids);
  return true;
}

function upsertMortydexCaught(PDO $pdo, string $player_id, string $morty_id): void {
  $chk = $pdo->prepare("SELECT id FROM mortydex WHERE player_id = ? AND morty_id = ? LIMIT 1");
  $chk->execute([$player_id, $morty_id]);
  $id = $chk->fetchColumn();
  if ($id) {
    $up = $pdo->prepare("UPDATE mortydex SET caught = 'true' WHERE id = ?");
    $up->execute([(int)$id]);
  } else {
    $ins = $pdo->prepare("INSERT INTO mortydex (player_id, morty_id, caught) VALUES (?, ?, 'true')");
    $ins->execute([$player_id, $morty_id]);
  }
}

/**
 * Inventory grant with per-item cap 10
 * - returns JSON entry where "quantity" is TOTAL after grant
 * - no substitute
 */
function grantItem(PDO $pdo, string $player_id, string $item_id, int $addQty): array {
  $st = $pdo->prepare("SELECT id, quantity FROM owned_items WHERE player_id = ? AND item_id = ? LIMIT 1");
  $st->execute([$player_id, $item_id]);
  $row = $st->fetch(PDO::FETCH_ASSOC);

  $curQty = $row ? (int)$row["quantity"] : 0;

  if ($curQty >= MAX_ITEM_QUANTITY) {
    return ["type"=>"ITEM","item_id"=>$item_id,"quantity"=>$curQty,"amount_received"=>0,"amount"=>1];
  }

  $targetQty = min(MAX_ITEM_QUANTITY, $curQty + $addQty);
  $added = max(0, $targetQty - $curQty);

  if ($row) {
    if ($added > 0) {
      $up = $pdo->prepare("UPDATE owned_items SET quantity = ? WHERE id = ?");
      $up->execute([$targetQty, (int)$row["id"]]);
    }
  } else {
    if ($added > 0) {
      $ins = $pdo->prepare("INSERT INTO owned_items (player_id, item_id, quantity) VALUES (?, ?, ?)");
      $ins->execute([$player_id, $item_id, $targetQty]);
    }
  }

  return ["type"=>"ITEM","item_id"=>$item_id,"quantity"=>$targetQty,"amount_received"=>$added,"amount"=>1];
}

// ---------------- DB GACHA LOOKUPS ----------------
function dbGetGacha(PDO $pdo, string $gacha_id): ?array {
  $st = $pdo->prepare("SELECT gacha_id, cost, lvl_min, lvl_max FROM gachas WHERE gacha_id = ? LIMIT 1");
  $st->execute([$gacha_id]);
  $row = $st->fetch(PDO::FETCH_ASSOC);
  if (!$row) return null;
  return [
    "gacha_id" => (string)$row["gacha_id"],
    "cost"     => (int)$row["cost"],
    "lvl_min"  => (int)$row["lvl_min"],
    "lvl_max"  => (int)$row["lvl_max"],
  ];
}

function dbGetGachaContents(PDO $pdo, string $gacha_id): array {
  $st = $pdo->prepare("SELECT id, reward, quantity, division_guarantee FROM gacha_contents WHERE gacha_id = ? ORDER BY id ASC");
  $st->execute([$gacha_id]);
  $rows = $st->fetchAll(PDO::FETCH_ASSOC) ?: [];
  foreach ($rows as &$r) {
    $r["id"] = (int)$r["id"];
    $r["quantity"] = (int)$r["quantity"];
    $r["division_guarantee"] = ($r["division_guarantee"] === null) ? null : (int)$r["division_guarantee"];
    $r["reward"] = (string)$r["reward"];
  }
  return $rows;
}

function dbPickRandomItemFromContent(PDO $pdo, int $gacha_content_id): ?string {
  $st = $pdo->prepare("SELECT item_id FROM gacha_content_items WHERE gacha_content_id = ?");
  $st->execute([$gacha_content_id]);
  $items = $st->fetchAll(PDO::FETCH_COLUMN) ?: [];
  if (!$items) return null;
  return (string)$items[array_rand($items)];
}

function dbGetActivePromo(PDO $pdo, int $now): ?array {
  $st = $pdo->prepare("
    SELECT gacha_promo_id
    FROM gacha_promos
    WHERE period_start <= ? AND period_end >= ?
    ORDER BY period_start DESC
    LIMIT 1
  ");
  $st->execute([$now, $now]);
  $row = $st->fetch(PDO::FETCH_ASSOC);
  if (!$row) return null;
  return ["gacha_promo_id" => (string)$row["gacha_promo_id"]];
}

/**
 * PROMO ONLY: pick a random promo morty row (uniform)
 */
function dbPickPromoMorty(PDO $pdo, string $promo_id): array {
  $st = $pdo->prepare("
    SELECT morty_id, variant, lvl_min, lvl_max, hp_min, hp_max, atk_min, atk_max, def_min, def_max, spd_min, spd_max
    FROM gacha_promo_mortys
    WHERE gacha_promo_id = ?
  ");
  $st->execute([$promo_id]);
  $rows = $st->fetchAll(PDO::FETCH_ASSOC) ?: [];
  if (!$rows) throw new RuntimeException("PROMO_HAS_NO_MORTYS");

  $r = $rows[array_rand($rows)];
  foreach (["lvl_min","lvl_max","hp_min","hp_max","atk_min","atk_max","def_min","def_max","spd_min","spd_max"] as $k) {
    $r[$k] = (int)$r[$k];
  }
  $r["morty_id"] = (string)$r["morty_id"];
  $r["variant"] = (string)($r["variant"] ?? "Normal");
  return $r;
}

function dbGetPromoAttacks(PDO $pdo, string $promo_id, string $morty_id): array {
  $st = $pdo->prepare("
    SELECT position, attack_id, pp, pp_stat
    FROM gacha_promo_morty_attacks
    WHERE gacha_promo_id = ? AND morty_id = ?
    ORDER BY position ASC
  ");
  $st->execute([$promo_id, $morty_id]);
  $rows = $st->fetchAll(PDO::FETCH_ASSOC) ?: [];
  if (!$rows) throw new RuntimeException("PROMO_MORTY_HAS_NO_ATTACKS");

  $out = [];
  foreach ($rows as $r) {
    $out[] = [
      "position" => (int)$r["position"],
      "attack_id" => (string)$r["attack_id"],
      "pp" => (int)$r["pp"],
      "pp_stat" => (int)$r["pp_stat"],
    ];
  }
  return $out;
}

// ---------------- COUPON CHARGE (ATOMIC) ----------------
function chargeCouponsOrFail(PDO $pdo, string $player_id, int $cost): int {
  if ($cost <= 0) {
    $st = $pdo->prepare("SELECT coupons FROM users WHERE player_id = ? LIMIT 1");
    $st->execute([$player_id]);
    $v = $st->fetchColumn();
    return ($v === false || $v === null) ? 0 : (int)$v;
  }

  // Atomic deduction only if enough coupons
  $up = $pdo->prepare("UPDATE users SET coupons = coupons - ? WHERE player_id = ? AND coupons >= ?");
  $up->execute([$cost, $player_id, $cost]);
  if ($up->rowCount() !== 1) {
    throw new RuntimeException("NOT_ENOUGH_COUPONS");
  }

  $st = $pdo->prepare("SELECT coupons FROM users WHERE player_id = ? LIMIT 1");
  $st->execute([$player_id]);
  $v = $st->fetchColumn();
  return ($v === false || $v === null) ? 0 : (int)$v;
}

// ---------------- OWNED MORTY INSERT ----------------
function insertOwnedMortyWithAttacks(PDO $pdo, string $player_id, string $morty_id, int $level, string $variant, int $hp, int $atk, int $def, int $spd, array $attacks): array {
  $owned_morty_id = uuidv4();
  $xp  = (int)round(($level * $level) * 28.0);

  $ins = $pdo->prepare("
    INSERT INTO owned_morties
      (player_id, owned_morty_id, morty_id, level, xp, hp, hp_stat, attack_stat, defence_stat, variant, speed_stat,
       is_locked, is_trading_locked, fight_pit_id, evolution_points, xp_lower, xp_upper)
    VALUES
      (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'false', 'false', 'null', 0, ?, ?)
  ");
  $ins->execute([
    $player_id, $owned_morty_id, $morty_id, $level, $xp,
    $hp, $hp, $atk, $def, $variant, $spd,
    $xp, $xp
  ]);

  $atkIns = $pdo->prepare("
    INSERT INTO owned_attacks (owned_morty_id, position, attack_id, pp, pp_stat, type, is_accurate, to_self, stat, amount)
    VALUES (?, ?, ?, ?, ?, NULL, NULL, NULL, NULL, NULL)
  ");

  $ownedAttacksOut = [];
  foreach ($attacks as $a) {
    $atkIns->execute([$owned_morty_id, (int)$a["position"], (string)$a["attack_id"], (int)$a["pp"], (int)$a["pp_stat"]]);
    // client expects attack_id, pp, position
    $ownedAttacksOut[] = ["attack_id" => (string)$a["attack_id"], "pp" => (int)$a["pp"], "position" => (int)$a["position"]];
  }

  upsertMortydexCaught($pdo, $player_id, $morty_id);

  return [
    "owned_morty_id" => $owned_morty_id,
    "player_id"      => $player_id,
    "morty_id"       => $morty_id,
    "level"          => $level,
    "xp"             => $xp,
    "hp"             => $hp,
    "hp_stat"        => $hp,
    "attack_stat"    => $atk,
    "defence_stat"   => $def,
    "speed_stat"     => $spd,
    "variant"        => $variant,
    "owned_attacks"  => $ownedAttacksOut
  ];
}

// ---------------- ENDPOINT ----------------
$body = json_decode(file_get_contents("php://input"), true) ?: [];
$session_id = (string)($body["session_id"] ?? "");
$gacha_id   = (string)($body["gacha_id"] ?? "");

if ($session_id === "" || $gacha_id === "") {
  jsonOut(400, ["error" => "Missing session_id or gacha_id"]);
}

$player_id = playerIdFromSession($pdo, $session_id);
if (!$player_id) {
  jsonOut(401, ["error" => "Invalid session_id"]);
}

$gacha = dbGetGacha($pdo, $gacha_id);
if (!$gacha) {
  jsonOut(404, ["error" => "Unknown gacha_id", "gacha_id" => $gacha_id]);
}

$contents = dbGetGachaContents($pdo, $gacha_id);
if (!$contents) {
  jsonOut(500, ["error" => "Gacha has no content", "gacha_id" => $gacha_id]);
}

// PROMO ONLY: must have an active promo
$promo = dbGetActivePromo($pdo, time());
if (!$promo) {
  jsonOut(409, ["error" => "NO_ACTIVE_PROMO"]);
}

$itemResults  = [];
$mortyResults = [];

$pdo->beginTransaction();
try {
  // 0) charge coupons based on gachas.cost
  $cost = (int)$gacha["cost"]; // set cost in DB (e.g., 2)
  $newCoupons = chargeCouponsOrFail($pdo, $player_id, $cost);

  $response = [
    "coupons" => $newCoupons,
    "coupons_deducted" => $cost,
    "result" => []
  ];

  $promo_id = (string)$promo["gacha_promo_id"];

  foreach ($contents as $content) {
    $reward = $content["reward"];
    $qty    = (int)$content["quantity"];

    // ---------- ITEMS ----------
    if ($reward === "ITEM") {
      for ($i = 0; $i < $qty; $i++) {
        $item_id = dbPickRandomItemFromContent($pdo, (int)$content["id"]);
        if ($item_id === null || $item_id === "") {
          throw new RuntimeException("GACHA_CONTENT_HAS_NO_ITEMS");
        }
        $itemResults[] = grantItem($pdo, $player_id, $item_id, 1);
      }
      continue;
    }

    // ---------- MORTYS (PROMO ONLY) ----------
    if ($reward === "MORTY") {
      for ($i = 0; $i < $qty; $i++) {
        // pick promo morty row
        $pm = dbPickPromoMorty($pdo, $promo_id);

        $morty_id = (string)$pm["morty_id"];
        $variant  = (string)$pm["variant"];

        // promo defines stats + level range
        $level = randInt((int)$pm["lvl_min"], (int)$pm["lvl_max"]);
        $hp  = randInt((int)$pm["hp_min"],  (int)$pm["hp_max"]);
        $atk = randInt((int)$pm["atk_min"], (int)$pm["atk_max"]);
        $def = randInt((int)$pm["def_min"], (int)$pm["def_max"]);
        $spd = randInt((int)$pm["spd_min"], (int)$pm["spd_max"]);

        $attacks = dbGetPromoAttacks($pdo, $promo_id, $morty_id);

        $owned = insertOwnedMortyWithAttacks($pdo, $player_id, $morty_id, $level, $variant, $hp, $atk, $def, $spd, $attacks);
        $added = maybeAddToActiveDeck($pdo, $player_id, $owned["owned_morty_id"]);

        $mortyResults[] = [
          "type" => "MORTY",
          "morty_id" => $morty_id,
          "level" => $level,
          "added_to_active_deck" => $added,
          "owned_morty_limit_reached" => false,
          "variant" => $variant,
          "owned_morty" => $owned
        ];
      }
      continue;
    }
  }

  // items first, then mortys
  $response["result"] = array_merge($itemResults, $mortyResults);

  $pdo->commit();
  echo json_encode($response, JSON_UNESCAPED_SLASHES);
} catch (Throwable $e) {
  $pdo->rollBack();

  if ($e->getMessage() === "NOT_ENOUGH_COUPONS") {
    jsonOut(403, ["error" => "NOT_ENOUGH_COUPONS"]);
  }

  jsonOut(500, ["error" => "pull_failed", "detail" => $e->getMessage()]);
}

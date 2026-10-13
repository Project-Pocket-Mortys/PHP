<?php
// room spawner (FULL STABLE FIX + COIN SAFE + ZERO CRASH VERSION)

error_reporting(E_ALL);
ini_set('display_errors', 1);

header("Content-Type: application/json; charset=utf-8");

require __DIR__ . "/../pocket_f4894h398r8h9w9er8he98he.php";
require __DIR__ . "/events.php";

// ---------------- CONFIG ----------------
const TARGET_PICKUPS_PER_ROOM  = 3;
const TARGET_WILD_MORTIES_ROOM = 4;
const TARGET_BOTS_PER_ROOM     = 5;
const MAX_SCAN_EVENTS = 3000;

// ---------------- SPAWN POINTS ----------------
const PICKUP_POINTS = [
  [65,79],[2,79],[48,87],[34,83],[8,57],[57,48],[25,87],[42,64]
];

const MOB_POINTS = [
  [5,82],[12,84],[15,4],[24,57],[24,76],[32,76],
  [36,59],[37,76],[42,75],[47,68],[49,84],[55,79],
];

// ---------------- SAFE HELPERS ----------------
function uuidv4(): string {
  $d = random_bytes(16);
  $d[6] = chr((ord($d[6]) & 0x0f) | 0x40);
  $d[8] = chr((ord($d[8]) & 0x3f) | 0x80);
  return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($d), 4));
}

function randInt($min,$max){
  return random_int($min,$max);
}
function botNamePool(): array {
  return ["Ataraxy","Carpedge","ChloeTombola","Loxodromy","Barbirdation","EasementJustice"];
}

function botAvatarPool(): array {
  return ["AvatarTeacherRick","AvatarMoochJerry","AvatarBeth","AvatarRickSuperFan","AvatarRickDefault"];
}

function botMortyPool(): array {
  return ["MortyPoorHouse","MortyGunk","MortySoldier","MortyTyrantLizard","MortyAndroid"];
}

// ---------------- SAFE WEIGHT PICK ----------------
function weighted_pick(array $choices) {
  if (empty($choices)) return null;

  $total = 0;
  foreach ($choices as $c) {
    $total += (int)($c["weight"] ?? 0);
  }

  if ($total <= 0) {
    return $choices[0]["value"] ?? null;
  }

  $r = random_int(1, $total);
  $acc = 0;

  foreach ($choices as $c) {
    $acc += (int)($c["weight"] ?? 0);
    if ($r <= $acc) {
      return $c["value"];
    }
  }

  return $choices[array_key_last($choices)]["value"] ?? null;
}

// ---------------- RARITY ----------------
function pickRarity(): int {
  return weighted_pick([
    ["value"=>5,"weight"=>55],
    ["value"=>75,"weight"=>30],
    ["value"=>100,"weight"=>15],
  ]) ?? 100;
}

// ---------------- WILD MORTY POOL ----------------
function wildMortyPool(): array {
  return [
    ["morty_id"=>"MortyScruffy","variant"=>"Normal","rarity"=>100],
    ["morty_id"=>"MortyOld","variant"=>"Normal","rarity"=>100],
    ["morty_id"=>"MortyRabbit","variant"=>"Normal","rarity"=>100],
    ["morty_id"=>"MortyStrawberry","variant"=>"Normal","rarity"=>100],
    ["morty_id"=>"MortyBlueShirt","variant"=>"Normal","rarity"=>100],

    ["morty_id"=>"MortyFawn","variant"=>"Normal","rarity"=>75],
    ["morty_id"=>"MortyMascot","variant"=>"Normal","rarity"=>75],
    ["morty_id"=>"MortyCowboy","variant"=>"Normal","rarity"=>75],

    ["morty_id"=>"MortyWildMascot","variant"=>"Normal","rarity"=>20],
    ["morty_id"=>"MortyAnimatronic","variant"=>"Normal","rarity"=>20],

    ["morty_id"=>"MortyGirl","variant"=>"Normal","rarity"=>5],
    ["morty_id"=>"MortyAndroid","variant"=>"Normal","rarity"=>5],
  ];
}

// ---------------- LOOT TABLE ----------------
function lootTableByRarity(): array {
    return [
        5 => [
            ["type"=>"ITEM","amount"=>1,"item_id"=>"ItemTinCan","rarity"=>5],
            ["type"=>"ITEM","amount"=>1,"item_id"=>"ItemCable","rarity"=>5],
        ],

        75 => [
            ["type"=>"ITEM","amount"=>1,"item_id"=>"ItemCircuitBoard","rarity"=>75],
            ["type"=>"ITEM","amount"=>1,"item_id"=>"ItemPlutonicRock","rarity"=>75],
            ["type"=>"ITEM","amount"=>1,"item_id"=>"ItemBacteriaCell","rarity"=>75],
        ],

        100 => [
            ["type"=>"ITEM","amount"=>1,"item_id"=>"ItemBattery","rarity"=>100],
            ["type"=>"ITEM","amount"=>1,"item_id"=>"ItemFleeb","rarity"=>100],
            ["type"=>"ITEM","amount"=>1,"item_id"=>"ItemBacteriaCell","rarity"=>100],
            ["type"=>"ITEM","amount"=>1,"item_id"=>"ItemCircuitBoard","rarity"=>100],
            ["type"=>"ITEM","amount"=>1,"item_id"=>"ItemDarkEnergyBall","rarity"=>100],
            ["type"=>"ITEM","amount"=>1,"item_id"=>"ItemTinCan","rarity"=>100],
            ["type"=>"ITEM","amount"=>1,"item_id"=>"ItemCable","rarity"=>100],
            ["type"=>"ITEM","amount"=>1,"item_id"=>"ItemTurbulentJuiceTube","rarity"=>100],
        ]
    ];
}

// ---------------- SAFE ITEM PICK ----------------
function pickItemId(int $rarity, array $exclude = []): string {
  $table = lootTableByRarity();

  if (!isset($table[$rarity]) || empty($table[$rarity])) {
    $rarity = 100;
  }

  $pool = $table[$rarity] ?? [];

  if (empty($pool)) return "ItemCable";

  if (!empty($exclude)) {
    $pool = array_values(array_filter($pool, function($i) use ($exclude) {
      return !in_array($i["item_id"], $exclude);
    }));
  }

  if (empty($pool)) {
    $pool = $table[$rarity] ?? [["item_id"=>"ItemCable"]];
  }

  return $pool[array_rand($pool)]["item_id"] ?? "ItemCable";
}

// ---------------- ROOM STATE (SAFE) ----------------
function getRoomState(PDO $pdo, string $room_id): array {
  $st = $pdo->prepare("
    SELECT event_name,payload_json,pickup_id,pickup_id_collected_by_player_id
    FROM event_queue
    WHERE room_id=?
    ORDER BY id ASC
    LIMIT 3000
  ");

  $st->execute([$room_id]);

  $p=[];$w=[];$b=[];$occ=[];

  while ($r=$st->fetch(PDO::FETCH_ASSOC)) {

    $payload = json_decode($r["payload_json"] ?? '', true);
    if (!is_array($payload)) $payload = [];

    if ($r["event_name"] === "room:pickup-added") {
      $id = $r["pickup_id"] ?? $payload["pickup_id"] ?? null;
      if ($id && empty($r["pickup_id_collected_by_player_id"])) {
        $p[$id] = $payload;
      }
    }

    if ($r["event_name"] === "room:wild-morty-added") {
      if (!empty($payload["wild_morty_id"])) {
        $w[$payload["wild_morty_id"]] = $payload;
      }
    }

    if ($r["event_name"] === "room:bot-added") {
      if (!empty($payload["bot_id"])) {
        $b[$payload["bot_id"]] = $payload;
      }
    }
  }

  foreach ([$p,$w,$b] as $set) {
    foreach ($set as $x) {
      if (isset($x["placement"][0],$x["placement"][1])) {
        $occ[$x["placement"][0].",".$x["placement"][1]] = true;
      }
    }
  }

  return ["pickups"=>$p,"wilds"=>$w,"bots"=>$b,"occupied"=>$occ];
}

// ---------------- FREE SPOT ----------------
function freeSpot(array $points,array $occ): array {
  $a=[];
  foreach ($points as $p) {
    if (!isset($occ[$p[0].",".$p[1]])) $a[]=$p;
  }
  return $a ? $a[array_rand($a)] : [];
}

// ---------------- PICKUP (COIN SAFE) ----------------
function spawnPickup(PDO $pdo,string $room_id,array &$occ): bool {

  $pos = freeSpot(PICKUP_POINTS,$occ);
  if (!$pos) return false;

  $contents = [];

  if (randInt(1,100) <= 30) {

    for ($i=0;$i<randInt(2,4);$i++) {
      $contents[]=[
        "type"=>"ITEM",
        "amount"=>1,
        "item_id"=>pickItemId(pickRarity())
      ];
    }

    $contents[]=[
      "type"=>"COIN",
      "amount"=>randInt(120,250)
    ];

  } else {
    $contents[]=[
      "type"=>"ITEM",
      "amount"=>1,
      "item_id"=>pickItemId(pickRarity())
    ];
  }

  publish_event($pdo,$room_id,"room:pickup-added",[
    "pickup_id"=>uuidv4(),
    "placement"=>$pos,
    "contents"=>$contents
  ]);

  $occ[$pos[0].",".$pos[1]] = true;
  return true;
}

// ---------------- WILD ----------------
function spawnWild(PDO $pdo,string $room_id,array &$occ): bool {
  $pos = freeSpot(MOB_POINTS,$occ);
  if (!$pos) return false;

  $m = wildMortyPool()[array_rand(wildMortyPool())];

  publish_event($pdo,$room_id,"room:wild-morty-added",[
    "morty_id"=>$m["morty_id"],
    "placement"=>$pos,
    "state"=>"WORLD",
    "division"=>randInt(1,1),
    "variant"=>$m["variant"],
    "shiny_if_potion"=>false,
    "_created"=>gmdate("Y-m-d\\TH:i:s").".000Z",
    "_updated"=>gmdate("Y-m-d\\TH:i:s").".000Z",
    "wild_morty_id"=>uuidv4()
  ]);

  $occ[$pos[0].",".$pos[1]] = true;
  return true;
}

// ---------------- BOT ----------------
function spawnBot(PDO $pdo,string $room_id,array &$occ): bool {
  $pos = freeSpot(MOB_POINTS,$occ);
  if (!$pos) return false;

  publish_event($pdo,$room_id,"room:bot-added",[
    "username"=>"Bot",
    "player_avatar_id"=>"AvatarRickDefault",
    "state"=>"WORLD",
	"division"=>randInt(1,1),
	"owned_morties"=>[[
      "morty_id"=>botMortyPool()[array_rand(botMortyPool())],
      "variant"=>"Normal",
      "hp"=>1,
      "owned_morty_id"=>"80700000-0000-0000-0000-000000000000"
    ]],
    "streak"=>0,
    "bot_id"=>uuidv4(),
    "placement"=>$pos
  ]);

  $occ[$pos[0].",".$pos[1]] = true;
  return true;
}

// ---------------- MAIN ----------------
$out=["ok"=>true,"rooms"=>[]];

$stmt = $pdo->query("SELECT room_id FROM room_ids");
$rooms = $stmt ? $stmt->fetchAll(PDO::FETCH_ASSOC) : [];

foreach($rooms as $r){

  $id = $r["room_id"] ?? null;
  if (!$id) continue;

  $pdo->beginTransaction();

  try {
    $s = getRoomState($pdo,$id);
    $occ = $s["occupied"];

    $needP = max(0, TARGET_PICKUPS_PER_ROOM - count($s["pickups"]));
    for($i=0;$i<$needP;$i++) spawnPickup($pdo,$id,$occ);

    $needW = max(0, TARGET_WILD_MORTIES_ROOM - count($s["wilds"]));
    for($i=0;$i<$needW;$i++) spawnWild($pdo,$id,$occ);

    $needB = max(0, TARGET_BOTS_PER_ROOM - count($s["bots"]));
    for($i=0;$i<$needB;$i++) spawnBot($pdo,$id,$occ);

    $pdo->commit();

    $out["rooms"][] = ["room_id"=>$id,"ok"=>true];

  } catch(Throwable $e){
    $pdo->rollBack();
    $out["rooms"][] = ["room_id"=>$id,"error"=>$e->getMessage()];
  }
}

echo json_encode($out, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES);
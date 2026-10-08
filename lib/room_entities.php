<?php
// lib/room_entities.php

require_once __DIR__ . "/events.php";

function uuidv4(): string {
    $data = random_bytes(16);
    $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
    $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
    return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
}

function now_iso_z(): string {
    return gmdate("Y-m-d\TH:i:s.v\Z");
}

function weighted_pick(array $choices) {
    $total = 0;
    foreach ($choices as $c) $total += (int)$c["weight"];
    $roll = random_int(1, max(1, $total));
    $acc = 0;
    foreach ($choices as $c) {
        $acc += (int)$c["weight"];
        if ($roll <= $acc) return $c["value"];
    }
    return $choices[count($choices) - 1]["value"];
}

function pick_rarity(): int {
    return (int) weighted_pick([
        ["value" => 5,   "weight" => 55],
        ["value" => 75,  "weight" => 30],
        ["value" => 100, "weight" => 15],
    ]);
}

function loot_table_by_rarity(): array {
    return [
        5 => ["ItemMegaSeedSpeed","ItemTinCan","ItemCircuitBoard","ItemCable","ItemPlutonicRock","ItemBacteriaCell"],
        75 => ["ItemPoisonCure","ItemCircuitBoard","ItemCable"],
        100 => ["ItemSerum","ItemDarkEnergyBall","ItemCircuitBoard","ItemPlutonicRock"],
    ];
}

function pick_item_id(int $rarity, array $exclude = []): string {
    $table = loot_table_by_rarity();
    $pool = $table[$rarity] ?? ["ItemCircuitBoard"];
    if (!empty($exclude)) {
        $filtered = array_values(array_diff($pool, $exclude));
        if (!empty($filtered)) $pool = $filtered;
    }
    return $pool[array_rand($pool)];
}

/**
 * Rule:
 * - NEVER coin-only
 * - single ITEM (no coin) OR bundle (2-4 ITEMs + COIN)
 */
function random_pickup_contents(array $excludeItemIds = []): array {
    $kind = weighted_pick([
        ["value" => "single", "weight" => 70],
        ["value" => "bundle", "weight" => 30],
    ]);

    if ($kind === "single") {
        $r = pick_rarity();
        $item = pick_item_id($r, $excludeItemIds);
        return [
            ["type" => "ITEM", "amount" => 1, "item_id" => $item, "rarity" => $r]
        ];
    }

    $nItems = random_int(2, 4);
    $contents = [];
    $picked = [];

    for ($i = 0; $i < $nItems; $i++) {
        $r = pick_rarity();
        $item = pick_item_id($r, array_merge($excludeItemIds, $picked));
        $picked[] = $item;
        $contents[] = ["type" => "ITEM", "amount" => 1, "item_id" => $item, "rarity" => $r];
    }

    $contents[] = ["type" => "COIN", "amount" => random_int(120, 250)];
    return $contents;
}

function room_is_initialized(PDO $pdo, string $room_id): bool {
    $stmt = $pdo->prepare("
      SELECT 1
      FROM event_queue
      WHERE room_id = ?
        AND event_name = 'room:initialized'
      LIMIT 1
    ");
    $stmt->execute([$room_id]);
    return (bool)$stmt->fetchColumn();
}

function spawn_pick_from_list(array &$pool): array {
    // If pool is empty, caller should refill it.
    $idx = array_rand($pool);
    $pt  = $pool[$idx];
    unset($pool[$idx]);
    // reindex so array_rand stays happy later
    $pool = array_values($pool);
    return $pt; // ['x'=>..., 'y'=>...]
}

function seed_room_entities(PDO $pdo, string $room_id, string $world_id, string $zone_id): void {
    mt_srand((int) sprintf("%u", crc32($room_id)));
    
	/*
    publish_event($pdo, $room_id, "room:initialized", [
        "world_id" => $world_id,
        "zone_id" => $zone_id,
        "_created" => now_iso_z()
    ]);
	*/

    // -------------------------
    // HARD-CODED SPAWN POINTS
    // -------------------------
    $spawn_item_points_base = [
        ['x' => 25, 'y' => 87],
        ['x' => 34, 'y' => 83],
        ['x' => 42, 'y' => 64],
        ['x' => 48, 'y' => 87],
        ['x' => 57, 'y' => 48],
        ['x' => 65, 'y' => 79],
    ];

    $spawn_morty_points_base = [
        ['x' => 5,  'y' => 82],
        ['x' => 12, 'y' => 84],
        ['x' => 15, 'y' => 4],
        ['x' => 24, 'y' => 57],
        ['x' => 24, 'y' => 76],
        ['x' => 32, 'y' => 76],
        ['x' => 36, 'y' => 59],
        ['x' => 37, 'y' => 76],
        ['x' => 42, 'y' => 75],
        ['x' => 47, 'y' => 68],
        ['x' => 49, 'y' => 84],
        ['x' => 55, 'y' => 79],
    ];

    // Working pools (we remove from these to avoid duplicates)
    $spawn_item_pool  = $spawn_item_points_base;
    $spawn_morty_pool = $spawn_morty_points_base;

    // --- spawn pickups ---
    for ($i = 0; $i < 3; $i++) {
        // If you want 3 pickups and we have 6 points:
        // refill when pool empties (means repeats AFTER all points used once)
        if (empty($spawn_item_pool)) {
            $spawn_item_pool = $spawn_item_points_base;
        }

        $pickup_id = uuidv4();
        $pt = spawn_pick_from_list($spawn_item_pool);
        $x = $pt['x'];
        $y = $pt['y'];

        publish_event($pdo, $room_id, "room:pickup-added", [
            "contents" => random_pickup_contents(),
            "placement" => [$x, $y],
            "pickup_id" => $pickup_id
        ]);
    }

    // --- wild morties ---
    $wild_pool = ["MortyDefault","MortyPrisoner","MortySurvivor","MortyCowboy","MortyBlueShirt","MortyNoEye"];

    for ($i = 0; $i < 5; $i++) {
        if (empty($spawn_morty_pool)) {
            $spawn_morty_pool = $spawn_morty_points_base;
        }

        $wid = uuidv4();
        $pt = spawn_pick_from_list($spawn_morty_pool);
        $x = $pt['x'];
        $y = $pt['y'];

        $created = now_iso_z();
        publish_event($pdo, $room_id, "room:wild-morty-added", [
            "morty_id" => $wild_pool[array_rand($wild_pool)],
            "placement" => [$x, $y],
            "state" => "WORLD",
            "division" => mt_rand(1, 4),
            "variant" => (mt_rand(0,100) < 10 ? "Shiny" : "Normal"),
            "shiny_if_potion" => (mt_rand(0,100) < 25),
            "_created" => $created,
            "_updated" => $created,
            "wild_morty_id" => $wid
        ]);
    }

    // --- bots --- (leave yours as-is)
    $bot_names = ["Ataraxy","Carpedge","ChloeTombola","Loxodromy","Barbirdation","EasementJustice"];
    $bot_avatars = ["AvatarTeacherRick","AvatarMoochJerry","AvatarBeth","AvatarRickSuperFan","AvatarRickDefault"];
    $bot_morties = ["MortyPoorHouse","MortyGunk","MortySoldier","MortyTyrantLizard","MortyAndroid"];

    for ($i=0; $i<4; $i++) {
        $bot_id = uuidv4();
        $zx = mt_rand(1, 5);
        $zy = mt_rand(1, 5);

        $created = now_iso_z();
        publish_event($pdo, $room_id, "room:bot-added", [
            "username" => $bot_names[array_rand($bot_names)],
            "player_avatar_id" => $bot_avatars[array_rand($bot_avatars)],
            "state" => "WORLD",
            "level" => 5,
            "owned_morties" => [[
                "morty_id" => $bot_morties[array_rand($bot_morties)],
                "variant" => "Normal",
                "hp" => 1,
                "owned_morty_id" => "80700000-0000-0000-0000-000000000000"
            ]],
            "zone" => [
                "player" => [$zx, $zy],
                "bots" => [
                    "count" => mt_rand(6, 12),
                    "morty_count" => ["min" => 1, "max" => 1],
                    "morty_hp_handicap" => ["min" => 0.4, "max" => 0.6]
                ],
                "zone_id" => "[{$zx}-{$zy}]"
            ],
            "streak" => 0,
            "_created" => $created,
            "_updated" => $created,
            "bot_id" => $bot_id
        ]);
    }
}


/**
 * Snapshot rebuild:
 * - pickup-added adds
 * - pickup-removed removes
 * - collected pickups are identified ONLY by pickup_id_collected_by_player_id
 */
function build_room_snapshot_from_events(PDO $pdo, string $room_id): array {
    $pickups = [];
    $wilds = [];
    $bots = [];

    $stmt = $pdo->prepare("
      SELECT event_name, payload_json, pickup_id_collected_by_player_id
      FROM event_queue
      WHERE room_id = ?
        AND event_name IN (
          'room:pickup-added','room:pickup-removed',
          'room:wild-morty-added','room:wild-morty-removed','room:wild-morty-state-changed',
          'room:bot-added','room:bot-removed','room:bot-state-changed'
        )
      ORDER BY id ASC
    ");
    $stmt->execute([$room_id]);

    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        $event = (string)$row["event_name"];
        $payload = json_decode((string)$row["payload_json"], true);
        if (!is_array($payload)) continue;

        if ($event === "room:pickup-added" && !empty($payload["pickup_id"])) {
            // ✅ Correct collected check for your schema
            if (!empty($row["pickup_id_collected_by_player_id"])) {
                continue;
            }
            $pickups[(string)$payload["pickup_id"]] = $payload;
        }

        if ($event === "room:pickup-removed" && !empty($payload["pickup_id"])) {
            unset($pickups[(string)$payload["pickup_id"]]);
        }

        if ($event === "room:wild-morty-added" && !empty($payload["wild_morty_id"])) {
            $wilds[(string)$payload["wild_morty_id"]] = $payload;
        }
        if ($event === "room:wild-morty-removed" && !empty($payload["wild_morty_id"])) {
            unset($wilds[(string)$payload["wild_morty_id"]]);
        }
        if ($event === "room:wild-morty-state-changed" && !empty($payload["wild_morty_id"])) {
            $id = (string)$payload["wild_morty_id"];
            if (isset($wilds[$id]) && isset($payload["state"])) {
                $wilds[$id]["state"] = $payload["state"];
                $wilds[$id]["_updated"] = now_iso_z();
            }
        }

        if ($event === "room:bot-added" && !empty($payload["bot_id"])) {
            $bots[(string)$payload["bot_id"]] = $payload;
        }
        if ($event === "room:bot-removed" && !empty($payload["bot_id"])) {
            unset($bots[(string)$payload["bot_id"]]);
        }
        if ($event === "room:bot-state-changed" && !empty($payload["bot_id"])) {
            $id = (string)$payload["bot_id"];
            if (isset($bots[$id]) && isset($payload["state"])) {
                $bots[$id]["state"] = $payload["state"];
                $bots[$id]["_updated"] = now_iso_z();
            }
        }
    }

    return [
        "pickups" => array_values($pickups),
        "wild_morties" => array_values($wilds),
        "bots" => array_values($bots),
    ];
}

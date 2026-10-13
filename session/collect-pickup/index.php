<?php
// collect-pickup.php

error_reporting(E_ALL);
ini_set('display_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");

require __DIR__ . "/../../pocket_f4894h398r8h9w9er8he98he.php";
require __DIR__ . "/../../lib/events.php";


/* ---------------- UUID ---------------- */
function uuidv4(): string {
    $data = random_bytes(16);
    $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
    $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);

    return vsprintf(
        '%s%s-%s-%s-%s-%s%s%s',
        str_split(bin2hex($data), 4)
    );
}


/* ---------------- LOOT HELPERS ---------------- */
function weighted_pick(array $choices) {
    $total = 0;

    foreach ($choices as $c) {
        $total += (int)$c["weight"];
    }

    $roll = random_int(1, max(1, $total));
    $acc = 0;

    foreach ($choices as $c) {
        $acc += (int)$c["weight"];

        if ($roll <= $acc) {
            return $c["value"];
        }
    }

    return $choices[count($choices)-1]["value"];
}


function pick_rarity(): int {
    return weighted_pick([
        ["value"=>5, "weight"=>55],
        ["value"=>75, "weight"=>30],
        ["value"=>100, "weight"=>15]
    ]);
}


function loot_table_by_rarity(): array {
    return [
        5 => [
            "ItemMegaSeedSpeed",
            "ItemTinCan",
            "ItemCircuitBoard",
            "ItemCable",
            "ItemPlutonicRock",
            "ItemBacteriaCell"
        ],

        75 => [
            "ItemPoisonCure",
            "ItemCable",
            "ItemCircuitBoard"
        ],

        100 => [
            "ItemSerum",
            "ItemDarkEnergyBall",
            "ItemCircuitBoard",
            "ItemPlutonicRock"
        ]
    ];
}


function pick_item_id(int $rarity, array $exclude=[]): string {
    $table = loot_table_by_rarity();
    $pool = $table[$rarity] ?? ["ItemCircuitBoard"];

    if (!empty($exclude)) {
        $filtered = array_values(
            array_diff($pool, $exclude)
        );

        if (!empty($filtered)) {
            $pool = $filtered;
        }
    }

    return $pool[array_rand($pool)];
}


/* ---------------- PICKUP SPAWNS ---------------- */
const PICKUP_POINTS = [
  [65,79],
  [2,79],
  [48,87],
  [34,83],
  [8,57],
  [57,48],
  [25,87],
  [42,64]
];


function get_available_spawn(PDO $pdo, string $room_id): array {
    $stmt = $pdo->prepare("
        SELECT placement
        FROM event_queue
        WHERE room_id = ?
        AND event_name = 'room:pickup-added'
        AND pickup_id_collected_by_player_id IS NULL
    ");

    $stmt->execute([$room_id]);

    $used = [];

    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        $parts = explode(",", $row["placement"]);

        if (count($parts) !== 2) {
            continue;
        }

        $used[$parts[0] . "," . $parts[1]] = true;
    }

    $available = [];

    foreach (PICKUP_POINTS as $pt) {
        $key = $pt[0] . "," . $pt[1];

        if (!isset($used[$key])) {
            $available[] = $pt;
        }
    }

    if (empty($available)) {
        $available = PICKUP_POINTS;
    }

    return $available[array_rand($available)];
}


/* ---------------- RANDOM PICKUP ---------------- */
function random_pickup_contents(array $exclude=[]): array {
    $kind = weighted_pick([
        ["value"=>"single","weight"=>70],
        ["value"=>"bundle","weight"=>30]
    ]);

    if ($kind === "single") {
        $rarity = pick_rarity();

        return [[
            "type" => "ITEM",
            "amount" => 1,
            "item_id" => pick_item_id($rarity, $exclude),
            "rarity" => $rarity
        ]];
    }

    $count = random_int(2,4);

    $items = [];
    $picked = [];

    for ($i=0; $i<$count; $i++) {
        $rarity = pick_rarity();

        $item = pick_item_id(
            $rarity,
            array_merge($exclude, $picked)
        );

        $picked[] = $item;

        $items[] = [
            "type"=>"ITEM",
            "amount"=>1,
            "item_id"=>$item,
            "rarity"=>$rarity
        ];
    }

    $items[] = [
        "type"=>"COIN",
        "amount"=>random_int(120,250)
    ];

    return $items;
}


function make_new_pickup(
    PDO $pdo,
    string $room_id,
    array $exclude=[]
): array {
    $pos = get_available_spawn($pdo, $room_id);

    return [
        "pickup_id" => uuidv4(),
        "placement" => $pos,
        "contents" => random_pickup_contents($exclude)
    ];
}


/* ---------------- INVENTORY ---------------- */
function grantItem(PDO $pdo, string $player_id, string $item_id, int $amount): array {
    $stmt = $pdo->prepare("
        SELECT id, quantity
        FROM owned_items
        WHERE player_id = ?
        AND item_id = ?
        LIMIT 1
    ");
    $stmt->execute([$player_id, $item_id]);

    $row = $stmt->fetch(PDO::FETCH_ASSOC);

    $current = $row ? (int)$row["quantity"] : 0;
    $newQty = min(10, $current + $amount);
    $added = max(0, $newQty - $current);

    if ($row) {
        $pdo->prepare("
            UPDATE owned_items
            SET quantity = ?
            WHERE id = ?
        ")->execute([$newQty, $row["id"]]);
    } else {
        $pdo->prepare("
            INSERT INTO owned_items (
                player_id,
                item_id,
                quantity
            ) VALUES (?, ?, ?)
        ")->execute([
            $player_id,
            $item_id,
            $newQty
        ]);
    }

    return [
        "type"=>"ITEM",
        "item_id"=>$item_id,
        "quantity"=>$newQty,
        "amount_received"=>$added,
        "amount"=>$amount
    ];
}


function grantCoins(PDO $pdo, string $player_id, int $amount): array {
    $pdo->prepare("
        UPDATE users
        SET coins = coins + ?
        WHERE player_id = ?
    ")->execute([$amount, $player_id]);

    $stmt = $pdo->prepare("
        SELECT coins
        FROM users
        WHERE player_id = ?
    ");
    $stmt->execute([$player_id]);

    return [
        "type"=>"COIN",
        "quantity"=>(int)$stmt->fetchColumn(),
        "amount_received"=>$amount,
        "amount"=>$amount
    ];
}


/* ---------------- INPUT ---------------- */
$body = json_decode(
    file_get_contents("php://input"),
    true
) ?: [];

$session_id = (string)($body["session_id"] ?? "");
$pickup_id = (string)($body["pickup_id"] ?? "");

if (!$session_id || !$pickup_id) {
    http_response_code(400);

    echo json_encode([
        "error"=>"Missing session_id or pickup_id"
    ]);
    exit;
}


try {
    $pdo->beginTransaction();

    /* PLAYER */
    $stmt = $pdo->prepare("
        SELECT player_id, room_id
        FROM users
        WHERE session_id = ?
        LIMIT 1
        FOR UPDATE
    ");
    $stmt->execute([$session_id]);

    $player = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$player) {
        throw new Exception("Invalid session");
    }

    $player_id = $player["player_id"];
    $room_id = $player["room_id"];


    /* PICKUP FROM REAL TABLE COLUMNS */
    $stmt = $pdo->prepare("
        SELECT id,
               pickup_id,
               placement,
               pick_up_contents
        FROM event_queue
        WHERE room_id = ?
        AND event_name = 'room:pickup-added'
        AND pickup_id = ?
        AND pickup_id_collected_by_player_id IS NULL
        ORDER BY id DESC
        LIMIT 1
        FOR UPDATE
    ");

    $stmt->execute([
        $room_id,
        $pickup_id
    ]);

    $pickup = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$pickup) {
        throw new Exception(
            "Pickup already collected or missing"
        );
    }


    $contents = json_decode($pickup["pick_up_contents"], true);

// 🔥 normalize bad legacy formats
if (is_string($contents)) {
    $contents = [
        [
            "type" => "ITEM",
            "amount" => 1,
            "item_id" => $contents
        ]
    ];
}

// if single object instead of array
if (is_array($contents) && isset($contents["type"])) {
    $contents = [$contents];
}

// final safety check
if (!is_array($contents)) {
    throw new Exception("Invalid pickup contents format");
}

    if (!is_array($contents)) {
        throw new Exception(
            "Malformed pickup contents"
        );
    }


    /* mark collected */
    $pdo->prepare("
        UPDATE event_queue
        SET pickup_id_collected_by_player_id = ?
        WHERE id = ?
    ")->execute([
        $player_id,
        $pickup["id"]
    ]);


    /* grant rewards */
    $results = [];
    $exclude = [];

    foreach ($contents as $reward) {
        if ($reward["type"] === "ITEM") {
            $exclude[] = $reward["item_id"];

            $results[] = grantItem(
                $pdo,
                $player_id,
                $reward["item_id"],
                (int)$reward["amount"]
            );
        }

        if ($reward["type"] === "COIN") {
            $results[] = grantCoins(
                $pdo,
                $player_id,
                (int)$reward["amount"]
            );
        }
    }


    /* remove event */
    publish_event(
        $pdo,
        $room_id,
        "room:pickup-removed",
        [
            "pickup_id"=>$pickup_id
        ]
    );


    /* respawn */
    $newPickup = make_new_pickup(
        $pdo,
        $room_id,
        $exclude
    );

    publish_event(
        $pdo,
        $room_id,
        "room:pickup-added",
        $newPickup
    );


    $pdo->commit();


    echo json_encode([
        "pickup_id"=>$pickup_id,
        "contents"=>$results
    ], JSON_UNESCAPED_SLASHES);


} catch (Throwable $e) {
    if ($pdo->inTransaction()) {
        $pdo->rollBack();
    }

    http_response_code(500);

    echo json_encode([
        "error"=>"Server error",
        "detail"=>$e->getMessage()
    ]);
}
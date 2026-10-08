<?php
// /session/battle/move

header("Content-Type: application/json; charset=utf-8");
header("Access-Control-Allow-Origin: *");

error_reporting(E_ALL);
ini_set('display_errors', 1);

require __DIR__ . "/../../../pocket_f4894h398r8h9w9er8he98he.php";
require_once __DIR__ . "/../../../lib/events.php";

// ========================
// INPUT
// ========================
$raw  = file_get_contents("php://input");
$body = json_decode($raw, true);

$session_id     = $body["session_id"] ?? "";
$battle_id      = $body["battle_id"] ?? "";
$type           = $body["type"] ?? "";
$owned_morty_id = $body["owned_morty_id"] ?? "";
$move_id        = $body["move_id"] ?? "";

if (!$session_id || !$battle_id || !$type) {
    http_response_code(400);
    echo json_encode(["success" => false]);
    exit;
}

// ========================
// PLAYER LOOKUP
// ========================
$stmt = $pdo->prepare("SELECT player_id, room_id FROM users WHERE session_id=? LIMIT 1");
$stmt->execute([$session_id]);
$user = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$user) {
    http_response_code(401);
    echo json_encode(["success" => false]);
    exit;
}

$player_id = $user["player_id"];
$room_id   = $user["room_id"];

// ========================
// GET BATTLE STATE
// ========================
$stmt = $pdo->prepare("SELECT * FROM battles WHERE battle_id=? LIMIT 1");
$stmt->execute([$battle_id]);
$battle = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$battle) {
    echo json_encode(["success" => false]);
    exit;
}

// ========================
// HELPERS
// ========================
function get_ai_move() {
    $moves = ["AttackBatteringRam","AttackVileSpew"];
	// $moves = ["AttackBatteringRam","AttackToxic","AttackVileSpew"];
    return $moves[array_rand($moves)];
}
function uuidv4(): string {
    $data = random_bytes(16);
    $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
    $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
    return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
}


// ========================
// TURN LOGIC
// ========================
$outcome = "CONTINUE";
$turn_datas = [];

$player_hp = isset($battle["player_hp"]) ? (int)$battle["player_hp"] : 0;
$enemy_hp  = isset($battle["opponent_hp"]) ? (int)$battle["opponent_hp"] : 0;

$ai_move = get_ai_move();

// ========================
// ITEM (CATCH) — STRICT FORMAT
// ========================
if ($type === "ITEM" && $move_id === "ItemMortyChip") {

    $success = rand(1,100) > 40;

    // opponent + wild morty references
    $opponent_id = $battle["opponent_id"];
    $wild_owned_morty_id = $battle["opponent_active_morty"];
    $wild_morty_id = $battle["wild_morty_id"] ?? "UnknownMorty";

    // reduce player item count
    //$stmt = $pdo->prepare("UPDATE owned_items SET quantity = quantity - 1 WHERE player_id=? AND item_id='ItemMortyChip'");
    //$stmt->execute([$player_id]);

    // get updated item count
    $stmt = $pdo->prepare("SELECT quantity FROM owned_items WHERE player_id=? AND item_id='ItemMortyChip'");
    $stmt->execute([$player_id]);
    $itemRow = $stmt->fetch(PDO::FETCH_ASSOC);
    $remaining = (int)($itemRow["quantity"] ?? 0);

    // base turn data (STRICT)
    $turn_datas[] = [
        "type" => "ITEM",
        "attacker_player_id" => $player_id,
        "defender_player_id" => $opponent_id,
        "item_id" => "ItemMortyChip",
        "owned_morty_id" => $wild_owned_morty_id,
        "success" => $success
    ];

    if ($success) {

        $outcome = "CAUGHT";

        // ========================
        // CREATE OWNED MORTY (SIMULATED CAPTURE)
        // ========================
        $new_owned_morty_id = uuidv4();

        $new_morty = [
            "owned_morty_id" => $new_owned_morty_id,
            "player_id" => $player_id,
            "morty_id" => $wild_morty_id,
            "level" => rand(30,50),
            "xp" => rand(50000,90000),
            "hp" => rand(100,150),
            "hp_stat" => rand(100,150),
            "attack_stat" => rand(60,90),
            "defence_stat" => rand(60,90),
            "speed_stat" => rand(60,90),
            "variant" => "Normal",
            "owned_attacks" => [
                ["attack_id"=>"AttackFanArt","pp"=>5,"position"=>0],
                ["attack_id"=>"AttackWetTongue","pp"=>5,"position"=>1],
                ["attack_id"=>"AttackScratchAndSniff","pp"=>5,"position"=>2],
                ["attack_id"=>"AttackLick","pp"=>18,"position"=>3],
            ]
        ];

        // ========================
        // SEND EXACT CLIENT FORMAT
        // ========================
        publish_event($pdo, $room_id, "battle:turn-result", [
            "battle_id" => $battle_id,
            "outcome" => "CAUGHT",
            "turn_datas" => $turn_datas,
            "player_datas" => [
                "player" => [
                    "owned_items" => [
                        [
                            "item_id" => "ItemMortyChip",
                            "quantity" => $remaining
                        ]
                    ],
                    "rewards" => [
                        [
                            "type" => "MORTY",
                            "morty_id" => $wild_morty_id,
                            "level" => $new_morty["level"],
                            "added_to_active_deck" => true,
                            "owned_morty_limit_reached" => false,
                            "variant" => "Normal",
                            "owned_morty" => $new_morty
                        ]
                    ],
                    "attacks_to_learn" => [],
                    "move_log" => [
                        "cooldown" => [
                            "ATTACK" => 0,
                            "ITEM" => 1
                        ],
                        "count" => [
                            "ATTACK" => 1,
                            "ITEM" => 1
                        ],
                        "cooldown_next" => [
                            "ITEM" => 2
                        ],
                        "last_move_type" => "ITEM"
                    ]
                ],
                "opponent" => (object)[]
            ]
        ], $player_id);

        echo json_encode(["success" => true]);
        //exit;
    }
}

// ========================
// ATTACK TURN
// ========================
if ($type === "ATTACK") {

    $player_damage = rand(20, 20);
    $ai_damage     = rand(1, 3);

    $enemy_hp_after  = max($enemy_hp - $player_damage, 0);
    $player_hp_after = max($player_hp - $ai_damage, 0);

    // --------------------
    // PLAYER ATTACK FIRST (matches real flow better)
    // --------------------
    $turn_datas[] = [
        "type" => "ATTACK",
        "attacker_player_id" => $player_id,
        "defender_player_id" => $battle["opponent_id"],
        "attack_id" => $move_id,
        "element_modifier" => 1,
        "effect_datas" => [[
            "type" => "Hit",
            "is_accurate" => true,
            "to_self" => false,
            "continue_on_miss" => false,
            "is_critical" => false,
            "damage" => $player_damage,
            "defender_morty_datas" => [[
                "owned_morty_id" => $battle["opponent_active_morty"],
                "hp" => $enemy_hp_after
            ]]
        ]],
        "attacker_morty_datas" => [[
            "owned_morty_id" => $owned_morty_id,
            "owned_attacks" => [[
                "attack_id" => $move_id,
                "pp" => rand(1,5)
            ]]
        ]]
    ];
    
	// apply HP change first
    $enemy_hp = $enemy_hp_after;
	
	// ========================
    // CHECK FAINT BEFORE AI ACTS
    // ========================
    if ($enemy_hp > 0) {
    // --------------------
    // AI ATTACK SECOND
    // --------------------
$turn_datas[] = [
    "type" => "ATTACK",
    "attacker_player_id" => $battle["opponent_id"],
    "defender_player_id" => $player_id,
    "attack_id" => $ai_move,
    "element_modifier" => $element_modifier ?? 1,

    "effect_datas" => array_values(array_filter([
        [
            "type" => "Hit",
            "is_accurate" => true,
            "to_self" => false,
            "continue_on_miss" => false,
            "is_critical" => $is_critical ?? false,
            "damage" => $ai_damage,

            "defender_morty_datas" => [[
                "owned_morty_id" => $owned_morty_id,
                "hp" => $player_hp_after
            ]]
        ],

        isset($apply_poison) && $apply_poison ? [
            "type" => "Poison",
            "is_accurate" => true,
            "to_self" => false,
            "defender_morty_datas" => [[
                "owned_morty_id" => $owned_morty_id,
                "is_poisoned" => true
            ]]
        ] : null
    ])),

    "attacker_morty_datas" => [[
        "owned_morty_id" => $battle["opponent_active_morty"],
        "owned_attacks" => [[
            "attack_id" => $ai_move,
            "pp" => $ai_attack_pp ?? 1
        ]]
    ]]
];
    // check player health after the ai attacks
    $player_hp = $player_hp_after;
	if ($player_hp <= 0) {
    $outcome = "LOSE";
    }
	} else {
    // enemy fainted → no AI turn
    $outcome = "WIN";
	$xp_earned = 117; // replace with real formula later
	$current_xp_earned = 100;
	$update_total_xp = $current_xp_earned+$xp_earned;
	$xp_lower = 100;
	$update_xp_lower = $xp_lower+$xp_earned;
	$xp_datas = [[
    "owned_morty_id" => $owned_morty_id,
    "xp_earned" => $xp_earned,
    "owned_morty_datas" => [[
        "level" => 6, // fetch updated from DB if possible
        "xp" => $update_total_xp, // updated XP after adding
        "hp" => 20,
        "hp_stat" => 20,
        "attack_stat" => 11,
        "defence_stat" => 10,
        "speed_stat" => 10,
        "variant" => "Normal",
        "xp_lower" => $update_xp_lower,
        "xp_upper" => 225
    ]]
    ]];
    }
}

// ========================
// SAVE STATE
// ========================
$stmt = $pdo->prepare("UPDATE battles SET player_hp=?, opponent_hp=? WHERE battle_id=?");
$stmt->execute([$player_hp, $enemy_hp, $battle_id]);

// ========================
// IF RUN
// ========================
if ($type === "RUN") {
$wild_morty_id = $battle["opponent_active_morty"];
publish_event($pdo, $room_id, "room:wild-morty-state-changed", ["wild_morty_id"=>$wild_morty_id,"state"=>"WORLD"]);
publish_event($pdo, $room_id, "room:user-state-changed", ["player_id"=>$player_id,"state"=>"WORLD"]);
publish_event($pdo, $room_id, "battle:turn-result", [
    "battle_id" => $battle_id,
    "outcome" => "RUN",
    "turn_datas" => $turn_datas,
    "player_datas" => [
        "player" => [
		    "attacks_to_learn" => [],
            "move_log" => [
                "cooldown" => ["ATTACK" => 0, "RUN" => 0],
                "count" => ["ATTACK" => count($turn_datas), "RUN" => 1],
                "cooldown_next" => ["ITEM" => 1],
                "last_move_type" => $type
            ]
        ],
        "opponent" => (object)[]
    ],
	"battle_abandoned" => true
], $player_id);
}else{
// ========================
// IF WIN
// ========================
if ($outcome === "WIN") {
$wild_morty_id = $battle["opponent_active_morty"];
//publish_event($pdo, $room_id, "room:wild-morty-removed", ["wild_morty_id"=>$wild_morty_id);
// for now
publish_event($pdo, $room_id, "room:wild-morty-state-changed", ["wild_morty_id"=>$wild_morty_id,"state"=>"WORLD"]);
publish_event($pdo, $room_id, "room:user-state-changed", ["player_id"=>$player_id,"state"=>"WORLD"]);

publish_event($pdo, $room_id, "battle:turn-result", [
    "battle_id" => $battle_id,
    "outcome" => "WIN",
    "turn_datas" => $turn_datas,

    "player_datas" => [
        "player" => [
            "xp_datas" => $xp_datas,

            "rewards" => [
                [
                    "type" => "ITEM",
                    "item_id" => "ItemCircuitBoard",
                    "quantity" => 10,
                    "amount_received" => 0,
                    "amount" => 1
                ]
            ],

            "attacks_to_learn" => [],

            "move_log" => [
                "cooldown" => ["ATTACK" => 0],
                "count" => ["ATTACK" => count($turn_datas)],
                "cooldown_next" => ["ITEM" => 1],
                "last_move_type" => $type
            ]
        ],
        "opponent" => (object)[]
    ]
], $player_id);
}else{

// ========================
// SEND STRICT SSE EVENT
// ========================
publish_event($pdo, $room_id, "battle:turn-result", [
    "battle_id" => $battle_id,
    "outcome" => $outcome,
    "turn_datas" => $turn_datas,
    "player_datas" => [
        "player" => [
            "move_log" => [
                "cooldown" => ["ATTACK" => 0],
                "count" => ["ATTACK" => count($turn_datas)],
                "cooldown_next" => ["ITEM" => 1],
                "last_move_type" => $type
            ]
        ],
        "opponent" => (object)[]
    ]
], $player_id);
}
}
// ========================
// IF LOSE
// ========================
if ($outcome === "LOSE") {
$wild_morty_id = $battle["opponent_active_morty"];
publish_event($pdo, $room_id, "room:wild-morty-state-changed", ["wild_morty_id"=>$wild_morty_id,"state"=>"WORLD"]);
publish_event($pdo, $room_id, "room:user-state-changed", ["player_id"=>$player_id,"state"=>"WORLD"]);
}

// ========================
// IF CAUGHT
// ========================
if ($outcome === "CAUGHT") {
$wild_morty_id = $battle["opponent_active_morty"];
//publish_event($pdo, $room_id, "room:wild-morty-removed", ["wild_morty_id"=>$wild_morty_id);
// for now
publish_event($pdo, $room_id, "room:wild-morty-state-changed", ["wild_morty_id"=>$wild_morty_id,"state"=>"WORLD"]);
publish_event($pdo, $room_id, "room:user-state-changed", ["player_id"=>$player_id,"state"=>"WORLD"]);
}

// ========================
// NEXT TURN TIMER
// ========================
/*
if ($outcome === "CONTINUE") {
    publish_event($pdo, $room_id, "battle:move-timer-started", [
        "battle_id" => $battle_id,
        "timeout" => 30
    ], $player_id);
}
*/

// ========================
// FINAL RESPONSE (IMPORTANT)
// ========================
echo json_encode(["success" => true]);
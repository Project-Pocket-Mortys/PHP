<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require __DIR__ . "/../../../pocket_f4894h398r8h9w9er8he98he.php";

// Deck config
$stmt = $pdo->prepare("SELECT config_id, starting_deck_slots, max_deck_slots, cost_additional_slot FROM deck_config LIMIT 1");
$stmt->execute();

$config = $stmt->fetch(PDO::FETCH_ASSOC);
if (!$config) {
    die("Deck config not found");
}

$config_id = $config['config_id'];
$starting_deck_slots  = (int)$config['starting_deck_slots'];
$max_deck_slots       = (int)$config['max_deck_slots'];
$cost_additional_slot = (int)$config['cost_additional_slot'];


echo json_encode([
    "config_data" => [
        "config_id" => $config_id,
        "starting_deck_slots" => $starting_deck_slots,
        "max_deck_slots" => $max_deck_slots,
        "cost_additional_slot" => $cost_additional_slot
    ]
], JSON_UNESCAPED_SLASHES);
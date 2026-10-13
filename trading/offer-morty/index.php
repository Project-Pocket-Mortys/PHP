<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");

require '../../pocket_f4894h398r8h9w9er8he98he.php';

$input = file_get_contents('php://input');
$data = json_decode($input, true);

$session_id = (string)($data['session_id'] ?? '');
$player_id = (string)($data['player_id'] ?? '');
$offered_morty_id = (string)($data['offered_morty_id'] ?? '');
$trade_request_id = (string)($data['trade_request_id'] ?? '');

try {
    // AUTH: validate session
    $stmt = $pdo->prepare("SELECT player_id, username FROM users WHERE session_id = ? LIMIT 1");
    $stmt->execute([$session_id]);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$user || $user['player_id'] !== $player_id) {
        http_response_code(401);
        echo json_encode(["error"=>"NOT_AUTHENTICATED"]);
        exit;
    }

    // CHECK trade request exists
    $stmt = $pdo->prepare("SELECT * FROM trades WHERE trade_id = ? LIMIT 1");
    $stmt->execute([$trade_request_id]);
    $trade = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$trade) {
        http_response_code(404);
        echo json_encode(["error"=>"TRADE_NOT_FOUND"]);
        exit;
    }

    // CHECK player owns the offered Morty
    $stmt = $pdo->prepare("SELECT * FROM owned_morties WHERE owned_morty_id = ? AND player_id = ? LIMIT 1");
    $stmt->execute([$offered_morty_id, $player_id]);
    $morty = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$morty) {
        http_response_code(400);
        echo json_encode(["error"=>"MORTY_NOT_OWNED"]);
        exit;
    }

    // INSERT trade offer
    $offer_id = bin2hex(random_bytes(16)); // unique ID
    $stmt = $pdo->prepare("
        INSERT INTO trade_offers (trade_offer_id, trade_id, player_id, morty_offer_id, created_at) 
        VALUES (?, ?, ?, ?, NOW())
    ");
    $stmt->execute([$offer_id, $trade_request_id, $player_id, $offered_morty_id]);

    // RETURN official-style JSON
    $response = [
        "error" => "None",
        "offer" => [
            "trade_offer_id" => $offer_id,
            "trade_id" => $trade_request_id,
            "player_id" => $player_id,
            "morty_offer_id" => $offered_morty_id,
            "_created" => gmdate("Y-m-d\TH:i:s.v\Z"),
            "request_user_name" => $trade['player_id'], // optional: map to username if available
            "offering_morty_id" => $morty['morty_id'],
            "request_morty_id" => $trade['morty_trade_id'] // requested Morty in the trade
        ]
    ];

    echo json_encode($response, JSON_UNESCAPED_SLASHES);

} catch(Throwable $e) {
    http_response_code(500);
    echo json_encode(["error"=>"SERVER_ERROR","message"=>$e->getMessage()]);
}
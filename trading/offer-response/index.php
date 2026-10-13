<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");

require '../../pocket_f4894h398r8h9w9er8he98he.php';

$input = file_get_contents('php://input');
$data = json_decode($input, true);

$trade_request_id = $data['trade_request_id'] ?? null;
$trade_offer_id = $data['trade_offer_id'] ?? null;
$request_accepted = (bool)($data['request_accepted'] ?? false);

try {
    if (!$trade_request_id || !$trade_offer_id) {
        http_response_code(400);
        echo json_encode(["error"=>"MISSING_PARAMETERS"]);
        exit;
    }

    // GET trade request
    $stmt = $pdo->prepare("SELECT * FROM trades WHERE trade_id = ? LIMIT 1");
    $stmt->execute([$trade_request_id]);
    $trade = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$trade) {
        http_response_code(404);
        echo json_encode(["error"=>"TRADE_REQUEST_NOT_FOUND"]);
        exit;
    }

    // GET trade offer
    $stmt = $pdo->prepare("SELECT * FROM trade_offers WHERE trade_offer_id = ? LIMIT 1");
    $stmt->execute([$trade_offer_id]);
    $offer = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$offer) {
        http_response_code(404);
        echo json_encode(["error"=>"TRADE_OFFER_NOT_FOUND"]);
        exit;
    }

    if ($request_accepted) {
        // Swap Morty ownerships
        $stmt = $pdo->prepare("UPDATE owned_morties SET player_id = ? WHERE owned_morty_id = ?");
        // Trade request Morty goes to offer player
        $stmt->execute([$offer['player_id'], $trade['morty_trade_id']]);
        // Offered Morty goes to request player
        $stmt->execute([$trade['player_id'], $offer['morty_offer_id']]);

        // Insert completed trade
        $completed_trade_id = bin2hex(random_bytes(16));
        $stmt = $pdo->prepare("
            INSERT INTO completed_trades (
                completed_trade_id,
                request_player_id,
                offer_player_id,
                morty_request_id,
                morty_offer_id,
                trade_request_id,
                trade_offer_id,
                is_free_trade,
                fulfilled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NOW())
        ");
        $stmt->execute([
            $completed_trade_id,
            $trade['player_id'],
            $offer['player_id'],
            $trade['morty_trade_id'],
            $offer['morty_offer_id'],
            $trade_request_id,
            $trade_offer_id,
            $trade['is_free_trade']
        ]);

        // Delete original trade offer and request if needed
        $stmt = $pdo->prepare("DELETE FROM trade_offers WHERE trade_offer_id = ?");
        $stmt->execute([$trade_offer_id]);

        // Optionally delete the trade request if fully completed
        $stmt = $pdo->prepare("DELETE FROM trades WHERE trade_id = ?");
        $stmt->execute([$trade_request_id]);

    } else {
        // Reject: just delete the offer
        $stmt = $pdo->prepare("DELETE FROM trade_offers WHERE trade_offer_id = ?");
        $stmt->execute([$trade_offer_id]);
    }

    // Official response
    echo json_encode([null, null]);

} catch(Throwable $e) {
    http_response_code(500);
    echo json_encode(["error"=>"SERVER_ERROR","message"=>$e->getMessage()]);
}
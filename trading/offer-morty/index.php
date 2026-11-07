<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");

require '../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../lib/trade_offer_metadata.php';
require_once __DIR__ . '/../../lib/trade_listing.php';

try {
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') throw new TradeListingError(405);
    $data = trade_listing_body(json_decode(file_get_contents('php://input')), true);
    $session_id = $data['session_id'];
    $player_id = $data['player_id'];
    $offered_morty_id = $data['offered_morty_id'];
    $trade_request_id = $data['trade_request_id'];

    // Actor first, then parent: serialize both listing routes and coordinate
    // with response/cancellation before checking reservations or inserting.
    $user = trade_listing_actor_lock($pdo, $session_id, $player_id);
    $trade = trade_listing_parent_lock($pdo, $trade_request_id);
    $morty = trade_listing_morty_lock($pdo, $user, $offered_morty_id, true);
    trade_listing_offer_criteria($trade, $morty);

    // INSERT trade offer
    $offer_id = bin2hex(random_bytes(16)); // unique ID
    $stmt = $pdo->prepare("
        INSERT INTO trade_offers (trade_offer_id, trade_id, player_id, morty_offer_id, created_at)
        VALUES (?, ?, ?, ?, NOW())
    ");
    $stmt->execute([$offer_id, $trade_request_id, $player_id, $offered_morty_id]);
    $metadata = trade_offer_metadata($pdo, $trade_request_id, $player_id, $offered_morty_id);
    $pdo->commit();

    // RETURN official-style JSON
    $response = [
        "error" => "None",
        "offer" => array_merge([
            "trade_offer_id" => $offer_id,
            "trade_id" => $trade_request_id,
            "player_id" => $player_id,
            "morty_offer_id" => $offered_morty_id,
            "_created" => gmdate("Y-m-d\TH:i:s.v\Z"),
        ], $metadata)
    ];

    echo json_encode($response, JSON_UNESCAPED_SLASHES);

} catch(Throwable $e) {
    trade_listing_error($pdo, $e);
}

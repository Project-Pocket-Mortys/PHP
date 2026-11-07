<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

error_reporting(E_ALL);
ini_set('display_errors', 0);

require '../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../lib/trade_listing.php';

// 🔒 Cost (adjust if needed)
$TRADE_COST = 1;

function uuidv4() {
    $data = random_bytes(16);
    $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
    $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
    return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
}

try {
    if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') throw new TradeListingError(405);
    $data = trade_listing_body(json_decode(file_get_contents('php://input')), false);
    $session_id = $data['session_id'];
    $owned_morty_id = $data['owned_morty_id'];
    $requested_morty_id = $data['requested_morty_id'];
    $request_variant = $data['request_variant'];
    $is_free_trade = $data['is_free_trade'];
    $user = trade_listing_actor_lock($pdo, $session_id, $data['player_id']);
    $player_id = $user['player_id'];
    $coupons = (int)$user['coupons'];
    trade_listing_morty_lock($pdo, $user, $owned_morty_id, false);

    if (!$is_free_trade) {

        if ($coupons < $TRADE_COST) throw new TradeListingError(409);

        // Deduct coupon
        $pdo->prepare("
            UPDATE users
            SET coupons = coupons - ?
            WHERE player_id = ?
        ")->execute([$TRADE_COST, $player_id]);

        $coupons -= $TRADE_COST;
    }

    // ============================
    // 🔥 CREATE TRADE
    // ============================
    $trade_id = uuidv4();
    $created  = gmdate("Y-m-d\TH:i:s.v\Z");

	if ($is_free_trade) {
	// PLAYER COOLDOWN DATA
	$expiry = gmdate("Y-m-d\TH:i:s.v\Z", time()+3600);
    $pdo->prepare("
        UPDATE users
        SET expiry_trade = ?
        WHERE player_id = ?
    ")->execute([$expiry, $player_id]);
	}

    $pdo->prepare("
        INSERT INTO trades
        (trade_id, player_id, morty_trade_id, requested_morty_id, request_variant, is_free_trade, created_at)
        VALUES (?, ?, ?, ?, ?, ?, NOW())
    ")->execute([
        $trade_id,
        $player_id,
        $owned_morty_id,
        $requested_morty_id ?: "any",
        $request_variant ?: "Normal",
        $is_free_trade ? 1 : 0
    ]);

    // ============================
    // ✅ RESPONSE
    // ============================
    $pdo->commit();
    echo json_encode([
        "error" => "None",
        "trade" => [
            "trade_id" => $trade_id,
            "player_id" => $player_id,
            "morty_trade_id" => $owned_morty_id,
            "morty_request" => $requested_morty_id ?: "any",
            "_created" => $created,
            "is_free_trade" => $is_free_trade,
            "request_variant" => $request_variant ?: "Normal"
        ],
        "coupons" => $coupons
    ], JSON_UNESCAPED_SLASHES);

} catch (Throwable $e) {
    trade_listing_error($pdo, $e);
}

/*
{
	"error": "None",
	"trade": {
		"trade_id": "86042588-2f19-11f1-a543-9fd732639dd7",
		"player_id": "dfd1bb4f-5a40-4841-ac32-d4ae2ba72b1f",
		"morty_trade_id": "423e6a46-a640-11f0-931e-c71f52c5f4ad",
		"morty_request": "any",
		"_created": "2026-04-03T04:56:49.430Z",
		"is_free_trade": true,
		"request_variant": "Normal"
	},
	"coupons": 13
}
OR
{
	"error": "None",
	"trade": {
		"trade_id": "ec3c5c8a-2f19-11f1-a3b2-478cac6ddb80",
		"player_id": "dfd1bb4f-5a40-4841-ac32-d4ae2ba72b1f",
		"morty_trade_id": "4f5fe948-1b28-11e9-9df6-f32d12ee61bb",
		"morty_request": "MortyAcePilot",
		"_created": "2026-04-03T04:59:40.926Z",
		"is_free_trade": false,
		"request_variant": "Normal"
	},
	"cooldown": {
		"expiry": "2026-04-04T04:58:02.159Z",
		"trades": 1
	},
	"coupons": 13
}
OR
{
	"error": {
		"code": "TRADE_MORTY_LOCKED"
	}
}
*/

<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

error_reporting(E_ALL);
ini_set('display_errors', 1);

require '../../pocket_f4894h398r8h9w9er8he98he.php';

$input = file_get_contents('php://input');
$data = json_decode($input, true);

// ✅ Inputs
$session_id         = (string)($data['session_id'] ?? '');
$owned_morty_id     = (string)($data['owned_morty_id'] ?? '');
$requested_morty_id = (string)($data['requested_morty_id'] ?? 'any');
$request_variant    = (string)($data['request_variant'] ?? 'Normal');
$is_free_trade      = filter_var($data['is_free_trade'] ?? false, FILTER_VALIDATE_BOOLEAN);

// 🔒 Cost (adjust if needed)
$TRADE_COST = 1;

function uuidv4() {
    $data = random_bytes(16);
    $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
    $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
    return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
}

try {

    // ============================
    // 🔐 AUTH
    // ============================
    $stmt = $pdo->prepare("SELECT player_id, coupons FROM users WHERE session_id = ? LIMIT 1");
    $stmt->execute([$session_id]);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$user) {
        http_response_code(401);
        echo json_encode(["error" => ["code" => "NOT_AUTHENTICATED"]]);
        exit;
    }

    $player_id = $user['player_id'];
    $coupons   = (int)$user['coupons'];

    // ============================
    // 🧠 VERIFY MORTY OWNERSHIP
    // ============================
    $stmt = $pdo->prepare("
        SELECT owned_morty_id 
        FROM owned_morties 
        WHERE owned_morty_id = ? AND player_id = ?
        LIMIT 1
    ");
    $stmt->execute([$owned_morty_id, $player_id]);

    if (!$stmt->fetch()) {
        http_response_code(403);
        echo json_encode(["error" => ["code" => "INVALID_MORTY"]]);
        exit;
    }

    // ============================
    // 🚫 PREVENT DUPLICATE TRADES
    // ============================
    $stmt = $pdo->prepare("
        SELECT trade_id 
        FROM trades 
        WHERE morty_trade_id = ?
        LIMIT 1
    ");
    $stmt->execute([$owned_morty_id]);

    if ($stmt->fetch()) {
        http_response_code(409);
        echo json_encode(["error" => ["code" => "ALREADY_TRADING"]]);
        exit;
    }

    // ============================
    // 💰 COUPON CHECK
    // ============================
    if (!$is_free_trade) {

        if ($coupons < $TRADE_COST) {
            http_response_code(409);
            echo json_encode(["error" => ["code" => "NOT_ENOUGH_COUPONS"]]);
            exit;
        }
		
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
    http_response_code(500);
    echo json_encode([
        "error" => ["code" => "SERVER_ERROR"]
    ]);
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
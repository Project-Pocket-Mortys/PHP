<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");

require '../../pocket_f4894h398r8h9w9er8he98he.php';

$input = file_get_contents('php://input');
$data = json_decode($input, true);

$session_id = (string)($data['session_id'] ?? '');
$use_friends = (bool)($data['use_friends'] ?? true);

try {
    // AUTH
    $stmt = $pdo->prepare("SELECT player_id FROM users WHERE session_id = ? LIMIT 1");
    $stmt->execute([$session_id]);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$user) {
        http_response_code(401);
        echo json_encode(["error"=>["code"=>"NOT_AUTHENTICATED"]]);
        exit;
    }
    $player_id = $user['player_id'];
	$expiry_trade = $user['expiry_trade'] ?? null;

	$player_cooldown_data = [
    	"expiry" => $expiry_trade,
    	"trades" => $expiry_trade ? 1 : 0
	];
	
    // FRIENDS
    $friends = [];
    if ($use_friends) {
        $stmt = $pdo->prepare("
            SELECT CASE 
                       WHEN player_id_a = ? THEN player_id_b 
                       ELSE player_id_a 
                   END AS friend_id
            FROM friend_list
            WHERE (player_id_a = ? OR player_id_b = ?) AND pending = false
        ");
        $stmt->execute([$player_id,$player_id,$player_id]);
        $friends = $stmt->fetchAll(PDO::FETCH_COLUMN);
    }

    // Include self as well, because official JSON sometimes shows your own trades
    $friends_and_self = $friends;
    $friends_and_self[] = $player_id;
    $placeholders = implode(',', array_fill(0, count($friends_and_self), '?'));

    // TRADE REQUESTS
    $stmt = $pdo->prepare("SELECT * FROM trades WHERE player_id IN ($placeholders) ORDER BY created_at DESC LIMIT 50");
    $stmt->execute($friends_and_self);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    $trade_requests = [];
    $trade_ids = [];
    foreach($rows as $r){
        $trade_requests[] = [
            "trade_id"=>$r['trade_id'],
            "player_id"=>$r['player_id'],
            "morty_trade_id"=>$r['morty_trade_id'],
            "morty_request"=>$r['requested_morty_id'] ?: "any",
            "request_variant"=>$r['request_variant'] ?: "Normal",
            "is_free_trade"=>(bool)$r['is_free_trade'],
            "is_request_morty_shiny"=>(bool)($r['is_request_morty_shiny'] ?? false),
            "_created"=>gmdate("Y-m-d\TH:i:s.v\Z", strtotime($r['created_at']))
        ];
        $trade_ids[] = $r['morty_trade_id'];
    }

    // TRADE OFFERS
    $stmt = $pdo->prepare("SELECT * FROM trade_offers WHERE player_id IN ($placeholders) ORDER BY created_at DESC LIMIT 50");
    $stmt->execute($friends_and_self);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    $trade_offers = [];
    foreach($rows as $r){
        $trade_offers[] = [
            "trade_offer_id"=>$r['trade_offer_id'],
            "trade_id"=>$r['trade_id'],
            "player_id"=>$r['player_id'],
            "morty_offer_id"=>$r['morty_offer_id'],
            "_created"=>gmdate("Y-m-d\TH:i:s.v\Z", strtotime($r['created_at']))
        ];
        $trade_ids[] = $r['morty_offer_id'];
    }

    if(empty($trade_ids)) $trade_ids = ['00000000-0000-0000-0000-000000000000'];
    $trade_placeholders = implode(',', array_fill(0, count($trade_ids), '?'));

    // TRADE MORTYS
    $stmt = $pdo->prepare("SELECT * FROM owned_morties WHERE owned_morty_id IN ($trade_placeholders)");
    $stmt->execute($trade_ids);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    $trade_mortys = [];
    foreach($rows as $m){
        $trade_mortys[] = [
            "net_id"=>$m['owned_morty_id'],
            "morty_id"=>$m['morty_id'],
            "xp"=>(int)$m['xp'],
            "level"=>(int)$m['level'],
            "level_confirmed"=>(int)$m['level'],
            "hp"=>(int)$m['hp'],
            "hp_stat"=>(int)$m['hp_stat'],
            "attack_stat"=>(int)$m['attack_stat'],
            "defence_stat"=>(int)$m['defence_stat'],
            "speed_stat"=>(int)$m['speed_stat'],
            "variant"=>$m['variant'] ?? "Normal",
            "xp_lower"=>(int)$m['xp_lower'],
            "xp_upper"=>(int)$m['xp_upper']
        ];
    }

    // TRADE ATTACKS
    $stmt = $pdo->prepare("SELECT * FROM owned_attacks WHERE owned_morty_id IN ($trade_placeholders)");
    $stmt->execute($trade_ids);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    $trade_attacks = [];
    foreach($rows as $a){
        $trade_attacks[] = [
            "net_id"=>$a['owned_morty_id'],
            "attack_id"=>$a['attack_id'],
            "position"=>(int)$a['position'],
            "pp"=>(int)$a['pp'],
            "pp_stat"=>(int)$a['pp_stat']
        ];
    }

    // COMPLETED TRADES
    $stmt = $pdo->prepare("
        SELECT * FROM completed_trades 
        WHERE request_player_id IN ($placeholders) OR offer_player_id IN ($placeholders) 
        ORDER BY fulfilled_at DESC LIMIT 20
    ");
    $stmt->execute(array_merge($friends_and_self,$friends_and_self));
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    $completed_trades = [];
    foreach($rows as $r){
        $completed_trades[] = [
            "completed_trade_id"=>$r['completed_trade_id'],
            "request_player_id"=>$r['request_player_id'],
            "offer_player_id"=>$r['offer_player_id'],
            "morty_request_id"=>$r['morty_request_id'],
            "morty_offer_id"=>$r['morty_offer_id'],
            "_fulfilled"=>gmdate("Y-m-d\TH:i:s.v\Z", strtotime($r['fulfilled_at'])),
            "trade_offer_id"=>$r['trade_offer_id'],
            "trade_request_id"=>$r['trade_request_id'],
            "is_free_trade"=>(bool)$r['is_free_trade']
        ];
    }

    echo json_encode([
        "trade_requests"=>$trade_requests,
        "trade_offers"=>$trade_offers,
        "trade_mortys"=>$trade_mortys,
        "trade_attacks"=>$trade_attacks,
        "player_cooldown_data"=>$player_cooldown_data,
        "completed_trades"=>$completed_trades
    ], JSON_UNESCAPED_SLASHES);

}catch(Throwable $e){
    http_response_code(500);
    echo json_encode(["error"=>["code"=>"SERVER_ERROR","message"=>$e->getMessage()]]);
}
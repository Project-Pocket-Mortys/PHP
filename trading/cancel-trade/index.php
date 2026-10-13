<?php
header("Content-Type: application/json; charset=utf-8");

require '../../pocket_f4894h398r8h9w9er8he98he.php';

$data = json_decode(file_get_contents('php://input'), true);

$trade_id = (string)($data['trade_id'] ?? '');

if (!$trade_id) {
    echo json_encode(["error" => ["code" => "INVALID_REQUEST"]]);
    exit;
}

// ============================
// 🔐 OPTIONAL SESSION CHECK
// ============================
$headers = getallheaders();
$session_id = "";

if (!empty($headers['Authorization'])) {
    if (preg_match('/Bearer\s+(.*)$/i', $headers['Authorization'], $m)) {
        $session_id = trim($m[1]);
    }
}

if (!$session_id && !empty($_COOKIE['session_id'])) {
    $session_id = $_COOKIE['session_id'];
}

$player_id = null;

if ($session_id) {
    $stmt = $pdo->prepare("SELECT player_id FROM users WHERE session_id = ? LIMIT 1");
    $stmt->execute([$session_id]);
    $u = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($u) {
        $player_id = $u['player_id'];
    }
}

// ============================
// 🔍 FIND TRADE
// ============================
$stmt = $pdo->prepare("SELECT * FROM trades WHERE trade_id = ? LIMIT 1");
$stmt->execute([$trade_id]);
$trade = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$trade) {
    echo json_encode([
        "error" => ["code" => "NOT_FOUND"]
    ]);
    exit;
}

// ============================
// 🔒 VERIFY OWNER (IF WE HAVE SESSION)
// ============================
if ($player_id && $trade['player_id'] !== $player_id) {
    echo json_encode([
        "error" => ["code" => "NOT_ALLOWED"]
    ]);
    exit;
}

// ============================
// 🧹 DELETE TRADE
// ============================
$pdo->beginTransaction();

$pdo->prepare("DELETE FROM trade_offers WHERE trade_id = ?")
    ->execute([$trade_id]);

$pdo->prepare("DELETE FROM trades WHERE trade_id = ?")
    ->execute([$trade_id]);

$pdo->commit();

// ============================
// ✅ RESPONSE
// ============================
echo json_encode([
    "error" => "None"
], JSON_UNESCAPED_SLASHES);
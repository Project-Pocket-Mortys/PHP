<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

error_reporting(E_ALL);
ini_set('display_errors', 0);

require __DIR__ . "/../../../../pocket_f4894h398r8h9w9er8he98he.php";
require_once __DIR__ . "/../../../../lib/preparation_writer_guard.php";

// Read + decode JSON safely
$input = file_get_contents('php://input');
$data  = json_decode($input, true);

if (!is_array($data)) {
    http_response_code(400);
    echo json_encode(["error" => ["code" => "BAD_JSON"]], JSON_UNESCAPED_SLASHES);
    exit;
}

$session_id = (string)($data['session_id'] ?? '');

if ($session_id === '') {
    http_response_code(401);
    echo json_encode(["error" => ["code" => "NOT_AUTHENTICATED"]], JSON_UNESCAPED_SLASHES);
    exit;
}

try {
$user = preparation_writer_lock($pdo, $session_id);

// Deck config
$stmt = $pdo->prepare("SELECT starting_deck_slots, max_deck_slots, cost_additional_slot FROM deck_config LIMIT 1");
$stmt->execute();
$config = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$config) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    http_response_code(500);
    echo json_encode(["error" => ["code" => "DECK_CONFIG_NOT_FOUND"]], JSON_UNESCAPED_SLASHES);
    exit;
}

$starting_deck_slots  = (int)$config['starting_deck_slots'];
$max_deck_slots       = (int)$config['max_deck_slots'];
$cost_additional_slot = (int)$config['cost_additional_slot'];

$player_id   = (string)$user['player_id'];
$decks_owned = (int)$user['decks_owned'];
$coupons     = (int)$user['coupons'];

// Check coupons
if ($coupons < $cost_additional_slot) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    http_response_code(400);
    echo json_encode([
        "error" => ["code" => "NOT_ENOUGH_COUPONS"]
    ], JSON_UNESCAPED_SLASHES);
    exit;
}

// Check max deck slots
if ($decks_owned >= $max_deck_slots) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    http_response_code(400);
    echo json_encode([
        "error" => ["code" => "MAX_DECKS_BOUGHT"]
    ], JSON_UNESCAPED_SLASHES);
    exit;
}

// Add a deck + charge coupons
$new_decks_owned = $decks_owned + 1;
$new_coupons     = $coupons - $cost_additional_slot;

$stmt = $pdo->prepare("
    UPDATE users
    SET decks_owned = ?, coupons = ?
    WHERE id = ?
    LIMIT 1
");
$stmt->execute([$new_decks_owned, $new_coupons, $user['id']]);

if ($stmt->rowCount() < 1) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    http_response_code(500);
    echo json_encode(["error" => ["code" => "DB_UPDATE_FAILED"]], JSON_UNESCAPED_SLASHES);
    exit;
}

$pdo->commit();
echo json_encode([
    "deck_slots" => $new_decks_owned,
    "coupons"    => $new_coupons
], JSON_UNESCAPED_SLASHES);
exit;

} catch (Throwable $e) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    http_response_code($e instanceof FriendError ? $e->status : 500);
    $code = $e instanceof FriendError ? ($e->status === 401 ? 'INVALID_SESSION' : $e->getMessage()) : 'SERVER_ERROR';
    echo json_encode(['error' => ['code' => $code]], JSON_UNESCAPED_SLASHES);
}

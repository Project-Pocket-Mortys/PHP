<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require '../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../lib/preparation_writer_guard.php';

$input = file_get_contents('php://input');
$data = json_decode($input, true);

$session_id = (string)($data['session_id'] ?? '');
$item_id    = (string)($data['item_id'] ?? '');

if ($session_id === '' || $item_id === '') {
    http_response_code(400);
    echo json_encode(["error" => ["code" => "BAD_REQUEST"]], JSON_UNESCAPED_SLASHES);
    exit;
}

// 🔒 Max limit per item (change if needed)
$MAX_ITEM_LIMIT = 10;

try {
    $user = preparation_writer_lock($pdo, $session_id);

    $player_id = $user['player_id'];

    // ✅ Check if item already exists
    $stmt = $pdo->prepare("
        SELECT quantity
        FROM owned_items
        WHERE player_id = ? AND item_id = ?
        LIMIT 1
    ");
    $stmt->execute([$player_id, $item_id]);
    $row = $stmt->fetch(PDO::FETCH_ASSOC);

    if ($row) {
        $current_qty = (int)$row['quantity'];

        // ❌ Limit reached
        if ($current_qty >= $MAX_ITEM_LIMIT) {
            $pdo->rollBack();
            http_response_code(409);
            echo json_encode([
                "error" => ["code" => "ITEM_LIMIT"]
            ], JSON_UNESCAPED_SLASHES);
            exit;
        }

        // ✅ Update quantity
        $new_qty = min($current_qty + 1, $MAX_ITEM_LIMIT);

        $stmt = $pdo->prepare("
            UPDATE owned_items
            SET quantity = ?
            WHERE player_id = ? AND item_id = ?
        ");
        $stmt->execute([$new_qty, $player_id, $item_id]);

        $final_qty = $new_qty;

    } else {
        // ✅ Insert new item
        $stmt = $pdo->prepare("
            INSERT INTO owned_items (player_id, item_id, quantity)
            VALUES (?, ?, 1)
        ");
        $stmt->execute([$player_id, $item_id]);

        $final_qty = 1;
    }

    // ✅ Success response
    $pdo->commit();
    echo json_encode([
        "coins" => 3205915, // you can replace with real value later
        "coupons" => 1,
        "result" => [
            "type" => "ITEM",
            "item_id" => $item_id,
            "quantity" => $final_qty,
            "amount_received" => 1,
            "amount" => 1
        ]
    ], JSON_UNESCAPED_SLASHES);

} catch (Throwable $e) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    http_response_code($e instanceof FriendError ? $e->status : 500);
    echo json_encode([
        "error" => ["code" => $e instanceof FriendError ? $e->getMessage() : "SERVER_ERROR"]
    ], JSON_UNESCAPED_SLASHES);
}

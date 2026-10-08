<?php
// owned_morties/absorb
error_reporting(E_ALL);
ini_set('display_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");

require '../../../pocket_f4894h398r8h9w9er8he98he.php';

// ============================
// 📥 INPUT
// ============================
$data = json_decode(file_get_contents('php://input'), true);

$session_id = (string)($data['session_id'] ?? '');
$target_id  = (string)($data['owned_morty_id'] ?? '');
$absorb_ids = $data['absorb_owned_morty_ids'] ?? [];

if (!$session_id || !$target_id || !is_array($absorb_ids)) {
    echo json_encode(["error" => ["code" => "INVALID_REQUEST"]]);
    exit;
}

try {

    // ============================
    // 🔐 AUTH
    // ============================
    $stmt = $pdo->prepare("SELECT player_id FROM users WHERE session_id = ? LIMIT 1");
    $stmt->execute([$session_id]);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$user) {
        echo json_encode(["error" => ["code" => "NOT_AUTHENTICATED"]]);
        exit;
    }

    $player_id = $user['player_id'];

    // ============================
    // ✅ VERIFY TARGET EXISTS
    // ============================
    $stmt = $pdo->prepare("SELECT evolution_points FROM owned_morties WHERE owned_morty_id = ? AND player_id = ?");
    $stmt->execute([$target_id, $player_id]);
    $target = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$target) {
        echo json_encode(["error" => ["code" => "NOT_FOUND"]]);
        exit;
    }

    // ============================
    // ✅ FILTER VALID ABSORBS
    // ============================
    $valid_absorb = [];

    foreach ($absorb_ids as $id) {
        if ($id === $target_id) continue;

        $stmt = $pdo->prepare("SELECT owned_morty_id FROM owned_morties WHERE owned_morty_id = ? AND player_id = ?");
        $stmt->execute([$id, $player_id]);

        if ($stmt->fetch()) {
            $valid_absorb[] = $id;
        }
    }

    if (empty($valid_absorb)) {
        echo json_encode(["error" => ["code" => "NO_VALID_MORTYS"]]);
        exit;
    }

    $pdo->beginTransaction();

    // ============================
    // 🔥 DELETE ABSORBED MORTYS
    // ============================
    $placeholders = implode(',', array_fill(0, count($valid_absorb), '?'));

    $stmt = $pdo->prepare("DELETE FROM owned_morties WHERE owned_morty_id IN ($placeholders)");
    $stmt->execute($valid_absorb);

    // also remove attacks tied to them
    $stmt = $pdo->prepare("DELETE FROM owned_attacks WHERE owned_morty_id IN ($placeholders)");
    $stmt->execute($valid_absorb);

    // ============================
    // 🔥 REMOVE FROM DECKS
    // ============================
    $stmt = $pdo->prepare("SELECT deck_id, owned_morty_ids FROM decks WHERE player_id = ?");
    $stmt->execute([$player_id]);
    $decks_raw = $stmt->fetchAll(PDO::FETCH_ASSOC);

    $updated_decks = [];

    foreach ($decks_raw as $deck) {
        $ids = json_decode(stripcslashes($deck['owned_morty_ids']), true);
        if (!is_array($ids)) $ids = [];

        // remove absorbed mortys
        $ids = array_values(array_diff($ids, $valid_absorb));

        // update db
        $stmt = $pdo->prepare("UPDATE decks SET owned_morty_ids = ? WHERE deck_id = ? AND player_id = ?");
        $stmt->execute([json_encode($ids), $deck['deck_id'], $player_id]);

        $updated_decks[] = [
            "deck_id" => (int)$deck['deck_id'],
            "owned_morty_ids" => $ids
        ];
    }

    // ============================
    // 🔥 UPDATE EVOLUTION POINTS
    // ============================
    $gain = count($valid_absorb);
    $new_points = (int)$target['evolution_points'] + $gain;

    $stmt = $pdo->prepare("UPDATE owned_morties SET evolution_points = ? WHERE owned_morty_id = ?");
    $stmt->execute([$new_points, $target_id]);

    $pdo->commit();

    // ============================
    // ✅ RESPONSE
    // ============================
    echo json_encode([
        "removed" => array_values($valid_absorb),
        "modified" => [
            "owned_morty_id" => $target_id,
            "evolution_points" => $new_points
        ],
        "decks" => $updated_decks
    ], JSON_UNESCAPED_SLASHES);

} catch (Throwable $e) {

    if ($pdo->inTransaction()) {
        $pdo->rollBack();
    }

    http_response_code(500);
    echo json_encode([
        "error" => ["code" => "SERVER_ERROR"]
    ]);
}
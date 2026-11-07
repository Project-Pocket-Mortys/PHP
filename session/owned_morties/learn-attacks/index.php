<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require '../../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../../lib/battle_membership_guard.php';
require_once __DIR__ . '/../../../lib/trade_references.php';

$input = file_get_contents('php://input');
$data = json_decode($input, true);

$session_id = (string)($data['session_id'] ?? '');
$morties    = $data['owned_morties'] ?? [];

if ($session_id === '' || empty($morties)) {
    http_response_code(400);
    echo json_encode(["error" => ["code" => "BAD_REQUEST"]], JSON_UNESCAPED_SLASHES);
    exit;
}

try {
    // ============================
    // 🔐 AUTH
    // ============================
    $stmt = $pdo->prepare("SELECT * FROM users WHERE session_id = ? LIMIT 1");
    $stmt->execute([$session_id]);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);

    if (!$user) {
        http_response_code(401);
        echo json_encode(["error" => ["code" => "NOT_AUTHENTICATED"]], JSON_UNESCAPED_SLASHES);
        exit;
    }

    $player_id = $user['player_id'];
    $pdo->beginTransaction();
    $lock = $pdo->prepare("SELECT * FROM users WHERE player_id = ? FOR UPDATE");
    $lock->execute([$player_id]);
    $lockedUsers = $lock->fetchAll(PDO::FETCH_ASSOC);
    $sessionCheck = $pdo->prepare("SELECT id FROM users WHERE session_id = ?");
    $sessionCheck->execute([$session_id]);
    $sessionUsers = $sessionCheck->fetchAll(PDO::FETCH_ASSOC);
    if (count($lockedUsers) !== 1 || $lockedUsers[0]['session_id'] !== $session_id || count($sessionUsers) !== 1) {
        $pdo->rollBack();
        respond(401, ["error" => ["code" => "NOT_AUTHENTICATED"]]);
    }
    $user = $lockedUsers[0];
    if (battle_has_shared_membership($pdo, $player_id)) {
        $pdo->rollBack();
        respond(409, ["error" => ["code" => "FAILED"]]);
    }

    // ============================
    // 🔥 PROCESS + TRACK UPDATED
    // ============================
    $updated_ids = [];

    foreach ($morties as $m) {

        $owned_morty_id = (string)($m['owned_morty_id'] ?? '');
        $attack_ids     = $m['attack_ids'] ?? [];

        if ($owned_morty_id === '' || empty($attack_ids)) continue;

        // Limit to 4 attacks (game behavior)
        $attack_ids = array_slice($attack_ids, 0, 4);
        // Native sends null for unused slots. An entirely empty selection
        // follows the existing empty-entry skip behavior, before deleting rows.
        if (!array_filter($attack_ids, static fn($attack_id) => $attack_id !== null)) continue;

        // Verify ownership
        $stmt = $pdo->prepare("
            SELECT owned_morty_id, player_id
            FROM owned_morties
            WHERE owned_morty_id = ?
            ORDER BY id
            FOR UPDATE
        ");
        $stmt->execute([$owned_morty_id]);
        $owners = $stmt->fetchAll(PDO::FETCH_ASSOC);
        // Attack rows are keyed only by logical Morty ID, so duplicates are unsafe.
        if (count($owners) !== 1 || $owners[0]['player_id'] !== $player_id) continue;

        // Delete old attacks
        $pdo->prepare("DELETE FROM owned_attacks WHERE owned_morty_id = ?")
            ->execute([$owned_morty_id]);

        // Insert new attacks
        $pos = 0;
        foreach ($attack_ids as $attack_id) {
            // Keep the native slot index without storing a blank attack ID.
            if ($attack_id === null) {
                $pos++;
                continue;
            }

            $attack_id = (string)$attack_id;

            // Default PP (can improve later)
            $pp = 8;

            $pdo->prepare("
                INSERT INTO owned_attacks
                (owned_morty_id, attack_id, position, pp, pp_stat)
                VALUES (?, ?, ?, ?, ?)
            ")->execute([
                $owned_morty_id,
                $attack_id,
                $pos,
                $pp,
                $pp
            ]);

            $pos++;
        }

        // Track updated morty
        $updated_ids[] = $owned_morty_id;
    }

    // ============================
    // 🔥 FETCH ONLY UPDATED MORTIES
    // ============================
    if (empty($updated_ids)) {
        $pdo->commit();
        echo json_encode([
            "player_id" => $user['player_id'],
            "username" => $user['username'],
            "player_avatar_id" => $user['player_avatar_id'] ?? "AvatarRickDefault",
            "level" => (int)$user['level'],
            "xp" => (int)$user['xp'],
            "streak" => (int)$user['streak'],
            "coins" => (int)$user['coins'],
            "coupons" => (int)$user['coupons'],
            "permits" => (int)$user['permits'],
            "owned_morties" => [],
            "xp_lower" => (int)$user['xp_lower'],
            "xp_upper" => (int)$user['xp_upper'],
            "tags" => []
        ], JSON_UNESCAPED_SLASHES);
        exit;
    }

    $placeholders = implode(',', array_fill(0, count($updated_ids), '?'));
    $tradeProjection = trade_reference_projection('m.owned_morty_id');

    $stmt = $pdo->prepare("
        SELECT
            m.*,
            $tradeProjection AS has_trade_reference,
            a.attack_id,
            a.position,
            a.pp,
            a.pp_stat
        FROM owned_morties m
        LEFT JOIN owned_attacks a
            ON m.owned_morty_id = a.owned_morty_id
        WHERE m.player_id = ?
          AND m.owned_morty_id IN ($placeholders)
        ORDER BY m.owned_morty_id, a.position
    ");

    $stmt->execute(array_merge([$player_id], $updated_ids));
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);

    // ============================
    // 🔥 BUILD RESPONSE
    // ============================
    $mortyMap = [];
    // Match player-details' legacy DB spellings; (bool)"false" is true in PHP.
    $responseBool = static fn($value): bool => in_array(
        strtolower(trim((string)$value)), ['1', 'true', 'yes', 'y', 'on'], true);

    foreach ($rows as $row) {

        $id = $row['owned_morty_id'];

        if (!isset($mortyMap[$id])) {
            $mortyMap[$id] = [
                "owned_morty_id" => $id,
                "morty_id" => $row['morty_id'],
                "level" => (int)$row['level'],
                "xp" => (int)$row['xp'],
                "hp" => (int)$row['hp'],
                "hp_stat" => (int)$row['hp_stat'],
                "attack_stat" => (int)$row['attack_stat'],
                "defence_stat" => (int)$row['defence_stat'],
                "variant" => $row['variant'] ?? "Normal",
                "speed_stat" => (int)$row['speed_stat'],
                "is_poisoned" => $responseBool($row['is_poisoned']),
                "is_paralysed" => $responseBool($row['is_paralysed']),
                "is_locked" => $responseBool($row['is_locked']),
                "is_trading_locked" => $responseBool($row['is_trading_locked']) || (int)$row['has_trade_reference'] === 1,
                "fight_pit_id" => $row['fight_pit_id'] ?: null,
                "evolution_points" => (int)$row['evolution_points'],
                "xp_lower" => (int)$row['xp_lower'],
                "xp_upper" => (int)$row['xp_upper'],
                "owned_attacks" => []
            ];
        }

        if (!empty($row['attack_id'])) {
            $mortyMap[$id]['owned_attacks'][] = [
                "attack_id" => $row['attack_id'],
                "position" => (int)$row['position'],
                "pp" => (int)$row['pp'],
                "pp_stat" => (int)$row['pp_stat']
            ];
        }
    }

    $owned_morties = array_values($mortyMap);
    $pdo->commit();

    // ============================
    // 🔥 FINAL RESPONSE
    // ============================
    echo json_encode([
        "player_id" => $user['player_id'],
        "username" => $user['username'],
        "player_avatar_id" => $user['player_avatar_id'] ?? "AvatarRickDefault",

        "level" => (int)$user['level'],
        "xp" => (int)$user['xp'],
        "streak" => (int)$user['streak'],

        "coins" => (int)$user['coins'],
        "coupons" => (int)$user['coupons'],
        "permits" => (int)$user['permits'],

        // ✅ ONLY UPDATED MORTIES
        "owned_morties" => $owned_morties,

        "xp_lower" => (int)$user['xp_lower'],
        "xp_upper" => (int)$user['xp_upper'],

        "tags" => []
    ], JSON_UNESCAPED_SLASHES);

} catch (Throwable $e) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    http_response_code(500);
    echo json_encode([
        "error" => ["code" => "SERVER_ERROR"]
    ], JSON_UNESCAPED_SLASHES);
}

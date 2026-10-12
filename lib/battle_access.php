<?php
declare(strict_types=1);

/** The existing PvWM handler mutates the initiator side only; it is not a PvP handler. */
function require_active_owned_battle(PDO $pdo, string $battle_id, string $player_id): array {
    $stmt = $pdo->prepare('SELECT * FROM battles WHERE battle_id = ? LIMIT 1');
    $stmt->execute([$battle_id]);
    $battle = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$battle) {
        respond(404, ['success' => false]);
    }
    if ((string)$battle['player_id'] !== $player_id) {
        respond(403, ['success' => false]);
    }
    if ($battle['state'] !== 'ACTIVE') {
        respond(409, ['success' => false]);
    }
    return $battle;
}

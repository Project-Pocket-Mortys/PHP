<?php
declare(strict_types=1);
require_once __DIR__ . '/battle_turn.php';

/** Caller holds the user's row lock before checking or changing world state. */
function world_action_has_active_battle(PDO $pdo, string $player_id): bool {
    // Old handlers left finished battles ACTIVE. Reuse the evidence-based repair
    // so a proven past terminal result does not disable ordinary world actions.
    battle_reconcile_legacy_terminals($pdo, $player_id);
    $query = $pdo->prepare("SELECT battle_id FROM battles WHERE player_id = ? AND state = 'ACTIVE' LIMIT 1 FOR UPDATE");
    $query->execute([$player_id]);
    return $query->fetchColumn() !== false;
}

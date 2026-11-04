<?php
declare(strict_types=1);

/** Reject through an exception so callers always roll back before responding. */
function battle_reject(int $status, string $code = 'FAILED'): never {
    throw new RuntimeException($code, $status);
}

/** Lock conflicts roll back the whole action and can be retried by the client. */
function battle_error_status(Throwable $error): int {
    if ($error instanceof PDOException && ($error->getCode() === '40001'
        || in_array((int)($error->errorInfo[1] ?? 0), [1205, 1213], true))) return 409;
    $code = $error->getCode();
    return $error instanceof RuntimeException && $code >= 400 && $code <= 599 ? (int)$code : 500;
}

/** Initial added rows are the current room snapshot in the legacy room readers. */
function battle_lock_spawn(PDO $pdo, string $room, string $spawn, string $player, string|array $state): array {
    $stmt = $pdo->prepare("SELECT * FROM event_queue WHERE room_id=? AND event_name='room:wild-morty-added' AND wild_morty_id=? FOR UPDATE");
    $stmt->execute([$room, $spawn]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    if (count($rows) !== 1) battle_reject(409);
    $row = $rows[0];
    $recipient = (string)($row['only_show_to_player_id'] ?? '');
    if ($recipient !== '' && $recipient !== $player) battle_reject(403);
    if (!in_array((string)$row['state'], (array)$state, true)) battle_reject(409);
    return $row;
}

/** No room column exists on battles: recover it from its private start snapshot. */
function battle_origin(PDO $pdo, array $battle, string $player, string $currentRoom): string {
    $stmt = $pdo->prepare("SELECT room_id, battle_start FROM event_queue WHERE event_name='battle:start' AND player_id=? AND only_show_to_player_id=? AND JSON_VALID(battle_start) AND JSON_UNQUOTE(JSON_EXTRACT(IF(JSON_VALID(battle_start), battle_start, '{}'), '$.battle_id'))=? FOR UPDATE");
    $stmt->execute([$player, $player, $battle['battle_id']]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    if (count($rows) !== 1) battle_reject(409);
    $snapshot = json_decode($rows[0]['battle_start'], true);
    $room = (string)$rows[0]['room_id'];
    if ($room === '' || $room !== $currentRoom || ($snapshot['battle_id'] ?? null) !== (string)$battle['battle_id']
        || ($snapshot['battle_type'] ?? null) !== 'PvWM'
        || ($snapshot['player']['player_id'] ?? null) !== $player
        || ($snapshot['player']['active_owned_morty'] ?? null) !== (string)$battle['player_active_morty']
        || ($snapshot['opponent']['player_id'] ?? null) !== (string)$battle['opponent_id']
        || ($snapshot['opponent']['active_owned_morty'] ?? null) !== (string)$battle['opponent_active_morty']) battle_reject(409);
    return $room;
}

/** Old move handlers emitted terminal results without closing their battle rows.
 * Reconcile only explicit, consistent private evidence; never replay its rewards.
 * Caller holds the user's lock and commits this with the new start or rolls back.
 */
function battle_reconcile_legacy_terminals(PDO $pdo, string $player): void {
    $stmt = $pdo->prepare("SELECT * FROM battles WHERE player_id=? AND state='ACTIVE' FOR UPDATE");
    $stmt->execute([$player]);
    foreach ($stmt->fetchAll(PDO::FETCH_ASSOC) as $battle) {
        $starts = $pdo->prepare("SELECT room_id, battle_start FROM event_queue WHERE event_name='battle:start' AND player_id=? AND only_show_to_player_id=? AND JSON_UNQUOTE(JSON_EXTRACT(IF(JSON_VALID(battle_start), battle_start, '{}'), '$.battle_id'))=? FOR UPDATE");
        $starts->execute([$player, $player, $battle['battle_id']]);
        $rows = $starts->fetchAll(PDO::FETCH_ASSOC);
        if (count($rows) !== 1 || (string)$rows[0]['room_id'] === '') continue;
        $start = json_decode($rows[0]['battle_start'], true);
        if (($start['battle_id'] ?? null) !== (string)$battle['battle_id']
            || ($start['battle_type'] ?? null) !== 'PvWM'
            || ($start['player']['player_id'] ?? null) !== $player
            || ($start['player']['active_owned_morty'] ?? null) !== (string)$battle['player_active_morty']
            || ($start['opponent']['player_id'] ?? null) !== (string)$battle['opponent_id']
            || ($start['opponent']['active_owned_morty'] ?? null) !== (string)$battle['opponent_active_morty']) continue;
        // Legacy delivery targets battle results by player_id; newer rows also
        // carry only_show_to_player_id. Conflicting explicit recipients are unsafe.
        $results = $pdo->prepare("SELECT battle_turn_result FROM event_queue WHERE room_id=? AND event_name='battle:turn-result' AND player_id=? AND (only_show_to_player_id IS NULL OR only_show_to_player_id='' OR only_show_to_player_id=?) AND JSON_UNQUOTE(JSON_EXTRACT(IF(JSON_VALID(battle_turn_result), battle_turn_result, '{}'), '$.battle_id'))=? FOR UPDATE");
        $results->execute([$rows[0]['room_id'], $player, $player, $battle['battle_id']]);
        $outcomes = [];
        foreach ($results->fetchAll(PDO::FETCH_COLUMN) as $raw) {
            $result = json_decode($raw, true);
            $outcome = $result['outcome'] ?? null;
            if (($result['battle_id'] ?? null) !== (string)$battle['battle_id']) continue;
            if (is_string($outcome) && in_array($outcome, ['RUN', 'WIN', 'LOSE', 'CAUGHT'], true)) $outcomes[$outcome] = true;
        }
        if (count($outcomes) !== 1) continue;
        $outcome = array_key_first($outcomes);
        $state = $outcome === 'RUN' ? 'CANCELLED' : 'COMPLETED';
        $winner = $outcome === 'RUN' ? null : ($outcome === 'LOSE' ? $battle['opponent_id'] : $player);
        $pdo->prepare('UPDATE battles SET state=?, winner=? WHERE battle_id=?')->execute([$state, $winner, $battle['battle_id']]);
    }
}

/** Legacy placeholder combat only: damage 20, AI damage 1..3, no derived stats. */
function battle_attack_data(string $attacker, string $defender, string $attack, string $attackerMorty, string $defenderMorty, int $damage, int $hp, int $pp): array {
    return [
        'type' => 'ATTACK', 'attacker_player_id' => $attacker, 'defender_player_id' => $defender,
        'attack_id' => $attack, 'element_modifier' => 1,
        'effect_datas' => [[
            'type' => 'Hit', 'is_accurate' => true, 'to_self' => false,
            'continue_on_miss' => false, 'is_critical' => false, 'damage' => $damage,
            'defender_morty_datas' => [['owned_morty_id' => $defenderMorty, 'hp' => $hp]],
        ]],
        'attacker_morty_datas' => [[
            'owned_morty_id' => $attackerMorty,
            'owned_attacks' => [['attack_id' => $attack, 'pp' => $pp]],
        ]],
    ];
}

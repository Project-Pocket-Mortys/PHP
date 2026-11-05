<?php
declare(strict_types=1);

require_once __DIR__ . '/battle_turn.php';
require_once __DIR__ . '/events.php';

/** Caller holds the user then owned ACTIVE battle locks in a transaction. */
function battle_timeout_validate_locked(PDO $pdo, array $user, array $battle): string {
    $player = (string)$user['player_id'];
    if (!$pdo->inTransaction() || (string)$battle['player_id'] !== $player
        || $battle['state'] !== 'ACTIVE' || $user['state'] !== 'BATTLE') battle_reject(409);
    $stmt = $pdo->prepare('SELECT COUNT(*) FROM users WHERE player_id=?');
    $stmt->execute([$player]);
    if ((int)$stmt->fetchColumn() !== 1) battle_reject(409);
    // User lock serializes normal starts; preserve ambiguous historical claims.
    $stmt = $pdo->prepare("SELECT COUNT(*) FROM battles WHERE player_id=? AND state='ACTIVE'");
    $stmt->execute([$player]);
    if ((int)$stmt->fetchColumn() !== 1) battle_reject(409);
    $room = battle_origin($pdo, $battle, $player, (string)($user['room_id'] ?? ''));
    $stmt = $pdo->prepare('SELECT 1 FROM room_ids WHERE room_id=? LIMIT 1');
    $stmt->execute([$room]);
    if (!$stmt->fetchColumn()) battle_reject(409);
    $spawn = (string)$battle['opponent_active_morty'];
    $stmt = $pdo->prepare("SELECT battle_id FROM battles WHERE opponent_active_morty=? AND state='ACTIVE' AND battle_id<>? FOR UPDATE");
    $stmt->execute([$spawn, $battle['battle_id']]);
    if ($stmt->fetch()) battle_reject(409);
    battle_lock_spawn($pdo, $room, $spawn, $player, 'BATTLE');
    return $room;
}

/** Re-read the persisted deadline with the DB clock after acquiring both locks.
 * A queued candidate never carries authority to expire a later selection.
 */
function battle_timeout_expire_locked(PDO $pdo, array $user, array $battle): bool {
    if (!$pdo->inTransaction()) throw new LogicException('Timeout expiry requires a transaction');
    if ($battle['state'] !== 'ACTIVE' || ($battle['move_deadline'] ?? null) === null) return false;
    $stmt = $pdo->prepare("SELECT 1 FROM battles WHERE battle_id=? AND state='ACTIVE' AND move_deadline IS NOT NULL AND move_deadline<=UTC_TIMESTAMP(6) FOR UPDATE");
    $stmt->execute([$battle['battle_id']]);
    if (!$stmt->fetchColumn()) return false;
    $room = battle_timeout_validate_locked($pdo, $user, $battle);
    $player = (string)$user['player_id'];
    $spawn = (string)$battle['opponent_active_morty'];
    $pdo->prepare("UPDATE battles SET state='CANCELLED', winner=NULL, move_deadline=NULL WHERE battle_id=?")->execute([$battle['battle_id']]);
    $pdo->prepare("UPDATE users SET state='WORLD' WHERE player_id=?")->execute([$player]);
    $pdo->prepare("UPDATE event_queue SET state='WORLD' WHERE room_id=? AND event_name='room:wild-morty-added' AND wild_morty_id=?")->execute([$room, $spawn]);
    publish_event($pdo, $room, 'room:wild-morty-state-changed', ['wild_morty_id' => $spawn, 'state' => 'WORLD']);
    publish_event($pdo, $room, 'room:user-state-changed', ['player_id' => $player, 'state' => 'WORLD']);
    // Replacement policy: timeout abandons without combat, rewards or inventory changes.
    publish_event($pdo, $room, 'battle:turn-result', [
        'battle_id' => (string)$battle['battle_id'], 'outcome' => 'ABANDONED',
        'battle_abandoned' => false, 'turn_datas' => [],
        'player_datas' => ['player' => (object)[], 'opponent' => (object)[]],
    ], $player);
    return true;
}

/** Candidates are hints only. Each attempt locks user -> battle and revalidates. */
function battle_timeout_expire_candidates(PDO $pdo, array $candidates, ?string $expectedSession = null): int {
    if ($pdo->inTransaction()) throw new LogicException('Standalone timeout worker requires no transaction');
    $expired = 0;
    foreach ($candidates as $candidate) {
        try {
            $pdo->beginTransaction();
            $stmt = $pdo->prepare('SELECT player_id, room_id, state, session_id FROM users WHERE player_id=? ORDER BY id FOR UPDATE');
            $stmt->execute([$candidate['player_id']]);
            $users = $stmt->fetchAll(PDO::FETCH_ASSOC);
            if (count($users) > 1) battle_reject(409);
            $user = $users[0] ?? null;
            $stmt = $pdo->prepare('SELECT * FROM battles WHERE battle_id=? FOR UPDATE');
            $stmt->execute([$candidate['battle_id']]);
            $battle = $stmt->fetch(PDO::FETCH_ASSOC);
            $changed = $user && $battle && ($expectedSession === null || (string)$user['session_id'] === $expectedSession)
                && (string)$battle['player_id'] === (string)$user['player_id']
                && battle_timeout_expire_locked($pdo, $user, $battle);
            $pdo->commit();
            if ($changed) $expired++;
        } catch (Throwable $error) {
            if ($pdo->inTransaction()) $pdo->rollBack();
            error_log('Battle timeout preserved ' . (string)$candidate['battle_id'] . ': ' . $error->getMessage());
        }
    }
    return $expired;
}

/** Bounded non-locking preflight keeps idle SSE polls out of user lock queues. */
function battle_timeout_expire_player(PDO $pdo, string $player, int $limit = 8, ?string $expectedSession = null): int {
    $limit = max(1, min(100, $limit));
    $stmt = $pdo->prepare("SELECT battle_id, player_id FROM battles WHERE player_id=? AND state='ACTIVE' AND move_deadline<=UTC_TIMESTAMP(6) ORDER BY move_deadline, battle_id LIMIT $limit");
    $stmt->execute([$player]);
    return battle_timeout_expire_candidates($pdo, $stmt->fetchAll(PDO::FETCH_ASSOC), $expectedSession);
}

/** Disconnected players are handled by this bounded CLI/scheduler sweep. */
function battle_timeout_sweep(PDO $pdo, int $limit = 100, ?array &$cursor = null): int {
    $limit = max(1, min(1000, $limit));
    $after = $cursor === null ? '' : ' AND (move_deadline>? OR (move_deadline=? AND battle_id>?))';
    $stmt = $pdo->prepare("SELECT battle_id, player_id, move_deadline FROM battles WHERE state='ACTIVE' AND move_deadline<=UTC_TIMESTAMP(6)$after ORDER BY move_deadline, battle_id LIMIT $limit");
    $stmt->execute($cursor === null ? [] : [$cursor['deadline'], $cursor['deadline'], $cursor['battle_id']]);
    $candidates = $stmt->fetchAll(PDO::FETCH_ASSOC);
    if (!$candidates) {
        $cursor = null;
        return 0;
    }
    $last = $candidates[count($candidates) - 1];
    $cursor = ['deadline' => (string)$last['move_deadline'], 'battle_id' => (string)$last['battle_id']];
    return battle_timeout_expire_candidates($pdo, $candidates);
}

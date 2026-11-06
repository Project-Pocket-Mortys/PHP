<?php
declare(strict_types=1);
require_once __DIR__ . '/friend_battle_membership.php';

/** Standalone cleanup: candidate identities are hints, never release authority. */
function friend_battle_prepare_expire_candidates(PDO $pdo, array $candidates, ?string $expectedSession = null, ?string $expectedPlayer = null): int {
    if ($pdo->inTransaction()) throw new LogicException('Preparation cleanup requires no transaction');
    $cancelled = 0;
    foreach ($candidates as $candidate) {
        try {
            foreach (['battle_id', 'sender_id', 'recipient_id'] as $key) {
                if (!isset($candidate[$key]) || !is_string($candidate[$key]) || $candidate[$key] === '') friend_fail(409, 'FAILED');
            }
            if ($candidate['sender_id'] === $candidate['recipient_id']) friend_fail(409, 'FAILED');
            $players = [$candidate['sender_id'], $candidate['recipient_id']];
            sort($players, SORT_STRING);
            $pdo->beginTransaction();
            $users = [];
            $query = $pdo->prepare('SELECT player_id,session_id FROM users WHERE player_id=? FOR UPDATE');
            foreach ($players as $player) {
                $query->execute([$player]);
                $rows = $query->fetchAll(PDO::FETCH_ASSOC);
                if (count($rows) !== 1 || $rows[0]['player_id'] !== $player) friend_fail(409, 'FAILED');
                $users[$player] = $rows[0];
            }
            if ($expectedSession !== null && ($expectedPlayer === null || !isset($users[$expectedPlayer])
                || $users[$expectedPlayer]['session_id'] !== $expectedSession
                || friend_auth($pdo, $expectedSession)['player_id'] !== $expectedPlayer)) friend_fail(401, 'FAILED');
            $query = $pdo->prepare('SELECT *,prepare_deadline<=UTC_TIMESTAMP(6) AS deadline_due FROM friend_battle_sessions WHERE battle_id=? FOR UPDATE');
            $query->execute([$candidate['battle_id']]);
            $row = $query->fetch(PDO::FETCH_ASSOC);
            if (!$row || $row['state'] !== 'PREPARING') { $pdo->commit(); continue; }
            if ($row['sender_id'] !== $candidate['sender_id'] || $row['recipient_id'] !== $candidate['recipient_id']) friend_fail(409, 'FAILED');
            if ($row['prepare_deadline'] === null) { $pdo->commit(); continue; }
            $query = $pdo->prepare('SELECT *,expires_at<=UTC_TIMESTAMP(6) AS expired FROM friend_battle_invites WHERE invite_id=? FOR UPDATE');
            $query->execute([$row['invite_id']]);
            $invite = $query->fetch(PDO::FETCH_ASSOC);
            if ($invite && ($invite['sender_id'] !== $row['sender_id'] || $invite['recipient_id'] !== $row['recipient_id']
                || !in_array($invite['state'], ['PENDING', 'DECLINED', 'REVOKED', 'EXPIRED'], true))) friend_fail(409, 'FAILED');
            $query = $pdo->prepare('SELECT pending FROM friend_list WHERE (player_id_a=? AND player_id_b=?) OR (player_id_a=? AND player_id_b=?)');
            $query->execute([$row['sender_id'], $row['recipient_id'], $row['recipient_id'], $row['sender_id']]);
            $friends = $query->fetchAll(PDO::FETCH_ASSOC);
            if (count($friends) > 1 || ($friends && !in_array($friends[0]['pending'], ['true', 'false'], true))) friend_fail(409, 'FAILED');
            $reason = (bool)$row['deadline_due'] ? 'PREPARATION_TIMEOUT'
                : ((!$invite || $invite['state'] !== 'PENDING' || (bool)$invite['expired']) ? 'INVITE_CLOSED'
                : ((!$friends || $friends[0]['pending'] !== 'false') ? 'FRIEND_REMOVED' : null));
            if ($reason !== null) {
                friend_battle_release_preparation_locked($pdo, $row, $reason);
            }
            $pdo->commit();
            if ($reason !== null) $cancelled++;
        } catch (Throwable $error) {
            if ($pdo->inTransaction()) $pdo->rollBack();
            error_log('Preparation cleanup preserved candidate: ' . get_class($error));
        }
    }
    return $cancelled;
}

/** A fair bounded scan includes future leases so closed invites are found too. */
function friend_battle_prepare_sweep(PDO $pdo, int $limit = 100, ?string &$cursor = null): int {
    if ($pdo->inTransaction()) throw new LogicException('Preparation sweep requires no transaction');
    $limit = max(1, min(1000, $limit));
    $query = $pdo->prepare("SELECT battle_id,sender_id,recipient_id FROM friend_battle_sessions WHERE state='PREPARING' AND prepare_deadline IS NOT NULL" . ($cursor === null ? '' : ' AND battle_id>?') . " ORDER BY battle_id LIMIT $limit");
    $query->execute($cursor === null ? [] : [$cursor]);
    $rows = $query->fetchAll(PDO::FETCH_ASSOC);
    if (!$rows) { $cursor = null; return 0; }
    $cursor = $rows[count($rows)-1]['battle_id'];
    return friend_battle_prepare_expire_candidates($pdo, $rows);
}

/** Called outside stream/world transactions, with the stream's exact session. */
function friend_battle_prepare_expire_player(PDO $pdo, string $player, int $limit = 8, ?string $session = null): int {
    if ($pdo->inTransaction()) throw new LogicException('Preparation player cleanup requires no transaction');
    $limit = max(1, min(100, $limit));
    $query = $pdo->prepare("SELECT battle_id,sender_id,recipient_id FROM friend_battle_sessions WHERE state='PREPARING' AND prepare_deadline IS NOT NULL AND (sender_id=? OR recipient_id=?) ORDER BY prepare_deadline,battle_id LIMIT $limit");
    $query->execute([$player, $player]);
    return friend_battle_prepare_expire_candidates($pdo, $query->fetchAll(PDO::FETCH_ASSOC), $session, $session === null ? null : $player);
}

<?php
declare(strict_types=1);
require_once __DIR__ . '/friend_battle_invites.php';

/** User locks serialize all claim writers; avoid empty-range/gap locks. */
function friend_battle_require_claims(PDO $pdo, array $session): void {
    $query = $pdo->prepare('SELECT player_id,battle_id FROM friend_battle_memberships WHERE battle_id=? ORDER BY player_id');
    $query->execute([$session['battle_id']]);
    $rows = $query->fetchAll(PDO::FETCH_ASSOC);
    if (count($rows) !== 2) friend_fail(409, 'FAILED');
    $ids = [];
    foreach ($rows as $row) {
        if ($row['battle_id'] !== $session['battle_id']) friend_fail(409, 'FAILED');
        $ids[] = $row['player_id'];
    }
    sort($ids, SORT_STRING);
    $expected = [$session['sender_id'], $session['recipient_id']];
    sort($expected, SORT_STRING);
    if ($ids !== $expected) friend_fail(409, 'FAILED');
}

function friend_battle_membership_error(PDO $pdo, Throwable $error): never {
    if ($pdo->inTransaction()) $pdo->rollBack();
    if ($error instanceof FriendError) {
        friend_fail($error->status, $error->getMessage() === 'NOT_AUTHENTICATED' ? 'FAILED' : $error->getMessage());
    }
    error_log('Shared battle preparation failed: ' . get_class($error));
    friend_fail(500, 'FAILED');
}

/** Internal only: public accept stays 501 until startup/ready/reconnect exist. */
function friend_battle_reserve(PDO $pdo, string $sessionId, string $recipientToken): string {
    if ($pdo->inTransaction()) throw new LogicException('Standalone reservation requires no transaction');
    try {
        $actor = friend_auth($pdo, $sessionId);
        $query = $pdo->prepare('SELECT * FROM friend_battle_invites WHERE recipient_token=?');
        $query->execute([$recipientToken]);
        $hints = $query->fetchAll(PDO::FETCH_ASSOC);
        if (count($hints) !== 1 || $hints[0]['recipient_id'] !== $actor['player_id']
            || !hash_equals($hints[0]['recipient_token'], $recipientToken)) friend_fail(403, 'TOKEN_NOTVALID');
        $hint = $hints[0];
        [$recipient, $sender, $friend] = friend_lock_pair($pdo, $sessionId, $hint['sender_id']);
        if (!$friend || $friend['pending'] !== 'false' || $recipient['state'] !== 'WORLD' || $sender['state'] !== 'WORLD') friend_fail(409, 'FAILED');
        $query = $pdo->prepare('SELECT *,TIMESTAMPDIFF(MICROSECOND,UTC_TIMESTAMP(6),expires_at)/1000000 AS ttl FROM friend_battle_invites WHERE invite_id=? FOR UPDATE');
        $query->execute([$hint['invite_id']]);
        $invite = $query->fetch(PDO::FETCH_ASSOC);
        if (!$invite || $invite['sender_id'] !== $sender['player_id'] || $invite['recipient_id'] !== $recipient['player_id']
            || !hash_equals($invite['recipient_token'], $recipientToken)) friend_fail(403, 'TOKEN_NOTVALID');
        if ($invite['state'] !== 'PENDING' || (float)$invite['ttl'] <= 0) friend_fail(409, 'FAILED');
        $query = $pdo->prepare("SELECT 1 FROM battles WHERE state='ACTIVE' AND (player_id IN (?,?) OR opponent_id IN (?,?)) LIMIT 1");
        $query->execute([$sender['player_id'], $recipient['player_id'], $sender['player_id'], $recipient['player_id']]);
        if ($query->fetchColumn() !== false) friend_fail(409, 'FAILED');
        $query = $pdo->prepare('SELECT * FROM friend_battle_sessions WHERE invite_id=?');
        $query->execute([$invite['invite_id']]);
        $existing = $query->fetch(PDO::FETCH_ASSOC);
        if ($existing) {
            if ($existing['state'] !== 'PREPARING' || $existing['sender_id'] !== $sender['player_id']
                || $existing['recipient_id'] !== $recipient['player_id']) friend_fail(409, 'FAILED');
            friend_battle_require_claims($pdo, $existing);
            $pdo->commit();
            return $existing['battle_id'];
        }
        if (friend_battle_invite_busy($pdo, $sender['player_id'])
            || friend_battle_invite_busy($pdo, $recipient['player_id'])) friend_fail(409, 'FAILED');
        $battle = friend_battle_invite_id();
        $query = $pdo->prepare("INSERT INTO friend_battle_sessions (battle_id,invite_id,sender_id,recipient_id,state,created_at,updated_at) VALUES (?,?,?,?,'PREPARING',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))");
        $query->execute([$battle, $invite['invite_id'], $sender['player_id'], $recipient['player_id']]);
        $query = $pdo->prepare('INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES (?,?)');
        $players = [$sender['player_id'], $recipient['player_id']];
        sort($players, SORT_STRING);
        foreach ($players as $player) $query->execute([$player, $battle]);
        $pdo->commit();
        return $battle;
    } catch (Throwable $error) {
        friend_battle_membership_error($pdo, $error);
    }
}

/** Internal preparation cancellation; never restores or changes gameplay rows. */
function friend_battle_cancel_reservation(PDO $pdo, string $sessionId, string $battleId): void {
    if ($pdo->inTransaction()) throw new LogicException('Standalone cancellation requires no transaction');
    try {
        $actor = friend_auth($pdo, $sessionId);
        $query = $pdo->prepare('SELECT * FROM friend_battle_sessions WHERE battle_id=?');
        $query->execute([$battleId]);
        $hint = $query->fetch(PDO::FETCH_ASSOC);
        if (!$hint || !in_array($actor['player_id'], [$hint['sender_id'], $hint['recipient_id']], true)) friend_fail(403, 'TOKEN_NOTVALID');
        $other = $hint[$actor['player_id'] === $hint['sender_id'] ? 'recipient_id' : 'sender_id'];
        [$lockedActor] = friend_lock_pair($pdo, $sessionId, $other);
        if ($lockedActor['player_id'] !== $actor['player_id']) friend_fail(401, 'FAILED');
        $query = $pdo->prepare('SELECT * FROM friend_battle_sessions WHERE battle_id=? FOR UPDATE');
        $query->execute([$battleId]);
        $row = $query->fetch(PDO::FETCH_ASSOC);
        if (!$row || $row['sender_id'] !== $hint['sender_id'] || $row['recipient_id'] !== $hint['recipient_id']) friend_fail(409, 'FAILED');
        if ($row['state'] === 'CANCELLED') { $pdo->commit(); return; }
        if ($row['state'] !== 'PREPARING') friend_fail(409, 'FAILED');
        friend_battle_require_claims($pdo, $row);
        $query = $pdo->prepare('DELETE FROM friend_battle_memberships WHERE player_id=? AND battle_id=?');
        foreach ([$row['sender_id'], $row['recipient_id']] as $player) {
            $query->execute([$player, $battleId]);
            if ($query->rowCount() !== 1) friend_fail(409, 'FAILED');
        }
        $pdo->prepare("UPDATE friend_battle_sessions SET state='CANCELLED',updated_at=UTC_TIMESTAMP(6) WHERE battle_id=?")->execute([$battleId]);
        $pdo->commit();
    } catch (Throwable $error) {
        friend_battle_membership_error($pdo, $error);
    }
}

<?php
declare(strict_types=1);
require_once __DIR__ . '/friends.php';

/** Policies here implement invitation state only, never human combat. */
function friend_battle_invite_ttl(): int {
    $configured = getenv('PM_FRIEND_INVITE_TTL_SECONDS');
    if ($configured === false || $configured === '') return 60;
    $ttl = filter_var($configured, FILTER_VALIDATE_INT, ['options' => ['min_range' => 10, 'max_range' => 300]]);
    if ($ttl === false) throw new RuntimeException('Invalid invitation lifetime');
    return $ttl;
}

function friend_battle_invite_busy(PDO $pdo, string $player): bool {
    $query = $pdo->prepare("SELECT battle_id FROM battles WHERE state='ACTIVE' AND (player_id=? OR opponent_id=?) LIMIT 1");
    $query->execute([$player, $player]);
    return $query->fetchColumn() !== false;
}

function friend_battle_invite_id(): string {
    $bytes = random_bytes(16);
    $bytes[6] = chr((ord($bytes[6]) & 15) | 64);
    $bytes[8] = chr((ord($bytes[8]) & 63) | 128);
    $hex = bin2hex($bytes);
    return substr($hex, 0, 8).'-'.substr($hex, 8, 4).'-'.substr($hex, 12, 4).'-'.substr($hex, 16, 4).'-'.substr($hex, 20);
}

function friend_battle_invite_result(array $row): array {
    return [200, ['battle_invite_id' => $row['invite_id'], 'battle_type' => 'PvF',
        'battle_invite_ttl' => (float)$row['ttl'], 'token' => $row['sender_token']]];
}

function friend_battle_invite_create(PDO $pdo, array $data, string $session): array {
    $target = friend_string($data, 'opponent_player_id', 'OPPONENT_PLAYER_ID_INVALID');
    if (($data['battle_type'] ?? null) !== 'PvF') friend_fail(400, 'FAILED');
    [$actor, $other, $friend] = friend_lock_pair($pdo, $session, $target);
    if (!$friend || $friend['pending'] !== 'false') friend_fail(400, 'OPPONENT_PLAYER_ID_INVALID');
    if ($actor['state'] !== 'WORLD' || friend_battle_invite_busy($pdo, $actor['player_id'])) friend_fail(409, 'FAILED');
    if ($other['state'] !== 'WORLD' || friend_battle_invite_busy($pdo, $other['player_id'])) friend_fail(409, 'OPPONENT_STATE_INVALID');
    // Every writer owns the sender user lock. Read without range/gap locks,
    // then mutate exact IDs so unrelated senders can create simultaneously.
    $query = $pdo->prepare("SELECT *,TIMESTAMPDIFF(MICROSECOND,UTC_TIMESTAMP(6),expires_at)/1000000 AS ttl FROM friend_battle_invites WHERE sender_id=? AND state='PENDING' ORDER BY invite_id");
    $query->execute([$actor['player_id']]);
    $pending = [];
    foreach ($query->fetchAll(PDO::FETCH_ASSOC) as $row) {
        if ((float)$row['ttl'] <= 0) {
            $pdo->prepare("UPDATE friend_battle_invites SET state='EXPIRED',updated_at=UTC_TIMESTAMP(6) WHERE invite_id=?")->execute([$row['invite_id']]);
        } else {
            $pending[] = $row;
        }
    }
    if (count($pending) > 1) friend_fail(409, 'FAILED');
    if ($pending) {
        if ($pending[0]['recipient_id'] !== $target) friend_fail(409, 'SENT_INVITE_PENDING');
        return friend_battle_invite_result($pending[0]);
    }
    $id = friend_battle_invite_id();
    $ttl = friend_battle_invite_ttl();
    $query = $pdo->prepare("INSERT INTO friend_battle_invites (invite_id,sender_id,recipient_id,sender_token,recipient_token,state,created_at,expires_at,updated_at) VALUES (?,?,?,?,?,'PENDING',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6)+INTERVAL ? SECOND,UTC_TIMESTAMP(6))");
    $senderToken = bin2hex(random_bytes(32));
    $query->execute([$id, $actor['player_id'], $target, $senderToken, bin2hex(random_bytes(32)), $ttl]);
    return friend_battle_invite_result(['invite_id' => $id, 'ttl' => $ttl, 'sender_token' => $senderToken]);
}

function friend_battle_invite_reply(PDO $pdo, array $data, string $session, string $action): array {
    $token = friend_string($data, 'token', 'TOKEN_INVALID');
    if ($action === 'response' && !is_bool($data['accept'] ?? null)) friend_fail(400, 'ACCEPT_INVALID');
    $actor = friend_auth($pdo, $session);
    $query = $pdo->prepare('SELECT * FROM friend_battle_invites WHERE sender_token=? OR recipient_token=?');
    $query->execute([$token, $token]);
    $matches = $query->fetchAll(PDO::FETCH_ASSOC);
    if (count($matches) !== 1) friend_fail(400, 'TOKEN_INVALID');
    $hint = $matches[0];
    $role = $action === 'revoke' ? 'sender' : 'recipient';
    if ($hint[$role.'_id'] !== $actor['player_id'] || !hash_equals($hint[$role.'_token'], $token)) friend_fail(403, 'TOKEN_NOTVALID');
    $target = $hint[$role === 'sender' ? 'recipient_id' : 'sender_id'];
    [$lockedActor] = friend_lock_pair($pdo, $session, $target);
    if ($lockedActor['player_id'] !== $actor['player_id']) friend_fail(401, 'FAILED');
    $query = $pdo->prepare('SELECT *,TIMESTAMPDIFF(MICROSECOND,UTC_TIMESTAMP(6),expires_at)/1000000 AS ttl FROM friend_battle_invites WHERE invite_id=? FOR UPDATE');
    $query->execute([$hint['invite_id']]);
    $row = $query->fetch(PDO::FETCH_ASSOC);
    if (!$row || $row[$role.'_id'] !== $actor['player_id'] || !hash_equals($row[$role.'_token'], $token)) friend_fail(403, 'TOKEN_NOTVALID');
    if ($row['state'] === 'EXPIRED' || ($row['state'] === 'PENDING' && (float)$row['ttl'] <= 0)) {
        $pdo->prepare("UPDATE friend_battle_invites SET state='EXPIRED',updated_at=UTC_TIMESTAMP(6) WHERE invite_id=? AND state='PENDING'")->execute([$row['invite_id']]);
        return [410, ['error' => ['code' => 'TOKEN_EXPIRED']]];
    }
    if ($action === 'response' && $data['accept']) {
        if ($row['state'] !== 'PENDING') friend_fail(409, 'TOKEN_NOTVALID');
        return [501, ['error' => ['code' => 'FAILED']]];
    }
    $terminal = $action === 'revoke' ? 'REVOKED' : 'DECLINED';
    if (!in_array($row['state'], ['PENDING', $terminal], true)) friend_fail(409, 'TOKEN_NOTVALID');
    $pdo->prepare('UPDATE friend_battle_invites SET state=?,updated_at=UTC_TIMESTAMP(6) WHERE invite_id=? AND state=\'PENDING\'')->execute([$terminal, $row['invite_id']]);
    return [200, ['success' => true]];
}

/** Called while Friend Remove holds both users' locks and its transaction. */
function friend_battle_invite_remove_pair(PDO $pdo, string $a, string $b): void {
    $query = $pdo->prepare("SELECT invite_id FROM friend_battle_invites WHERE state='PENDING' AND ((sender_id=? AND recipient_id=?) OR (sender_id=? AND recipient_id=?))");
    $query->execute([$a, $b, $b, $a]);
    $rows = $query->fetchAll(PDO::FETCH_ASSOC);
    $update = $pdo->prepare("UPDATE friend_battle_invites SET state=IF(expires_at<=UTC_TIMESTAMP(6),'EXPIRED','REVOKED'),updated_at=UTC_TIMESTAMP(6) WHERE invite_id=? AND state='PENDING'");
    foreach ($rows as $row) $update->execute([$row['invite_id']]);
}

function friend_battle_invite_endpoint(PDO $pdo, string $action): void {
    try {
        if (($_SERVER['REQUEST_METHOD'] ?? '') !== 'POST') friend_fail(405, 'FAILED');
        $data = friend_input();
        $session = friend_string($data, 'session_id', $action === 'create' ? 'SESSION_ID_INVALID' : 'FAILED');
        [$status, $body] = $action === 'create' ? friend_battle_invite_create($pdo, $data, $session)
            : friend_battle_invite_reply($pdo, $data, $session, $action);
        if ($pdo->inTransaction()) $pdo->commit();
        http_response_code($status);
        echo json_encode($body, JSON_THROW_ON_ERROR | JSON_UNESCAPED_SLASHES);
    } catch (Throwable $error) {
        if ($pdo->inTransaction()) $pdo->rollBack();
        $code = $error instanceof FriendError ? $error->getMessage() : 'FAILED';
        if ($code === 'NOT_AUTHENTICATED') $code = $action === 'create' ? 'SESSION_ID_INVALID' : 'FAILED';
        if ($code === 'PLAYER_ID_INVALID') $code = $action === 'create' ? 'OPPONENT_PLAYER_ID_INVALID' : 'TOKEN_NOTVALID';
        if (!$error instanceof FriendError) error_log('Battle invitation failed: ' . get_class($error));
        http_response_code($error instanceof FriendError ? $error->status : 500);
        echo json_encode(['error' => ['code' => $code]]);
    }
}

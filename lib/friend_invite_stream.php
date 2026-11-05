<?php
declare(strict_types=1);

require_once __DIR__ . '/friends.php';

/** Read-only eligibility: do not reconcile battles or mutate invitation state. */
function friend_invite_stream_pair(PDO $pdo, string $sender, string $recipient): ?array {
    $q = $pdo->prepare('SELECT player_id, username, player_avatar_id, level, state FROM users WHERE player_id IN (?, ?)');
    $q->execute([$sender, $recipient]);
    $users = $q->fetchAll(PDO::FETCH_ASSOC);
    if (count($users) !== 2 || $sender === $recipient) return null;
    $from = null;
    foreach ($users as $user) {
        if ($user['state'] !== 'WORLD') return null;
        if ($user['player_id'] === $sender) $from = $user;
    }
    if ($from === null) return null;
    $q = $pdo->prepare('SELECT pending FROM friend_list WHERE (player_id_a=? AND player_id_b=?) OR (player_id_a=? AND player_id_b=?)');
    $q->execute([$sender, $recipient, $recipient, $sender]);
    $friends = $q->fetchAll(PDO::FETCH_ASSOC);
    if (count($friends) !== 1 || $friends[0]['pending'] !== 'false') return null;
    $q = $pdo->prepare("SELECT 1 FROM battles WHERE (player_id IN (?, ?) OR opponent_id IN (?, ?)) AND state='ACTIVE' LIMIT 1");
    $q->execute([$sender, $recipient, $sender, $recipient]);
    if ($q->fetchColumn() !== false) return null;
    return ['player_id' => (string)$from['player_id'], 'username' => (string)$from['username'],
        'player_avatar_id' => (string)$from['player_avatar_id'], 'level' => (int)$from['level']];
}

/**
 * Global per-connection invitation delivery, independent of room cursors.
 * Native create has no HTTP acknowledgement barrier: repeat terminal ID-only
 * events at most once a second through the retention window. Native handlers
 * safely ignore repeated IDs once removed, including an early decline received
 * before the create callback installs the sent ID. Received events append in the
 * client, so deliver those exactly once per connection; reconnect rehydrates.
 * Errors deliberately propagate to the SSE boundary, which logs and closes.
 */
function friend_battle_invite_events(PDO $pdo, string $player, string $session, array &$seen): array {
    if ($session === '' || (string)friend_auth($pdo, $session)['player_id'] !== $player) {
        friend_fail(401, 'NOT_AUTHENTICATED');
    }
    $q = $pdo->prepare("SELECT invite_id, sender_id, recipient_id, recipient_token, state,
        TIMESTAMPDIFF(MICROSECOND, UTC_TIMESTAMP(6), expires_at) / 1000000.0 AS ttl,
        TIMESTAMPDIFF(MICROSECOND, UTC_TIMESTAMP(6), DATE_ADD(GREATEST(expires_at, updated_at), INTERVAL 5 SECOND)) / 1000000.0 AS retained
        FROM friend_battle_invites WHERE (sender_id=? OR recipient_id=?)
        AND (expires_at >= DATE_SUB(UTC_TIMESTAMP(6), INTERVAL 5 SECOND)
             OR updated_at >= DATE_SUB(UTC_TIMESTAMP(6), INTERVAL 5 SECOND))
        ORDER BY created_at, invite_id");
    $q->execute([$player, $player]);
    $events = [];
    $now = microtime(true);
    foreach ($seen as $id => $delivery) {
        if ($delivery['until'] < $now) unset($seen[$id]);
    }
    foreach ($q->fetchAll(PDO::FETCH_ASSOC) as $invite) {
        $id = (string)$invite['invite_id'];
        $ttl = (float)$invite['ttl'];
        $retained = (float)$invite['retained'];
        $from = null;
        $pending = $invite['state'] === 'PENDING' && $ttl > 0;
        if ($pending) {
            $from = friend_invite_stream_pair($pdo, (string)$invite['sender_id'], (string)$invite['recipient_id']);
            // A read-only availability observation cannot durably terminate an
            // invitation. Suppress new delivery until eligibility returns; pair
            // mutations persist revocation and expiry is authoritative by time.
            if ($from === null) continue;
        }
        if ($pending) {
            if ($invite['recipient_id'] !== $player || isset($seen[$id]['received'])) continue;
            $events[] = ['event' => 'battle-invite:received', 'payload' => [
                'battle_invite_id' => $id, 'battle_type' => 'PvF', 'battle_invite_ttl' => $ttl,
                'from_player' => $from, 'token' => (string)$invite['recipient_token'],
            ]];
            $seen[$id] = ['received' => true, 'until' => $now + max(0.0, $retained)];
            continue;
        }
        if (!in_array($invite['state'], ['PENDING', 'DECLINED', 'REVOKED', 'EXPIRED'], true)) continue;
        if ($retained < 0 || (isset($seen[$id]['terminal']) && $now - $seen[$id]['terminal'] < 1.0)) continue;
        $events[] = ['event' => $invite['recipient_id'] === $player ? 'battle-invite:revoked' : 'battle-invite:declined',
            'payload' => ['battle_invite_id' => $id]];
        $seen[$id]['terminal'] = $now;
        $seen[$id]['until'] = $now + $retained;
    }
    // Do not emit a batch after a session was revoked or became ambiguous while
    // reading invitations. This also checks the supplied player's identity.
    if ((string)friend_auth($pdo, $session)['player_id'] !== $player) friend_fail(401, 'NOT_AUTHENTICATED');
    return $events;
}

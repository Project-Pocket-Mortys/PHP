<?php
declare(strict_types=1);
require_once __DIR__ . '/friends.php';

/** Native handlers invalidate both trade data and owned inventory. */
function trade_refresh_event(string $event): bool {
    return in_array($event, ['trade:request-submit', 'trade:offer-submit',
        'trade:offer-accepted', 'trade:offer-rejected'], true);
}

/**
 * Replacement delivery policy: one latest invalidation per account. The row
 * lock serializes revisions through commit, independently of room cursors.
 * Call last inside the mutation transaction; no recipient user locks are added.
 */
function trade_refresh_publish(PDO $pdo, array $recipients, string $event): void {
    if (!$pdo->inTransaction() || !trade_refresh_event($event)) {
        throw new LogicException('Transactional native trade invalidation required');
    }
    foreach ($recipients as $recipient) {
        if (!is_string($recipient) || trim($recipient) === '' || strlen($recipient) > 255) {
            throw new LogicException('Invalid trade refresh recipient');
        }
    }
    $recipients = array_values(array_unique($recipients, SORT_STRING));
    sort($recipients, SORT_STRING);
    $query = $pdo->prepare('INSERT INTO trade_refresh_notifications (player_id,revision,event_name)
        VALUES (?,1,?) ON DUPLICATE KEY UPDATE revision=revision+1,event_name=VALUES(event_name)');
    foreach ($recipients as $recipient) $query->execute([$recipient, $event]);
}

/**
 * No persistent acknowledgement: each connection replays the latest revision.
 * Coalescing is safe for these four refresh-only handlers, not arbitrary events.
 * Authentication is checked around the read, including exact logical identity.
 */
function trade_refresh_poll(PDO $pdo, string $player, string $session, ?string $seen): ?array {
    if ($pdo->inTransaction()) throw new LogicException('Trade refresh poll must see committed state');
    if ($session === '' || (string)friend_auth($pdo, $session)['player_id'] !== $player) {
        friend_fail(401, 'NOT_AUTHENTICATED');
    }
    $query = $pdo->prepare('SELECT CAST(revision AS CHAR) AS revision,event_name
        FROM trade_refresh_notifications WHERE player_id=?');
    $query->execute([$player]);
    $row = $query->fetch(PDO::FETCH_ASSOC);
    if ((string)friend_auth($pdo, $session)['player_id'] !== $player) friend_fail(401, 'NOT_AUTHENTICATED');
    if (!$row || $row['revision'] === $seen) return null;
    if (!ctype_digit($row['revision']) || $row['revision'] === '0' || !trade_refresh_event($row['event_name'])) {
        throw new LogicException('Invalid stored trade refresh');
    }
    return ['revision' => $row['revision'], 'event' => $row['event_name'], 'payload' => new stdClass()];
}

<?php
declare(strict_types=1);

require_once __DIR__ . '/friends.php';
require_once __DIR__ . '/battle_membership_guard.php';

/** Serialize resource/profile writes with reservation creation and cancellation. */
function preparation_writer_lock(PDO $pdo, string $session): array {
    $actor = friend_auth($pdo, $session);
    $pdo->beginTransaction();
    // Lock only the authenticated primary-key row on the legacy users table.
    $query = $pdo->prepare('SELECT * FROM users FORCE INDEX (PRIMARY) WHERE id = ? AND player_id = ? FOR UPDATE');
    $query->execute([$actor['id'], $actor['player_id']]);
    $user = $query->fetch(PDO::FETCH_ASSOC);
    // Reauthenticate after waiting, before establishing any resource snapshot.
    if (!$user || $user['session_id'] !== $session ||
        friend_auth($pdo, $session)['id'] !== $user['id']) {
        friend_fail(401, 'NOT_AUTHENTICATED');
    }
    if (battle_has_shared_membership($pdo, (string)$user['player_id'])) friend_fail(409, 'FAILED');
    return $user;
}

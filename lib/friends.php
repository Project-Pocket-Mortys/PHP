<?php
declare(strict_types=1);

/** Friend rows use A = requester, B = recipient. Never infer a legacy direction. */
final class FriendError extends RuntimeException {
    public int $status;
    public function __construct(int $status, string $code) {
        parent::__construct($code);
        $this->status = $status;
    }
}

function friend_fail(int $status, string $code): void {
    throw new FriendError($status, $code);
}

function friend_input(): array {
    $data = json_decode(file_get_contents('php://input'), true);
    if (!is_array($data)) friend_fail(400, 'FAILED');
    return $data;
}

function friend_string(array $data, string $field, string $code): string {
    $value = $data[$field] ?? null;
    if (!is_string($value) || $value === '' || trim($value) !== $value) {
        friend_fail($field === 'session_id' ? 401 : 400, $code);
    }
    return $value;
}

function friend_auth(PDO $pdo, string $session): array {
    $stmt = $pdo->prepare('SELECT * FROM users WHERE session_id = ?');
    $stmt->execute([$session]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    if (count($rows) !== 1 || $rows[0]['session_id'] !== $session || !is_string($rows[0]['player_id']) || $rows[0]['player_id'] === '') {
        friend_fail(401, 'NOT_AUTHENTICATED');
    }
    $stmt = $pdo->prepare('SELECT id FROM users WHERE player_id = ?');
    $stmt->execute([$rows[0]['player_id']]);
    if (count($stmt->fetchAll()) !== 1) friend_fail(401, 'NOT_AUTHENTICATED');
    return $rows[0];
}

/** All pair writers take the same user locks before inspecting or changing rows. */
function friend_lock_pair(PDO $pdo, string $session, string $target): array {
    $actor = friend_auth($pdo, $session);
    if ($actor['player_id'] === $target) friend_fail(400, 'PLAYER_ID_INVALID');
    $ids = [$actor['player_id'], $target];
    sort($ids, SORT_STRING);
    $pdo->beginTransaction();
    $users = [];
    foreach ($ids as $id) {
        $stmt = $pdo->prepare('SELECT * FROM users WHERE player_id = ? FOR UPDATE');
        $stmt->execute([$id]);
        $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
        if (count($rows) !== 1 || $rows[0]['player_id'] !== $id) friend_fail(400, 'PLAYER_ID_INVALID');
        $users[$id] = $rows[0];
    }
    // A revoked or reassigned session must not survive waiting for the pair locks.
    if ($users[$actor['player_id']]['session_id'] !== $session ||
        friend_auth($pdo, $session)['player_id'] !== $actor['player_id']) {
        friend_fail(401, 'NOT_AUTHENTICATED');
    }
    // The ordered user locks serialize all friend writers. A locking scan here
    // would unnecessarily lock unrelated pairs on the legacy unindexed table.
    $stmt = $pdo->prepare('SELECT * FROM friend_list WHERE (player_id_a = ? AND player_id_b = ?) OR (player_id_a = ? AND player_id_b = ?)');
    $stmt->execute([$actor['player_id'], $target, $target, $actor['player_id']]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    if (count($rows) > 1) friend_fail(409, 'FAILED');
    if ($rows && !in_array($rows[0]['pending'], ['true', 'false'], true)) friend_fail(409, 'FAILED');
    return [$users[$actor['player_id']], $users[$target], $rows[0] ?? null];
}

function friend_error_response(PDO $pdo, Throwable $error): void {
    if ($pdo->inTransaction()) $pdo->rollBack();
    http_response_code($error instanceof FriendError ? $error->status : 500);
    $code = $error instanceof FriendError ? $error->getMessage() : 'FAILED';
    // Every friend enum has FAILED; none has NOT_AUTHENTICATED.
    if ($code === 'NOT_AUTHENTICATED') $code = 'FAILED';
    if (!$error instanceof FriendError) error_log('Friend operation failed: ' . get_class($error));
    echo json_encode(['error' => ['code' => $code]]);
}

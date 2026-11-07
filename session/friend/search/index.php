<?php
declare(strict_types=1);
header('Content-Type: application/json; charset=utf-8');
header('X-Powered-By: Express');
header('Access-Control-Allow-Origin: *');
header('Vary: Accept-Encoding');
header('Cache-Control: no-store');
require __DIR__ . '/../../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../../lib/friends.php';
try {
    $data = friend_input();
    $session = friend_string($data, 'session_id', 'NOT_AUTHENTICATED');
    $query = friend_string($data, 'query', 'QUERY_INVALID');
    friend_auth($pdo, $session);
    $stmt = $pdo->prepare('SELECT player_id, username, player_avatar_id, level FROM users WHERE username = ?');
    $stmt->execute([$query]);
    $rows = $stmt->fetchAll(PDO::FETCH_ASSOC);
    if (count($rows) === 1) {
        $row = $rows[0];
        $row['level'] = (int)$row['level'];
        $response = json_encode($row, JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
        header('ETag: W/"' . md5($response) . '"');
        echo $response;
    }
} catch (Throwable $error) {
    friend_error_response($pdo, $error);
}

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
    // One response must not mix pending and accepted versions of a relation.
    $pdo->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
    $pdo->beginTransaction();
    $actor = friend_auth($pdo, $session);
    $player = $actor['player_id'];
    $requests = [];
    foreach (['sent' => ['player_id_a', 'player_id_b'], 'received' => ['player_id_b', 'player_id_a']] as $kind => [$mine, $theirs]) {
        $stmt = $pdo->prepare("SELECT p.username, p.player_avatar_id, p.level, p.player_id, r.created AS _created
            FROM friend_list r JOIN users p ON p.player_id = r.$theirs
            WHERE r.$mine = ? AND r.pending = 'true' ORDER BY r.created DESC, p.player_id ASC");
        $stmt->execute([$player]);
        $requests[$kind] = $stmt->fetchAll(PDO::FETCH_ASSOC);
        foreach ($requests[$kind] as &$request) $request['level'] = (int)$request['level'];
        unset($request);
    }
    $stmt = $pdo->prepare("SELECT p.username, p.player_avatar_id, p.level, p.player_id,
        COALESCE(p.wins, 0) AS wins, COALESCE(p.losses, 0) AS losses,
        CASE WHEN p.last_seen IS NOT NULL AND p.last_seen >= (NOW() - INTERVAL 5 MINUTE)
            THEN 'true' ELSE 'false' END AS online, p.donation_request
        FROM friend_list r JOIN users p ON p.player_id =
            CASE WHEN r.player_id_a = ? THEN r.player_id_b ELSE r.player_id_a END
        WHERE (r.player_id_a = ? OR r.player_id_b = ?) AND r.pending = 'false'
        ORDER BY p.username ASC, p.player_id ASC");
    $stmt->execute([$player, $player, $player]);
    $friends = $stmt->fetchAll(PDO::FETCH_ASSOC);
    foreach ($friends as &$friend) {
        foreach (['level', 'wins', 'losses'] as $field) $friend[$field] = (int)$friend[$field];
    }
    unset($friend);
    $response = json_encode([
        'requests_sent' => $requests['sent'], 'requests_received' => $requests['received'],
        'friends' => $friends, 'poll_period' => 5,
        'donation_request' => ['morty_id' => null, 'next_countdown' => 0, 'donation' => null],
        'limit_friends' => 30
    ], JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
    $pdo->commit();
    echo $response;
} catch (Throwable $error) {
    friend_error_response($pdo, $error);
}

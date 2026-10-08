<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require '../../../pocket_f4894h398r8h9w9er8he98he.php';

$input = file_get_contents('php://input');
$data = json_decode($input, true);

$session_id = $data['session_id'];
$query = $data['query'];

if (empty($session_id)) {
    die("Not authenticated");
}

$stmt = $pdo->prepare("SELECT * FROM users WHERE session_id = ?");
$stmt->execute([$session_id]);
$user = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$user) {
    die("Not authenticated");
}

$stmt = $pdo->prepare("SELECT * FROM users WHERE username = ?");
$stmt->execute([$query]);
$search_user = $stmt->fetch(PDO::FETCH_ASSOC);

if ($search_user) {
$search_user_player_avatar_id = $search_user['player_avatar_id']; 

$response = json_encode([
    "player_id" => $search_user['player_id'],
    "username" => $search_user['username'],
    "player_avatar_id" => $search_user_player_avatar_id,
    "level" => (int)$search_user['level']
], JSON_UNESCAPED_SLASHES);

$etag = 'W/"' . md5($response) . '"';
header("ETag: $etag");

echo $response;
}
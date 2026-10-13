<?php
error_reporting(E_ALL);
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require '../../../pocket_f4894h398r8h9w9er8he98he.php';

function pm_error(int $status, string $code) {
    http_response_code($status);
    echo json_encode([
        "error" => [
            "code" => $code
        ]
    ], JSON_UNESCAPED_SLASHES);
    exit;
}

$input = file_get_contents('php://input');
$data  = json_decode($input, true);

$session_id = $data['session_id'] ?? null;
$target_player_id = $data['player_id'] ?? null; // the player we are trying to friend

if (!$session_id) {
    pm_error(401, "NOT_AUTHENTICATED");
}
if (!$target_player_id) {
    pm_error(400, "MISSING_PLAYER_ID");
}

/** 1) Find the sender by session_id */
$stmt = $pdo->prepare("SELECT player_id, wins FROM users WHERE session_id = ? LIMIT 1");
$stmt->execute([$session_id]);
$sender = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$sender) {
    pm_error(401, "NOT_AUTHENTICATED");
}

$sender_player_id = $sender['player_id'];
$wins_sender = (int)$sender['wins'];

/** 2) Block self friend request */
if ($sender_player_id === $target_player_id) {
    pm_error(400, "FRIEND_SELF");
}

/** 3) Make sure target exists */
$stmt = $pdo->prepare("SELECT player_id, wins FROM users WHERE player_id = ? LIMIT 1");
$stmt->execute([$target_player_id]);
$target = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$target) {
    pm_error(404, "PLAYER_NOT_FOUND");
}

$wins_target = (int)$target['wins'];

/** UTC timestamp */
$date = (new DateTime('now', new DateTimeZone('UTC')))->format('Y-m-d\TH:i:s.v') . 'Z';

/**
 * 4) Prevent duplicates BOTH directions:
 * - sender -> target
 * - target -> sender
 *
 * If any row exists, it means either:
 * - already friends, or
 * - pending request exists either direction
 */
$stmt = $pdo->prepare("
    SELECT 1
    FROM friend_list
    WHERE (player_id_a = ? AND player_id_b = ?)
       OR (player_id_a = ? AND player_id_b = ?)
    LIMIT 1
");
$stmt->execute([$sender_player_id, $target_player_id, $target_player_id, $sender_player_id]);
$exists = $stmt->fetchColumn();

if ($exists) {
    pm_error(400, "FRIEND_DUPLICATE");
}

/**
 * 5) Insert a pending request.
 * IMPORTANT: Decide what "direction" means in your schema.
 * Your original code inserted:
 *   player_id_a = target
 *   player_id_b = sender
 * which is backwards for most systems.
 *
 * I’m going to make it logical:
 *   A = sender, B = target
 *
 * If your client expects the old behavior, tell me and I’ll flip it back.
 */
$stmt_1 = $pdo->prepare("
    INSERT INTO friend_list (player_id_a, player_id_b, pending, direction, created, modified)
    VALUES (?, ?, ?, ?, ?, ?)
");
$stmt_1->execute([$sender_player_id, $target_player_id, 'true', 'false', $date, $date]);

$response = json_encode([
    "player_id_a" => $sender_player_id,
    "player_id_b" => $target_player_id,
    "wins_a" => $wins_sender,
    "wins_b" => $wins_target,
    "pending" => true,
    "direction" => false,
    "_created" => $date,
    "_modified" => $date,
], JSON_UNESCAPED_SLASHES);

$etag = 'W/"' . md5($response) . '"';
header("ETag: $etag");
echo $response;
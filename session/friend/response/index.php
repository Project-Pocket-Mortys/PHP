<?php
/*
$input = file_get_contents('php://input');
$data = json_decode($input, true);

$session_id = $data['session_id'];

if (empty($session_id)) {
    die("Not authenticated");
}

$stmt = $pdo->prepare("SELECT * FROM users WHERE session_id = ?");
$stmt->execute([$session_id]);
$user = $stmt->fetch(PDO::FETCH_ASSOC);
$player_id = $user['player_id'];
*/

error_reporting(E_ALL);
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);

header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");
header("Cache-Control: no-store");

require '../../../pocket_f4894h398r8h9w9er8he98he.php';

$raw = file_get_contents("php://input");
$data = json_decode($raw, true);

if (!is_array($data)) {
    http_response_code(400);
    echo json_encode(["error" => "Invalid JSON body"]);
    exit;
}

$session_id = $data["session_id"] ?? "";
$sender_player_id = $data["player_id"] ?? "";
$approve = $data["approve"] ?? null;

if ($session_id === "" || $sender_player_id === "" || !is_bool($approve)) {
    http_response_code(400);
    echo json_encode([
        "error" => "Missing/invalid fields",
        "required" => ["session_id" => "string", "player_id" => "string", "approve" => "boolean"]
    ]);
    exit;
}

// 1) Resolve the current user's player_id from session_id
$stmt = $pdo->prepare("SELECT player_id FROM users WHERE session_id = ? LIMIT 1");
$stmt->execute([$session_id]);
$row = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$row || empty($row["player_id"])) {
    http_response_code(401);
    echo json_encode(["error" => "Not authenticated"]);
    exit;
}

$my_player_id = $row["player_id"];

// Prevent weird self-request edge case
if ($my_player_id === $sender_player_id) {
    http_response_code(400);
    echo json_encode(["error" => "player_id cannot be the same as the authenticated user"]);
    exit;
}

// 2) Find the pending friend request row (either orientation)
$find = $pdo->prepare("
    SELECT player_id_a, player_id_b, pending, direction
    FROM friend_list
    WHERE
      (
        pending = 'true'
      )
      AND (
            (player_id_a = ? AND player_id_b = ?)
         OR (player_id_a = ? AND player_id_b = ?)
      )
    ORDER BY created DESC
    LIMIT 1
");
$find->execute([$sender_player_id, $my_player_id, $my_player_id, $sender_player_id]);
$req = $find->fetch(PDO::FETCH_ASSOC);

if (!$req) {
    http_response_code(400);
    echo json_encode(["error" => "No pending friend request found"]);
    exit;
}


// 3) Approve or reject
if ($approve === true) {
    $upd = $pdo->prepare("
        UPDATE friend_list
        SET pending = 'false',
            modified = NOW()
        WHERE pending = 'true'
          AND (
                (player_id_a = ? AND player_id_b = ?)
             OR (player_id_a = ? AND player_id_b = ?)
          )
        LIMIT 1
    ");
    $upd->execute([$sender_player_id, $my_player_id, $my_player_id, $sender_player_id]);

    echo '1';
    exit;
}

// Reject = delete the pending request row
$del = $pdo->prepare("
    DELETE FROM friend_list
	WHERE
      (
        pending = 'true'
      )
      AND (
            (player_id_a = ? AND player_id_b = ?)
         OR (player_id_a = ? AND player_id_b = ?)
      )
    LIMIT 1
");
$del->execute([$sender_player_id, $my_player_id, $my_player_id, $sender_player_id]);

echo '1';

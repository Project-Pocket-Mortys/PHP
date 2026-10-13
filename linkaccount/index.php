<?php
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require __DIR__ . "/../pocket_f4894h398r8h9w9er8he98he.php";

$input = file_get_contents("php://input");
$data  = json_decode($input, true);

$session_id = isset($data["session_id"]) ? (string)$data["session_id"] : "";
$rewards_id = isset($data["rewards_id"]) ? (string)$data["rewards_id"] : "";

if ($session_id === "" || $rewards_id === "") {
  http_response_code(400);
  echo json_encode([
    "success" => false,
    "error" => "MISSING_FIELDS",
    "message" => "session_id and recovery_code_hash are required"
  ], JSON_UNESCAPED_SLASHES);
  exit;
}

/*
  Check if user exists with this session_id
*/
$stmt = $pdo->prepare("SELECT id, session_id, recovery_code_hash FROM users WHERE session_id = ? LIMIT 1");
$stmt->execute([$session_id]);
$user = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$user) {
  http_response_code(404);
  echo json_encode([
    "success" => false,
    "error" => "SESSION_NOT_FOUND"
  ], JSON_UNESCAPED_SLASHES);
  exit;
}

/*
  If its already linked.
*/
if (!empty($user["recovery_code_hash"])) {
  echo json_encode([
    "success" => true,
    "message" => "Already linked"
  ], JSON_UNESCAPED_SLASHES);
  exit;
}

/*
  Link account
*/
$upd = $pdo->prepare("UPDATE users SET recovery_code_hash = ? WHERE session_id = ?");
$upd->execute([$rewards_id, $session_id]);

echo json_encode([
  "success" => true
], JSON_UNESCAPED_SLASHES);

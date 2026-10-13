<?php
declare(strict_types=1);
require __DIR__ . "/auth.php";

if ($_SERVER["REQUEST_METHOD"] !== "POST") {
  respond(405, ["success" => false, "error" => "METHOD_NOT_ALLOWED"]);
}

$user = require_user($pdo);
$userId = (int)$user["id"];

function make_recovery_code(): string {
  $alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"; // no confusing O/0/I/1
  $parts = [];
  for ($p=0; $p<3; $p++) {
    $chunk = "";
    for ($i=0; $i<4; $i++) {
      $chunk .= $alphabet[random_int(0, strlen($alphabet)-1)];
    }
    $parts[] = $chunk;
  }
  return implode("-", $parts);
}

$code = make_recovery_code();
$hash = password_hash($code, PASSWORD_DEFAULT);

// Store hash + timestamp in registered users table
$stmt = $pdo->prepare("
  UPDATE registered_users
  SET recovery_code_hash = ?, recovery_code_created_at = NOW()
  WHERE id = ?
");
$stmt->execute([$hash, $userId]);

respond(200, [
  "success" => true,
  "recovery_code" => $code,
  "message" => "Recovery code generated. Save it somewhere safe. Refresh page once saved."
]);

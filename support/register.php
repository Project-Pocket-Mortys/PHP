<?php
declare(strict_types=1);
require __DIR__ . "/auth.php";

if ($_SERVER["REQUEST_METHOD"] !== "POST") {
  respond(405, ["success" => false, "error" => "METHOD_NOT_ALLOWED"]);
}

$data = json_input();
$email = normalize_email((string)($data["email"] ?? ""));
$password = (string)($data["password"] ?? "");

// Basic validation
if ($email === "" || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
  respond(400, ["success" => false, "error" => "INVALID_EMAIL", "message" => "Enter a valid email."]);
}
if (strlen($password) < 6) {
  respond(400, ["success" => false, "error" => "WEAK_PASSWORD", "message" => "Password must be at least 6 characters."]);
}

// Check if user exists
$stmt = $pdo->prepare("SELECT id FROM registered_users WHERE email = ?");
$stmt->execute([$email]);
if ($stmt->fetch()) {
  respond(409, ["success" => false, "error" => "EMAIL_EXISTS", "message" => "That email is already registered."]);
}

// Create user
$hash = password_hash($password, PASSWORD_DEFAULT);

$stmt = $pdo->prepare("INSERT INTO registered_users (email, password_hash) VALUES (?, ?)");
$stmt->execute([$email, $hash]);

$userId = (int)$pdo->lastInsertId();

respond(201, [
  "success" => true,
  "message" => "Account created.",
  "redirect" => "/dashboard"
]);

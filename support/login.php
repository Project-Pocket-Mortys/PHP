<?php
declare(strict_types=1);
require __DIR__ . "/auth.php";

if (session_status() !== PHP_SESSION_ACTIVE) {
  session_start();
}

if ($_SERVER["REQUEST_METHOD"] !== "POST") {
  respond(405, ["success" => false, "error" => "METHOD_NOT_ALLOWED"]);
}

$data = json_input();
$email = normalize_email((string)($data["email"] ?? ""));
$password = (string)($data["password"] ?? "");
$remember = (int)($data["remember"] ?? 0);

if ($email === "" || !filter_var($email, FILTER_VALIDATE_EMAIL)) {
  respond(400, ["success" => false, "error" => "INVALID_EMAIL", "message" => "Enter a valid email."]);
}
if ($password === "") {
  respond(400, ["success" => false, "error" => "MISSING_PASSWORD", "message" => "Enter your password."]);
}

// Fetch user
$stmt = $pdo->prepare("SELECT id, password_hash, recovery_code_hash FROM registered_users WHERE email = ?");
$stmt->execute([$email]);
$user = $stmt->fetch();

if (!$user || !password_verify($password, $user["password_hash"])) {
  respond(401, ["success" => false, "error" => "INVALID_CREDENTIALS", "message" => "Email or password is incorrect."]);
}

$userId = (int)$user["id"];

/* =========================
   SESSION AUTH
   ========================= */

$_SESSION["user"] = [
  "id"    => $userId,
  "email" => $email
];

/* =========================
   TOKEN AUTH
   ========================= */
   
$token = random_token(32); // 64 hex chars
$tokenHash = token_hash($token);

$expiresAt = (new DateTimeImmutable("now"))
  ->modify("+7 days")
  ->format("Y-m-d H:i:s");

$ip = $_SERVER["REMOTE_ADDR"] ?? null;
$ua = substr($_SERVER["HTTP_USER_AGENT"] ?? "", 0, 255);

$stmt = $pdo->prepare("
  INSERT INTO user_sessions (user_id, token_hash, expires_at, ip, user_agent)
  VALUES (?, ?, ?, ?, ?)
");
$stmt->execute([$userId, $tokenHash, $expiresAt, $ip, $ua]);

// Update last_login
$pdo->prepare("UPDATE registered_users SET last_login = NOW() WHERE id = ?")->execute([$userId]);

// Remember me cookie (optional)
if ($remember === 1) {
  // store raw token in cookie, but only store hash in DB
  set_remember_cookie($token);
} else {
  clear_remember_cookie();
}

respond(200, [
  "success" => true,
  "message" => "Signed in.",
  "redirect" => "/dashboard",
  "token" => $token
]);

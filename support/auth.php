<?php
declare(strict_types=1);
require __DIR__ . "/../www/pocket_f4894h398r8h9w9er8he98he.php";   // IMPORTANT: make sure filename matches

if (session_status() !== PHP_SESSION_ACTIVE) {
  session_start();
}

function require_user(PDO $pdo): array {
  global $COOKIE_NAME;

  // 1) Session user already set
  if (!empty($_SESSION["user"])) {
    return $_SESSION["user"];
  }

  // 2) Token from session OR cookie
  $token = $_SESSION["token"] ?? ($_COOKIE[$COOKIE_NAME] ?? "");
  if (!$token) {
    header("Location: /../");
    exit;
  }

  $hash = token_hash($token);

  $stmt = $pdo->prepare("
    SELECT u.id, u.email, recovery_code_hash
    FROM user_sessions s
    JOIN registered_users u ON u.id = s.user_id
    WHERE s.token_hash = ?
      AND s.expires_at > NOW()
    LIMIT 1
  ");
  $stmt->execute([$hash]);
  $user = $stmt->fetch();

  if (!$user) {
    clear_remember_cookie();
    $_SESSION = [];
    session_destroy();
    header("Location: /../");
    exit;
  }

  // 3) Restore session
  $_SESSION["user"] = [
    "id"    => (int)$user["id"],
    "email" => $user["email"]
  ];

  // keep token in session so dashboard works even without remember cookie
  $_SESSION["token"] = $token;

  return $_SESSION["user"];
}

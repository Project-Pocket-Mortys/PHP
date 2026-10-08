<?php
declare(strict_types=1);
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
  http_response_code(204);
  exit;
}

error_reporting(E_ALL);
ini_set('display_errors', '1');

/** ✅ Configure these */
$DB_HOST = "";
$DB_NAME = "";
$DB_USER = "";
$DB_PASS = "";

/** Cookie settings */
$COOKIE_NAME = "pm_remember";
$COOKIE_DAYS = 30;

/** Session token settings */
$SESSION_TTL_DAYS = 7; // API token expiry

try {
  $pdo = new PDO(
    "mysql:host={$DB_HOST};port=3306;dbname={$DB_NAME};charset=utf8mb4",
    $DB_USER,
    $DB_PASS,
    [
      PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
      PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
    ]
  );
} catch (Throwable $e) {
  http_response_code(500);
  echo json_encode(["success" => false, "error" => "DB_CONNECTION_FAILED"]);
  exit;
}

function json_input(): array {
  $raw = file_get_contents("php://input");
  $data = json_decode($raw ?: "{}", true);
  return is_array($data) ? $data : [];
}

function respond(int $code, array $payload): void {
  http_response_code($code);
  echo json_encode($payload, JSON_UNESCAPED_SLASHES);
  exit;
}

function normalize_email(string $email): string {
  return strtolower(trim($email));
}

function random_token(int $bytes = 32): string {
  return bin2hex(random_bytes($bytes)); // 64 hex chars when bytes=32
}

function token_hash(string $token): string {
  return hash("sha256", $token);
}

function cookie_params(): array {
  // If you're serving HTTPS, set 'secure' => true
  $isHttps = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off')
            || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https');

  return [
    "expires"  => time() + 60 * 60 * 24 * 30,
    "path"     => "/",
    "domain"   => "",     // leave blank for current host
    "secure"   => $isHttps,
    "httponly" => true,
    "samesite" => "Lax",
  ];
}

function set_remember_cookie(string $token): void {
  global $COOKIE_NAME;
  setcookie($COOKIE_NAME, $token, cookie_params());
}

function clear_remember_cookie(): void {
  global $COOKIE_NAME;
  $p = cookie_params();
  $p["expires"] = time() - 3600;
  setcookie($COOKIE_NAME, "", $p);
}
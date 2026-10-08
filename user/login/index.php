<?php
//login
header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

$input = file_get_contents('php://input');
$data = json_decode($input, true);

$secret = $data['secret'];
$consent_identifier = $data['consent_identifier'];

$allowedSecrets = [
    '4f0b1131-08d0-449c-9f6e-c70241b8cb70',
    '9af289a7-1bd7-471b-8a96-23926e244967'
];

if (!in_array($secret, $allowedSecrets, true)) {
    http_response_code(400);

    echo json_encode([
        "error" => [
            "code" => "MAINTENANCE"
        ]
    ], JSON_UNESCAPED_SLASHES);

    exit;
}

require '../../pocket_f4894h398r8h9w9er8he98he.php';

function uuidv4() {
    $data = random_bytes(16);
    // Set version to 0100 (UUID v4)
    $data[6] = chr((ord($data[6]) & 0x0f) | 0x40);
    // Set variant to 10xx
    $data[8] = chr((ord($data[8]) & 0x3f) | 0x80);
    return vsprintf('%s%s-%s-%s-%s-%s%s%s', str_split(bin2hex($data), 4));
}

$stmt = $pdo->prepare("SELECT * FROM users WHERE secret = ?");
$stmt->execute([$secret]);
$user = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$user) {
http_response_code(400);
$error = json_encode([
    "error" => [
        "code" => "SECRET_INVALID"
    ]
], JSON_UNESCAPED_SLASHES);
echo $error;
exit;
}


//encrypt this data with the token
$player_id = $user['player_id'];
$username = $user['username'];
$level = $user['level'];
$tags = $user['tags'];
$session_id = uuidv4();
$ping_url = 'https://game.conspiracyrick.com/session/ping-dynamic';
// Generate issued token time
$iat = time(); // issued at (now)
// when to expire token
$exp = time() + 60;   // expires in 60 seconds

// ---------------- Update Session ----------------
$stmt = $pdo->prepare("UPDATE users SET session_id=? WHERE player_id=?");
$stmt->execute([$session_id, $player_id]);

//generate 419 token length
function base64url_encode($data) {
    return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
}

//$noshare = "seepageorgelickhackpooploopyourstours";
$noshare = rtrim(strtr(base64_encode(random_bytes(32)), '+/', '-_'), '=');

$header = [
    "alg" => "HS256",
    "typ" => "JWT"
];

$payload = [
    "player_id" => $player_id,
    "username"  => $username,
	"level"  => (int)$level,
	"tags"  => $tags,
	"session_id"  => $session_id,
	"ping_url"  => $ping_url,
    "iat"       => (int)$iat,
    "exp"       => (int)$exp
];

$base64Header  = base64url_encode(json_encode($header));
$base64Payload = base64url_encode(json_encode($payload));
$signature = hash_hmac(
    'sha256',
    $base64Header . "." . $base64Payload,
    $noshare,
    true
);
$base64Signature = base64url_encode($signature);
$jwt = $base64Header . "." . $base64Payload . "." . $base64Signature;

$response = json_encode([
    "session_url" => "https://game.conspiracyrick.com/sse/?token=".$jwt,
    "session_url_ttl" => "60"
], JSON_UNESCAPED_SLASHES);

$etag = 'W/"' . md5($response) . '"';

header("ETag: $etag");
echo $response;
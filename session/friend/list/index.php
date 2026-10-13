<?php
// friend_list

header("Content-Type: application/json; charset=utf-8");
header("X-Powered-By: Express");
header("Access-Control-Allow-Origin: *");
header("Vary: Accept-Encoding");

require '../../../pocket_f4894h398r8h9w9er8he98he.php';

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


/*
echo '{
	"requests_sent": [{
		"username": "SadoMadoinK",
		"player_avatar_id": "AvatarPaulFleischman",
		"level": 29,
		"player_id": "e3426a1c-7562-43a5-a510-8f2fc869019a",
		"_created": "2025-10-10T11:31:50.167Z"
	}],
	"requests_received": [],
	"friends": [{
		"username": "BarsonInc",
		"player_avatar_id": "AvatarRickDefault",
		"level": 1,
		"player_id": "845f3b05-03d6-413c-b32a-0816becba44c",
		"wins": 0,
		"losses": 0,
		"donation_request": null,
		"online": false
	}, {
		"username": "COZY_NUTZZ",
		"player_avatar_id": "AvatarCrowRick",
		"level": 12,
		"player_id": "904ef9d1-9e6a-4e4a-b987-23c47a61f34e",
		"wins": 0,
		"losses": 0,
		"donation_request": null,
		"online": false
	}, {
		"username": "farfas",
		"player_avatar_id": "AvatarRickDefault",
		"level": 13,
		"player_id": "642ca9c2-3858-439f-938c-ae7c140f076b",
		"wins": 0,
		"losses": 0,
		"donation_request": null,
		"online": false
	}, {
		"username": "isabella20147",
		"player_avatar_id": "AvatarRickDefault",
		"level": 1,
		"player_id": "eab38a5e-9fcc-4c12-b95f-057ccf6e53ab",
		"wins": 2,
		"losses": 1,
		"donation_request": null,
		"online": false
	}, {
		"username": "junbchvc",
		"player_avatar_id": "AvatarRickDefault",
		"level": 8,
		"player_id": "cbcd4b0e-9158-4667-96cc-1f4da9586808",
		"wins": 0,
		"losses": 0,
		"donation_request": null,
		"online": false
	}, {
		"username": "PentSolicitude2",
		"player_avatar_id": "AvatarSleepyGarry",
		"level": 12,
		"player_id": "2d0c62a9-22fb-4be5-9022-9d77bb4022be",
		"wins": 0,
		"losses": 0,
		"donation_request": null,
		"online": false
	}, {
		"username": "Zlatan428j",
		"player_avatar_id": "AvatarMrAlwaysWantsToBeHunter",
		"level": 9,
		"player_id": "0ceea05b-56ef-4988-9610-65b7ddd817f0",
		"wins": 0,
		"losses": 0,
		"donation_request": null,
		"online": false
	}, {
		"username": "zvital_7",
		"player_avatar_id": "AvatarRickSashAndCape",
		"level": 15,
		"player_id": "60bf0743-5ec9-4c28-8727-b554a4a02090",
		"wins": 0,
		"losses": 0,
		"donation_request": null,
		"online": false
	}],
	"poll_period": 5,
	"donation_request": {
		"morty_id": null,
		"next_countdown": 0,
		"donation": null
	},
	"limit_friends": 30
}';
*/

/*
{
	"requests_sent": [],
	"requests_received": [],
	"friends": null,
	"poll_period": 5,
	"donation_request": {
		"morty_id": null,
		"next_countdown": 0,
		"donation": null
	},
	"limit_friends": 30
}


echo json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);
*/

try {
    // ─── 1. Requests SENT (you sent to others) ────────────────────────────────
    $sentStmt = $pdo->prepare("
    SELECT 
        p.username,
        p.player_avatar_id,
        p.level,
        p.player_id          AS player_id,
        r.created            AS _created
    FROM friend_list r
    JOIN users p ON p.player_id = r.player_id_b          -- get info of the receiver
    WHERE r.player_id_a = :me
      AND r.pending     = 'true'
    ORDER BY r.created DESC
");
$sentStmt->execute([':me' => $player_id]);
$requests_sent = $sentStmt->fetchAll(PDO::FETCH_ASSOC) ?? [];

    // ─── 2. Requests RECEIVED (others sent to you) ────────────────────────────
$receivedStmt = $pdo->prepare("
    SELECT 
        p.username,
        p.player_avatar_id,
        p.level,
        p.player_id          AS player_id,
        r.created            AS _created
    FROM friend_list r
    JOIN users p ON p.player_id = r.player_id_a          -- get info of the sender
    WHERE r.player_id_b = :me
      AND r.pending     = 'true'
    ORDER BY r.created DESC
");
$receivedStmt->execute([':me' => $player_id]);
$requests_received = $receivedStmt->fetchAll(PDO::FETCH_ASSOC) ?? [];

    // ─── 3. Friends (accepted / mutual) ──────────────────────────────────
$friendsStmt = $pdo->prepare("
    SELECT 
        p.username,
        p.player_avatar_id,
        p.level,
        p.player_id,
        COALESCE(p.wins,   0) AS wins,
        COALESCE(p.losses, 0) AS losses,

        -- Online if seen in last 5 minutes
        CASE
            WHEN p.last_seen IS NOT NULL
             AND p.last_seen >= (NOW() - INTERVAL 5 MINUTE)
            THEN 'true'
            ELSE 'false'
        END AS online,

        p.donation_request AS donation_request
    FROM friend_list r
    JOIN users p ON p.player_id = 
        CASE 
            WHEN r.player_id_a = ? THEN r.player_id_b
            WHEN r.player_id_b = ? THEN r.player_id_a
        END
    WHERE ? IN (r.player_id_a, r.player_id_b)
      AND r.pending != 'true'
    ORDER BY p.username ASC
");

$friendsStmt->execute([
    $player_id,   // CASE player_id_a
    $player_id,   // CASE player_id_b
    $player_id    // WHERE clause
]);

$friends = $friendsStmt->fetchAll(PDO::FETCH_ASSOC) ?? [];

    // Final structure
    $result = [
        'requests_sent'     => $requests_sent,
        'requests_received' => $requests_received,
        'friends'           => $friends,
        'poll_period'       => 5,
        'donation_request'  => [
            'morty_id'       => null,
            'next_countdown' => 0,
            'donation'       => null
        ],
        'limit_friends'     => 30
    ];

    echo json_encode($result, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR);

} catch (Exception $e) {
    http_response_code(500);
    echo json_encode([
        'error'  => $e->getMessage(),
        'file'   => basename($e->getFile() ?? 'unknown'),
        'line'   => $e->getLine() ?? 'unknown'
    ]);
}
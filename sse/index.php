<?php
// sse-stream
// Streams session + room events via SSE.

error_reporting(E_ALL);
ini_set('display_errors', 1);
ini_set('display_startup_errors', 1);

set_time_limit(0);
ignore_user_abort(true);

header('Content-Type: text/event-stream; charset=utf-8');
header('Cache-Control: no-cache');
header('Connection: keep-alive');
header('X-Accel-Buffering: no');

require __DIR__ . "/../pocket_f4894h398r8h9w9er8he98he.php";
require __DIR__ . "/../lib/auth.php";
require __DIR__ . "/../lib/events.php"; // provides sse_send()

// ---------------- SSE HELPERS ----------------
function sse_send_id(string $event, string $dataJson, ?int $id = null): void {
    //if ($id !== null) echo "id: {$id}\n"; // enable if you want EventSource resume support
    echo "event: {$event}\n";
    echo "data: {$dataJson}\n\n";
    @ob_flush(); @flush();
}

function base64url_decode($data) { return base64_decode(strtr($data, '-_', '+/')); }
function decode_jwt_payload($jwt) {
    $parts = explode('.', $jwt);
    if (count($parts) < 2) return null;
    return json_decode(base64url_decode($parts[1]), true);
}

// Cursor stored in users table
function cursor_get(PDO $pdo, string $player_id): int {
    $q = $pdo->prepare("SELECT COALESCE(last_event_id, 0) FROM users WHERE player_id = ? LIMIT 1");
    $q->execute([$player_id]);
    return (int)$q->fetchColumn();
}
function cursor_set(PDO $pdo, string $player_id, int $last_id, string $session_id, string $room_id, string $generation): void {
    // A previous membership's poll must not overwrite a new join's cursor,
    // including a leave/rejoin to the same room between polls.
    $q = $pdo->prepare("UPDATE users SET last_event_id = ?, last_seen = NOW() WHERE player_id = ? AND session_id = ? AND room_id = ? AND room_membership_generation = ?");
    $q->execute([$last_id, $player_id, $session_id, $room_id, $generation]);
}
function room_max_event_id(PDO $pdo, string $room_id): int {
    $q = $pdo->prepare("SELECT COALESCE(MAX(id), 0) FROM event_queue WHERE room_id = ?");
    $q->execute([$room_id]);
    return (int)$q->fetchColumn();
}

// A stream belongs to the session that opened it, not every future login
// for the same player. End revoked streams without inventing a wire event.
function require_live_stream_session(PDO $pdo, string $player_id, string $session_id): array {
    $q = $pdo->prepare("SELECT room_id, room_membership_generation, COALESCE(last_event_id, 0) AS last_event_id FROM users WHERE player_id = ? AND session_id = ? LIMIT 1");
    $q->execute([$player_id, $session_id]);
    $membership = $q->fetch(PDO::FETCH_ASSOC);
    if (!$membership) exit;
    return $membership;
}


// Keep BIGINT generations as decimal strings, including values above PHP_INT_MAX.
function stream_membership_matches(array $membership, string $room_id, string $generation): bool {
    return (string)$membership['room_id'] === $room_id
        && (string)$membership['room_membership_generation'] === $generation;
}

/* ---------------- ACTIVE DECK MORTIES ---------------- */
require_once __DIR__ . '/../lib/active_deck.php';

// -------------------- AUTH --------------------

$token   = $_GET['token'] ?? null;
$profile = $token ? decode_jwt_payload($token) : null;

$session_id = (string)($profile['session_id'] ?? "");
if ($session_id === "") {
    http_response_code(400);
    sse_send_id("error", json_encode(["error" => "Missing session_id"], JSON_UNESCAPED_SLASHES));
    exit;
}

$stmt = $pdo->prepare("
    SELECT player_id, username, level, tags, room_id, player_avatar_id, state, COALESCE(last_event_id, 0) AS last_event_id
    FROM users
    WHERE session_id = ?
    LIMIT 1
");
$stmt->execute([$session_id]);
$user = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$user) {
    http_response_code(401);
    sse_send_id("error", json_encode(["error" => "Not authenticated"], JSON_UNESCAPED_SLASHES));
    exit;
}

$player_id = (string)$user["player_id"];

$tags = $user["tags"] ?? [];
if (is_string($tags)) {
    $decoded = json_decode($tags, true);
    $tags = is_array($decoded) ? $decoded : [];
} elseif (!is_array($tags)) {
    $tags = [];
}

$ping_url = (string)($profile['ping_url'] ?? "https://game.conspiracyrick.com/session/ping-dynamic");

// -------------------- SESSION START --------------------
// "server_instance" => "/ip-10-100-0-46/1/1143",
$session = [
    "player_id" => $player_id,
    "session_id" => $session_id,
    "username" => (string)$user["username"],
    "level" => (int)$user["level"],
    "tags" => $tags,
    "ping_interval" => 30,
    "ping_url" => $ping_url,
    "keep_alive" => 30,
    "server_instance" => "/ip-10-100-0-46/0/1142",
    "worlds" => [
        ["world_id"=>"1","player_level"=>["min"=>1,"max"=>50]],
        ["world_id"=>"2","player_level"=>["min"=>5,"max"=>50]],
        ["world_id"=>"3","player_level"=>["min"=>15,"max"=>50]],
        ["world_id"=>"4","player_level"=>["min"=>30,"max"=>50]],
        ["world_id"=>"5","player_level"=>["min"=>5,"max"=>50]],
        ["world_id"=>"6","player_level"=>["min"=>10,"max"=>50]],
        ["world_id"=>"7","player_level"=>["min"=>15,"max"=>50]],
    ],
    "owned_morty_limit" => 750
];

sse_send("session:start", json_encode($session, JSON_UNESCAPED_SLASHES));

// -------------------- WAIT FOR ROOM --------------------

$room_id = "";
$last_keepalive = time();

while (!connection_aborted()) {
    $st = $pdo->prepare("SELECT room_id, room_membership_generation FROM users WHERE player_id = ? AND session_id = ? LIMIT 1");
    $st->execute([$player_id, $session_id]);
    $membership = $st->fetch(PDO::FETCH_ASSOC);
    if (!$membership) exit;
    $room_id = (string)$membership['room_id'];
    $generation = (string)$membership['room_membership_generation'];

    if ($room_id !== "" && $room_id !== "0") break;

    if ((time() - $last_keepalive) >= 25) {
        sse_send("session:keep-alive", "0");
        $last_keepalive = time();
    }
    usleep(250000);
}

if ($room_id === "" || $room_id === "0") exit;

// -------------------- RESUME OR FRESH CONNECT? --------------------

$client_last_event_id = null;
if (!empty($_SERVER['HTTP_LAST_EVENT_ID']) && ctype_digit($_SERVER['HTTP_LAST_EVENT_ID'])) {
    $client_last_event_id = (int)$_SERVER['HTTP_LAST_EVENT_ID'];
}
if ($client_last_event_id === null && isset($_GET['since']) && ctype_digit((string)$_GET['since'])) {
    $client_last_event_id = (int)$_GET['since'];
}

$fresh_connect = ($client_last_event_id === null);

// -------------------- INITIAL SNAPSHOT (ONLY ON FRESH CONNECT) --------------------

if ($fresh_connect) {
    // Fix one boundary before reading entities. Later publications belong to
    // the live queue, even if they arrive while a snapshot is being sent.
    $snapshot_last_id = room_max_event_id($pdo, $room_id);

    // ---------------- PICKUPS ----------------
    $pickupStmt = $pdo->prepare("
        SELECT id, only_show_to_player_id, pickup_id, placement, pick_up_contents
        FROM event_queue
        WHERE room_id = ? AND id <= ?
        AND event_name = 'room:pickup-added'
        AND pickup_id_collected_by_player_id IS NULL
        ORDER BY id ASC
    ");
    $pickupStmt->execute([$room_id, $snapshot_last_id]);

    while ($p = $pickupStmt->fetch(PDO::FETCH_ASSOC)) {
        if (!event_is_visible_to_player($p, $player_id)) continue;
        if (!stream_membership_matches(require_live_stream_session($pdo, $player_id, $session_id), $room_id, $generation)) break;

        $placement = explode(",", $p["placement"] ?? "0,0");

        $payload = [
            "pickup_id" => $p["pickup_id"],
            "placement" => [
                (int)($placement[0] ?? 0),
                (int)($placement[1] ?? 0)
            ],
            "contents" => json_decode($p["pick_up_contents"], true) ?? []
        ];

        sse_send_id(
            "room:pickup-added",
            json_encode($payload, JSON_UNESCAPED_SLASHES),
            (int)$p["id"]
        );
    }

    // ---------------- WILD MORTIES ----------------
    $wildStmt = $pdo->prepare("
        SELECT id, only_show_to_player_id, wild_morty_id, morty_id, placement, state, division, variant, shiny_if_potion
        FROM event_queue
        WHERE room_id = ? AND id <= ?
        AND event_name = 'room:wild-morty-added'
        ORDER BY id ASC
    ");
    $wildStmt->execute([$room_id, $snapshot_last_id]);

    while ($w = $wildStmt->fetch(PDO::FETCH_ASSOC)) {
        if (!event_is_visible_to_player($w, $player_id)) continue;
        if (!stream_membership_matches(require_live_stream_session($pdo, $player_id, $session_id), $room_id, $generation)) break;

        $placement = explode(",", $w["placement"] ?? "0,0");

        $payload = [
            "morty_id" => $w["morty_id"],
            "placement" => [
                (int)($placement[0] ?? 0),
                (int)($placement[1] ?? 0)
            ],
            "state" => $w["state"] ?: "WORLD",
            "division" => (int)($w["division"] ?: 1),
            "variant" => $w["variant"] ?: "Normal",
            "shiny_if_potion" => (bool)$w["shiny_if_potion"],
            "_created" => gmdate("Y-m-d\\TH:i:s").".000Z",
            "_updated" => gmdate("Y-m-d\\TH:i:s").".000Z",
            "wild_morty_id" => $w["wild_morty_id"]
        ];

        sse_send_id(
            "room:wild-morty-added",
            json_encode($payload, JSON_UNESCAPED_SLASHES),
            (int)$w["id"]
        );
    }

    // ---------------- BOTS ----------------
    $botStmt = $pdo->prepare("
        SELECT id, only_show_to_player_id, bot_id, username, player_avatar_id, placement, state, owned_morties
        FROM event_queue
        WHERE room_id = ? AND id <= ?
        AND event_name = 'room:bot-added'
        ORDER BY id ASC
    ");
    $botStmt->execute([$room_id, $snapshot_last_id]);

    while ($b = $botStmt->fetch(PDO::FETCH_ASSOC)) {
        if (!event_is_visible_to_player($b, $player_id)) continue;
        if (!stream_membership_matches(require_live_stream_session($pdo, $player_id, $session_id), $room_id, $generation)) break;

        $placement = explode(",", $b["placement"] ?? "0,0");

        $payload = [
            "username" => $b["username"],
            "player_avatar_id" => $b["player_avatar_id"],
            "state" => $b["state"] ?: "WORLD",
            "level" => 1,
            "owned_morties" => json_decode($b["owned_morties"], true) ?? [],
            "streak" => 0,
            "bot_id" => $b["bot_id"],
            "placement" => [
                (int)($placement[0] ?? 0),
                (int)($placement[1] ?? 0)
            ]
        ];

        sse_send_id(
            "room:bot-added",
            json_encode($payload, JSON_UNESCAPED_SLASHES),
            (int)$b["id"]
        );
    }

    // Continue above the original boundary, not a new maximum after delivery.
    $last_id = $snapshot_last_id;
    cursor_set($pdo, $player_id, $last_id, $session_id, $room_id, $generation);

} else {
    $last_id = (int)$client_last_event_id;
    cursor_set($pdo, $player_id, $last_id, $session_id, $room_id, $generation);
}

// -------------------- MAIN STREAM LOOP --------------------

$keepalive_interval_sec = 30;
$last_keepalive = time();

while (!connection_aborted()) {

    $membership = require_live_stream_session($pdo, $player_id, $session_id);
    $current_room_id = (string)$membership['room_id'];
    if (!stream_membership_matches($membership, $room_id, $generation)) {
        $room_id = $current_room_id;
        $generation = (string)$membership['room_membership_generation'];
        // join-room supplies the snapshot over HTTP and installs this baseline
        // together with membership. Do not replay the destination's history.
        $last_id = (int)$membership['last_event_id'];
    }
    if ($room_id === '' || $room_id === '0') {
        if ((time() - $last_keepalive) >= $keepalive_interval_sec) {
            sse_send('session:keep-alive', '0');
            $last_keepalive = time();
        }
        usleep(250000);
        continue;
    }

    // keep user online
    $pdo->prepare("
        UPDATE users
        SET last_seen = NOW()
        WHERE player_id = ?
    ")->execute([$player_id]);

    $stmt = $pdo->prepare("
        SELECT
            id,
            room_id,
            event_name,
			player_id,
			emote,
			current_raid,
			battle_start,
			battle_turn_result,
			battle_move_timer_started,
			bot_id,
			username,
			player_avatar_id,
			wild_morty_id,
			morty_id,
			placement,
			state,
			division,
			zone_id,
			variant,
			shiny_if_potion,
            pickup_id,
            pick_up_contents,
			owned_morties,
            only_show_to_player_id
        FROM event_queue
        WHERE room_id = ?
        AND id > ?
        ORDER BY id ASC
        LIMIT 200
    ");

    $stmt->execute([$room_id, $last_id]);

    $sent = false;

    while ($row = $stmt->fetch(PDO::FETCH_ASSOC)) {
        if (!stream_membership_matches(require_live_stream_session($pdo, $player_id, $session_id), $room_id, $generation)) break;

        $eventName = (string)$row["event_name"];
        $eid = (int)$row["id"];
        $targetPid = (string)($row["player_id"] ?? "");

        $payload = (string)null;

        // Recipient metadata is authoritative; ambiguous private events stay private.
        if (!event_is_visible_to_player($row, $player_id)) {
            $last_id = $eid;
            continue;
        }

        // ---------------- REBUILD PICKUP EVENTS ----------------
        if ($eventName === "room:pickup-added") {

            $placement = explode(",", $row["placement"] ?? "0,0");

            $rebuilt = [
                "pickup_id" => $row["pickup_id"],
                "placement" => [
                    (int)($placement[0] ?? 0),
                    (int)($placement[1] ?? 0)
                ],
                "contents" => json_decode(
                    $row["pick_up_contents"] ?? "[]",
                    true
                ) ?? []
            ];

            $payload = json_encode(
                $rebuilt,
                JSON_UNESCAPED_SLASHES
            );
        }

        // ---------------- REBUILD WILD EVENTS ----------------
        elseif ($eventName === "room:wild-morty-added") {

            $placement = explode(",", $row["placement"] ?? "0,0");

            $rebuilt = [
                "morty_id" => $row["morty_id"],
                "placement" => [
                    (int)($placement[0] ?? 0),
                    (int)($placement[1] ?? 0)
                ],
                "state" => $row["state"] ?: "WORLD",
                "division" => (int)($row["division"] ?: 1),
                "variant" => $row["variant"] ?: "Normal",
                "shiny_if_potion" => (bool)$row["shiny_if_potion"],
                "_created" => gmdate("Y-m-d\\TH:i:s") . ".000Z",
                "_updated" => gmdate("Y-m-d\\TH:i:s") . ".000Z",
                "wild_morty_id" => $row["wild_morty_id"]
            ];

            $payload = json_encode(
                $rebuilt,
                JSON_UNESCAPED_SLASHES
            );
        }

        // ---------------- REBUILD BOT EVENTS ----------------
        elseif ($eventName === "room:bot-added") {

            $placement = explode(",", $row["placement"] ?? "0,0");

            $rebuilt = [
                "username" => $row["username"],
                "player_avatar_id" => $row["player_avatar_id"],
                "state" => $row["state"] ?: "WORLD",
                "level" => 1,
                "owned_morties" => json_decode(
                    $row["owned_morties"] ?? "[]",
                    true
                ) ?? [],
                "streak" => 0,
                "bot_id" => $row["bot_id"],
                "placement" => [
                    (int)($placement[0] ?? 0),
                    (int)($placement[1] ?? 0)
                ]
            ];

            $payload = json_encode(
                $rebuilt,
                JSON_UNESCAPED_SLASHES
            );
        }

		// ---------------- RAID EVENTS ----------------
        elseif ($eventName === "shard:raid-boss-state-changed") {
           $payload = (string)$row["current_raid"];
		}

		// ---------------- WILD MORTY STATE CHANGE ----------------
        elseif ($eventName === "room:wild-morty-state-changed") {
		   $rebuilt = [
                "wild_morty_id" => $row["wild_morty_id"],
                "state" => $row["state"]
            ];

            $payload = json_encode(
                $rebuilt,
                JSON_UNESCAPED_SLASHES
            );
		}

		// ---------------- USER ROOM STATE CHANGE ----------------
        elseif ($eventName === "room:user-state-changed") {
		   $rebuilt = [
                "player_id" => $row["player_id"],
                "state" => $row["state"]
            ];

            $payload = json_encode(
                $rebuilt,
                JSON_UNESCAPED_SLASHES
            );
		}

		// ---------------- BATTLE START EVENT ----------------
        elseif ($eventName === "battle:start") {
           $payload = (string)$row["battle_start"];
		}

		// ---------------- BATTLE TURN ----------------
		elseif ($eventName === "battle:turn-result") {
           $payload = (string)$row["battle_turn_result"];
		}

		// ---------------- BATTLE TIMER ----------------
		elseif ($eventName === "battle:move-timer-started") {
           $payload = (string)$row["battle_move_timer_started"];
		}

		// ---------------- REMOVE PICKUP ----------------
        elseif ($eventName === "room:pickup-removed") {
		   $rebuilt = [
                "pickup_id" => $row["pickup_id"]
            ];

            $payload = json_encode(
                $rebuilt,
                JSON_UNESCAPED_SLASHES
            );
		}

		// ---------------- EMOTE ----------------
        elseif ($eventName === "emote:room") {
		   $rebuilt = [
                "player_id" => $row["player_id"],
				"emote" => $row["emote"]
            ];

            $payload = json_encode(
                $rebuilt,
                JSON_UNESCAPED_SLASHES
            );
		}

		// ---------------- ROOM USER ADDED ----------------
        elseif ($eventName === "room:user-added") {
		// The queued player is the arriving subject, not the stream subscriber.
		$subjectStmt = $pdo->prepare("SELECT player_id, username, player_avatar_id, level, state FROM users WHERE player_id = ? LIMIT 1");
		$subjectStmt->execute([$targetPid]);
		$subject = $subjectStmt->fetch(PDO::FETCH_ASSOC);
		if (!$subject) {
		    $last_id = $eid;
		    continue;
		}
		$roomuser = [
                "player_id" => (string)$subject["player_id"],
                "username" => (string)$subject["username"],
                "player_avatar_id" => (string)$subject["player_avatar_id"],
                "level" => (int)$subject["level"],
                "owned_morties" => get_active_deck_morties($pdo, (string)$subject["player_id"]),
                "state" => (string)($row["state"] ?: "WORLD")
            ];
		$payload = json_encode(
                $roomuser,
                JSON_UNESCAPED_SLASHES
            );
		}

		// ---------------- ROOM USER LEFT ----------------
        elseif ($eventName === "room:user-removed") {
		$roomuser = [
                "player_id" => $targetPid
            ];
		$payload = json_encode(
                $roomuser,
                JSON_UNESCAPED_SLASHES
            );
		}


        // send the payload to the live SSE
        sse_send_id($eventName, $payload, $eid);

        $last_id = $eid;
        $sent = true;
    }

    cursor_set($pdo, $player_id, $last_id, $session_id, $room_id, $generation);

    if (
        !$sent &&
        (time() - $last_keepalive) >= $keepalive_interval_sec
    ) {
        sse_send("session:keep-alive", "0");
        $last_keepalive = time();
    }

    usleep(300000);
}

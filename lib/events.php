<?php
// lib/events.php (FIXED SAFE VERSION)

function publish_event(PDO $pdo, string $room_id, string $event, array $payload, ?string $player_id = null): void {
    $pickup_id = null;
    $placement = null;
    $wild_morty_id = null;
    $morty_id = null;
    $state = null;
    $division = null;
    $variant = null;
    $shiny_if_potion = 0;
    $pick_up_contents = null;
	$zone_id = "[1,1]";
	$bot_id = null;
	$username = null;
	$player_avatar_id = null;
	$owned_morties = null;
	$battle_start = null;
	$get_current_raid = null;
	$battle_turn_result = null;
	$battle_move_timer_started = null;
	$emote = null;
	$only_show_to_player_id = null;

    // ---------------- PICKUP ----------------
    if ($event === "room:pickup-added") {

        $pickup_id = $payload["pickup_id"] ?? null;

        if (isset($payload["placement"][0], $payload["placement"][1])) {
            $placement = $payload["placement"][0] . "," . $payload["placement"][1];
        }

        // IMPORTANT FIX:
        // store FULL contents array, NOT only index 0
        $pick_up_contents = isset($payload["contents"])
            ? json_encode($payload["contents"], JSON_UNESCAPED_SLASHES)
            : json_encode([], JSON_UNESCAPED_SLASHES);
    }
    
	
	// ---------------- REMOVE PICKUP IF PICKED UP ----------------
    if ($event === "room:pickup-removed") {
        $pickup_id = $payload["pickup_id"] ?? null;
    }

    // ---------------- WILD MORTY ----------------
    if ($event === "room:wild-morty-added") {

        $wild_morty_id = $payload["wild_morty_id"] ?? null;
        $morty_id      = $payload["morty_id"] ?? null;
        $state         = $payload["state"] ?? "WORLD";
        $division      = $payload["division"] ?? null;
        $variant       = $payload["variant"] ?? null;
        $shiny_if_potion = !empty($payload["shiny_if_potion"]) ? 1 : 0;

        if (isset($payload["placement"][0], $payload["placement"][1])) {
            $placement = $payload["placement"][0] . "," . $payload["placement"][1];
        }
    }

    // ---------------- BOT ----------------
    if ($event === "room:bot-added") {
		$bot_id = $payload["bot_id"] ?? null;
		$username = $payload["username"] ?? null;
        $player_avatar_id = $payload["player_avatar_id"] ?? null;
        $state = $payload["state"] ?? "WORLD";
		
		$owned_morties = isset($payload["owned_morties"])
            ? json_encode($payload["owned_morties"], JSON_UNESCAPED_SLASHES)
            : json_encode([], JSON_UNESCAPED_SLASHES);
		
		if (isset($payload["placement"][0], $payload["placement"][1])) {
            $placement = $payload["placement"][0] . "," . $payload["placement"][1];
        }
    }
	
	// ---------------- RAID EVENT ----------------
    if ($event === "shard:raid-boss-state-changed") {
		// ALWAYS preserve original payload
    	$get_current_raid = json_encode($payload, JSON_UNESCAPED_SLASHES);
	}
	
	// ---------------- ROOM USER ADDED ----------------
    if ($event === "room:user-added") {
		// ALWAYS preserve original payload
		$room_id = $payload["room_id"] ?? null;
		$player_id = $payload["player_id"] ?? null;
		$state = $payload["state"] ?? null;
    }
	
	// ---------------- ROOM USER LEFT ----------------
    if ($event === "room:user-removed") {
		// ALWAYS preserve original payload
		$player_id = $payload["player_id"] ?? null;
    }
	
	// ---------------- WILD MORTY STATE CHANGE ----------------
    if ($event === "room:wild-morty-state-changed") {
		$wild_morty_id = $payload["wild_morty_id"] ?? null;
		$state = $payload["state"] ?? null;
    }
	
	// ---------------- USER ROOM STATE CHANGE ----------------
    if ($event === "room:user-state-changed") {
		$player_id = $payload["player_id"] ?? null;
		$state = $payload["state"] ?? null;
    }
	
	 // ---------------- BATTLE START ----------------
    if ($event === "battle:start") {
		// ALWAYS preserve original payload
    	$battle_start = json_encode($payload, JSON_UNESCAPED_SLASHES);
		$only_show_to_player_id = $player_id;
	}

	// ---------------- BATTLE TURN ----------------
    if ($event === "battle:turn-result") {
		// ALWAYS preserve original payload
    	$battle_turn_result = json_encode($payload, JSON_UNESCAPED_SLASHES);
    }
	
	// ---------------- BATTLE TIMER ----------------
    if ($event === "battle:move-timer-started") {
		// ALWAYS preserve original payload
        $battle_move_timer_started = json_encode($payload, JSON_UNESCAPED_SLASHES);
    }
	
	// ---------------- ROOM EMOTE ----------------
    if ($event === "emote:room") {
		$player_id = $payload["player_id"] ?? null;
		$emote = $payload["emote"] ?? null;
    }
	
	

    // ---------------- SAFE INSERT ----------------
    $stmt = $pdo->prepare("
        INSERT INTO event_queue (
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
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)");

    $stmt->execute([
        $room_id,
        $event,
		$player_id,
		$emote,
		$get_current_raid,
		$battle_start,
		$battle_turn_result,
		$battle_move_timer_started,
		$bot_id,
		$username,
		$player_avatar_id,
		$wild_morty_id,
		$morty_id,
		$placement,
		$state,
		$division,
		$zone_id,
		$variant,
		$shiny_if_potion,
        $pickup_id,
		$pick_up_contents,
		$owned_morties,
		$only_show_to_player_id
    ]);
}

/**
 * SSE helper
 */
function sse_send(string $event, string $dataJson, ?int $id = null): void {
    echo "event: {$event}\n";
    echo "data: {$dataJson}\n\n";
    @ob_flush();
    @flush();
}
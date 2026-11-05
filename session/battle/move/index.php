<?php
// PvWM lifecycle; combat numbers remain explicit legacy placeholders.
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
require __DIR__ . '/../../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../../lib/events.php';
require_once __DIR__ . '/../../../lib/battle_turn.php';
require_once __DIR__ . '/../../../lib/battle_items.php';
require_once __DIR__ . '/../../../lib/battle_timeouts.php';

$body = json_input();
foreach (['session_id', 'battle_id', 'type'] as $key) {
    if (!is_string($body[$key] ?? null) || $body[$key] === '') respond(400, ['success' => false, 'error' => ['code' => 'FAILED']]);
}
foreach (['owned_morty_id', 'move_id'] as $key) {
    // Android sends move_id:null for RUN; ATTACK/SWITCH require both strings.
    if (isset($body[$key]) && !is_string($body[$key])) respond(400, ['success' => false, 'error' => ['code' => 'FAILED']]);
}
$session_id = $body['session_id'];
$battle_id = $body['battle_id'];
$type = $body['type'];
$owned_morty_id = $body['owned_morty_id'] ?? '';
$move_id = $body['move_id'] ?? '';
if (in_array($type, ['ATTACK', 'SWITCH'], true) && ($owned_morty_id === '' || $move_id === '')) respond(400, ['success' => false, 'error' => ['code' => 'FAILED']]);

try {
    $pdo->beginTransaction();
    // All battle paths lock the user first, then the battle.
    $stmt = $pdo->prepare('SELECT player_id, room_id, state FROM users WHERE session_id=? LIMIT 1 FOR UPDATE');
    $stmt->execute([$session_id]);
    $user = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$user) battle_reject(401);
    $player_id = (string)$user['player_id'];
    $stmt = $pdo->prepare('SELECT * FROM battles WHERE battle_id=? FOR UPDATE');
    $stmt->execute([$battle_id]);
    $battle = $stmt->fetch(PDO::FETCH_ASSOC);
    if (!$battle) battle_reject(404);
    if ((string)$battle['player_id'] !== $player_id) battle_reject(403);
    if ($battle['state'] !== 'ACTIVE') battle_reject(409);
    // A due selection wins before any HP/AP/stock validation or mutation.
    if (battle_timeout_expire_locked($pdo, $user, $battle)) {
        $pdo->commit();
        respond(409, ['success' => false, 'error' => ['code' => 'FAILED']]);
    }
    if ($type === 'ITEM') {
        if ($move_id === '') battle_reject(400);
        // Capture/unsupported items retain their legacy rejection before origin checks.
        if (!battle_supported_item($move_id)) battle_reject(501, 'ITEM_UNUSABLE');
        if ($owned_morty_id === '') battle_reject(400);
    }
    if (!in_array($type, ['ATTACK', 'SWITCH', 'RUN', 'ITEM'], true)) battle_reject(400);

    $morty = null;
    $attack = null;
    if ($type !== 'RUN') {
        $current_id = $type === 'ITEM' ? (string)$battle['player_active_morty'] : $owned_morty_id;
        if ($current_id !== (string)$battle['player_active_morty']) {
            if ($type === 'SWITCH') {
                $stmt = $pdo->prepare('SELECT player_id FROM owned_morties WHERE owned_morty_id=? ORDER BY id FOR UPDATE');
                $stmt->execute([$owned_morty_id]);
                $outgoing = $stmt->fetchAll(PDO::FETCH_ASSOC);
                if (count($outgoing) > 1 || (count($outgoing) === 1 && (string)$outgoing[0]['player_id'] === $player_id)) battle_reject(409);
            }
            battle_reject(403);
        }
        // owned_attacks has no owner column: a globally ambiguous Morty ID is unsafe.
        $stmt = $pdo->prepare('SELECT * FROM owned_morties WHERE owned_morty_id=? ORDER BY id FOR UPDATE');
        $stmt->execute([$current_id]);
        $morties = $stmt->fetchAll(PDO::FETCH_ASSOC);
        if (!$morties) battle_reject(409);
        $owned = array_filter($morties, fn($row) => (string)$row['player_id'] === $player_id);
        if (!$owned) battle_reject(403);
        if (count($morties) !== 1) battle_reject(409);
        $morty = $morties[0];
        if (!battle_valid_hp($morty) || (int)$morty['hp'] !== (int)$battle['player_hp']) battle_reject(409);
        if ($type === 'ITEM' && (int)$morty['hp'] <= 0) battle_reject(409);
    }
    if ($type === 'RUN' ? !in_array($user['state'], ['WORLD', 'BATTLE'], true) : $user['state'] !== 'BATTLE') battle_reject(409);
    $room_id = battle_origin($pdo, $battle, $player_id, (string)($user['room_id'] ?? ''), $start);
    $roster = battle_snapshot_roster($start, (string)$battle['player_active_morty']);
    $party = [];
    if ($type !== 'RUN') {
        if ($type === 'ITEM') {
            if ($roster === null) battle_reject(409);
            if (!in_array($owned_morty_id, $roster, true)) battle_reject(403);
            $stmt = $pdo->prepare('SELECT player_id FROM owned_morties WHERE owned_morty_id=? ORDER BY id FOR UPDATE');
            $stmt->execute([$owned_morty_id]);
            $targets = $stmt->fetchAll(PDO::FETCH_ASSOC);
            if ($targets && !array_filter($targets, fn($row) => (string)$row['player_id'] === $player_id)) battle_reject(403);
        }
        if ($type === 'SWITCH') {
            if ($roster === null) battle_reject(409);
            if ($move_id === $owned_morty_id) battle_reject(409);
            if (!in_array($move_id, $roster, true)) battle_reject(403);
            // Report explicit target ownership failures before generic roster damage.
            $stmt = $pdo->prepare('SELECT player_id FROM owned_morties WHERE owned_morty_id=? ORDER BY id FOR UPDATE');
            $stmt->execute([$move_id]);
            $targets = $stmt->fetchAll(PDO::FETCH_ASSOC);
            if ($targets && !array_filter($targets, fn($row) => (string)$row['player_id'] === $player_id)) battle_reject(403);
        }
        $party = battle_lock_party($pdo, $roster ?? [$owned_morty_id], $player_id);
        if ($type === 'SWITCH' && (int)$party[$move_id]['hp'] <= 0) battle_reject(409);
    }
    if ($type === 'ATTACK') {
        if ((int)$morty['hp'] <= 0) battle_reject(409);
        $stmt = $pdo->prepare('SELECT id, pp FROM owned_attacks WHERE owned_morty_id=? AND attack_id=? FOR UPDATE');
        $stmt->execute([$owned_morty_id, $move_id]);
        $attacks = $stmt->fetchAll(PDO::FETCH_ASSOC);
        if (!$attacks) battle_reject(400);
        if (count($attacks) !== 1 || (int)$attacks[0]['pp'] <= 0) battle_reject(409);
        $attack = $attacks[0];
    }
    $spawn = (string)$battle['opponent_active_morty'];
    // Do not release or damage a spawn simultaneously claimed by another legacy
    // ACTIVE row. Ambiguous historical battles require evidence before repair.
    $stmt = $pdo->prepare("SELECT battle_id FROM battles WHERE opponent_active_morty=? AND state='ACTIVE' AND battle_id<>? FOR UPDATE");
    $stmt->execute([$spawn, $battle_id]);
    if ($stmt->fetch()) battle_reject(409);
    // Old starts left the snapshot WORLD; a verified RUN can still release them.
    battle_lock_spawn($pdo, $room_id, $spawn, $player_id, $type === 'RUN' ? ['WORLD', 'BATTLE'] : 'BATTLE');

    $player_hp = (int)$battle['player_hp'];
    $enemy_hp = (int)$battle['opponent_hp'];
    $turn_datas = [];
    $outcome = $type === 'RUN' ? 'RUN' : 'CONTINUE';
    $active_id = (string)$battle['player_active_morty'];
    $forced_switch = $type === 'SWITCH' && $player_hp === 0 && (int)$morty['hp'] === 0;
    $item_result = null;
    if ($type === 'ITEM') {
        if ($enemy_hp <= 0) battle_reject(409);
        $item_result = battle_apply_item($pdo, $player_id, (string)$battle['opponent_id'], $owned_morty_id, $move_id, $party);
        $turn_datas[] = $item_result['action'];
        $morty = $party[$active_id];
        $player_hp = (int)$morty['hp'];
    }
    if ($type === 'SWITCH') {
        if ($enemy_hp <= 0) battle_reject(409);
        $active_id = $move_id;
        $morty = $party[$active_id];
        $player_hp = (int)$morty['hp'];
        $turn_datas[] = [
            'type' => 'SWITCH', 'attacker_player_id' => $player_id, 'owned_morty_id' => $active_id,
            'defender_player_id' => (string)$battle['opponent_id'],
            'attacker_morty_datas' => [[
                'owned_morty_id' => $active_id, 'hp' => $player_hp,
                'is_poisoned' => (bool)$morty['is_poisoned'], 'is_paralysed' => (bool)$morty['is_paralysed'],
            ]],
            'defender_morty_datas' => [],
        ];
    }
    if ($type === 'ATTACK') {
        if ($enemy_hp <= 0) battle_reject(409);
        $pp = (int)$attack['pp'] - 1;
        $enemy_hp = max(0, $enemy_hp - 20);
        $turn_datas[] = battle_attack_data($player_id, (string)$battle['opponent_id'], $move_id, $owned_morty_id, $spawn, 20, $enemy_hp, $pp);
        if ($enemy_hp === 0) {
            $outcome = 'WIN';
        }
        $pdo->prepare('UPDATE owned_attacks SET pp=? WHERE id=?')->execute([$pp, $attack['id']]);
    }
    // Replacement policy: an item or voluntary switch consumes the player's action;
    // the placeholder AI attacks the current Morty. Forced replacement
    // only selects a survivor; original game's initiative/turn cost is unverified.
    if (($type === 'ATTACK' && $outcome !== 'WIN') || ($type === 'SWITCH' && !$forced_switch) || $type === 'ITEM') {
        $damage = random_int(1, 3);
        $player_hp = max(0, $player_hp - $damage);
        $ai_move = ['AttackBatteringRam', 'AttackVileSpew'][random_int(0, 1)];
        // Wild AI PP remains a legacy placeholder: no owned wild attack rows exist.
        $turn_datas[] = battle_attack_data((string)$battle['opponent_id'], $player_id, $ai_move, $spawn, $active_id, $damage, $player_hp, 1);
        if ($player_hp === 0) {
            $living = array_filter($party, fn($row) => (string)$row['owned_morty_id'] !== $active_id && (int)$row['hp'] > 0);
            $outcome = $living ? 'FORCE_SWITCH' : 'LOSE';
        }
        $pdo->prepare('UPDATE owned_morties SET hp=? WHERE id=? AND player_id=?')->execute([$player_hp, $morty['id'], $player_id]);
    }
    $terminal = in_array($outcome, ['RUN', 'WIN', 'LOSE'], true);
    $state = $outcome === 'RUN' ? 'CANCELLED' : ($terminal ? 'COMPLETED' : 'ACTIVE');
    $winner = $outcome === 'WIN' ? $player_id : ($outcome === 'LOSE' ? $battle['opponent_id'] : null);
    $pdo->prepare('UPDATE battles SET player_active_morty=?, player_hp=?, opponent_hp=?, state=?, winner=?, move_deadline=NULL WHERE battle_id=?')->execute([$active_id, $player_hp, $enemy_hp, $state, $winner, $battle_id]);
    if ($terminal) {
        $pdo->prepare("UPDATE users SET state='WORLD' WHERE player_id=?")->execute([$player_id]);
        if ($outcome === 'WIN') {
            $pdo->prepare("DELETE FROM event_queue WHERE room_id=? AND event_name='room:wild-morty-added' AND wild_morty_id=?")->execute([$room_id, $spawn]);
            publish_event($pdo, $room_id, 'room:wild-morty-removed', ['wild_morty_id' => $spawn]);
        } else {
            $pdo->prepare("UPDATE event_queue SET state='WORLD' WHERE room_id=? AND event_name='room:wild-morty-added' AND wild_morty_id=?")->execute([$room_id, $spawn]);
            publish_event($pdo, $room_id, 'room:wild-morty-state-changed', ['wild_morty_id' => $spawn, 'state' => 'WORLD']);
        }
        publish_event($pdo, $room_id, 'room:user-state-changed', ['player_id' => $player_id, 'state' => 'WORLD']);
    }
    $player_data = ['move_log' => [
        'cooldown' => $type === 'RUN' ? ['ATTACK' => 0, 'RUN' => 0] : [$type => 0],
        'count' => $type === 'RUN' ? ['ATTACK' => 0, 'RUN' => 1] : [$type => 1],
        'cooldown_next' => ['ITEM' => 1], 'last_move_type' => $type,
    ]];
    if ($item_result !== null) $player_data['owned_items'] = [$item_result['owned_item']];
    if ($terminal) $player_data['attacks_to_learn'] = [];
    if ($outcome === 'WIN') {
        // Reward/stat formulas are unverified: never promise unsaved gains.
        $player_data['xp_datas'] = [];
        $player_data['rewards'] = [];
    }
    $payload = ['battle_id' => $battle_id, 'outcome' => $outcome, 'turn_datas' => $turn_datas,
        'player_datas' => ['player' => $player_data, 'opponent' => (object)[]]];
    if ($outcome === 'RUN') $payload['battle_abandoned'] = true;
    publish_event($pdo, $room_id, 'battle:turn-result', $payload, $player_id);
    $pdo->commit();
    respond(200, ['success' => true]);
} catch (Throwable $e) {
    if ($pdo->inTransaction()) $pdo->rollBack();
    $status = battle_error_status($e);
    if ($status === 500) error_log((string)$e);
    respond($status, ['success' => false, 'error' => ['code' => $status === 501 ? 'ITEM_UNUSABLE' : 'FAILED']]);
}

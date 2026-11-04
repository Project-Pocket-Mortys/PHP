<?php
// PvWM lifecycle; combat numbers remain explicit legacy placeholders.
header('Content-Type: application/json; charset=utf-8');
header('Access-Control-Allow-Origin: *');
require __DIR__ . '/../../../pocket_f4894h398r8h9w9er8he98he.php';
require_once __DIR__ . '/../../../lib/events.php';
require_once __DIR__ . '/../../../lib/battle_turn.php';

$body = json_input();
foreach (['session_id', 'battle_id', 'type'] as $key) {
    if (!is_string($body[$key] ?? null) || $body[$key] === '') respond(400, ['success' => false, 'error' => ['code' => 'FAILED']]);
}
foreach (['owned_morty_id', 'move_id'] as $key) {
    // Android sends move_id:null for RUN. ATTACK still requires both strings.
    if (isset($body[$key]) && !is_string($body[$key])) respond(400, ['success' => false, 'error' => ['code' => 'FAILED']]);
}
$session_id = $body['session_id'];
$battle_id = $body['battle_id'];
$type = $body['type'];
$owned_morty_id = $body['owned_morty_id'] ?? '';
$move_id = $body['move_id'] ?? '';
if ($type === 'ATTACK' && ($owned_morty_id === '' || $move_id === '')) respond(400, ['success' => false, 'error' => ['code' => 'FAILED']]);

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
    // Capture has no trustworthy stat/attack source yet. Never consume or fabricate it.
    if ($type === 'ITEM') battle_reject(501, 'ITEM_UNUSABLE');
    if (!in_array($type, ['ATTACK', 'RUN'], true)) battle_reject(400);

    $morty = null;
    $attack = null;
    if ($type === 'ATTACK') {
        if ($owned_morty_id !== (string)$battle['player_active_morty']) battle_reject(403);
        // owned_attacks has no owner column: a globally ambiguous Morty ID is unsafe.
        $stmt = $pdo->prepare('SELECT id, player_id, hp FROM owned_morties WHERE owned_morty_id=? FOR UPDATE');
        $stmt->execute([$owned_morty_id]);
        $morties = $stmt->fetchAll(PDO::FETCH_ASSOC);
        $owned = array_filter($morties, fn($row) => (string)$row['player_id'] === $player_id);
        if (!$owned) battle_reject(403);
        if (count($morties) !== 1) battle_reject(409);
        $morty = $morties[0];
        $stmt = $pdo->prepare('SELECT id, pp FROM owned_attacks WHERE owned_morty_id=? AND attack_id=? FOR UPDATE');
        $stmt->execute([$owned_morty_id, $move_id]);
        $attacks = $stmt->fetchAll(PDO::FETCH_ASSOC);
        if (!$attacks) battle_reject(400);
        if (count($attacks) !== 1 || (int)$attacks[0]['pp'] <= 0) battle_reject(409);
        $attack = $attacks[0];
        if ((int)$morty['hp'] <= 0 || (int)$morty['hp'] !== (int)$battle['player_hp']) battle_reject(409);
    }
    if ($type === 'ATTACK' ? $user['state'] !== 'BATTLE' : !in_array($user['state'], ['WORLD', 'BATTLE'], true)) battle_reject(409);
    $room_id = battle_origin($pdo, $battle, $player_id, (string)($user['room_id'] ?? ''));
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
    if ($type === 'ATTACK') {
        if ($enemy_hp <= 0) battle_reject(409);
        $pp = (int)$attack['pp'] - 1;
        $enemy_hp = max(0, $enemy_hp - 20);
        $turn_datas[] = battle_attack_data($player_id, (string)$battle['opponent_id'], $move_id, $owned_morty_id, $spawn, 20, $enemy_hp, $pp);
        if ($enemy_hp === 0) {
            $outcome = 'WIN';
        } else {
            $damage = random_int(1, 3);
            $player_hp = max(0, $player_hp - $damage);
            $ai_move = ['AttackBatteringRam', 'AttackVileSpew'][random_int(0, 1)];
            // Wild AI PP remains a legacy placeholder: no owned wild attack rows exist.
            $turn_datas[] = battle_attack_data((string)$battle['opponent_id'], $player_id, $ai_move, $spawn, $owned_morty_id, $damage, $player_hp, 1);
            // SWITCH is unsupported: the sole active Morty fainting is legacy defeat.
            if ($player_hp === 0) $outcome = 'LOSE';
        }
        $pdo->prepare('UPDATE owned_attacks SET pp=? WHERE id=?')->execute([$pp, $attack['id']]);
        $pdo->prepare('UPDATE owned_morties SET hp=? WHERE id=? AND player_id=?')->execute([$player_hp, $morty['id'], $player_id]);
    }
    $terminal = $outcome !== 'CONTINUE';
    $state = $outcome === 'RUN' ? 'CANCELLED' : ($terminal ? 'COMPLETED' : 'ACTIVE');
    $winner = $outcome === 'WIN' ? $player_id : ($outcome === 'LOSE' ? $battle['opponent_id'] : null);
    $pdo->prepare('UPDATE battles SET player_hp=?, opponent_hp=?, state=?, winner=? WHERE battle_id=?')->execute([$player_hp, $enemy_hp, $state, $winner, $battle_id]);
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
        'cooldown' => $type === 'RUN' ? ['ATTACK' => 0, 'RUN' => 0] : ['ATTACK' => 0],
        'count' => $type === 'RUN' ? ['ATTACK' => 0, 'RUN' => 1] : ['ATTACK' => 1],
        'cooldown_next' => ['ITEM' => 1], 'last_move_type' => $type,
    ]];
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

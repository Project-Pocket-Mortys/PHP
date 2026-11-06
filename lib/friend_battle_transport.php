<?php
declare(strict_types=1);
require_once __DIR__ . '/friends.php';

function friend_battle_transport_enabled(): bool {
    return getenv('PM_RESEARCH_SHARED_BATTLE_STREAM') === '1';
}

/** Research policy: a stream must poll within ten seconds to remain live. */
function friend_battle_transport_seconds(): int { return 10; }

function friend_transport_error(PDO $pdo, Throwable $error): never {
    if ($pdo->inTransaction()) $pdo->rollBack();
    if ($error instanceof FriendError) throw $error;
    if ($error instanceof JsonException || $error instanceof MortyReleaseError) friend_fail(409,'FAILED');
    error_log('Shared battle transport failed: '.get_class($error));
    friend_fail(500,'FAILED');
}

/** Single-user lock is never retained while acquiring a pair lock. */
function friend_transport_lock_user(PDO $pdo, string $session, string $player): array {
    $actor=friend_auth($pdo,$session);
    if ($actor['player_id']!==$player) friend_fail(403,'TOKEN_NOTVALID');
    $pdo->beginTransaction();
    $query=$pdo->prepare('SELECT * FROM users WHERE player_id=? FOR UPDATE');
    $query->execute([$player]); $users=$query->fetchAll(PDO::FETCH_ASSOC);
    if (count($users)!==1 || $users[0]['session_id']!==$session || friend_auth($pdo,$session)['player_id']!==$player) friend_fail(401,'NOT_AUTHENTICATED');
    return $users[0];
}

function friend_transport_stream(PDO $pdo, string $player): ?array {
    $seconds=friend_battle_transport_seconds();
    $query=$pdo->prepare("SELECT *,heartbeat_at>UTC_TIMESTAMP(6)-INTERVAL $seconds SECOND AND heartbeat_at<=UTC_TIMESTAMP(6) AS live FROM friend_battle_streams WHERE player_id=?");
    $query->execute([$player]); return $query->fetch(PDO::FETCH_ASSOC) ?: null;
}

function friend_transport_current(?array $stream, string $streamId, string $session): bool {
    return $stream!==null && $stream['stream_id']===$streamId && hash_equals($stream['session_sha256'],hash('sha256',$session));
}

/** User lock protects this hint against activation and registration. */
function friend_transport_claim(PDO $pdo, string $player): ?array {
    $query=$pdo->prepare('SELECT s.* FROM friend_battle_memberships m JOIN friend_battle_sessions s ON s.battle_id=m.battle_id WHERE m.player_id=?');
    $query->execute([$player]); $rows=$query->fetchAll(PDO::FETCH_ASSOC);
    if (count($rows)>1) friend_fail(409,'FAILED');
    return $rows[0] ?? null;
}

function friend_battle_transport_open(PDO $pdo, string $session, string $player): string {
    if (!friend_battle_transport_enabled()) return '';
    if ($pdo->inTransaction()) throw new LogicException('Standalone stream registration required');
    try {
        for ($retry=0;$retry<3;$retry++) {
            friend_transport_lock_user($pdo,$session,$player);
            $claim=friend_transport_claim($pdo,$player);
            if ($claim && in_array($claim['state'],['STARTING','READY'],true)) {
                $pdo->rollBack();
                friend_battle_startup_cancel($pdo,$session,$claim['battle_id']);
                continue;
            }
            $streamId=friend_battle_invite_id();
            $query=$pdo->prepare('INSERT INTO friend_battle_streams (player_id,stream_id,session_sha256,opened_at,heartbeat_at) VALUES (?,?,?,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6)) ON DUPLICATE KEY UPDATE stream_id=VALUES(stream_id),session_sha256=VALUES(session_sha256),opened_at=VALUES(opened_at),heartbeat_at=VALUES(heartbeat_at)');
            $query->execute([$player,$streamId,hash('sha256',$session)]);
            $pdo->commit(); return $streamId;
        }
        friend_fail(409,'FAILED');
    } catch (Throwable $error) { friend_transport_error($pdo,$error); }
}

/** Activation holds both users; these immutable bindings cannot follow a reconnect. */
function friend_battle_transport_bind_locked(PDO $pdo, array $row, array $users): void {
    if (!friend_battle_transport_enabled()) return;
    if (!$pdo->inTransaction() || count($users)!==2) throw new LogicException('Locked pair required');
    $query=$pdo->prepare('SELECT 1 FROM friend_battle_stream_bindings WHERE battle_id=? LIMIT 1');
    $query->execute([$row['battle_id']]); if ($query->fetchColumn()!==false) friend_fail(409,'FAILED');
    $players=[$row['sender_id'],$row['recipient_id']]; sort($players,SORT_STRING);
    $insert=$pdo->prepare('INSERT INTO friend_battle_stream_bindings (battle_id,player_id,stream_id,session_sha256,bound_at) VALUES (?,?,?,?,UTC_TIMESTAMP(6))');
    foreach ($players as $player) {
        $user=$users[$player] ?? null; $stream=friend_transport_stream($pdo,$player);
        if (!$user || !$stream || !(bool)$stream['live'] || !is_string($user['session_id']) || $user['session_id']===''
            || !hash_equals($stream['session_sha256'],hash('sha256',$user['session_id']))) friend_fail(409,'FAILED');
        if (friend_auth($pdo,$user['session_id'])['player_id']!==$player) friend_fail(409,'FAILED');
        // A native connection carries one startup only; terminal generations need a fresh open.
        $query=$pdo->prepare('SELECT 1 FROM friend_battle_stream_bindings WHERE player_id=? AND stream_id=? LIMIT 1');
        $query->execute([$player,$stream['stream_id']]);
        if ($query->fetchColumn()!==false) friend_fail(409,'FAILED');
        $insert->execute([$row['battle_id'],$player,$stream['stream_id'],$stream['session_sha256']]);
    }
}

/** Returns false for a missing, replaced, revoked or stale participant stream. */
function friend_transport_bindings_live(PDO $pdo, array $row, array $users): bool {
    $query=$pdo->prepare('SELECT * FROM friend_battle_stream_bindings WHERE battle_id=? ORDER BY player_id');
    $query->execute([$row['battle_id']]); $bindings=$query->fetchAll(PDO::FETCH_ASSOC);
    if (count($bindings)!==2) return false;
    $seen=[];
    foreach ($bindings as $binding) {
        $player=$binding['player_id']; $user=$users[$player] ?? null;
        if (!$user || isset($seen[$player]) || !in_array($player,[$row['sender_id'],$row['recipient_id']],true)) return false;
        $seen[$player]=true; $stream=friend_transport_stream($pdo,$player);
        if (!$stream || !(bool)$stream['live'] || !is_string($user['session_id']) || $user['session_id']===''
            || !friend_transport_current($stream,$binding['stream_id'],$user['session_id'])
            || !hash_equals($binding['session_sha256'],$stream['session_sha256'])) return false;
        try {
            if (friend_auth($pdo,$user['session_id'])['player_id']!==$player) return false;
        } catch (FriendError $error) { return false; }
    }
    return true;
}

function friend_battle_transport_ready_locked(PDO $pdo, array $row, array $user): void {
    if (!friend_battle_transport_enabled()) return;
    if (!$pdo->inTransaction()) throw new LogicException('Locked pair required');
    $query=$pdo->prepare('SELECT * FROM users WHERE player_id IN (?,?) ORDER BY player_id');
    $query->execute([$row['sender_id'],$row['recipient_id']]); $users=[];
    foreach ($query->fetchAll(PDO::FETCH_ASSOC) as $participant) $users[$participant['player_id']]=$participant;
    if (!friend_transport_bindings_live($pdo,$row,$users)) friend_fail(409,'FAILED');
    $query=$pdo->prepare('SELECT a.delivery_id FROM friend_battle_start_attempts a JOIN friend_battle_stream_bindings b ON b.battle_id=a.battle_id AND b.player_id=a.player_id AND b.stream_id=a.stream_id JOIN friend_battle_start_intents i ON i.battle_id=a.battle_id AND i.player_id=a.player_id AND i.delivery_id=a.delivery_id WHERE a.battle_id=? AND a.player_id=? AND i.retired_at IS NULL');
    $query->execute([$row['battle_id'],$user['player_id']]);
    if ($query->fetchColumn()===false) friend_fail(409,'FAILED');
}

/** Native EOF ends this stream. No retry/replay or guaranteed-receipt claim. */
function friend_battle_transport_poll(PDO $pdo, string $session, string $player, string $streamId): array {
    $empty=['close'=>false,'events'=>[]]; $closed=['close'=>true,'events'=>[]];
    $ended=['close'=>true,'events'=>[['event'=>'session:end','payload'=>(object)[]]]];
    if (!friend_battle_transport_enabled()) return $empty;
    if ($pdo->inTransaction()) throw new LogicException('Standalone stream poll required');
    try {
        // Read hints only. Release the single-user transaction before taking pair locks.
        friend_transport_lock_user($pdo,$session,$player);
        if (!friend_transport_current(friend_transport_stream($pdo,$player),$streamId,$session)) { $pdo->commit(); return $closed; }
        $query=$pdo->prepare('SELECT s.* FROM friend_battle_stream_bindings b JOIN friend_battle_sessions s ON s.battle_id=b.battle_id WHERE b.player_id=? AND b.stream_id=? ORDER BY b.bound_at DESC');
        $query->execute([$player,$streamId]); $bound=$query->fetchAll(PDO::FETCH_ASSOC);
        if (count($bound)>1) friend_fail(409,'FAILED');
        $hint=$bound[0] ?? friend_transport_claim($pdo,$player);
        if (!$hint || $hint['state']==='PREPARING') {
            $pdo->prepare('UPDATE friend_battle_streams SET heartbeat_at=UTC_TIMESTAMP(6) WHERE player_id=? AND stream_id=?')->execute([$player,$streamId]);
            $pdo->commit(); return $empty;
        }
        if (!in_array($hint['state'],['STARTING','READY'],true)) { $pdo->commit(); return $bound ? $ended : $closed; }
        $pdo->rollBack();
        [$row,$self,$peer]=friend_startup_lock($pdo,$session,$hint['battle_id']);
        // Generation fence precedes every cleanup: old streams cannot cancel new starts.
        $own=friend_transport_stream($pdo,$player);
        if ($self['player_id']!==$player || !friend_transport_current($own,$streamId,$session)) { $pdo->commit(); return $closed; }
        if (!in_array($row['state'],['STARTING','READY'],true)) { $pdo->commit(); return $ended; }
        $users=[$self['player_id']=>$self,$peer['player_id']=>$peer];
        $startup=friend_startup_validate_active($pdo,$row,$users,false);
        if (!(bool)$startup['live'] || !friend_transport_bindings_live($pdo,$row,$users)) {
            friend_startup_cancel_locked($pdo,$row,$users,!(bool)$startup['live']?'STARTUP_TIMEOUT':'STARTUP_CANCELLED');
            $pdo->commit(); return $ended;
        }
        $query=$pdo->prepare('SELECT * FROM friend_battle_stream_bindings WHERE battle_id=? AND player_id=?');
        $query->execute([$row['battle_id'],$player]); $binding=$query->fetch(PDO::FETCH_ASSOC);
        if (!$binding || $binding['stream_id']!==$streamId || !hash_equals($binding['session_sha256'],hash('sha256',$session))) friend_fail(409,'FAILED');
        $pdo->prepare('UPDATE friend_battle_streams SET heartbeat_at=UTC_TIMESTAMP(6) WHERE player_id=? AND stream_id=?')->execute([$player,$streamId]);
        $query=$pdo->prepare('SELECT * FROM friend_battle_start_attempts WHERE battle_id=? AND player_id=?');
        $query->execute([$row['battle_id'],$player]); $attempt=$query->fetch(PDO::FETCH_ASSOC);
        $query=$pdo->prepare('SELECT delivery_id,payload_json FROM friend_battle_start_intents WHERE battle_id=? AND player_id=? AND retired_at IS NULL');
        $query->execute([$row['battle_id'],$player]); $intent=$query->fetch(PDO::FETCH_ASSOC);
        if (!$intent) friend_fail(409,'FAILED');
        if ($attempt) {
            if ($attempt['stream_id']!==$streamId || $attempt['delivery_id']!==$intent['delivery_id']) friend_fail(409,'FAILED');
            $pdo->commit(); return $empty;
        }
        $ready=$player===$row['sender_id']?'sender_ready_at':'recipient_ready_at';
        if ($startup[$ready]!==null) friend_fail(409,'FAILED');
        $payload=json_decode($intent['payload_json'],false,512,JSON_THROW_ON_ERROR);
        $query=$pdo->prepare('INSERT INTO friend_battle_start_attempts (battle_id,player_id,delivery_id,stream_id,attempted_at) VALUES (?,?,?,?,UTC_TIMESTAMP(6))');
        $query->execute([$row['battle_id'],$player,$intent['delivery_id'],$streamId]);
        // Slow writes must not commit a publication attempt beyond either live lease.
        friend_startup_record_locked($pdo,$row,true);
        if (!friend_transport_bindings_live($pdo,$row,$users)) friend_fail(409,'FAILED');
        // The durable marker precedes publication; a crash may lose this event forever.
        $pdo->commit(); return ['close'=>false,'events'=>[['event'=>'battle:start','payload'=>$payload]]];
    } catch (Throwable $error) { friend_transport_error($pdo,$error); }
}

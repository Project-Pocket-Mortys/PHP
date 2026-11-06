<?php
declare(strict_types=1);
require_once __DIR__ . '/friend_battle_start_views.php';

/** Replacement-server startup lease; never interpreted as a combat timer. */
function friend_battle_startup_seconds(): int {
    $value=getenv('PM_FRIEND_BATTLE_STARTUP_SECONDS');
    if ($value===false || $value==='') return 30;
    $seconds=filter_var($value,FILTER_VALIDATE_INT,['options'=>['min_range'=>10,'max_range'=>120]]);
    if ($seconds===false) throw new RuntimeException('Invalid startup lifetime');
    return $seconds;
}

/** Hint lookup outside a fresh transaction; all authority is rechecked after pair locks. */
function friend_startup_lock(PDO $pdo, string $session, string $battleId): array {
    $actor=friend_auth($pdo,$session);
    $query=$pdo->prepare('SELECT * FROM friend_battle_sessions WHERE battle_id=?');
    $query->execute([$battleId]); $hint=$query->fetch(PDO::FETCH_ASSOC);
    if (!$hint || !in_array($actor['player_id'],[$hint['sender_id'],$hint['recipient_id']],true)) friend_fail(403,'TOKEN_NOTVALID');
    if ($hint['sender_id']===$hint['recipient_id']) friend_fail(409,'FAILED');
    $other=$hint[$actor['player_id']===$hint['sender_id']?'recipient_id':'sender_id'];
    [$self,$peer,$friend]=friend_lock_pair($pdo,$session,$other);
    $query=$pdo->prepare('SELECT *,prepare_deadline>UTC_TIMESTAMP(6) AS preparation_live FROM friend_battle_sessions WHERE battle_id=? FOR UPDATE');
    $query->execute([$battleId]); $row=$query->fetch(PDO::FETCH_ASSOC);
    if (!$row || $row['sender_id']!==$hint['sender_id'] || $row['recipient_id']!==$hint['recipient_id']
        || $self['player_id']!==$actor['player_id']) friend_fail(409,'FAILED');
    return [$row,$self,$peer,$friend];
}

function friend_startup_invite_locked(PDO $pdo, array $row, string $state): array {
    $query=$pdo->prepare('SELECT *,expires_at>UTC_TIMESTAMP(6) AS live FROM friend_battle_invites WHERE invite_id=? FOR UPDATE');
    $query->execute([$row['invite_id']]); $invite=$query->fetch(PDO::FETCH_ASSOC);
    if (!$invite || $invite['sender_id']!==$row['sender_id'] || $invite['recipient_id']!==$row['recipient_id']
        || $invite['state']!==$state || ($state==='PENDING' && !(bool)$invite['live'])) friend_fail(409,'FAILED');
    return $invite;
}

function friend_startup_no_legacy(PDO $pdo, array $row): void {
    $query=$pdo->prepare("SELECT 1 FROM battles WHERE state='ACTIVE' AND (player_id IN (?,?) OR opponent_id IN (?,?)) LIMIT 1");
    $query->execute([$row['sender_id'],$row['recipient_id'],$row['sender_id'],$row['recipient_id']]);
    if ($query->fetchColumn()!==false) friend_fail(409,'FAILED');
}

/** Activation cannot reserve a stale party after an out-of-band storage change. */
function friend_startup_current_parties_locked(PDO $pdo, array $row, array $users): void {
    $stored=friend_party_load_stored($pdo,$row);
    if ($stored===null) friend_fail(409,'FAILED');
    $players=array_keys($users); sort($players,SORT_STRING);
    foreach ($players as $player) {
        $current=friend_party_capture_locked($pdo,$users[$player]);
        if (friend_start_json($current)!==friend_start_json($stored[$player])) friend_fail(409,'FAILED');
    }
}

/** Validate immutable recipient intents against already captured, validated views. */
function friend_startup_intents_locked(PDO $pdo, array $row, array $views, bool $retired=false): array {
    $query=$pdo->prepare('SELECT * FROM friend_battle_start_intents WHERE battle_id=? ORDER BY player_id');
    $query->execute([$row['battle_id']]); $intents=$query->fetchAll(PDO::FETCH_ASSOC);
    if (count($intents)!==2) friend_fail(409,'FAILED');
    $expected=[$row['sender_id']=>$views['sender'],$row['recipient_id']=>$views['recipient']]; $seen=[];
    foreach ($intents as $intent) {
        $player=$intent['player_id'];
        if (!isset($expected[$player]) || isset($seen[$player])
            || !preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/D',$intent['delivery_id'])
            || ($intent['retired_at']!==null)!==$retired
            || !hash_equals($intent['payload_sha256'],hash('sha256',$intent['payload_json']))
            || $intent['payload_json']!==friend_start_json($expected[$player])) friend_fail(409,'FAILED');
        $seen[$player]=true;
    }
    return $intents;
}

/** Both users and session are locked; nullable legacy deadlines fail closed. */
function friend_startup_record_locked(PDO $pdo, array $row, bool $requireLive): array {
    $query=$pdo->prepare('SELECT *,ready_deadline>UTC_TIMESTAMP(6) AS live,ready_deadline<=UTC_TIMESTAMP(6) AS due,
        (started_at<=UTC_TIMESTAMP(6) AND ready_deadline>=started_at+INTERVAL 10 SECOND AND ready_deadline<=started_at+INTERVAL 120 SECOND
        AND (sender_ready_at IS NULL OR (sender_ready_at>=started_at AND sender_ready_at<=ready_deadline AND sender_ready_at<=UTC_TIMESTAMP(6)))
        AND (recipient_ready_at IS NULL OR (recipient_ready_at>=started_at AND recipient_ready_at<=ready_deadline AND recipient_ready_at<=UTC_TIMESTAMP(6)))
        AND (ready_at IS NULL OR (ready_at>=sender_ready_at AND ready_at>=recipient_ready_at AND ready_at<=ready_deadline AND ready_at<=UTC_TIMESTAMP(6)))) AS coherent
        FROM friend_battle_startups WHERE battle_id=? FOR UPDATE');
    $query->execute([$row['battle_id']]); $startup=$query->fetch(PDO::FETCH_ASSOC);
    if (!$startup || !in_array($row['state'],['STARTING','READY'],true)
        || $startup['cancelled_at']!==null || $startup['ready_deadline']===null
        || !(bool)$startup['coherent'] || ($requireLive && !(bool)$startup['live'])) friend_fail(409,'FAILED');
    $both=$startup['sender_ready_at']!==null && $startup['recipient_ready_at']!==null;
    if (($row['state']==='READY')!==$both || ($startup['ready_at']!==null)!==$both) friend_fail(409,'FAILED');
    return $startup;
}

function friend_startup_validate_active(PDO $pdo, array $row, array $users, bool $requireLive): array {
    if (!in_array($row['state'],['STARTING','READY'],true)) friend_fail(409,'FAILED');
    foreach ($users as $user) if ($user['state']!=='BATTLE') friend_fail(409,'FAILED');
    friend_battle_require_claims($pdo,$row);
    friend_startup_no_legacy($pdo,$row);
    friend_startup_invite_locked($pdo,$row,'ACCEPTED');
    $startup=friend_startup_record_locked($pdo,$row,$requireLive);
    $views=friend_start_views_locked($pdo,$row,$users,false);
    friend_startup_intents_locked($pdo,$row,$views);
    return $startup;
}

/** Internal only: stores publication intent; never publishes SSE or enables acceptance. */
function friend_battle_startup_activate(PDO $pdo, string $session, string $battleId): array {
    if ($pdo->inTransaction()) throw new LogicException('Standalone startup requires no transaction');
    try {
        [$row,$self,$peer,$friend]=friend_startup_lock($pdo,$session,$battleId);
        if ($self['player_id']!==$row['recipient_id']) friend_fail(403,'TOKEN_NOTVALID');
        $users=[$self['player_id']=>$self,$peer['player_id']=>$peer];
        if (in_array($row['state'],['STARTING','READY'],true)) {
            $startup=friend_startup_validate_active($pdo,$row,$users,true);
        } else {
            if ($row['state']!=='PREPARING' || !(bool)$row['preparation_live'] || !$friend || $friend['pending']!=='false'
                || $self['state']!=='WORLD' || $peer['state']!=='WORLD') friend_fail(409,'FAILED');
            friend_battle_require_claims($pdo,$row);
            friend_startup_no_legacy($pdo,$row);
            friend_startup_invite_locked($pdo,$row,'PENDING');
            $views=friend_start_views_locked($pdo,$row,$users,false);
            friend_startup_current_parties_locked($pdo,$row,$users);
            foreach (['friend_battle_startups','friend_battle_start_intents'] as $table) {
                $query=$pdo->prepare("SELECT 1 FROM $table WHERE battle_id=? LIMIT 1"); $query->execute([$battleId]);
                if ($query->fetchColumn()!==false) friend_fail(409,'FAILED');
            }
            $query=$pdo->prepare('INSERT INTO friend_battle_startups (battle_id,started_at,ready_deadline) VALUES (?,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6)+INTERVAL ? SECOND)');
            $query->execute([$battleId,friend_battle_startup_seconds()]);
            $insert=$pdo->prepare('INSERT INTO friend_battle_start_intents (battle_id,player_id,delivery_id,payload_json,payload_sha256,created_at) VALUES (?,?,?,?,?,UTC_TIMESTAMP(6))');
            $players=array_keys($users); sort($players,SORT_STRING);
            foreach ($players as $player) {
                $view=$views[$player===$row['sender_id']?'sender':'recipient']; $json=friend_start_json($view);
                $insert->execute([$battleId,$player,friend_battle_invite_id(),$json,hash('sha256',$json)]);
            }
            $update=$pdo->prepare("UPDATE users SET state='BATTLE',last_seen=last_seen WHERE id=? AND player_id=? AND state='WORLD'");
            foreach ($players as $player) {
                $update->execute([$users[$player]['id'],$player]); if ($update->rowCount()!==1) friend_fail(409,'FAILED');
            }
            $query=$pdo->prepare("UPDATE friend_battle_invites SET state='ACCEPTED',updated_at=UTC_TIMESTAMP(6) WHERE invite_id=? AND state='PENDING' AND expires_at>UTC_TIMESTAMP(6)");
            $query->execute([$row['invite_id']]); if ($query->rowCount()!==1) friend_fail(409,'FAILED');
            $query=$pdo->prepare("UPDATE friend_battle_sessions SET state='STARTING',updated_at=UTC_TIMESTAMP(6) WHERE battle_id=? AND state='PREPARING' AND prepare_deadline>UTC_TIMESTAMP(6)");
            $query->execute([$battleId]); if ($query->rowCount()!==1) friend_fail(409,'FAILED');
            $row['state']='STARTING'; $startup=friend_startup_record_locked($pdo,$row,true);
        }
        $startup=friend_startup_record_locked($pdo,$row,true);
        $result=['battle_id'=>$battleId,'state'=>$row['state'],'ready_deadline'=>$startup['ready_deadline']];
        $pdo->commit(); return $result;
    } catch (MortyReleaseError|JsonException $error) {
        if ($pdo->inTransaction()) $pdo->rollBack(); friend_fail(409,'FAILED');
    } catch (Throwable $error) { friend_battle_membership_error($pdo,$error); }
}

/** Initial animation barrier only; no later turn, timer or move semantics. */
function friend_battle_startup_ready(PDO $pdo, string $session, string $battleId): array {
    if ($pdo->inTransaction()) throw new LogicException('Standalone readiness requires no transaction');
    try {
        [$row,$self,$peer]=friend_startup_lock($pdo,$session,$battleId);
        $startup=friend_startup_validate_active($pdo,$row,[$self['player_id']=>$self,$peer['player_id']=>$peer],true);
        $column=$self['player_id']===$row['sender_id']?'sender_ready_at':'recipient_ready_at';
        if ($startup[$column]===null) {
            $query=$pdo->prepare("UPDATE friend_battle_startups SET $column=UTC_TIMESTAMP(6) WHERE battle_id=? AND $column IS NULL");
            $query->execute([$battleId]); if ($query->rowCount()!==1) friend_fail(409,'FAILED');
            $startup[$column]='ready';
            if ($startup['sender_ready_at']!==null && $startup['recipient_ready_at']!==null) {
                $pdo->prepare('UPDATE friend_battle_startups SET ready_at=UTC_TIMESTAMP(6) WHERE battle_id=?')->execute([$battleId]);
                $pdo->prepare("UPDATE friend_battle_sessions SET state='READY',updated_at=UTC_TIMESTAMP(6) WHERE battle_id=?")->execute([$battleId]);
                $row['state']='READY';
            }
        }
        friend_startup_record_locked($pdo,$row,true);
        $pdo->commit(); return ['battle_id'=>$battleId,'state'=>$row['state'],'ready'=>$row['state']==='READY'];
    } catch (JsonException $error) {
        if ($pdo->inTransaction()) $pdo->rollBack(); friend_fail(409,'FAILED');
    } catch (Throwable $error) { friend_battle_membership_error($pdo,$error); }
}

/** Trusted retrieval only: returns exactly the authenticated participant's intent. */
function friend_battle_startup_intent(PDO $pdo, string $session, string $battleId): array {
    if ($pdo->inTransaction()) throw new LogicException('Standalone intent read requires no transaction');
    try {
        [$row,$self,$peer]=friend_startup_lock($pdo,$session,$battleId);
        friend_startup_validate_active($pdo,$row,[$self['player_id']=>$self,$peer['player_id']=>$peer],true);
        $query=$pdo->prepare('SELECT delivery_id,payload_json FROM friend_battle_start_intents WHERE battle_id=? AND player_id=?');
        $query->execute([$battleId,$self['player_id']]); $intent=$query->fetch(PDO::FETCH_ASSOC);
        if (!$intent) friend_fail(409,'FAILED');
        $result=['battle_id'=>$battleId,'state'=>$row['state'],'delivery_id'=>$intent['delivery_id'],
            'payload'=>json_decode($intent['payload_json'],false,512,JSON_THROW_ON_ERROR)];
        friend_startup_record_locked($pdo,$row,true);
        $pdo->commit(); return $result;
    } catch (JsonException $error) {
        if ($pdo->inTransaction()) $pdo->rollBack(); friend_fail(409,'FAILED');
    } catch (Throwable $error) { friend_battle_membership_error($pdo,$error); }
}

/** Internal terminal cleanup, intentionally without a fabricated client outcome. */
function friend_startup_cancel_locked(PDO $pdo, array $row, array $users, string $reason): void {
    friend_startup_validate_active($pdo,$row,$users,false);
    $players=array_keys($users); sort($players,SORT_STRING);
    $update=$pdo->prepare("UPDATE users SET state='WORLD',last_seen=last_seen WHERE id=? AND player_id=? AND state='BATTLE'");
    $delete=$pdo->prepare('DELETE FROM friend_battle_memberships WHERE player_id=? AND battle_id=?');
    foreach ($players as $player) {
        $update->execute([$users[$player]['id'],$player]); if ($update->rowCount()!==1) friend_fail(409,'FAILED');
        $delete->execute([$player,$row['battle_id']]); if ($delete->rowCount()!==1) friend_fail(409,'FAILED');
    }
    $query=$pdo->prepare('UPDATE friend_battle_start_intents SET retired_at=UTC_TIMESTAMP(6) WHERE battle_id=? AND retired_at IS NULL');
    $query->execute([$row['battle_id']]); if ($query->rowCount()!==2) friend_fail(409,'FAILED');
    $pdo->prepare('UPDATE friend_battle_startups SET cancelled_at=UTC_TIMESTAMP(6) WHERE battle_id=?')->execute([$row['battle_id']]);
    $pdo->prepare("UPDATE friend_battle_sessions SET state='CANCELLED',cancel_reason=?,updated_at=UTC_TIMESTAMP(6) WHERE battle_id=?")->execute([$reason,$row['battle_id']]);
}

function friend_battle_startup_cancel(PDO $pdo, string $session, string $battleId): void {
    if ($pdo->inTransaction()) throw new LogicException('Standalone cancellation requires no transaction');
    try {
        [$row,$self,$peer]=friend_startup_lock($pdo,$session,$battleId);
        if ($row['state']==='CANCELLED' && in_array($row['cancel_reason'],['STARTUP_CANCELLED','STARTUP_TIMEOUT'],true)) {
            $query=$pdo->prepare('SELECT cancelled_at FROM friend_battle_startups WHERE battle_id=?'); $query->execute([$battleId]);
            if (!$query->fetchColumn()) friend_fail(409,'FAILED');
            // Do not inspect or modify newer claims/users during an old retry.
            $pdo->commit(); return;
        }
        friend_startup_cancel_locked($pdo,$row,[$self['player_id']=>$self,$peer['player_id']=>$peer],'STARTUP_CANCELLED');
        $pdo->commit();
    } catch (JsonException $error) {
        if ($pdo->inTransaction()) $pdo->rollBack(); friend_fail(409,'FAILED');
    } catch (Throwable $error) { friend_battle_membership_error($pdo,$error); }
}

/** Hints carry no release authority; fresh current rows decide timeout cleanup. */
function friend_battle_startup_expire_candidates(PDO $pdo, array $candidates): int {
    if ($pdo->inTransaction()) throw new LogicException('Standalone startup cleanup requires no transaction');
    $cancelled=0;
    foreach ($candidates as $candidate) {
        try {
            foreach (['battle_id','sender_id','recipient_id'] as $key) if (!is_string($candidate[$key]??null) || $candidate[$key]==='') friend_fail(409,'FAILED');
            if ($candidate['sender_id']===$candidate['recipient_id']) friend_fail(409,'FAILED');
            $players=[$candidate['sender_id'],$candidate['recipient_id']]; sort($players,SORT_STRING);
            $pdo->beginTransaction(); $users=[];
            $query=$pdo->prepare('SELECT * FROM users WHERE player_id=? FOR UPDATE');
            foreach ($players as $player) {
                $query->execute([$player]); $rows=$query->fetchAll(PDO::FETCH_ASSOC);
                if (count($rows)!==1 || $rows[0]['player_id']!==$player) friend_fail(409,'FAILED');
                $users[$player]=$rows[0];
            }
            $query=$pdo->prepare('SELECT * FROM friend_battle_sessions WHERE battle_id=? FOR UPDATE');
            $query->execute([$candidate['battle_id']]); $row=$query->fetch(PDO::FETCH_ASSOC);
            if (!$row || !in_array($row['state'],['STARTING','READY'],true)) { $pdo->commit(); continue; }
            if ($row['sender_id']!==$candidate['sender_id'] || $row['recipient_id']!==$candidate['recipient_id']) friend_fail(409,'FAILED');
            $startup=friend_startup_record_locked($pdo,$row,false);
            if (!(bool)$startup['due']) { $pdo->commit(); continue; }
            friend_startup_cancel_locked($pdo,$row,$users,'STARTUP_TIMEOUT');
            $pdo->commit(); $cancelled++;
        } catch (Throwable $error) {
            if ($pdo->inTransaction()) $pdo->rollBack();
            error_log('Startup cleanup preserved candidate: '.get_class($error));
        }
    }
    return $cancelled;
}

function friend_battle_startup_sweep(PDO $pdo, int $limit=100, ?string &$cursor=null): int {
    if ($pdo->inTransaction()) throw new LogicException('Standalone startup sweep requires no transaction');
    $limit=max(1,min(1000,$limit));
    $query=$pdo->prepare("SELECT s.battle_id,s.sender_id,s.recipient_id FROM friend_battle_sessions s JOIN friend_battle_startups u ON u.battle_id=s.battle_id WHERE s.state IN ('STARTING','READY')".($cursor===null?'':' AND s.battle_id>?')." ORDER BY s.battle_id LIMIT $limit");
    $query->execute($cursor===null?[]:[$cursor]); $rows=$query->fetchAll(PDO::FETCH_ASSOC);
    if (!$rows) { $cursor=null; return 0; }
    $cursor=$rows[count($rows)-1]['battle_id'];
    return friend_battle_startup_expire_candidates($pdo,$rows);
}

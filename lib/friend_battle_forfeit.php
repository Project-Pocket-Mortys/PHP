<?php
declare(strict_types=1);
require_once __DIR__ . '/friend_battle_startup.php';

function friend_forfeit_decision(array $row, string $player, string $morty): array {
    return ['schema_version'=>1,'battle_id'=>$row['battle_id'],'player_id'=>$player,
        'type'=>'RUN','owned_morty_id'=>$morty,'move_id'=>null];
}

function friend_forfeit_payload(array $row, string $actor, string $player): array {
    return ['battle_id'=>$row['battle_id'],'outcome'=>$actor===$player?'RUN':'WIN',
        'battle_abandoned'=>$actor!==$player,'turn_datas'=>[],
        'player_datas'=>['player'=>(object)[],'opponent'=>(object)[]]];
}

/** Current reads are essential: authentication may have opened an older RR snapshot. */
function friend_forfeit_rows_locked(PDO $pdo, string $table, string $battle): array {
    static $tables=['friend_battle_forfeits','friend_battle_terminal_intents','friend_battle_terminal_attempts',
        'friend_battle_startups','friend_battle_party_snapshots','friend_battle_start_views',
        'friend_battle_start_intents','friend_battle_start_attempts','friend_battle_stream_bindings',
        'friend_battle_selections','friend_battle_selection_pairs'];
    if (!$pdo->inTransaction() || !in_array($table,$tables,true)) throw new LogicException('Locked forfeit history required');
    $query=$pdo->prepare("SELECT * FROM $table WHERE battle_id=? FOR UPDATE");
    $query->execute([$battle]); return $query->fetchAll(PDO::FETCH_ASSOC);
}

function friend_forfeit_time($value, string $lower, string $upper): void {
    if (!is_string($value) || !preg_match('/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d{6}$/D',$value)
        || $value<$lower || $value>$upper) friend_fail(409,'FAILED');
}

/** Strictly validate saved JSON, including object/array distinctions and key order. */
function friend_forfeit_saved(array $row, string $field, array $expected): void {
    $json=$row[$field.'_json']??null; $hash=$row[$field.'_sha256']??null;
    if (!is_string($json) || !is_string($hash) || !hash_equals($hash,hash('sha256',$json))
        || $json!==friend_start_json($expected)) friend_fail(409,'FAILED');
}

function friend_forfeit_context(array $context, string $player): void {
    $keys=array_keys($context); sort($keys,SORT_STRING);
    $expected=['schema_version','player_id','username','player_avatar_id','level','streak',
        'xp','xp_lower','xp_upper','coins','coupons','permits','owned_items']; sort($expected,SORT_STRING);
    $catalog=friend_start_catalog();
    if ($keys!==$expected || $context['schema_version']!==1 || $context['player_id']!==$player
        || !is_string($context['username']) || trim($context['username'])===''
        || !is_string($context['player_avatar_id']) || !isset($catalog['avatars'][$context['player_avatar_id']])
        || !is_array($context['owned_items']) || !array_is_list($context['owned_items'])) friend_fail(409,'FAILED');
    friend_party_integer($context['level'],1);
    foreach (['streak','xp','xp_lower','xp_upper','coins','coupons','permits'] as $field) friend_party_integer($context[$field]);
    $seen=[];
    foreach ($context['owned_items'] as $item) {
        if (!is_array($item) || array_keys($item)!==['item_id','quantity'] || !is_string($item['item_id'])
            || !isset($catalog['items'][$item['item_id']]) || isset($seen[$item['item_id']])
            || friend_party_integer($item['quantity'])>32767) friend_fail(409,'FAILED');
        $seen[$item['item_id']]=true;
    }
}

function friend_forfeit_roles(array $rows, array $session): array {
    if (count($rows)!==2) friend_fail(409,'FAILED');
    $result=[];
    foreach ($rows as $row) {
        $player=$row['player_id']??null;
        if (!is_string($player) || !in_array($player,[$session['sender_id'],$session['recipient_id']],true)
            || isset($result[$player]) || ($row['battle_id']??null)!==$session['battle_id']) friend_fail(409,'FAILED');
        $result[$player]=$row;
    }
    return $result;
}

/** Validate both original publication attempts without consulting mutable stream leases. */
function friend_forfeit_starts_locked(PDO $pdo, array $row, array $startup, array $views, bool $retired): array {
    $battle=$row['battle_id'];
    $intents=friend_forfeit_roles(friend_forfeit_rows_locked($pdo,'friend_battle_start_intents',$battle),$row);
    $bindings=friend_forfeit_roles(friend_forfeit_rows_locked($pdo,'friend_battle_stream_bindings',$battle),$row);
    $attempts=friend_forfeit_roles(friend_forfeit_rows_locked($pdo,'friend_battle_start_attempts',$battle),$row);
    $ids=[]; $streams=[];
    foreach ($intents as $player=>$intent) {
        $binding=$bindings[$player]; $attempt=$attempts[$player];
        $ready=$startup[$player===$row['sender_id']?'sender_ready_at':'recipient_ready_at'];
        if ($ready===null || !friend_selection_uuid($intent['delivery_id']) || in_array($intent['delivery_id'],$ids,true)
            || !friend_selection_uuid($binding['stream_id']) || in_array($binding['stream_id'],$streams,true)
            || !preg_match('/^[0-9a-f]{64}$/D',$binding['session_sha256'])
            || ($intent['retired_at']!==null)!==$retired || $attempt['delivery_id']!==$intent['delivery_id']
            || $attempt['stream_id']!==$binding['stream_id']) friend_fail(409,'FAILED');
        friend_forfeit_saved($intent,'payload',$views[$player]);
        friend_forfeit_time($binding['bound_at'],'0000-00-00 00:00:00.000000',$startup['started_at']);
        friend_forfeit_time($intent['created_at'],$startup['started_at'],$ready);
        friend_forfeit_time($attempt['attempted_at'],$intent['created_at'],$ready);
        if ($retired) friend_forfeit_time($intent['retired_at'],$ready,$startup['cancelled_at']);
        $ids[]=$intent['delivery_id']; $streams[]=$binding['stream_id'];
    }
    return $bindings;
}

/** Only frozen history is used here: newer claims, users and parties are irrelevant. */
function friend_forfeit_history_locked(PDO $pdo, array $hint): array {
    $query=$pdo->prepare('SELECT * FROM friend_battle_sessions WHERE battle_id=? FOR UPDATE');
    $query->execute([$hint['battle_id']]); $row=$query->fetch(PDO::FETCH_ASSOC);
    if (!$row || $row['sender_id']!==$hint['sender_id'] || $row['recipient_id']!==$hint['recipient_id']
        || $row['sender_id']===$row['recipient_id'] || $row['state']!=='CANCELLED' || $row['cancel_reason']!=='STARTUP_RUN'
        || $row['start_views_created_at']===null) friend_fail(409,'FAILED');
    $battle=$row['battle_id']; $now=$pdo->query('SELECT UTC_TIMESTAMP(6)')->fetchColumn();
    $saved=friend_forfeit_rows_locked($pdo,'friend_battle_startups',$battle);
    $decisions=friend_forfeit_rows_locked($pdo,'friend_battle_forfeits',$battle);
    if (count($saved)!==1 || count($decisions)!==1) friend_fail(409,'FAILED');
    $startup=$saved[0]; $decision=$decisions[0]; $actor=$decision['player_id'];
    if (!in_array($actor,[$row['sender_id'],$row['recipient_id']],true) || !friend_selection_uuid($decision['decision_id'])) friend_fail(409,'FAILED');
    friend_forfeit_time($startup['started_at'],'0000-00-00 00:00:00.000000',$now);
    friend_forfeit_time($startup['ready_deadline'],$startup['started_at'],'9999-12-31 23:59:59.999999');
    $query=$pdo->prepare('SELECT TIMESTAMPDIFF(MICROSECOND,?,?)/1000000');
    $query->execute([$startup['started_at'],$startup['ready_deadline']]); $duration=(float)$query->fetchColumn();
    if ($duration<10 || $duration>120) friend_fail(409,'FAILED');
    foreach (['sender_ready_at','recipient_ready_at'] as $field) friend_forfeit_time($startup[$field],$startup['started_at'],$startup['ready_deadline']);
    friend_forfeit_time($startup['ready_at'],max($startup['sender_ready_at'],$startup['recipient_ready_at']),$startup['ready_deadline']);
    friend_forfeit_time($decision['decided_at'],$startup['ready_at'],min($startup['ready_deadline'],$now));
    friend_forfeit_time($startup['cancelled_at'],$decision['decided_at'],$now);
    friend_forfeit_saved($decision,'decision',friend_forfeit_decision($row,$actor,$decision['owned_morty_id']));
    $parties=[];
    foreach (friend_forfeit_roles(friend_forfeit_rows_locked($pdo,'friend_battle_party_snapshots',$battle),$row) as $player=>$snapshot) {
        $party=json_decode($snapshot['snapshot_json'],true,512,JSON_THROW_ON_ERROR);
        if (!is_array($party)) friend_fail(409,'FAILED');
        friend_party_validate($party,$player); friend_forfeit_saved($snapshot,'snapshot',$party);
        if ($party['deck_id']!==(int)$snapshot['deck_id'] || $party['active_owned_morty_id']!==$snapshot['active_owned_morty_id']) friend_fail(409,'FAILED');
        $parties[$player]=$party;
    }
    if ($parties[$actor]['active_owned_morty_id']!==$decision['owned_morty_id']) friend_fail(409,'FAILED');
    $views=[]; $contexts=[];
    $storedViews=friend_forfeit_roles(friend_forfeit_rows_locked($pdo,'friend_battle_start_views',$battle),$row);
    foreach ($storedViews as $player=>$snapshot) {
        $context=json_decode($snapshot['context_json'],true,512,JSON_THROW_ON_ERROR);
        if (!is_array($context)) friend_fail(409,'FAILED');
        friend_forfeit_context($context,$player);
        friend_forfeit_saved($snapshot,'context',$context);
        $view=json_decode($snapshot['view_json'],true,512,JSON_THROW_ON_ERROR);
        if (!is_array($view) || ($view['battle_id']??null)!==$battle || ($view['battle_type']??null)!=='PvF') friend_fail(409,'FAILED');
        $other=$player===$row['sender_id']?$row['recipient_id']:$row['sender_id'];
        $contexts[$player]=$context; $views[$player]=$view;
        if (($view['player']['player_id']??null)!==$player || ($view['opponent']['player_id']??null)!==$other) friend_fail(409,'FAILED');
    }
    foreach ($views as $player=>$view) {
        $other=$player===$row['sender_id']?$row['recipient_id']:$row['sender_id'];
        $views[$player]=['battle_id'=>$battle,'battle_type'=>'PvF',
            'player'=>friend_start_trainer($contexts[$player],$parties[$player],true),
            'opponent'=>friend_start_trainer($contexts[$other],$parties[$other],false),'meta'=>(object)[]];
    }
    foreach ($storedViews as $player=>$snapshot) friend_forfeit_saved($snapshot,'view',$views[$player]);
    $query=$pdo->prepare('SELECT * FROM friend_battle_invites WHERE invite_id=? FOR UPDATE');
    $query->execute([$row['invite_id']]); $invite=$query->fetch(PDO::FETCH_ASSOC);
    if (!$invite || $invite['sender_id']!==$row['sender_id'] || $invite['recipient_id']!==$row['recipient_id'] || $invite['state']!=='ACCEPTED') friend_fail(409,'FAILED');
    $bindings=friend_forfeit_starts_locked($pdo,$row,$startup,$views,true);
    $selections=friend_forfeit_rows_locked($pdo,'friend_battle_selections',$battle);
    if (count($selections)>1 || friend_forfeit_rows_locked($pdo,'friend_battle_selection_pairs',$battle)
        || (($startup['selection_started_at']!==null)!==(count($selections)===1))) friend_fail(409,'FAILED');
    foreach ($selections as $selection) {
        $player=$selection['player_id'];
        if ($player===$actor || !isset($parties[$player]) || !friend_selection_uuid($selection['selection_id'])) friend_fail(409,'FAILED');
        $payload=json_decode($selection['selection_json'],true,512,JSON_THROW_ON_ERROR);
        if (!is_array($payload)) friend_fail(409,'FAILED');
        friend_selection_validate($payload,$row,$player,$parties[$player]); friend_forfeit_saved($selection,'selection',$payload);
        friend_forfeit_time($selection['created_at'],$startup[$player===$row['sender_id']?'sender_ready_at':'recipient_ready_at'],$decision['decided_at']);
        friend_forfeit_time($startup['selection_started_at'],$selection['created_at'],$decision['decided_at']);
        friend_forfeit_time($selection['retired_at'],$decision['decided_at'],$startup['cancelled_at']);
    }
    $intents=friend_forfeit_roles(friend_forfeit_rows_locked($pdo,'friend_battle_terminal_intents',$battle),$row);
    $attempts=friend_forfeit_rows_locked($pdo,'friend_battle_terminal_attempts',$battle); $byPlayer=[]; $ids=[];
    foreach ($attempts as $attempt) {
        if (!isset($intents[$attempt['player_id']]) || isset($byPlayer[$attempt['player_id']])) friend_fail(409,'FAILED');
        $byPlayer[$attempt['player_id']]=$attempt;
    }
    foreach ($intents as $player=>$intent) {
        if (!friend_selection_uuid($intent['delivery_id']) || in_array($intent['delivery_id'],$ids,true)) friend_fail(409,'FAILED');
        $ids[]=$intent['delivery_id']; friend_forfeit_saved($intent,'payload',friend_forfeit_payload($row,$actor,$player));
        friend_forfeit_time($intent['created_at'],$decision['decided_at'],$startup['cancelled_at']);
        $attempt=$byPlayer[$player]??null;
        if (($intent['attempted_at']!==null)!==($attempt!==null)) friend_fail(409,'FAILED');
        if ($attempt!==null) {
            if ($attempt['delivery_id']!==$intent['delivery_id'] || $attempt['stream_id']!==$bindings[$player]['stream_id']
                || $attempt['attempted_at']!==$intent['attempted_at']) friend_fail(409,'FAILED');
            friend_forfeit_time($attempt['attempted_at'],$startup['cancelled_at'],$now);
        }
    }
    return ['row'=>$row,'decision'=>$decision,'intents'=>$intents,'bindings'=>$bindings];
}

/** An old acknowledgement must not depend on the peer's present account or claims. */
function friend_forfeit_retry(PDO $pdo, array $data, string $session): ?array {
    $actor=friend_auth($pdo,$session);
    $self=friend_transport_lock_user($pdo,$session,$actor['player_id']);
    $query=$pdo->prepare('SELECT * FROM friend_battle_sessions WHERE battle_id=? FOR UPDATE');
    $query->execute([$data['battle_id']]); $row=$query->fetch(PDO::FETCH_ASSOC);
    if (!$row || !in_array($self['player_id'],[$row['sender_id'],$row['recipient_id']],true)) friend_fail(403,'TOKEN_NOTVALID');
    if ($row['cancel_reason']!=='STARTUP_RUN') { $pdo->commit(); return null; }
    $history=friend_forfeit_history_locked($pdo,$row); $decision=$history['decision'];
    if ($decision['player_id']!==$self['player_id'] || $decision['owned_morty_id']!==$data['owned_morty_id']) friend_fail(409,'FAILED');
    $pdo->commit(); return ['decision_id'=>$decision['decision_id']];
}

/** Accept only initial RUN after both native startup acknowledgements. */
function friend_battle_forfeit_submit(PDO $pdo, array $data, string $session): array {
    if (!friend_battle_transport_enabled()) friend_fail(501,'FAILED');
    if ($pdo->inTransaction()) throw new LogicException('Standalone forfeit requires no transaction');
    $keys=array_keys($data); sort($keys,SORT_STRING);
    $expected=['session_id','battle_id','type','owned_morty_id','move_id']; sort($expected,SORT_STRING);
    if ($keys!==$expected || $data['move_id']!==null) friend_fail(400,'FAILED');
    foreach (['session_id','battle_id','type','owned_morty_id'] as $field) if (!is_string($data[$field]) || trim($data[$field])==='') friend_fail(400,'FAILED');
    if ($data['session_id']!==$session) friend_fail(403,'TOKEN_NOTVALID');
    if ($data['type']!=='RUN') friend_fail(501,'FAILED');
    try {
        $retry=friend_forfeit_retry($pdo,$data,$session);
        if ($retry!==null) return $retry;
        [$row,$self,$peer]=friend_startup_lock($pdo,$session,$data['battle_id']);
        if ($row['cancel_reason']==='STARTUP_RUN') {
            // Another RUN committed between our single-user check and pair lock.
            $pdo->rollBack(); $retry=friend_forfeit_retry($pdo,$data,$session);
            if ($retry===null) friend_fail(409,'FAILED');
            return $retry;
        }
        $users=[$self['player_id']=>$self,$peer['player_id']=>$peer];
        $startup=friend_startup_validate_active($pdo,$row,$users,true);
        if ($row['state']!=='READY' || $startup['sender_ready_at']===null || $startup['recipient_ready_at']===null) friend_fail(409,'FAILED');
        friend_battle_transport_ready_locked($pdo,$row,$self);
        friend_startup_current_parties_locked($pdo,$row,$users);
        $parties=friend_party_load_stored($pdo,$row);
        if ($parties===null || $parties[$self['player_id']]['active_owned_morty_id']!==$data['owned_morty_id']) friend_fail(409,'FAILED');
        $views=friend_start_views_locked($pdo,$row,$users,false);
        friend_forfeit_starts_locked($pdo,$row,$startup,[$row['sender_id']=>$views['sender'],$row['recipient_id']=>$views['recipient']],false);
        $selections=friend_selections_ledger_locked($pdo,$row,$startup,$parties);
        if (isset($selections[$self['player_id']]) || count($selections)>1) friend_fail(409,'FAILED');
        foreach (['friend_battle_forfeits','friend_battle_terminal_intents','friend_battle_terminal_attempts'] as $table) if (friend_forfeit_rows_locked($pdo,$table,$row['battle_id'])) friend_fail(409,'FAILED');
        $id=friend_battle_invite_id(); $json=friend_start_json(friend_forfeit_decision($row,$self['player_id'],$data['owned_morty_id']));
        $query=$pdo->prepare('INSERT INTO friend_battle_forfeits (battle_id,decision_id,player_id,owned_morty_id,decision_json,decision_sha256,decided_at) VALUES (?,?,?,?,?,?,UTC_TIMESTAMP(6))');
        $query->execute([$row['battle_id'],$id,$self['player_id'],$data['owned_morty_id'],$json,hash('sha256',$json)]);
        $query=$pdo->prepare('INSERT INTO friend_battle_terminal_intents (battle_id,player_id,delivery_id,payload_json,payload_sha256,created_at) VALUES (?,?,?,?,?,UTC_TIMESTAMP(6))');
        foreach ([$row['sender_id'],$row['recipient_id']] as $player) {
            $json=friend_start_json(friend_forfeit_payload($row,$self['player_id'],$player));
            $query->execute([$row['battle_id'],$player,friend_battle_invite_id(),$json,hash('sha256',$json)]);
        }
        friend_startup_cancel_locked($pdo,$row,$users,'STARTUP_RUN');
        friend_forfeit_history_locked($pdo,$row);
        // Cleanup may itself be slow. Fence the original persisted leases last.
        $query=$pdo->prepare('SELECT ready_deadline>UTC_TIMESTAMP(6) FROM friend_battle_startups WHERE battle_id=? FOR UPDATE');
        $query->execute([$row['battle_id']]);
        if (!(bool)$query->fetchColumn() || !friend_transport_bindings_live($pdo,$row,$users)) friend_fail(409,'FAILED');
        $pdo->commit(); return ['decision_id'=>$id];
    } catch (JsonException|MortyReleaseError $error) {
        if ($pdo->inTransaction()) $pdo->rollBack(); friend_fail(409,'FAILED');
    } catch (Throwable $error) { friend_battle_membership_error($pdo,$error); }
}

/** Caller holds its own current user lock; never acquire the peer's user lock. */
function friend_battle_forfeit_poll_locked(PDO $pdo, array $row, array $user, string $streamId): ?array {
    if (($row['cancel_reason']??null)!=='STARTUP_RUN') return null;
    if (!friend_battle_transport_enabled()) friend_fail(501,'FAILED');
    if (!$pdo->inTransaction()) throw new LogicException('Locked forfeit poll required');
    $history=friend_forfeit_history_locked($pdo,$row); $player=$user['player_id'];
    $binding=$history['bindings'][$player]??null;
    $query=$pdo->prepare('SELECT *,heartbeat_at>UTC_TIMESTAMP(6)-INTERVAL 10 SECOND AND heartbeat_at<=UTC_TIMESTAMP(6) AS live FROM friend_battle_streams WHERE player_id=? FOR UPDATE');
    $query->execute([$player]); $stream=$query->fetch(PDO::FETCH_ASSOC)?:null;
    if (!$binding || !is_string($user['session_id']) || !friend_transport_current($stream,$streamId,$user['session_id'])
        || !(bool)$stream['live'] || $binding['stream_id']!==$streamId
        || !hash_equals($binding['session_sha256'],$stream['session_sha256'])) return ['close'=>true,'events'=>[]];
    $query=$pdo->prepare('UPDATE friend_battle_streams SET heartbeat_at=UTC_TIMESTAMP(6) WHERE player_id=? AND stream_id=?');
    $query->execute([$player,$streamId]);
    $intent=$history['intents'][$player];
    if ($intent['attempted_at']!==null) return ['close'=>false,'events'=>[]];
    $query=$pdo->prepare('INSERT INTO friend_battle_terminal_attempts (battle_id,player_id,delivery_id,stream_id,attempted_at) VALUES (?,?,?,?,UTC_TIMESTAMP(6))');
    $query->execute([$row['battle_id'],$player,$intent['delivery_id'],$streamId]);
    $query=$pdo->prepare('UPDATE friend_battle_terminal_intents i JOIN friend_battle_terminal_attempts a ON a.battle_id=i.battle_id AND a.player_id=i.player_id AND a.delivery_id=i.delivery_id SET i.attempted_at=a.attempted_at WHERE i.battle_id=? AND i.player_id=? AND i.attempted_at IS NULL');
    $query->execute([$row['battle_id'],$player]); if ($query->rowCount()!==1) friend_fail(409,'FAILED');
    friend_forfeit_history_locked($pdo,$row);
    // A slow insert cannot publish after this generation's refreshed lease dies.
    $query=$pdo->prepare('SELECT *,heartbeat_at>UTC_TIMESTAMP(6)-INTERVAL 10 SECOND AND heartbeat_at<=UTC_TIMESTAMP(6) AS live FROM friend_battle_streams WHERE player_id=? FOR UPDATE');
    $query->execute([$player]); $current=$query->fetch(PDO::FETCH_ASSOC)?:null;
    if (!friend_transport_current($current,$streamId,$user['session_id']) || !(bool)$current['live']) friend_fail(409,'FAILED');
    return ['close'=>false,'events'=>[['event'=>'battle:turn-result','payload'=>json_decode($intent['payload_json'],false,512,JSON_THROW_ON_ERROR)]]];
}

/** Fence existing research history across services; this does not enable creation or polling. */
function friend_battle_forfeit_require_drained_locked(PDO $pdo, array $user): void {
    if (!$pdo->inTransaction()) throw new LogicException('Locked terminal drain check required');
    $player=$user['player_id'];
    $query=$pdo->prepare('SELECT *,heartbeat_at>UTC_TIMESTAMP(6)-INTERVAL 10 SECOND AND heartbeat_at<=UTC_TIMESTAMP(6) AS live FROM friend_battle_streams WHERE player_id=? FOR UPDATE');
    $query->execute([$player]); $stream=$query->fetch(PDO::FETCH_ASSOC)?:null;
    if (!$stream || !(bool)$stream['live'] || !is_string($user['session_id'])
        || !hash_equals($stream['session_sha256'],hash('sha256',$user['session_id']))) return;
    // Do not join terminal intents: deleting an intent must not bypass the fence.
    // The join may lock a binding before its session. Never wait in that order:
    // a peer's terminal poll holds the session before reading both bindings.
    $query=$pdo->prepare("SELECT s.* FROM friend_battle_stream_bindings b JOIN friend_battle_sessions s ON s.battle_id=b.battle_id WHERE b.player_id=? AND b.stream_id=? AND b.session_sha256=? AND s.cancel_reason='STARTUP_RUN' FOR UPDATE NOWAIT");
    try {
        $query->execute([$player,$stream['stream_id'],$stream['session_sha256']]);
        $rows=$query->fetchAll(PDO::FETCH_ASSOC);
    } catch (PDOException $error) {
        if (in_array((int)($error->errorInfo[1]??0),[1205,3572,1213],true)) friend_fail(409,'FAILED');
        throw $error;
    }
    if (count($rows)>1) friend_fail(409,'FAILED');
    foreach ($rows as $row) {
        $history=friend_forfeit_history_locked($pdo,$row);
        if (($history['intents'][$player]['attempted_at']??null)===null) friend_fail(409,'FAILED');
    }
}

<?php
declare(strict_types=1);
require_once __DIR__ . '/friends.php';

/** First initial ATTACK only. This queue never spends PP or resolves combat. */
function friend_selection_payload(array $row, string $player, string $morty, string $move): array {
    return ['schema_version'=>1,'battle_id'=>$row['battle_id'],'player_id'=>$player,
        'type'=>'ATTACK','owned_morty_id'=>$morty,'move_id'=>$move];
}

function friend_selection_uuid($value): bool {
    return is_string($value) && preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/D',$value)===1;
}

/** Both fresh requests and stored actions must refer to the frozen initial actor. */
function friend_selection_validate(array $payload, array $row, string $player, array $party): void {
    foreach (['owned_morty_id','move_id'] as $key) {
        if (!is_string($payload[$key]??null) || trim($payload[$key])==='') friend_fail(409,'FAILED');
    }
    if ($payload!==friend_selection_payload($row,$player,$payload['owned_morty_id'],$payload['move_id'])
        || $party['player_id']!==$player || $party['active_owned_morty_id']!==$payload['owned_morty_id']
        || !isset(friend_start_catalog()['attacks'][$payload['move_id']])) friend_fail(409,'FAILED');
    $matches=[];
    foreach ($party['owned_morties'] as $morty) {
        if ($morty['owned_morty_id']!==$payload['owned_morty_id']) continue;
        if ($morty['player_id']!==$player || friend_party_integer($morty['hp'])<1) friend_fail(409,'FAILED');
        foreach ($morty['owned_attacks'] as $attack) if ($attack['attack_id']===$payload['move_id']) $matches[]=$attack;
    }
    if (count($matches)!==1 || friend_party_integer($matches[0]['pp'])<1) friend_fail(409,'FAILED');
}

/** Pair/session locks serialize this ledger, including its initial empty state. */
function friend_selections_ledger_locked(PDO $pdo, array $row, array $startup, array $parties): array {
    $query=$pdo->prepare('SELECT * FROM friend_battle_selections WHERE battle_id=? ORDER BY player_id');
    $query->execute([$row['battle_id']]); $stored=$query->fetchAll(PDO::FETCH_ASSOC);
    $query=$pdo->prepare('SELECT * FROM friend_battle_selection_pairs WHERE battle_id=?');
    $query->execute([$row['battle_id']]); $pairs=$query->fetchAll(PDO::FETCH_ASSOC);
    if (($startup['selection_started_at']??null)===null) {
        if ($stored || $pairs) friend_fail(409,'FAILED');
        return [];
    }
    if (count($stored)<1 || count($stored)>2 || count($pairs)!==(count($stored)===2?1:0)) friend_fail(409,'FAILED');
    $selections=[]; $ids=[];
    foreach ($stored as $selection) {
        $player=$selection['player_id'];
        $ready=$player===$row['sender_id']?'sender_ready_at':'recipient_ready_at';
        if ($selection['battle_id']!==$row['battle_id'] || !in_array($player,[$row['sender_id'],$row['recipient_id']],true)
            || ($startup[$ready]??null)===null
            || isset($selections[$player]) || !isset($parties[$player]) || !friend_selection_uuid($selection['selection_id'])
            || in_array($selection['selection_id'],$ids,true) || $selection['retired_at']!==null
            || !is_string($selection['selection_json']) || !is_string($selection['selection_sha256'])
            || !hash_equals($selection['selection_sha256'],hash('sha256',$selection['selection_json']))) friend_fail(409,'FAILED');
        $payload=json_decode($selection['selection_json'],true,512,JSON_THROW_ON_ERROR);
        if (!is_array($payload)) friend_fail(409,'FAILED');
        friend_selection_validate($payload,$row,$player,$parties[$player]);
        if ($selection['selection_json']!==friend_start_json($payload)) friend_fail(409,'FAILED');
        $selections[$player]=$selection; $ids[]=$selection['selection_id'];
    }
    if ($pairs) {
        $pair=$pairs[0];
        if ($row['state']!=='READY' || ($startup['sender_ready_at']??null)===null || ($startup['recipient_ready_at']??null)===null
            || $pair['battle_id']!==$row['battle_id'] || $pair['retired_at']!==null
            || $pair['sender_selection_id']!==$selections[$row['sender_id']]['selection_id']
            || $pair['recipient_selection_id']!==$selections[$row['recipient_id']]['selection_id']) friend_fail(409,'FAILED');
    }
    return $selections;
}

function friend_battle_selection_submit(PDO $pdo, array $data, string $session): array {
    if ($pdo->inTransaction()) throw new LogicException('Standalone selection requires no transaction');
    $keys=array_keys($data); sort($keys,SORT_STRING);
    $expected=['session_id','battle_id','type','owned_morty_id','move_id']; sort($expected,SORT_STRING);
    if ($keys!==$expected) friend_fail(400,'FAILED');
    foreach ($expected as $key) if (!is_string($data[$key]) || trim($data[$key])==='') friend_fail(400,'FAILED');
    if ($data['session_id']!==$session) friend_fail(403,'TOKEN_NOTVALID');
    if ($data['type']!=='ATTACK') friend_fail(501,'FAILED');
    try {
        [$row,$self,$peer]=friend_startup_lock($pdo,$session,$data['battle_id']);
        $users=[$self['player_id']=>$self,$peer['player_id']=>$peer];
        $startup=friend_startup_validate_active($pdo,$row,$users,true);
        $ready=$self['player_id']===$row['sender_id']?'sender_ready_at':'recipient_ready_at';
        if ($startup[$ready]===null) friend_fail(409,'FAILED');
        friend_battle_transport_ready_locked($pdo,$row,$self);
        friend_startup_current_parties_locked($pdo,$row,$users);
        $parties=friend_party_load_stored($pdo,$row);
        if ($parties===null) friend_fail(409,'FAILED');
        $payload=friend_selection_payload($row,$self['player_id'],$data['owned_morty_id'],$data['move_id']);
        friend_selection_validate($payload,$row,$self['player_id'],$parties[$self['player_id']]);
        $json=friend_start_json($payload);
        $selections=friend_selections_ledger_locked($pdo,$row,$startup,$parties);
        $selection=$selections[$self['player_id']]??null;
        if ($selection!==null) {
            if ($selection['selection_json']!==$json) friend_fail(409,'FAILED');
            $id=$selection['selection_id'];
        } else {
            $id=friend_battle_invite_id();
            $query=$pdo->prepare('INSERT INTO friend_battle_selections (battle_id,player_id,selection_id,selection_json,selection_sha256,created_at) VALUES (?,?,?,?,?,UTC_TIMESTAMP(6))');
            $query->execute([$row['battle_id'],$self['player_id'],$id,$json,hash('sha256',$json)]);
            if (($startup['selection_started_at']??null)===null) {
                $query=$pdo->prepare('UPDATE friend_battle_startups SET selection_started_at=UTC_TIMESTAMP(6) WHERE battle_id=? AND selection_started_at IS NULL');
                $query->execute([$row['battle_id']]); if ($query->rowCount()!==1) friend_fail(409,'FAILED');
            }
            $selections[$self['player_id']]=['selection_id'=>$id];
            if (count($selections)===2) {
                $query=$pdo->prepare('INSERT INTO friend_battle_selection_pairs (battle_id,sender_selection_id,recipient_selection_id,paired_at) VALUES (?,?,?,UTC_TIMESTAMP(6))');
                $query->execute([$row['battle_id'],$selections[$row['sender_id']]['selection_id'],$selections[$row['recipient_id']]['selection_id']]);
            }
        }
        // A slow insert cannot extend the startup or stream lease.
        $startup=friend_startup_record_locked($pdo,$row,true);
        friend_selections_ledger_locked($pdo,$row,$startup,$parties);
        friend_startup_record_locked($pdo,$row,true);
        friend_battle_transport_ready_locked($pdo,$row,$self);
        $pdo->commit(); return ['selection_id'=>$id,'paired'=>count($selections)===2];
    } catch (MortyReleaseError|JsonException $error) {
        if ($pdo->inTransaction()) $pdo->rollBack(); friend_fail(409,'FAILED');
    } catch (Throwable $error) { friend_battle_membership_error($pdo,$error); }
}

/** Caller retains the pair and startup locks; cleanup does not inspect live parties. */
function friend_battle_selections_retire_locked(PDO $pdo, array $row, array $users, array $startup): void {
    if (($startup['selection_started_at']??null)===null) return;
    if (!$pdo->inTransaction()) throw new LogicException('Locked selection retirement required');
    $parties=friend_party_load_stored($pdo,$row);
    if ($parties===null) friend_fail(409,'FAILED');
    $selections=friend_selections_ledger_locked($pdo,$row,$startup,$parties);
    $query=$pdo->prepare('UPDATE friend_battle_selections SET retired_at=UTC_TIMESTAMP(6) WHERE battle_id=? AND player_id=? AND selection_id=? AND retired_at IS NULL');
    foreach ($selections as $player=>$selection) {
        $query->execute([$row['battle_id'],$player,$selection['selection_id']]);
        if ($query->rowCount()!==1) friend_fail(409,'FAILED');
    }
    if (count($selections)===2) {
        $query=$pdo->prepare('UPDATE friend_battle_selection_pairs SET retired_at=UTC_TIMESTAMP(6) WHERE battle_id=? AND sender_selection_id=? AND recipient_selection_id=? AND retired_at IS NULL');
        $query->execute([$row['battle_id'],$selections[$row['sender_id']]['selection_id'],$selections[$row['recipient_id']]['selection_id']]);
        if ($query->rowCount()!==1) friend_fail(409,'FAILED');
    }
}

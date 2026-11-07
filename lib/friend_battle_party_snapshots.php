<?php
declare(strict_types=1);
require_once __DIR__ . '/friend_battle_membership.php';
require_once __DIR__ . '/morty_release.php';

function friend_party_integer($value, int $minimum = 0): int {
    $number = filter_var($value, FILTER_VALIDATE_INT, ['options' => ['min_range' => $minimum, 'max_range' => 2147483647]]);
    if ($number === false || is_bool($value)) friend_fail(409, 'FAILED');
    return $number;
}

/** Validate stored facts; no stat generation, repair or native wire serialization. */
function friend_party_validate(array $party, string $player): void {
    static $species = null;
    if ($species === null) {
        $catalog = json_decode(file_get_contents(__DIR__.'/../config/multiplayer_morty_ids.json'),true,512,JSON_THROW_ON_ERROR);
        $species = array_fill_keys($catalog['morty_ids'],true);
    }
    $keys = array_keys($party); sort($keys);
    $expected = ['schema_version','player_id','deck_id','active_owned_morty_id','owned_morties']; sort($expected);
    if ($keys !== $expected || $party['schema_version'] !== 1 || $party['player_id'] !== $player
        || !is_array($party['owned_morties']) || !array_is_list($party['owned_morties'])
        || !$party['owned_morties'] || count($party['owned_morties']) > 5) friend_fail(409, 'FAILED');
    friend_party_integer($party['deck_id']);
    $seen = []; $living = [];
    foreach ($party['owned_morties'] as $morty) {
        if (!is_array($morty) || ($morty['player_id'] ?? null) !== $player
            || !is_string($morty['owned_morty_id'] ?? null) || trim($morty['owned_morty_id']) === ''
            || in_array($morty['owned_morty_id'], $seen, true)
            || !is_string($morty['morty_id'] ?? null) || !isset($species[$morty['morty_id']])
            || !in_array($morty['variant'] ?? 'Normal', ['Normal','Shiny','Pulsing'], true)) friend_fail(409, 'FAILED');
        $seen[] = $morty['owned_morty_id'];
        foreach (['level','hp_stat','attack_stat','defence_stat','speed_stat'] as $field) friend_party_integer($morty[$field] ?? null, 1);
        $hp = friend_party_integer($morty['hp'] ?? null);
        if ($hp > friend_party_integer($morty['hp_stat'], 1)) friend_fail(409, 'FAILED');
        if ($hp > 0) $living[] = $morty['owned_morty_id'];
        if (!isset($morty['owned_attacks']) || !is_array($morty['owned_attacks'])
            || !array_is_list($morty['owned_attacks']) || !$morty['owned_attacks']
            || count($morty['owned_attacks']) > 4) friend_fail(409, 'FAILED');
        $slots = [];
        foreach ($morty['owned_attacks'] as $attack) {
            if (!is_array($attack) || ($attack['owned_morty_id'] ?? null) !== $morty['owned_morty_id']
                || !is_string($attack['attack_id'] ?? null) || trim($attack['attack_id']) === '') friend_fail(409, 'FAILED');
            $slot = friend_party_integer($attack['position'] ?? null);
            if ($slot > 3 || in_array($slot, $slots, true)
                || friend_party_integer($attack['pp'] ?? null) > friend_party_integer($attack['pp_stat'] ?? null, 1)) friend_fail(409, 'FAILED');
            $slots[] = $slot;
        }
    }
    if (!$living || $party['active_owned_morty_id'] !== $living[0]) friend_fail(409, 'FAILED');
}

/** Both users are locked before deck, Morty and attack reads. */
function friend_party_capture_locked(PDO $pdo, array $user): array {
    $player = $user['player_id'];
    $deckId = friend_party_integer($user['active_deck_id'] ?? null);
    $query = $pdo->prepare('SELECT * FROM decks WHERE player_id=? AND deck_id=? ORDER BY id FOR UPDATE');
    $query->execute([$player,$deckId]);
    $decks = $query->fetchAll(PDO::FETCH_ASSOC);
    if (count($decks) !== 1 || $decks[0]['player_id'] !== $player) friend_fail(409, 'FAILED');
    $ids = morty_release_deck_ids((string)$decks[0]['owned_morty_ids']);
    if (!$ids || count($ids)>5 || count(array_unique($ids,SORT_STRING))!==count($ids)) friend_fail(409,'FAILED');
    $ordered = $ids; sort($ordered,SORT_STRING); $morties = [];
    $query = $pdo->prepare('SELECT * FROM owned_morties WHERE owned_morty_id=? ORDER BY id FOR UPDATE');
    foreach ($ordered as $id) {
        $query->execute([$id]); $rows=$query->fetchAll(PDO::FETCH_ASSOC);
        if (count($rows)!==1 || $rows[0]['player_id']!==$player || $rows[0]['owned_morty_id']!==$id) friend_fail(409,'FAILED');
        $morties[$id]=$rows[0];
        $attacks=$pdo->prepare('SELECT * FROM owned_attacks WHERE owned_morty_id=? ORDER BY position,id FOR UPDATE');
        $attacks->execute([$id]); $morties[$id]['owned_attacks']=$attacks->fetchAll(PDO::FETCH_ASSOC);
    }
    $party=['schema_version'=>1,'player_id'=>$player,'deck_id'=>$deckId,'active_owned_morty_id'=>null,'owned_morties'=>[]];
    foreach ($ids as $id) {
        $party['owned_morties'][]=$morties[$id];
        if ($party['active_owned_morty_id']===null && friend_party_integer($morties[$id]['hp']??null)>0) $party['active_owned_morty_id']=$id;
    }
    friend_party_validate($party,$player);
    return $party;
}

/** Lock and revalidate the complete live preparation, without committing. */
function friend_party_prepare_locked(PDO $pdo, string $session, string $battleId): array {
    $actor=friend_auth($pdo,$session);
    $query=$pdo->prepare('SELECT * FROM friend_battle_sessions WHERE battle_id=?'); $query->execute([$battleId]); $hint=$query->fetch(PDO::FETCH_ASSOC);
    if (!$hint || !in_array($actor['player_id'],[$hint['sender_id'],$hint['recipient_id']],true)) friend_fail(403,'TOKEN_NOTVALID');
    if ($hint['sender_id']===$hint['recipient_id']) friend_fail(409,'FAILED');
    $other=$hint[$actor['player_id']===$hint['sender_id']?'recipient_id':'sender_id'];
    [$self,$peer,$friend]=friend_lock_pair($pdo,$session,$other);
    if ($self['player_id']!==$actor['player_id'] || !$friend || $friend['pending']!=='false'
        || $self['state']!=='WORLD' || $peer['state']!=='WORLD') friend_fail(409,'FAILED');
    $query=$pdo->prepare('SELECT *,prepare_deadline>UTC_TIMESTAMP(6) AS live FROM friend_battle_sessions WHERE battle_id=? FOR UPDATE');
    $query->execute([$battleId]); $row=$query->fetch(PDO::FETCH_ASSOC);
    if (!$row || $row['sender_id']!==$hint['sender_id'] || $row['recipient_id']!==$hint['recipient_id'] || $row['state']!=='PREPARING' || !(bool)$row['live']) friend_fail(409,'FAILED');
    $query=$pdo->prepare('SELECT *,expires_at>UTC_TIMESTAMP(6) AS live FROM friend_battle_invites WHERE invite_id=? FOR UPDATE');
    $query->execute([$row['invite_id']]); $invite=$query->fetch(PDO::FETCH_ASSOC);
    if (!$invite || $invite['sender_id']!==$row['sender_id'] || $invite['recipient_id']!==$row['recipient_id'] || $invite['state']!=='PENDING' || !(bool)$invite['live']) friend_fail(409,'FAILED');
    friend_battle_require_claims($pdo,$row);
    $query=$pdo->prepare("SELECT 1 FROM battles WHERE state='ACTIVE' AND (player_id IN (?,?) OR opponent_id IN (?,?)) LIMIT 1");
    $query->execute([$self['player_id'],$peer['player_id'],$self['player_id'],$peer['player_id']]); if ($query->fetchColumn()!==false) friend_fail(409,'FAILED');
    return [$row,$self,$peer];
}

/** Read immutable source parties; never recapture missing or malformed rows. */
function friend_party_load_stored(PDO $pdo, array $row): ?array {
    $battleId=$row['battle_id'];
    $query=$pdo->prepare('SELECT * FROM friend_battle_party_snapshots WHERE battle_id=? ORDER BY player_id');
    $query->execute([$battleId]); $stored=$query->fetchAll(PDO::FETCH_ASSOC); $parties=[];
    if (!$stored) return null;
    if (count($stored)!==2) friend_fail(409,'FAILED');
    foreach ($stored as $snapshot) {
        $player=$snapshot['player_id'];
        if (!in_array($player,[$row['sender_id'],$row['recipient_id']],true)
            || !hash_equals($snapshot['snapshot_sha256'],hash('sha256',$snapshot['snapshot_json']))) friend_fail(409,'FAILED');
        $party=json_decode($snapshot['snapshot_json'],true,512,JSON_THROW_ON_ERROR);
        if (!is_array($party)) friend_fail(409,'FAILED');
        friend_party_validate($party,$player);
        if ($party['deck_id']!==(int)$snapshot['deck_id'] || $party['active_owned_morty_id']!==$snapshot['active_owned_morty_id']) friend_fail(409,'FAILED');
        $parties[$player]=$party;
    }
    return $parties;
}

/** Internal capture step; it neither renews a lease nor enables public acceptance. */
function friend_battle_snapshot_parties(PDO $pdo, string $session, string $battleId): array {
    if ($pdo->inTransaction()) throw new LogicException('Standalone party capture requires no transaction');
    try {
        [$row,$self,$peer]=friend_party_prepare_locked($pdo,$session,$battleId);
        $parties=friend_party_load_stored($pdo,$row);
        if ($parties===null) {
            $users=[$self['player_id']=>$self,$peer['player_id']=>$peer]; $players=array_keys($users); sort($players,SORT_STRING);
            foreach ($players as $player) $parties[$player]=friend_party_capture_locked($pdo,$users[$player]);
            $insert=$pdo->prepare('INSERT INTO friend_battle_party_snapshots (battle_id,player_id,deck_id,active_owned_morty_id,snapshot_json,snapshot_sha256,created_at) VALUES (?,?,?,?,?,?,UTC_TIMESTAMP(6))');
            foreach ($players as $player) {
                $party=$parties[$player]; $json=json_encode($party,JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);
                $insert->execute([$battleId,$player,$party['deck_id'],$party['active_owned_morty_id'],$json,hash('sha256',$json)]);
            }
        }
        $result=['sender'=>$parties[$row['sender_id']],'recipient'=>$parties[$row['recipient_id']]];
        $pdo->commit(); return $result;
    } catch (MortyReleaseError|JsonException $error) {
        if ($pdo->inTransaction()) $pdo->rollBack(); friend_fail(409,'FAILED');
    } catch (Throwable $error) { friend_battle_membership_error($pdo,$error); }
}

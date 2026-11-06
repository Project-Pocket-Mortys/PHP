<?php
declare(strict_types=1);
require_once __DIR__ . '/friend_battle_party_snapshots.php';

function friend_start_json(array $value): string {
    return json_encode($value, JSON_THROW_ON_ERROR|JSON_UNESCAPED_SLASHES|JSON_UNESCAPED_UNICODE);
}

function friend_start_catalog(): array {
    static $ids = null;
    if ($ids === null) {
        $catalog = json_decode(file_get_contents(__DIR__.'/../config/multiplayer_start_ids.json'),true,512,JSON_THROW_ON_ERROR);
        $attacks = json_decode(file_get_contents(__DIR__.'/../config/attack_max_ap.json'),true,512,JSON_THROW_ON_ERROR);
        $ids = ['avatars'=>array_fill_keys($catalog['player_avatar_ids'],true),
            'items'=>array_fill_keys($catalog['item_ids'],true), 'attacks'=>array_fill_keys(array_keys($attacks),true)];
    }
    return $ids;
}

/** Only current public trainer fields and this owner's resources enter storage. */
function friend_start_context_locked(PDO $pdo, array $user): array {
    $catalog = friend_start_catalog();
    if (!is_string($user['username'] ?? null) || trim($user['username']) === ''
        || !is_string($user['player_avatar_id'] ?? null) || !isset($catalog['avatars'][$user['player_avatar_id']])) friend_fail(409,'FAILED');
    $context = ['schema_version'=>1,'player_id'=>$user['player_id'],'username'=>$user['username'],
        'player_avatar_id'=>$user['player_avatar_id'],'level'=>friend_party_integer($user['level'] ?? null,1)];
    foreach (['streak','xp','xp_lower','xp_upper','coins','coupons','permits'] as $field) {
        if (!array_key_exists($field,$user)) friend_fail(409,'FAILED');
        $context[$field] = friend_party_integer($user[$field] ?? 0);
    }
    $query = $pdo->prepare('SELECT item_id,quantity FROM owned_items WHERE player_id=? ORDER BY item_id,id FOR UPDATE');
    $query->execute([$user['player_id']]);
    $context['owned_items'] = []; $seen = [];
    foreach ($query->fetchAll(PDO::FETCH_ASSOC) as $item) {
        $id = $item['item_id'];
        if (!is_string($id) || !isset($catalog['items'][$id]) || isset($seen[$id])) friend_fail(409,'FAILED');
        $quantity = friend_party_integer($item['quantity']);
        // SetItemsFromDicts converts quantity to System.Int16 in Android 2.41.0.
        if ($quantity > 32767) friend_fail(409,'FAILED');
        $context['owned_items'][] = ['item_id'=>$id,'quantity'=>$quantity]; $seen[$id]=true;
    }
    return $context;
}

function friend_start_flag($value): bool {
    if ($value === null) return false;
    $flag = filter_var($value,FILTER_VALIDATE_BOOLEAN,FILTER_NULL_ON_FAILURE);
    if ($flag === null) friend_fail(409,'FAILED');
    return $flag;
}

/** Explicit wire allowlist: never serialize raw snapshot/database rows. */
function friend_start_trainer(array $context, array $party, bool $owner): array {
    $trainer = [];
    foreach (['player_id','username','player_avatar_id','level','streak'] as $field) $trainer[$field]=$context[$field];
    $trainer['type'] = $owner ? 'PLAYER' : 'USER'; $trainer['state']='BATTLE';
    if ($owner) {
        foreach (['xp','xp_lower','xp_upper','coins','coupons','permits','owned_items'] as $field) $trainer[$field]=$context[$field];
        $trainer['move_log']=['cooldown'=>(object)[],'cooldown_next'=>(object)[],'count'=>(object)[]];
    }
    $trainer['owned_morties']=[]; $catalog=friend_start_catalog();
    foreach ($party['owned_morties'] as $raw) {
        $morty=['owned_morty_id'=>$raw['owned_morty_id'],'morty_id'=>$raw['morty_id'],'variant'=>$raw['variant'] ?? 'Normal'];
        foreach (['level','hp','hp_stat','attack_stat','defence_stat','speed_stat'] as $field) $morty[$field]=friend_party_integer($raw[$field]);
        foreach (['is_poisoned','is_paralysed'] as $field) $morty[$field]=friend_start_flag($raw[$field] ?? null);
        if ($owner) {
            foreach (['xp','xp_lower','xp_upper','evolution_points'] as $field) {
                if (!array_key_exists($field,$raw)) friend_fail(409,'FAILED');
                $morty[$field]=friend_party_integer($raw[$field] ?? 0);
            }
            foreach (['is_locked','is_trading_locked'] as $field) $morty[$field]=friend_start_flag($raw[$field] ?? null);
        }
        $morty['owned_attacks']=[];
        foreach ($raw['owned_attacks'] as $attack) {
            if (!isset($catalog['attacks'][$attack['attack_id']])) friend_fail(409,'FAILED');
            $wire=['attack_id'=>$attack['attack_id']];
            foreach (['position','pp','pp_stat'] as $field) $wire[$field]=friend_party_integer($attack[$field]);
            $morty['owned_attacks'][]=$wire;
        }
        $trainer['owned_morties'][]=$morty;
    }
    $trainer['active_owned_morty']=$party['active_owned_morty_id'];
    return $trainer;
}

/** Trusted internal API returns both perspectives; never expose both over HTTP. */
function friend_battle_build_start_views(PDO $pdo, string $session, string $battleId): array {
    if ($pdo->inTransaction()) throw new LogicException('Standalone start capture requires no transaction');
    try {
        [$row,$self,$peer]=friend_party_prepare_locked($pdo,$session,$battleId);
        $parties=friend_party_load_stored($pdo,$row);
        if ($parties === null) friend_fail(409,'FAILED');
        $users=[$self['player_id']=>$self,$peer['player_id']=>$peer];
        $players=array_keys($users); sort($players,SORT_STRING); $contexts=[]; $views=[];
        foreach ($players as $player) $contexts[$player]=friend_start_context_locked($pdo,$users[$player]);
        foreach ($players as $player) {
            $other=$player===$row['sender_id'] ? $row['recipient_id'] : $row['sender_id'];
            $views[$player]=['battle_id'=>$battleId,'battle_type'=>'PvF',
                'player'=>friend_start_trainer($contexts[$player],$parties[$player],true),
                'opponent'=>friend_start_trainer($contexts[$other],$parties[$other],false),'meta'=>(object)[]];
        }
        $query=$pdo->prepare('SELECT * FROM friend_battle_start_views WHERE battle_id=? ORDER BY player_id');
        $query->execute([$battleId]); $stored=$query->fetchAll(PDO::FETCH_ASSOC);
        if ($stored) {
            if (count($stored)!==2 || $row['start_views_created_at'] === null) friend_fail(409,'FAILED');
            $seen=[];
            foreach ($stored as $snapshot) {
                $player=$snapshot['player_id'];
                if (!isset($contexts[$player]) || isset($seen[$player])) friend_fail(409,'FAILED');
                $seen[$player]=true;
                foreach (['context'=>$contexts[$player],'view'=>$views[$player]] as $field=>$expected) {
                    $json=$snapshot[$field.'_json'];
                    if (!hash_equals($snapshot[$field.'_sha256'],hash('sha256',$json))
                        || $json!==friend_start_json($expected)) friend_fail(409,'FAILED');
                }
            }
        } else {
            if ($row['start_views_created_at'] !== null) friend_fail(409,'FAILED');
            $insert=$pdo->prepare('INSERT INTO friend_battle_start_views (battle_id,player_id,context_json,context_sha256,view_json,view_sha256,created_at) VALUES (?,?,?,?,?,?,UTC_TIMESTAMP(6))');
            foreach ($players as $player) {
                $context=friend_start_json($contexts[$player]); $view=friend_start_json($views[$player]);
                $insert->execute([$battleId,$player,$context,hash('sha256',$context),$view,hash('sha256',$view)]);
            }
            $query=$pdo->prepare('UPDATE friend_battle_sessions SET start_views_created_at=UTC_TIMESTAMP(6) WHERE battle_id=? AND start_views_created_at IS NULL');
            $query->execute([$battleId]);
            if ($query->rowCount()!==1) friend_fail(409,'FAILED');
        }
        $result=['sender'=>$views[$row['sender_id']],'recipient'=>$views[$row['recipient_id']]];
        $pdo->commit(); return $result;
    } catch (JsonException $error) {
        if ($pdo->inTransaction()) $pdo->rollBack(); friend_fail(409,'FAILED');
    } catch (Throwable $error) { friend_battle_membership_error($pdo,$error); }
}

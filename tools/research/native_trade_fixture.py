"""Private, append-only fixture receipts for native PMTrade01 trading research.

Only `prepare` mutates the database: it copies the account's native starter and
attacks without changing progression, decks, currency, or any other account.
Run with the explicitly installed research Python; never publish receipt files.
"""
import argparse
import datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import uuid


ROOT = Path(__file__).resolve().parents[2]
PHP = r'''
ini_set('display_errors', '0');
function need($ok) { if (!$ok) throw new RuntimeException('Fixture invariant rejected'); }
function rows($sql, $args=[]) { global $pdo; $q=$pdo->prepare($sql); $q->execute($args); return $q->fetchAll(PDO::FETCH_ASSOC); }
function stableUser($u) { foreach (['session_id','room_id','state','last_seen','last_event_id','room_membership_generation','expiry_trade'] as $k) unset($u[$k]); return $u; }
function capture($expected=null) {
    $u=rows('SELECT * FROM users WHERE username=? ORDER BY id', ['PMTrade01']);
    need(count($u)===1 && $u[0]['username']==='PMTrade01'); $u=$u[0];
    need(is_string($u['player_id']) && preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/D',$u['player_id']));
    $p=$u['player_id']; if ($expected!==null) need($p===$expected);
    $owners=rows('SELECT * FROM users WHERE player_id=? ORDER BY id',[$p]);
    need(count($owners)===1 && $owners[0]['id']===$u['id']);
    if(is_string($u['session_id']) && $u['session_id']!=='') {
        $sessions=rows('SELECT * FROM users WHERE session_id=? ORDER BY id',[$u['session_id']]);
        need(count($sessions)===1 && $sessions[0]['id']===$u['id']);
    }
    need(!rows('SELECT * FROM friend_battle_memberships WHERE player_id=? ORDER BY player_id',[$p]));
    $m=rows('SELECT * FROM owned_morties WHERE player_id=? ORDER BY id',[$p]); need(count($m)>0);
    $ids=array_column($m,'owned_morty_id'); need(count(array_unique($ids,SORT_STRING))===count($ids));
    foreach($ids as $id) { need(is_string($id) && $id!==''); $all=rows('SELECT * FROM owned_morties WHERE owned_morty_id=? ORDER BY id',[$id]); need(count($all)===1 && $all[0]['owned_morty_id']===$id && $all[0]['player_id']===$p); }
    $in=implode(',',array_fill(0,count($ids),'?'));
    $tr=rows("SELECT * FROM trades WHERE player_id=? OR morty_trade_id IN ($in) ORDER BY id",[$p,...$ids]);
    $tradeIds=array_column($tr,'trade_id');
    $parent=$tradeIds ? ' OR trade_id IN ('.implode(',',array_fill(0,count($tradeIds),'?')).')' : '';
    return ['users'=>[$u], 'decks'=>rows('SELECT * FROM decks WHERE player_id=? ORDER BY id',[$p]),
        'owned_morties'=>$m, 'owned_attacks'=>rows("SELECT * FROM owned_attacks WHERE owned_morty_id IN ($in) ORDER BY id",$ids),
        'owned_items'=>rows('SELECT * FROM owned_items WHERE player_id=? ORDER BY id',[$p]), 'trades'=>$tr,
        'trade_offers'=>rows("SELECT * FROM trade_offers WHERE player_id=? OR morty_offer_id IN ($in)$parent ORDER BY id",[$p,...$ids,...$tradeIds]),
        'completed_trades'=>rows("SELECT * FROM completed_trades WHERE request_player_id=? OR offer_player_id=? OR morty_request_id IN ($in) OR morty_offer_id IN ($in) ORDER BY id",[$p,$p,...$ids,...$ids]),
        'event_queue'=>rows('SELECT * FROM event_queue WHERE player_id LIKE ? OR username=? OR payload_json LIKE ? ORDER BY id',['%'.$p.'%','PMTrade01','%'.$p.'%']),
        'friend_battle_memberships'=>[]];
}
function emptyTrades($s) { foreach(['trades','trade_offers','completed_trades'] as $t) need(!$s[$t]); }
function starter($s) {
    emptyTrades($s); need(count($s['owned_morties'])===1 && count($s['decks'])===1 && count($s['owned_attacks'])===1);
    $m=$s['owned_morties'][0]; $a=$s['owned_attacks'][0]; $u=$s['users'][0]; $d=$s['decks'][0];
    need((string)$u['active_deck_id']==='0' && (string)$d['deck_id']==='0');
    need(json_decode($d['owned_morty_ids'],true)===[$m['owned_morty_id']]);
    foreach(['morty_id'=>'MortyDefault','level'=>'5','xp'=>'125','hp'=>'20','hp_stat'=>'20','attack_stat'=>'11','defence_stat'=>'10','speed_stat'=>'10','variant'=>'Normal','is_locked'=>'false','is_trading_locked'=>'false','fight_pit_id'=>'null','evolution_points'=>'0','xp_lower'=>'125','xp_upper'=>'216'] as $k=>$v) need((string)$m[$k]===$v);
    foreach(['is_poisoned','is_paralysed'] as $k) if(array_key_exists($k,$m)) need((string)$m[$k]==='0');
    need($a['owned_morty_id']===$m['owned_morty_id'] && $a['attack_id']==='AttackOutburst' && (string)$a['position']==='0' && (string)$a['pp']==='12' && (string)$a['pp_stat']==='12');
}
function compareState($a,$b) {
    need(stableUser($a['users'][0])===stableUser($b['users'][0]));
    foreach(['decks','owned_morties','owned_attacks','owned_items'] as $t) need($a[$t]===$b[$t]);
}
function copyRow($table,$row,$new) {
    global $pdo; unset($row['id']); $row['owned_morty_id']=$new;
    foreach(array_keys($row) as $k) need((bool)preg_match('/^[a-z_]+$/D',$k));
    $cols=implode(',',array_map(fn($k)=>'`'.$k.'`',array_keys($row)));
    $q=$pdo->prepare('INSERT INTO '.$table.' ('.$cols.') VALUES ('.implode(',',array_fill(0,count($row),'?')).')'); $q->execute(array_values($row));
}
try {
    need(PHP_SAPI==='cli' && getenv('PM_DB_HOST')==='db' && getenv('PM_DB_NAME')==='pocket_mortys');
    $arg=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
    $pdo=new PDO('mysql:host=db;port=3306;dbname=pocket_mortys;charset=utf8mb4',getenv('PM_DB_USER'),getenv('PM_DB_PASS'),[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
    $pdo->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ'); $pdo->beginTransaction();
    if($arg['action']==='prepare') {
        $base=$arg['baseline']; $p=$base['users'][0]['player_id'];
        $locked=rows('SELECT * FROM users WHERE player_id=? ORDER BY id FOR UPDATE',[$p]); need(count($locked)===1 && $locked[0]['username']==='PMTrade01');
        $before=capture($p); starter($before); compareState($base,$before);
        $new=$arg['new_uuid']; need((bool)preg_match('/^[0-9a-f-]{36}$/D',$new));
        foreach([['owned_morties','owned_morty_id'],['owned_attacks','owned_morty_id'],['trades','morty_trade_id'],['trade_offers','morty_offer_id']] as [$t,$c]) need(!rows("SELECT * FROM $t WHERE $c=?",[$new]));
        foreach(rows('SELECT * FROM decks ORDER BY id') as $d) need(stripos((string)$d['owned_morty_ids'],$new)===false);
        copyRow('owned_morties',$before['owned_morties'][0],$new);
        foreach($before['owned_attacks'] as $a) copyRow('owned_attacks',$a,$new);
        $after=capture($p); emptyTrades($after); need(count($after['owned_morties'])===2 && count($after['owned_attacks'])===2);
        $filtered=$after;
        foreach(['owned_morties','owned_attacks'] as $t) $filtered[$t]=array_values(array_filter($after[$t],fn($r)=>$r['owned_morty_id']!==$new));
        compareState($before,$filtered);
        foreach(['owned_morties','owned_attacks'] as $t) {
            $copy=array_values(array_filter($after[$t],fn($r)=>$r['owned_morty_id']===$new)); need(count($copy)===1);
            $original=$before[$t][0]; unset($original['id'],$copy[0]['id']); $original['owned_morty_id']=$new; need($original===$copy[0]);
        }
        $pdo->commit(); echo json_encode(['before'=>$before,'snapshot'=>$after,'synthetic_uuid'=>$new],JSON_THROW_ON_ERROR);
    } else {
        $s=capture($arg['player_id']??null);
        if($arg['action']==='snapshot') starter($s);
        if($arg['action']==='verify-cancelled') { emptyTrades($s); compareState($arg['baseline'],$s); }
        $pdo->commit(); echo json_encode(['snapshot'=>$s],JSON_THROW_ON_ERROR);
    }
} catch(Throwable $e) { if(isset($pdo) && $pdo->inTransaction()) $pdo->rollBack(); fwrite(STDERR,"Native trade fixture rejected; no automatic recovery performed.\n"); exit(1); }
'''


def safe_path(value, fresh=False):
    path = Path(os.path.abspath(value))
    research = ROOT / '.research'
    if not path.is_relative_to(research) or path == research:
        raise ValueError('Output must be inside repository .research')
    for part in [path, *path.parents]:
        if part.is_symlink() or part.is_junction():
            raise ValueError('Symlink/junction output paths are forbidden')
        if part == ROOT:
            break
    if fresh and path.exists():
        raise ValueError('Output directory must be fresh')
    return path


def write_new(path, data):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write('\n')


def database(payload):
    result = subprocess.run(
        ['docker', 'compose', '-f', str(ROOT / 'compose.research.yaml'),
         'exec', '-T', 'web', 'php', '-r', PHP],
        cwd=ROOT, input=json.dumps(payload), text=True, capture_output=True,
        encoding='utf-8', timeout=60,
    )
    if result.returncode:
        raise RuntimeError('Database operation rejected; private process output suppressed')
    try:
        return json.loads(result.stdout)
    except (ValueError, TypeError):
        raise RuntimeError('Invalid private database receipt') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['snapshot', 'prepare', 'observe', 'verify-cancelled'])
    parser.add_argument('--output', required=True, help='Fresh .research directory for snapshot; existing receipt directory otherwise')
    parser.add_argument('--label', help='Unique observation label (observe only)')
    args = parser.parse_args()
    if args.action == 'observe':
        if not args.label or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', args.label):
            parser.error('observe requires a safe unique --label')
    elif args.label:
        parser.error('--label is only supported by observe')
    output = safe_path(args.output, fresh=args.action == 'snapshot')
    if args.action == 'snapshot':
        output.mkdir(parents=True, exist_ok=False)
        write_new(output / 'snapshot-attempt.json', {'action': 'snapshot', 'private': True})
        receipt = database({'action': 'snapshot'})
        write_new(output / 'manifest.json', {
            'version': 1, 'account': 'PMTrade01', 'private': True,
            'created_utc': datetime.datetime.now(datetime.UTC).isoformat(),
            'provenance': 'Native-registration starter baseline; synthetic clone not yet created',
            **receipt,
        })
    else:
        manifest_path = safe_path(output / 'manifest.json')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if manifest.get('account') != 'PMTrade01' or manifest.get('version') != 1:
            raise ValueError('Unsupported private manifest')
        player = manifest['snapshot']['users'][0]['player_id']
        payload = {'action': args.action, 'player_id': player}
        if args.action == 'prepare':
            destination = safe_path(output / 'prepared.json')
            # A durable attempt marker prevents retries even if a process dies
            # after committing but before recording the private result.
            write_new(safe_path(output / 'prepare-attempt.json'), {'action': 'prepare', 'private': True})
            if destination.exists():
                raise ValueError('Preparation receipt already exists')
            payload.update(baseline=manifest['snapshot'], new_uuid=str(uuid.uuid4()))
        elif args.action == 'observe':
            destination = safe_path(output / f'observe-{args.label}.json')
            write_new(safe_path(output / f'observe-{args.label}-attempt.json'), {'action': 'observe', 'private': True})
            if destination.exists():
                raise ValueError('Observation label already exists')
        else:
            prepared = json.loads(safe_path(output / 'prepared.json').read_text(encoding='utf-8'))
            if prepared['snapshot']['users'][0]['player_id'] != player:
                raise ValueError('Prepared identity mismatch')
            payload['baseline'] = prepared['snapshot']
            destination = safe_path(output / 'verified-cancelled.json')
            write_new(safe_path(output / 'verify-cancelled-attempt.json'), {'action': args.action, 'private': True})
            if destination.exists():
                raise ValueError('Verification already recorded')
        receipt = database(payload)
        write_new(destination, {'private': True, 'action': args.action,
                               'created_utc': datetime.datetime.now(datetime.UTC).isoformat(),
                               'provenance': 'Synthetic fixture copies own native-registration starter and attacks; only instance UUID and auto-increment IDs differ',
                               **receipt})
    print(f'{args.action}: OK; private receipt saved')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Fixture operation rejected; no automatic recovery performed. Private details suppressed.', file=sys.stderr)
        sys.exit(1)

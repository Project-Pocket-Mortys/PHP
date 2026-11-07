"""Private, append-only, read-only receipts for the dedicated native trading pair."""
import argparse
import datetime
import json
import re
import subprocess
import sys

from native_trade_fixture import ACCOUNTS, ROOT, safe_path, write_new


PHP = r'''
ini_set('display_errors','0');
function need($ok) { if (!$ok) throw new RuntimeException('Pair invariant rejected'); }
function rows($sql,$args=[]) { global $pdo; $q=$pdo->prepare($sql); $q->execute($args); return $q->fetchAll(PDO::FETCH_ASSOC); }
function slots($values) { need(count($values)>0); return implode(',',array_fill(0,count($values),'?')); }
try {
    need(PHP_SAPI==='cli' && getenv('PM_DB_HOST')==='db' && getenv('PM_DB_NAME')==='pocket_mortys');
    $arg=json_decode(stream_get_contents(STDIN),true,512,JSON_THROW_ON_ERROR);
    need($arg===['action'=>'capture']);
    $pdo=new PDO('mysql:host=db;port=3306;dbname=pocket_mortys;charset=utf8mb4',getenv('PM_DB_USER'),getenv('PM_DB_PASS'),[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
    $pdo->exec('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ');
    $pdo->exec('START TRANSACTION WITH CONSISTENT SNAPSHOT, READ ONLY');
    $users=[]; $players=[]; $morties=[]; $attacks=[]; $decks=[]; $items=[];
    foreach(['PMTrade01','PMTrade02'] as $account) {
        $u=rows('SELECT * FROM users WHERE username=? ORDER BY id',[$account]);
        need(count($u)===1 && $u[0]['username']===$account); $u=$u[0]; $p=$u['player_id'];
        need(is_string($p) && preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/D',$p));
        $owners=rows('SELECT * FROM users WHERE player_id=? ORDER BY id',[$p]);
        need(count($owners)===1 && $owners[0]['id']===$u['id']);
        need(is_string($u['session_id']) && $u['session_id']!=='');
        $sessions=rows('SELECT * FROM users WHERE session_id=? ORDER BY id',[$u['session_id']]);
        need(count($sessions)===1 && $sessions[0]['id']===$u['id']);
        need(!rows('SELECT * FROM friend_battle_memberships WHERE player_id=? ORDER BY player_id',[$p]));
        $m=rows('SELECT * FROM owned_morties WHERE player_id=? ORDER BY id',[$p]); need(count($m)===2);
        $ids=array_column($m,'owned_morty_id'); need(count(array_unique($ids,SORT_STRING))===2);
        foreach($m as $r) {
            $id=$r['owned_morty_id']; need(is_string($id) && preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/D',$id));
            $all=rows('SELECT * FROM owned_morties WHERE owned_morty_id=? ORDER BY id',[$id]);
            need(count($all)===1 && $all[0]['id']===$r['id'] && $all[0]['player_id']===$p && $all[0]['owned_morty_id']===$id);
            foreach(['morty_id'=>'MortyDefault','level'=>'5','xp'=>'125','hp'=>'20','hp_stat'=>'20','attack_stat'=>'11','defence_stat'=>'10','speed_stat'=>'10','variant'=>'Normal','is_locked'=>'false','is_trading_locked'=>'false','fight_pit_id'=>'null','evolution_points'=>'0','xp_lower'=>'125','xp_upper'=>'216'] as $k=>$v) need((string)$r[$k]===$v);
            foreach(['is_poisoned','is_paralysed'] as $k) if(array_key_exists($k,$r)) need((string)$r[$k]==='0');
            $a=rows('SELECT * FROM owned_attacks WHERE owned_morty_id=? ORDER BY id',[$id]); need(count($a)===1);
            need($a[0]['owned_morty_id']===$id && $a[0]['attack_id']==='AttackOutburst' && (string)$a[0]['position']==='0' && (string)$a[0]['pp']==='12' && (string)$a[0]['pp_stat']==='12');
            $attacks=[...$attacks,...$a];
        }
        $d=rows('SELECT * FROM decks WHERE player_id=? ORDER BY id',[$p]); need(count($d)===1);
        need((string)$u['active_deck_id']==='0' && (string)$d[0]['deck_id']==='0');
        $party=json_decode($d[0]['owned_morty_ids'],true,512,JSON_THROW_ON_ERROR);
        need(is_array($party) && count($party)===1 && array_is_list($party) && in_array($party[0],$ids,true));
        $users[]=$u; $players[]=$p; $morties=[...$morties,...$m]; $decks=[...$decks,...$d];
        $items=[...$items,...rows('SELECT * FROM owned_items WHERE player_id=? ORDER BY id',[$p])];
    }
    need(count(array_unique($players,SORT_STRING))===2);
    $ids=array_column($morties,'owned_morty_id'); need(count(array_unique($ids,SORT_STRING))===4);
    $ps=slots($players); $ms=slots($ids);
    $trades=rows("SELECT * FROM trades WHERE player_id IN ($ps) OR morty_trade_id IN ($ms) ORDER BY id",[...$players,...$ids]);
    $tradeIds=array_column($trades,'trade_id');
    $parent=$tradeIds ? ' OR trade_id IN ('.slots($tradeIds).')' : '';
    $offers=rows("SELECT * FROM trade_offers WHERE player_id IN ($ps) OR morty_offer_id IN ($ms)$parent ORDER BY id",[...$players,...$ids,...$tradeIds]);
    $tradeIds=array_values(array_unique([...$tradeIds,...array_column($offers,'trade_id')],SORT_STRING));
    if($tradeIds) {
        $ts=slots($tradeIds);
        $trades=rows("SELECT * FROM trades WHERE trade_id IN ($ts) ORDER BY id",$tradeIds);
        $offers=rows("SELECT * FROM trade_offers WHERE player_id IN ($ps) OR morty_offer_id IN ($ms) OR trade_id IN ($ts) ORDER BY id",[...$players,...$ids,...$tradeIds]);
    }
    $offerIds=array_column($offers,'trade_offer_id');
    $linked=($tradeIds ? ' OR trade_request_id IN ('.slots($tradeIds).')' : '').($offerIds ? ' OR trade_offer_id IN ('.slots($offerIds).')' : '');
    $completed=rows("SELECT * FROM completed_trades WHERE request_player_id IN ($ps) OR offer_player_id IN ($ps) OR morty_request_id IN ($ms) OR morty_offer_id IN ($ms)$linked ORDER BY id",[...$players,...$players,...$ids,...$ids,...$tradeIds,...$offerIds]);
    $friends=rows("SELECT * FROM friend_list WHERE player_id_a IN ($ps) OR player_id_b IN ($ps) ORDER BY id",[...$players,...$players]);
    $tokens=[...$players,...$ids,...$tradeIds,...$offerIds,'PMTrade01','PMTrade02'];
    $events=array_values(array_filter(rows('SELECT * FROM event_queue ORDER BY id'),function($row) use($tokens) {
        foreach($row as $v) if(is_string($v)) foreach($tokens as $token) if($token!=='' && strpos($v,$token)!==false) return true;
        return false;
    }));
    $snapshot=['users'=>$users,'owned_morties'=>$morties,'owned_attacks'=>$attacks,'decks'=>$decks,'owned_items'=>$items,'trades'=>$trades,'trade_offers'=>$offers,'completed_trades'=>$completed,'friend_list'=>$friends,'event_queue'=>$events,'friend_battle_memberships'=>[]];
    $pdo->commit(); echo json_encode(['snapshot'=>$snapshot],JSON_THROW_ON_ERROR);
} catch(Throwable $e) { if(isset($pdo) && $pdo->inTransaction()) $pdo->rollBack(); fwrite(STDERR,"Native trading pair snapshot rejected; private details suppressed.\n"); exit(1); }
'''


def identity(snapshot):
    users = snapshot['users']
    if len(users) != 2 or {u['username'] for u in users} != set(ACCOUNTS):
        raise ValueError('Unexpected pair accounts')
    if len({u['id'] for u in users}) != 2 or len({u['player_id'] for u in users}) != 2:
        raise ValueError('Pair owner identities collide')
    result = {}
    instances = set()
    for account in ACCOUNTS:
        user = next(u for u in users if u['username'] == account)
        morties = [m for m in snapshot['owned_morties'] if m['player_id'] == user['player_id']]
        if len(morties) != 2:
            raise ValueError('Unexpected paired inventory')
        owned = sorted((m['id'], m['owned_morty_id']) for m in morties)
        for _, instance in owned:
            if not instance or instance in instances:
                raise ValueError('Pair instance identities collide')
            instances.add(instance)
        result[account] = {'user_id': user['id'], 'player_id': user['player_id'],
                           'morties': [list(row) for row in owned]}
    if len(snapshot['owned_morties']) != 4:
        raise ValueError('Unexpected inventory owner')
    if len({m['id'] for m in snapshot['owned_morties']}) != 4:
        raise ValueError('Pair inventory row identities collide')
    return result


def baseline_identity(baseline):
    if baseline.get('version') != 1 or baseline.get('accounts') != list(ACCOUNTS):
        raise ValueError('Unsupported pair baseline')
    anchor = identity(baseline['snapshot'])
    if baseline.get('identity') != anchor:
        raise ValueError('Pair baseline identity conflict')
    if any(row['player_id'] == anchor['PMTrade01']['player_id']
           for row in baseline['snapshot']['trade_offers']):
        raise ValueError('Primary account already has a baseline offer')
    return anchor


def database():
    result = subprocess.run(
        ['docker', 'compose', '-f', str(ROOT / 'compose.research.yaml'), 'exec', '-T', 'web', 'php', '-r', PHP],
        cwd=ROOT, input=json.dumps({'action': 'capture'}), text=True,
        capture_output=True, encoding='utf-8', timeout=60,
    )
    if result.returncode:
        raise RuntimeError('Pair snapshot rejected; private process output suppressed')
    try:
        return json.loads(result.stdout)
    except (ValueError, TypeError):
        raise RuntimeError('Invalid private pair receipt') from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['snapshot', 'observe'])
    parser.add_argument('--output', required=True)
    parser.add_argument('--label')
    args = parser.parse_args()
    if args.action == 'observe':
        if not args.label or not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', args.label):
            parser.error('observe requires a safe unique --label')
    elif args.label:
        parser.error('--label is only supported by observe')
    output = safe_path(args.output, fresh=args.action == 'snapshot')
    anchor = None
    if args.action == 'snapshot':
        output.mkdir(parents=True, exist_ok=False)
        destination = output / 'baseline.json'
        marker = output / 'snapshot-attempt.json'
    else:
        baseline = json.loads(safe_path(output / 'baseline.json').read_text(encoding='utf-8'))
        anchor = baseline_identity(baseline)
        destination = output / f'observe-{args.label}.json'
        marker = output / f'observe-{args.label}-attempt.json'
    destination = safe_path(destination)
    write_new(safe_path(marker), {'action': args.action, 'private': True})
    if destination.exists():
        raise ValueError('Private receipt already exists')
    receipt = database()
    captured = identity(receipt['snapshot'])
    if anchor is not None and captured != anchor:
        raise ValueError('Observation identity differs from immutable baseline')
    document = {'version': 1, 'accounts': list(ACCOUNTS), 'private': True,
                'action': args.action, 'identity': captured,
                'created_utc': datetime.datetime.now(datetime.UTC).isoformat(), **receipt}
    if args.action == 'snapshot':
        baseline_identity(document)
    write_new(destination, document)
    print(f'{args.action}: OK; private pair receipt saved')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Pair snapshot rejected; private details suppressed.', file=sys.stderr)
        sys.exit(1)

"""Dedicated native startup smoke fixture; raw evidence stays under .research.

Create PMStartup01 and PMStartup02 in fresh Android AVDs first. Snapshot before
prepare; prepare adds only the social pair/invitation through HTTP. Activation is
an explicit research CLI operation, never a native acceptance claim. This helper
does not open SSE, send readiness, modify owned rows, or delete evidence/accounts.
For a later round, snapshot into a fresh output with --previous pointing to the
prior cancelled manifest. Its save baseline and accepted friendship are checked
and retained; the prior artifact and history are never rewritten. Use verify
--expect-paired to require the first selection pair before or after retirement.
"""
import argparse
import base64
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
NAMES = ['PMStartup01', 'PMStartup02']
COMPOSE = ['docker', 'compose', '-f', str(ROOT / 'compose.research.yaml')]
VOLATILE = {'session_id', 'state', 'last_event_id', 'last_seen',
            'room_membership_generation'}

PHP = r'''
if (PHP_SAPI!=='cli' || getenv('PM_DB_HOST')!=='db' || getenv('PM_DB_NAME')!=='pocket_mortys') throw new RuntimeException('Isolated CLI required');
require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';
require_once '/var/www/html/lib/friend_battle_startup.php';
$pdo->setAttribute(PDO::ATTR_DEFAULT_FETCH_MODE,PDO::FETCH_ASSOC);
function fixture_rows($pdo,$sql,$args=[]) { $q=$pdo->prepare($sql); $q->execute($args); return $q->fetchAll(PDO::FETCH_ASSOC); }
function fixture_accounts($pdo,$expected) {
    $rows=fixture_rows($pdo,"SELECT * FROM users WHERE username IN ('PMStartup01','PMStartup02') ORDER BY username");
    if(count($rows)!==2 || array_column($rows,'username')!==['PMStartup01','PMStartup02'] || $rows[0]['player_id']===$rows[1]['player_id']) throw new RuntimeException('Dedicated accounts required');
    foreach($rows as $i=>$u) {
        if(!preg_match('/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/D',$u['player_id'])) throw new RuntimeException('UUID required');
        // Native autoSignIn legitimately rotates session_id after session:end.
        // Anchor immutable identity, then authenticate the current DB session.
        if($expected && ($expected[$i]['player_id']!==$u['player_id'] || $expected[$i]['username']!==$u['username'] || $expected[$i]['secret']!==$u['secret'])) throw new RuntimeException('Account identity changed');
        if(!is_string($u['session_id']) || $u['session_id']==='' || friend_auth($pdo,$u['session_id'])['player_id']!==$u['player_id']) throw new RuntimeException('Authenticated session required');
    }
    return $rows;
}
function fixture_live($pdo,$users) {
    foreach($users as $u) {
        $s=friend_transport_stream($pdo,$u['player_id']);
        if(!$s || !(bool)$s['live'] || !hash_equals($s['session_sha256'],hash('sha256',$u['session_id']))) throw new RuntimeException('Live native streams required');
        if(fixture_rows($pdo,'SELECT 1 FROM friend_battle_stream_bindings WHERE player_id=? AND stream_id=?',[$u['player_id'],$s['stream_id']])) throw new RuntimeException('Fresh stream generation required');
    }
}
$users=fixture_accounts($pdo,$x['accounts']??null);
'''


def php(code, data=None, seconds=120):
    payload = base64.b64encode(json.dumps(data or {}).encode()).decode()
    source = "<?php\n$x=json_decode(base64_decode('" + payload + "'),true);\n" + PHP + code
    result = subprocess.run(COMPOSE + ['exec', '-T', '-e',
        'PM_RESEARCH_SHARED_BATTLE_STREAM=1', '-e',
        f'PM_FRIEND_BATTLE_STARTUP_SECONDS={seconds}', 'web', 'php'], input=source,
        cwd=ROOT, capture_output=True, text=True, encoding='utf-8', timeout=30)
    if result.returncode:
        # PHP errors can contain private data; callers retain evidence locally.
        raise RuntimeError('Research CLI failed; no private subprocess output printed')
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        raise RuntimeError('Research CLI returned invalid JSON') from None


def save(path, value):
    temporary = path.with_suffix('.next.json')
    temporary.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')
    temporary.replace(path)


def snapshot(accounts=None):
    return php(r'''
    $pdo->beginTransaction();
    $players=array_column($users,'player_id'); $sorted=$players; sort($sorted,SORT_STRING);
    foreach($sorted as $p) fixture_rows($pdo,'SELECT player_id FROM users WHERE player_id=? FOR UPDATE',[$p]);
    $users=fixture_accounts($pdo,$x['accounts']??null);
    $result=['accounts'=>$users,'owned'=>[]];
    $tables=fixture_rows($pdo,"SELECT TABLE_NAME FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND COLUMN_NAME='player_id' AND (TABLE_NAME LIKE 'owned\\_%' OR TABLE_NAME IN ('decks','mortydex')) ORDER BY TABLE_NAME");
    foreach($tables as $table) {
        $t=$table['TABLE_NAME']; if(!preg_match('/^[a-z_]+$/D',$t)) throw new RuntimeException('Unsafe schema');
        $result['owned'][$t]=fixture_rows($pdo,"SELECT * FROM `$t` WHERE player_id IN (?,?) ORDER BY id FOR UPDATE",$players);
    }
    $result['owned']['owned_attacks']=fixture_rows($pdo,'SELECT a.* FROM owned_attacks a JOIN owned_morties m ON m.owned_morty_id=a.owned_morty_id WHERE m.player_id IN (?,?) ORDER BY a.id FOR UPDATE',$players);
    $result['friends']=fixture_rows($pdo,'SELECT * FROM friend_list WHERE player_id_a IN (?,?) OR player_id_b IN (?,?) ORDER BY id',[...$players,...$players]);
    $result['invites']=fixture_rows($pdo,'SELECT * FROM friend_battle_invites WHERE sender_id IN (?,?) OR recipient_id IN (?,?) ORDER BY invite_id',[...$players,...$players]);
    $result['battles']=fixture_rows($pdo,'SELECT * FROM battles WHERE player_id IN (?,?) OR opponent_id IN (?,?) ORDER BY battle_id',[...$players,...$players]);
    $result['sessions']=fixture_rows($pdo,'SELECT * FROM friend_battle_sessions WHERE sender_id IN (?,?) OR recipient_id IN (?,?) ORDER BY battle_id',[...$players,...$players]);
    $result['memberships']=fixture_rows($pdo,'SELECT * FROM friend_battle_memberships WHERE player_id IN (?,?) ORDER BY player_id',$players);
    $result['streams']=fixture_rows($pdo,'SELECT * FROM friend_battle_streams WHERE player_id IN (?,?) ORDER BY player_id',$players);
    $pdo->commit(); echo json_encode($result,JSON_THROW_ON_ERROR);
    ''', {'accounts': accounts})


def guard(f):
    current = snapshot(f['before']['accounts'])
    assert current['owned'] == f['before']['owned'], 'Owned save rows changed; preserve evidence'
    assert current['battles'] == f['before']['battles'], 'Legacy battles changed'
    # Room/world/zone remain strict persistent comparisons. A recovery into a
    # different room requires explicit review of captured membership evidence.
    for before, after in zip(f['before']['accounts'], current['accounts']):
        assert {k: v for k, v in before.items() if k not in VOLATILE} == {
            k: v for k, v in after.items() if k not in VOLATILE}, 'Persistent trainer data changed'
    if f.get('reuse_social'):
        previous = research_path(Path(f['previous_artifact']['path']))
        assert hashlib.sha256(previous.read_bytes()).hexdigest() == f['previous_artifact']['sha256'], 'Previous artifact changed'
        assert current['friends'] == [f['accepted_friend']], 'Accepted social pair changed'
        for table, key in [('invites', 'invite_id'), ('sessions', 'battle_id')]:
            by_id = {row[key]: row for row in current[table]}
            assert all(by_id.get(row[key]) == row for row in f['before'][table]), 'Previous social/startup history changed'
    invite_by_id = {row['invite_id']: row for row in current['invites']}
    for refresh in f.get('invite_refreshes', []):
        retired = refresh.get('after_previous_invite')
        if retired is not None:
            assert invite_by_id.get(retired['invite_id']) == retired, 'Refreshed invitation history changed'
    return current


def research_path(path):
    path = path.resolve()
    assert path.is_relative_to((ROOT / '.research').resolve()), 'Ignored .research path required'
    return path


def accepted_pair(f, current):
    row = f['accepted_friend']
    players = {u['player_id'] for u in current['accounts']}
    assert row['pending'] == 'false' and {row['player_id_a'], row['player_id_b']} == players
    assert current['friends'] == [row], 'Exactly the saved accepted pair required'


def post(f, path, role, **body):
    current = guard(f)
    body['session_id'] = current['accounts'][role]['session_id']
    request = urllib.request.Request(f['origin'] + path + '/', json.dumps(body).encode(),
                                    {'Content-Type': 'application/json'}, method='POST')
    try:
        response = urllib.request.urlopen(request, timeout=20)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        result = {'path': path, 'role': role, 'status': response.status,
                  'response': json.loads(response.read())}
    f.setdefault('http', []).append(result)
    save(Path(f['_manifest']), {k: v for k, v in f.items() if k != '_manifest'})
    assert result['status'] == 200, 'HTTP fixture setup failed; preserve manifest'
    return result['response']


def status(f):
    return php(r'''
    $pdo->beginTransaction();
    $ids=array_column($users,'player_id'); sort($ids,SORT_STRING);
    foreach($ids as $id) fixture_rows($pdo,'SELECT player_id FROM users WHERE player_id=? FOR UPDATE',[$id]);
    $users=fixture_accounts($pdo,$x['accounts']);
    $result=['roles'=>[],'startup'=>null];
    foreach($users as $i=>$u) {
        $s=friend_transport_stream($pdo,$u['player_id']);
        $age=$s ? fixture_rows($pdo,'SELECT TIMESTAMPDIFF(MICROSECOND,heartbeat_at,UTC_TIMESTAMP(6))/1000000 AS seconds FROM friend_battle_streams WHERE player_id=?',[$u['player_id']])[0]['seconds'] : null;
        $result['roles'][$i===0?'sender':'recipient']=['state'=>$u['state'],'in_room'=>$u['room_id']!==null,'stream_present'=>$s!==null,'stream_live'=>$s?(bool)$s['live']:false,'stream_generation'=>$s?hash('sha256',$s['stream_id']):null,'heartbeat_age_seconds'=>$age];
    }
    if($x['battle']??null) {
        $id=$x['battle'];
        $rows=fixture_rows($pdo,'SELECT s.state,s.cancel_reason,t.sender_ready_at IS NOT NULL AS sender_ready,t.recipient_ready_at IS NOT NULL AS recipient_ready,t.ready_at IS NOT NULL AS both_ready,TIMESTAMPDIFF(MICROSECOND,UTC_TIMESTAMP(6),t.ready_deadline)/1000000 AS deadline_remaining_seconds FROM friend_battle_sessions s LEFT JOIN friend_battle_startups t ON t.battle_id=s.battle_id WHERE s.battle_id=? AND s.sender_id=? AND s.recipient_id=?',[$id,$users[0]['player_id'],$users[1]['player_id']]);
        if(count($rows)!==1) throw new RuntimeException('Exact startup required');
        $result['startup']=$rows[0];
        $counts=fixture_rows($pdo,'SELECT (SELECT COUNT(*) FROM friend_battle_memberships WHERE battle_id=?) AS claims_for_battle,(SELECT COUNT(*) FROM friend_battle_start_intents WHERE battle_id=?) AS intent_count,(SELECT COUNT(*) FROM friend_battle_start_intents WHERE battle_id=? AND retired_at IS NOT NULL) AS retired_intent_count',[$id,$id,$id])[0];
        foreach($counts as $key=>$value) $result['startup'][$key]=(int)$value;
        $selection_tables=fixture_rows($pdo,"SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME IN ('friend_battle_selections','friend_battle_selection_pairs')");
        if(count($selection_tables)===2) {
            $counts=fixture_rows($pdo,'SELECT (SELECT COUNT(*) FROM friend_battle_selections WHERE battle_id=?) AS selection_count,(SELECT COUNT(*) FROM friend_battle_selections WHERE battle_id=? AND retired_at IS NOT NULL) AS retired_selection_count,(SELECT COUNT(*) FROM friend_battle_selection_pairs WHERE battle_id=?) AS pair_count,(SELECT COUNT(*) FROM friend_battle_selection_pairs WHERE battle_id=? AND retired_at IS NOT NULL) AS retired_pair_count',[$id,$id,$id,$id])[0];
            foreach($counts as $key=>$value) $result['startup'][$key]=(int)$value;
        }
        $result['attempts']=[];
        foreach($users as $i=>$u) $result['attempts'][$i===0?'sender':'recipient']=fixture_rows($pdo,'SELECT TIMESTAMPDIFF(MICROSECOND,attempted_at,UTC_TIMESTAMP(6))/1000000 AS age_seconds FROM friend_battle_start_attempts WHERE battle_id=? AND player_id=?',[$id,$u['player_id']]);
    }
    $pdo->commit(); echo json_encode($result,JSON_THROW_ON_ERROR);
    ''', {'accounts': f['before']['accounts'], 'battle': f.get('battle')})


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=['snapshot', 'prepare', 'refresh-invite', 'reserve-activate', 'status', 'verify', 'cancel'])
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--origin', default='http://127.0.0.1:8089', choices=['http://127.0.0.1:8089'])
    p.add_argument('--startup-seconds', type=int, default=120, choices=range(30, 121))
    p.add_argument('--previous', type=Path, help='Prior terminal fixture manifest; snapshot only')
    p.add_argument('--expect-paired', action='store_true', help='Require two selections and one pair; verify only')
    args = p.parse_args()
    assert args.previous is None or args.action == 'snapshot', '--previous is snapshot-only'
    assert not args.expect_paired or args.action == 'verify', '--expect-paired is verify-only'
    out = research_path(args.output)
    manifest = out / 'startup-fixture.json'
    if args.action == 'snapshot':
        assert not manifest.exists(), 'Fresh manifest required'
        reuse = {}
        if args.previous is not None:
            previous_path = research_path(args.previous)
            assert previous_path != manifest, 'Previous manifest must remain separate'
            previous_bytes = previous_path.read_bytes()
            previous = json.loads(previous_bytes.decode('utf-8'))
            assert previous['names'] == NAMES and previous.get('battle'), 'Prior dedicated fixture required'
            before = guard(previous)
            prior_status = status(previous)['startup']
            assert prior_status['state'] == 'CANCELLED' and prior_status['claims_for_battle'] == 0
            assert prior_status['intent_count'] == 2 and prior_status['retired_intent_count'] == 2
            assert all(key in prior_status for key in ('selection_count', 'retired_selection_count', 'pair_count', 'retired_pair_count')), 'Selection migration required for a new round'
            accepted_pair(previous, before)
            assert not before['memberships'], 'No retained claims allowed'
            assert all(s['state'] == 'CANCELLED' for s in before['sessions']), 'Only cancelled shared history allowed'
            assert hashlib.sha256(previous_path.read_bytes()).digest() == hashlib.sha256(previous_bytes).digest(), 'Previous manifest changed during validation'
            reuse = {'reuse_social': True, 'accepted_friend': previous['accepted_friend'],
                     'previous_artifact': {'path': str(previous_path), 'sha256': hashlib.sha256(previous_bytes).hexdigest()}}
        else:
            before = snapshot()
            assert not before['friends'] and not before['invites'] and not before['sessions']
        assert all(u['state'] == 'WORLD' for u in before['accounts'])
        assert not any(b['state'] == 'ACTIVE' for b in before['battles'])
        out.mkdir(parents=True, exist_ok=True)
        save(manifest, {'names': NAMES, 'before': before, 'origin': args.origin,
                        'owned_additions': [], 'policy': 'Preserve native registration party; fail closed if invalid', **reuse})
        print('Dedicated native accounts snapshotted; private credentials retained only in ignored manifest.')
        return
    f = json.loads(manifest.read_text(encoding='utf-8'))
    assert f['names'] == NAMES
    f['_manifest'] = str(manifest)
    current = guard(f)
    accounts = f['before']['accounts']
    if args.action == 'prepare':
        assert not f.get('prepared')
        if f.get('reuse_social'):
            accepted_pair(f, current)
            assert current['invites'] == f['before']['invites'] and current['sessions'] == f['before']['sessions']
            assert not current['memberships'] and all(s['state'] == 'CANCELLED' for s in current['sessions'])
        else:
            assert not current['friends'] and not current['invites'] and not current['sessions']
        assert all(u['state'] == 'WORLD' for u in current['accounts'])
        php('''$pdo->beginTransaction(); $ids=array_column($users,'player_id'); sort($ids,SORT_STRING); foreach($ids as $id) fixture_rows($pdo,'SELECT player_id FROM users WHERE player_id=? FOR UPDATE',[$id]); $users=fixture_accounts($pdo,$x['accounts']); foreach($users as $u) { friend_party_capture_locked($pdo,$u); friend_start_context_locked($pdo,$u); } $pdo->rollBack(); echo '{}';''', {'accounts': accounts})
        if not f.get('reuse_social'):
            post(f, '/session/friend/request', 0, player_id=accounts[1]['player_id'])
            current = guard(f)
            assert len(current['friends']) == 1
            f['created_friend'] = current['friends'][0]
            save(manifest, {k: v for k, v in f.items() if k != '_manifest'})
            post(f, '/session/friend/response', 1, player_id=accounts[0]['player_id'], approve=True)
            current = guard(f)
            assert len(current['friends']) == 1 and current['friends'][0]['id'] == f['created_friend']['id'] and current['friends'][0]['pending'] == 'false'
            f['accepted_friend'] = current['friends'][0]
        reply = post(f, '/session/battle-invite/create', 0, opponent_player_id=accounts[1]['player_id'], battle_type='PvF')
        current = guard(f)
        assert reply['battle_invite_id'] not in {row['invite_id'] for row in f['before']['invites']}, 'Fresh invitation ID required'
        invites = [row for row in current['invites'] if row['invite_id'] == reply['battle_invite_id']]
        assert len(current['invites']) == len(f['before']['invites']) + 1
        assert len(invites) == 1 and invites[0]['invite_id'] == reply['battle_invite_id']
        assert invites[0]['sender_id'] == accounts[0]['player_id'] and invites[0]['recipient_id'] == accounts[1]['player_id']
        f['invite'] = invites[0]
        f['prepared'] = True
    elif args.action == 'refresh-invite':
        assert f.get('prepared') and not f.get('battle'), 'Only an unreserved prepared fixture may refresh'
        accepted_pair(f, current)
        assert all(u['state'] == 'WORLD' for u in current['accounts'])
        assert not current['memberships'] and all(s['state'] == 'CANCELLED' for s in current['sessions'])
        assert not any(b['state'] == 'ACTIVE' for b in current['battles'])
        old_id = f['invite']['invite_id']
        old_rows = [row for row in current['invites'] if row['invite_id'] == old_id]
        assert len(old_rows) == 1, 'Exact prior invitation required'
        old = old_rows[0]
        assert old['sender_id'] == accounts[0]['player_id'] and old['recipient_id'] == accounts[1]['player_id']
        eligibility = php(r'''
        $rows=fixture_rows($pdo,"SELECT (state IN ('EXPIRED','DECLINED','REVOKED') OR (state='PENDING' AND expires_at<=UTC_TIMESTAMP(6))) AS eligible FROM friend_battle_invites WHERE invite_id=? AND sender_id=? AND recipient_id=?",[$x['invite'],$users[0]['player_id'],$users[1]['player_id']]);
        if(count($rows)!==1) throw new RuntimeException('Exact prior invitation required');
        echo json_encode(['eligible'=>(bool)$rows[0]['eligible']]);
        ''', {'accounts': accounts, 'invite': old_id})
        assert eligibility['eligible'], 'A live or accepted invitation cannot be refreshed'
        refresh = {'previous_manifest_invite': f['invite'], 'before_invites': current['invites']}
        f.setdefault('invite_refreshes', []).append(refresh)
        save(manifest, {k: v for k, v in f.items() if k != '_manifest'})
        reply = post(f, '/session/battle-invite/create', 0, opponent_player_id=accounts[1]['player_id'], battle_type='PvF')
        after = guard(f)
        new_id = reply['battle_invite_id']
        prior_ids = {row['invite_id'] for row in current['invites']}
        assert new_id not in prior_ids, 'Refresh must create a new invitation'
        by_id = {row['invite_id']: row for row in after['invites']}
        assert set(by_id) == prior_ids | {new_id}, 'Unexpected invitation history change'
        for row in current['invites']:
            saved = by_id[row['invite_id']]
            if row['invite_id'] == old_id and row['state'] == 'PENDING':
                assert saved['state'] == 'EXPIRED', 'Normal API expiry required'
                assert {k: v for k, v in saved.items() if k not in ('state', 'updated_at')} == {
                    k: v for k, v in row.items() if k not in ('state', 'updated_at')}, 'Expired invitation identity changed'
            else:
                assert saved == row, 'Prior invitation history changed'
        fresh = by_id[new_id]
        assert fresh['sender_id'] == accounts[0]['player_id'] and fresh['recipient_id'] == accounts[1]['player_id']
        assert fresh['state'] == 'PENDING' and after['sessions'] == current['sessions']
        refresh['after_previous_invite'] = by_id[old_id]
        refresh['new_invite_id'] = new_id
        f['invite'] = fresh
    elif args.action == 'reserve-activate':
        assert f.get('prepared') and not f.get('battle')
        assert current['friends'] == [f['accepted_friend']]
        php("fixture_live($pdo,$users); echo '{}';", {'accounts': accounts})
        data = {'accounts': accounts, 'token': f['invite']['recipient_token']}
        f['battle'] = php("echo json_encode(friend_battle_reserve($pdo,$users[1]['session_id'],$x['token']));", data)
        save(manifest, {k: v for k, v in f.items() if k != '_manifest'})
        data['battle'] = f['battle']
        for step, function in [('freeze', 'friend_battle_snapshot_parties'), ('views', 'friend_battle_build_start_views'), ('activate', 'friend_battle_startup_activate')]:
            guard(f)
            result = php('fixture_accounts($pdo,$x[\'accounts\']); ' + function + "($pdo,$users[1]['session_id'],$x['battle']); echo '{\"ok\":true}';", data, args.startup_seconds)
            f.setdefault('steps', {})[step] = result
            save(manifest, {k: v for k, v in f.items() if k != '_manifest'})
    elif args.action == 'cancel':
        assert f.get('battle')
        state = status(f)['startup']['state']
        if state in ('STARTING', 'READY', 'PREPARING'):
            function = 'friend_battle_cancel_reservation' if state == 'PREPARING' else 'friend_battle_startup_cancel'
            php(function + "($pdo,$users[1]['session_id'],$x['battle']); echo '{}';", {'accounts': accounts, 'battle': f['battle']})
        else:
            assert state == 'CANCELLED'
        f['cancelled'] = True
    result = status(f)
    if args.action == 'verify':
        assert f.get('battle') and result['startup']['state'] in ('READY', 'CANCELLED')
        if result['startup']['state'] == 'READY':
            assert int(result['startup']['both_ready']) == 1
            assert all(len(v) == 1 for v in result['attempts'].values())
            assert result['startup']['claims_for_battle'] == 2
            assert result['startup']['intent_count'] == 2
            assert result['startup']['retired_intent_count'] == 0
        else:
            assert result['startup']['claims_for_battle'] == 0
            assert result['startup']['intent_count'] == 2
            assert result['startup']['retired_intent_count'] == 2
        if args.expect_paired:
            startup = result['startup']
            assert startup['selection_count'] == 2 and startup['pair_count'] == 1
            retired = startup['state'] == 'CANCELLED'
            assert startup['retired_selection_count'] == (2 if retired else 0)
            assert startup['retired_pair_count'] == (1 if retired else 0)
        guard(f)
        result['persistent_data_unchanged'] = True
    f.setdefault('observations', []).append({'action': args.action, 'status': result})
    save(manifest, {k: v for k, v in f.items() if k != '_manifest'})
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Fixture stopped: ' + type(error).__name__ + '; preserve ignored manifest and inspect locally.', file=sys.stderr)
        sys.exit(1)

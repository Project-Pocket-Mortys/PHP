"""Guard two existing research accounts; all friend actions originate in Android UI.

Preparation and cleanup never alter friend rows. Complete the native remove/cancel
path to return the pair to its original state. Raw artifacts remain in .research.
"""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import uuid

import battle_item_fixture as items
import capture_battle_lifecycle as capture
import probe_android_peers as peers
import status_cure_fixture as guards

ROOT, sql = capture.ROOT, capture.sql
NAMES = ('PMResearch01', 'PMResearch02')
VOLATILE = {'session_id', 'state', 'last_event_id', 'last_seen', 'room_membership_generation'}


def queries(players):
    result = {}
    columns = [r['Field'] for r in sql('SHOW COLUMNS FROM users') if r['Field'] not in VOLATILE]
    for player in players:
        for key, query in guards.queries(player).items():
            if key == 'user':
                query = 'SELECT ' + ','.join('`'+c+'`' for c in columns) + f" FROM users WHERE player_id='{player}'"
            result[player + ':' + key] = query
    ids = "','".join(players)
    result['friend_rows'] = f"SELECT * FROM friend_list WHERE player_id_a IN ('{ids}') OR player_id_b IN ('{ids}') ORDER BY id"
    return result


def locked_snapshot(players):
    payload = base64.b64encode(json.dumps(dict(queries=queries(players), players=players)).encode()).decode()
    return json.loads(items.locked_php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; $x=json_decode(base64_decode('" + payload + "'),true);" + """
      $pdo->beginTransaction();
      try {
        $result=[];
        foreach($x['players'] as $p) {
          $q=$pdo->prepare('SELECT state FROM users WHERE player_id=? FOR UPDATE');
          $q->execute([$p]); $u=$q->fetchAll();
          if(count($u)!==1 || $u[0]['state']!=='WORLD') throw new RuntimeException('Require WORLD');
          $q=$pdo->prepare("SELECT battle_id FROM battles WHERE player_id=? AND state='ACTIVE' FOR UPDATE");
          $q->execute([$p]); if($q->fetch()) throw new RuntimeException('Active battle');
        }
        foreach($x['queries'] as $k=>$query) $result[$k]=$pdo->query($query.' FOR UPDATE')->fetchAll();
        $pdo->commit(); echo json_encode($result);
      } catch(Throwable $e) {if($pdo->inTransaction()) $pdo->rollBack(); throw $e;}
    """))


def log_lines():
    return subprocess.run(capture.http.COMPOSE + ['exec', '-T', 'web', 'cat', '/tmp/pocket-research-http.jsonl'],
                          cwd=ROOT, capture_output=True, text=True, check=True, timeout=20).stdout.splitlines()


def native(f):
    lines = log_lines()
    assert len(lines) >= f['log_floor'], 'Capture log truncated'
    # Session IDs are intentionally redacted by the server capture middleware.
    # Empty polls cannot be assigned to an account, so retain them separately;
    # never attribute concurrent UUID-only regression traffic to native Android.
    result = dict(pair=[], unattributed_empty_polls=[], search=[])
    players = set(f['players'])
    for line in lines[f['log_floor']:]:
        row = json.loads(line)
        if not row.get('path', '').startswith('/session/friend/'):
            continue
        request, response = row.get('request'), row.get('response')
        request = request if isinstance(request, dict) else {}
        response = response if isinstance(response, dict) else {}
        ids = {response.get('player_id'), response.get('player_id_a'), response.get('player_id_b')}
        for key in ('requests_sent', 'requests_received', 'friends'):
            ids.update(r.get('player_id') for r in (response.get(key) or []) if isinstance(r, dict))
        target = request.get('player_id')
        if (isinstance(target, str) and target in players) or ids & players:
            result['pair'].append(row)
        elif row['path'].rstrip('/') == '/session/friend/list' and row['status'] == 200 and all(response.get(k) == [] for k in ('requests_sent', 'requests_received', 'friends')):
            result['unattributed_empty_polls'].append(row)
        elif row['path'].rstrip('/') == '/session/friend/search' and request.get('query') in f['names']:
            result['search'].append(row)
    return result


def pair_rows(rows, players):
    return [r for r in rows if {r['player_id_a'], r['player_id_b']} == set(players)]


def baseline(f):
    # Old manifests retain their original generation field for audit. A room
    # rejoin advances this connection counter; it is never save data to restore.
    expected = json.loads(json.dumps(f['before']))
    for player in f['players']:
        for row in expected[player+':user']:
            for key in VOLATILE:
                row.pop(key, None)
    return expected


def guard(f, current):
    expected = baseline(f)
    expected.pop('friend_rows')
    actual = dict(current)
    rows = actual.pop('friend_rows')
    assert actual == expected, 'Account save data changed; preserve evidence'
    assert [r for r in rows if r not in pair_rows(rows, f['players'])] == f['before']['friend_rows'], 'Original friend rows changed'
    pair = pair_rows(rows, f['players'])
    assert len(pair) <= 1, 'Ambiguous pair'
    return pair


def acceptance(f):
    rows = native(f)['pair']
    mutations = [r for r in rows if r['path'].rstrip('/').rsplit('/', 1)[-1] in ('request', 'response', 'remove')]
    actions = [(r['path'].rstrip('/').rsplit('/', 1)[-1], r['request'].get('approve')) for r in mutations]
    assert actions[:5] == [('request', None), ('response', False), ('request', None), ('response', True), ('remove', None)], actions
    assert actions[5:] in ([], [('request', None), ('remove', None)]), actions
    assert all(r['status'] == 200 for r in mutations)
    a, b = f['players']
    for r in mutations:
        action = r['path'].rstrip('/').rsplit('/', 1)[-1]
        assert set(r['request']) == ({'session_id', 'player_id', 'approve'} if action == 'response' else {'session_id', 'player_id'})
        if action == 'request':
            assert r['request']['player_id'] == b
            assert r['response']['player_id_a'] == a and r['response']['player_id_b'] == b
            assert r['response']['pending'] is True
        elif action == 'response':
            assert r['request']['player_id'] == a and type(r['request']['approve']) is bool
            assert r['response'] == 1
    sightings = set()
    pending_fields = {'player_id', 'username', 'player_avatar_id', 'level', '_created'}
    friend_fields = {'player_id', 'username', 'player_avatar_id', 'level', 'wins', 'losses', 'donation_request', 'online'}
    for r in rows:
        if r['path'].rstrip('/') != '/session/friend/list' or r['status'] != 200:
            continue
        response = r['response']
        assert response['poll_period'] == 5 and response['limit_friends'] == 30
        assert isinstance(response['donation_request'], dict)
        for key in ('requests_sent', 'requests_received', 'friends'):
            assert isinstance(response[key], list)
            for peer in response[key]:
                assert set(peer) <= (friend_fields if key == 'friends' else pending_fields), 'Private peer field leaked'
                assert type(peer['level']) is int
                if key == 'friends':
                    assert type(peer['wins']) is int and type(peer['losses']) is int
                if peer['player_id'] in f['players']:
                    sightings.add((key, peer['player_id']))
    assert {('requests_sent', b), ('requests_received', a), ('friends', a), ('friends', b)} <= sightings
    return dict(native_mutations=len(mutations), decline_then_accept_then_remove=True,
                both_native_friend_projections=True, public_peer_fields_only=True,
                canonical_sender_recipient=True, pair_http=rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'record', 'cleanup', 'verify', 'acceptance'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--label', default='current')
    parser.add_argument('--screens', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    assert out.is_relative_to((ROOT / '.research').resolve())
    assert args.label.replace('-', '').replace('_', '').isalnum()
    assert capture.php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');") == 'db:http://localhost:8087'
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / 'fixture.json'
    if args.action == 'prepare':
        assert not manifest.exists(), 'Preserve existing evidence; use fresh directory'
        users = sql("SELECT username,player_id FROM users WHERE username IN ('PMResearch01','PMResearch02') ORDER BY username")
        assert [r['username'] for r in users] == list(NAMES)
        players = [r['player_id'] for r in users]
        assert all(str(uuid.UUID(p)) == p for p in players)
        before = locked_snapshot(players)
        assert not pair_rows(before['friend_rows'], players), 'Original pair exists; do not remove it'
        assert all(before[p+':user'][0]['shiny_potion_expires_at'] is None for p in players)
        f = dict(players=players, names=list(NAMES), before=before, log_floor=len(log_lines()),
                 provenance='Existing research accounts; native Android friend mutations only; no fixture SQL mutations')
        items.save(manifest, f)
        print('Locked original accounts and all touching friend rows retained; no database changes.')
        return
    f = json.loads(manifest.read_text())
    current = locked_snapshot(f['players'])
    pair = guard(f, current)
    if args.action == 'acceptance':
        assert current == baseline(f), 'Finish native removal before acceptance'
        items.save(out / 'acceptance.json', acceptance(f))
        print('Native decline, acceptance, mutual lists, removal, and public response fields verified.')
        return
    if args.action in ('cleanup', 'verify'):
        assert current == baseline(f), 'Complete native remove/cancel; fixture never deletes friend rows'
        if args.action == 'verify':
            assert (out / 'cleanup.json').exists()
        items.save(out / ('cleanup.json' if args.action == 'cleanup' else args.label+'-verified.json'),
                   dict(exact_original_accounts=True, exact_original_friend_rows=True, snapshots=current))
        print('Both original accounts and every original friend row match under locks.')
    else:
        target = out / (args.label+'-accounts.json')
        assert not target.exists(), 'Preserve previous record'
        items.save(target, current)
        items.save(out / (args.label+'-http.json'), native(f))
        items.save(out / (args.label+'-pair.json'), pair)
    if args.screens:
        for role, (_, avd) in peers.DEVICES.items():
            assert peers.adb(role, 'emu', 'avd', 'name').splitlines()[0].strip() == avd
            target = out / (args.label+'-'+role+'.png')
            assert not target.exists()
            target.write_bytes(peers.adb(role, 'exec-out', 'screencap', '-p', binary=True, timeout=30))
    print('Guard passed; raw evidence remains private.')


if __name__ == '__main__':
    main()

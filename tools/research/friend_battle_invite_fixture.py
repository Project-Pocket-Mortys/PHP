"""Guard native invitation send/decline/cancel; never synthesize invitation POSTs.

Only social setup/removal uses synthetic HTTP. Observe opens separate authenticated
replacement-server SSE connections; it is not a capture of the Android sockets.
Original saves are never restored or edited. Raw evidence stays in .research.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import re
import time
import urllib.request
import uuid

import friend_battle_probe as probe
import friend_lifecycle_fixture as friends
import battle_item_fixture as items
import probe_android_peers as peers

ROOT = probe.ROOT


def rows(players):
    ids = "','".join(players)
    return probe.sql("SELECT * FROM friend_battle_invites WHERE sender_id IN ('" + ids +
        "') OR recipient_id IN ('" + ids + "') ORDER BY invite_id")


def battle_events(players):
    ids = "','".join(players)
    return probe.sql("SELECT * FROM event_queue WHERE event_name IN ('battle:start','battle:turn-result',"
        "'battle:move-timer-started','battle-invite:accepted') AND (player_id IN ('" + ids +
        "') OR only_show_to_player_id IN ('" + ids + "')) ORDER BY id")


def store(f):
    probe.save(f['_manifest'], {k: v for k, v in f.items() if k != '_manifest'})


def native(f):
    lines = friends.log_lines()
    assert len(lines) >= f['log_floor'], 'Capture log truncated'
    all_rows = [json.loads(line) for line in lines[f['log_floor']:]]
    creates = [r for r in all_rows if r.get('path', '').rstrip('/') == '/session/battle-invite/create'
        and r.get('request', {}).get('opponent_player_id') == f['players'][1]]
    # Tests must finish before this exercise: reply logs redact the correlating
    # token, so retain serial native replies separately instead of guessing actor.
    replies = [r for r in all_rows if r.get('path', '').rstrip('/') in
        ('/session/battle-invite/response', '/session/battle-invite/revoke')]
    return dict(creates=creates, serial_replies=replies)


def check(f):
    current, pair = probe.check(f)
    assert battle_events(f['players']) == f['before_battle_events'], 'Battle events changed'
    initial = {r['invite_id']: r for r in f['before_invites']}
    invitations = rows(f['players'])
    assert [r for r in invitations if r['invite_id'] in initial] == f['before_invites'], 'Original invites changed'
    new = [r for r in invitations if r['invite_id'] not in initial]
    evidence = native(f)
    creates = {r['response']['battle_invite_id']: r for r in evidence['creates']
        if r['status'] == 200 and isinstance(r.get('response'), dict)}
    for row in new:
        assert row['sender_id'] == f['players'][0] and row['recipient_id'] == f['players'][1], 'Untracked actor pair'
        assert str(uuid.UUID(row['invite_id'])) == row['invite_id']
        assert row['invite_id'] in creates, 'New invitation lacks native create evidence'
        assert creates[row['invite_id']]['request']['battle_type'] == 'PvF'
        assert all(re.fullmatch('[0-9a-f]{64}', row[k]) for k in ('sender_token', 'recipient_token'))
        assert row['sender_token'] != row['recipient_token']
        assert row['state'] in ('PENDING', 'DECLINED', 'REVOKED', 'EXPIRED')
        previous = f.setdefault('tracked_invites', {}).get(row['invite_id'])
        if previous:
            for key in ('invite_id', 'sender_id', 'recipient_id', 'sender_token', 'recipient_token', 'created_at', 'expires_at'):
                assert row[key] == previous[key], 'Tracked invitation identity changed'
        f['tracked_invites'][row['invite_id']] = row
    return current, pair, invitations, evidence


def observe(f, out, label, duration):
    users = probe.accounts()
    assert [r['player_id'] for r in users] == f['players']
    def stream(role):
        session = users[role]['session_id']
        token = base64.urlsafe_b64encode(json.dumps({'session_id': session}).encode()).decode().rstrip('=')
        path = out / (label + '-' + ('primary' if role == 0 else 'peer') + '-observer.jsonl')
        assert not path.exists()
        started = time.monotonic()
        with path.open('x', encoding='utf-8') as file:
            with urllib.request.urlopen('http://127.0.0.1:8087/sse/?token=e30.' + token + '.test', timeout=duration + 5) as response:
                event = None
                while time.monotonic() - started < duration:
                    raw = response.readline()
                    if not raw:
                        break
                    line = raw.decode().strip()
                    if not line and time.monotonic() - started >= duration:
                        break
                    if line.startswith('event: '):
                        event = line[7:]
                    elif line.startswith('data: '):
                        payload = json.loads(line[6:])
                        if event == 'session:start':
                            file.write(json.dumps(dict(event=event, observed=True)) + '\n')
                            file.flush()
                            print(('primary' if role == 0 else 'peer') + ' observer ready', flush=True)
                        elif event.startswith('battle-invite:') or event == 'battle:start':
                            file.write(json.dumps(dict(event=event, payload=payload)) + '\n')
                            file.flush()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(stream, (0, 1)))
    print('Separate replacement-server SSE observer capture complete; not native socket capture.')


def acceptance(f, out):
    current, pair, invitations, evidence = check(f)
    assert len(f['tracked_invites']) == 2
    ordered = sorted(f['tracked_invites'].values(), key=lambda r: (r['created_at'], r['invite_id']))
    assert [r['state'] for r in ordered] == ['DECLINED', 'REVOKED']
    assert len(evidence['creates']) == 2 and all(r['status'] == 200 for r in evidence['creates'])
    replies = evidence['serial_replies']
    assert [(r['path'].rstrip('/').rsplit('/', 1)[-1], r['request'].get('accept')) for r in replies] == [('response', False), ('revoke', None)]
    assert all(r['status'] == 200 for r in replies)
    for label, row in zip(('decline', 'cancel'), ordered):
        captured = {}
        for role in ('primary', 'peer'):
            path = out / (label + '-' + role + '-observer.jsonl')
            captured[role] = [json.loads(line) for line in path.read_text().splitlines()]
            assert all(r['event'] not in ('battle:start', 'battle-invite:accepted') for r in captured[role])
        incoming = [r['payload'] for r in captured['peer'] if r['event'] == 'battle-invite:received' and r['payload']['battle_invite_id'] == row['invite_id']]
        assert len(incoming) == 1 and incoming[0]['token'] == row['recipient_token']
        assert incoming[0]['from_player']['player_id'] == f['players'][0]
        assert set(incoming[0]['from_player']) == {'player_id', 'username', 'player_avatar_id', 'level'}
        assert incoming[0]['battle_type'] == 'PvF' and incoming[0]['battle_invite_ttl'] > 0
        assert not any(r['event'] == 'battle-invite:received' for r in captured['primary'])
        for role, event in (('primary', 'battle-invite:declined'), ('peer', 'battle-invite:revoked')):
            assert any(r['event'] == event and r['payload'] == {'battle_invite_id': row['invite_id']} for r in captured[role])
        assert row['sender_token'] not in json.dumps(captured)
    return dict(native_create_decline_create_revoke=True, successful_native_requests=4,
        separate_private_sse_observers=True, no_accepted_or_start=True,
        exact_original_saves=True, battle_rows_unchanged=True)


def cleanup_invites(f):
    tracked = list(f['tracked_invites'].values())
    assert len(tracked) == 2 and all(r['state'] in ('DECLINED', 'REVOKED') for r in tracked)
    payload = base64.b64encode(json.dumps(dict(players=sorted(f['players']), expected=rows(f['players']),
        initial=f['before_invites'], tracked=tracked)).encode()).decode()
    # Exact full-row comparison under the same sorted user locks as writers.
    items.locked_php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; $x=json_decode(base64_decode('" + payload + "'),true);" + """
      $pdo->beginTransaction();
      try {
        foreach($x['players'] as $p) {
          $q=$pdo->prepare('SELECT player_id,state FROM users WHERE player_id=? FOR UPDATE'); $q->execute([$p]); $u=$q->fetchAll();
          if(count($u)!==1 || $u[0]['state']!=='WORLD') throw new RuntimeException('Require unique WORLD');
          $q=$pdo->prepare("SELECT battle_id FROM battles WHERE (player_id=? OR opponent_id=?) AND state='ACTIVE'"); $q->execute([$p,$p]);
          if($q->fetch()) throw new RuntimeException('Active battle');
        }
        $q=$pdo->prepare('SELECT * FROM friend_battle_invites WHERE sender_id IN (?,?) OR recipient_id IN (?,?) ORDER BY invite_id FOR UPDATE');
        $q->execute(array_merge($x['players'],$x['players'])); $rows=$q->fetchAll();
        if($rows!==$x['expected']) throw new RuntimeException('Invitation rows changed');
        foreach($x['tracked'] as $row) {
          if(!in_array($row,$rows,true) || !in_array($row['state'],['DECLINED','REVOKED'],true)) throw new RuntimeException('Untracked terminal');
          foreach($x['initial'] as $old) if($old['invite_id']===$row['invite_id']) throw new RuntimeException('Original invite');
          $q=$pdo->prepare('DELETE FROM friend_battle_invites WHERE invite_id=? AND sender_id=? AND recipient_id=? AND sender_token=? AND recipient_token=? AND state=?');
          $q->execute([$row['invite_id'],$row['sender_id'],$row['recipient_id'],$row['sender_token'],$row['recipient_token'],$row['state']]);
          if($q->rowCount()!==1) throw new RuntimeException('Delete mismatch');
        }
        $pdo->commit(); echo 'tracked terminal invitations removed';
      } catch(Throwable $e) {if($pdo->inTransaction()) $pdo->rollBack(); throw $e;}
    """)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'prepare', 'record', 'observe', 'acceptance', 'cleanup', 'verify'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--label', default='current')
    parser.add_argument('--duration', type=int, default=45)
    parser.add_argument('--screens', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    assert out.is_relative_to((ROOT / '.research').resolve())
    assert re.fullmatch('[A-Za-z0-9_-]+', args.label)
    assert 10 <= args.duration <= 60
    assert probe.capture.php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');") == 'db:http://localhost:8087'
    for role, (_, avd) in peers.DEVICES.items():
        assert peers.adb(role, 'emu', 'avd', 'name').splitlines()[0].strip() == avd
    manifest = out / 'fixture.json'
    if args.action in ('preflight', 'prepare'):
        assert not manifest.exists(), 'Use fresh output'
        users = probe.accounts()
        players = [r['player_id'] for r in users]
        before = friends.locked_snapshot(players)
        before_battles = probe.battle_rows(players)
        assert not friends.pair_rows(before['friend_rows'], players)
        assert not any(r['state'] == 'ACTIVE' for r in before_battles)
        before_invites = rows(players)
        assert not any(r['state'] == 'PENDING' for r in before_invites), 'Original pending invite; preserve and stop'
        assert all(before[p + ':user'][0]['shiny_potion_expires_at'] is None for p in players)
        if args.action == 'preflight':
            print('Both WORLD; original pair absent; no active battle or pending invitation; no mutations.')
            return
        out.mkdir(parents=True, exist_ok=True)
        f = dict(players=players, names=list(friends.NAMES), before=before, before_battles=before_battles,
            before_invites=before_invites, before_battle_events=battle_events(players), tracked_invites={}, created_pair_id=None,
            log_floor=len(friends.log_lines()), provenance='Synthetic friendship setup only; native Android invitation mutations')
        probe.save(manifest, f)
        f['_manifest'] = manifest
        probe.social(f, 'request', 0, 1)
        _, pair = probe.check(f)
        assert len(pair) == 1 and pair[0]['pending'] == 'true'
        f['created_pair_id'], f['created_pair'] = pair[0]['id'], pair[0]
        store(f)
        probe.social(f, 'response', 1, 0, approve=True)
        _, pair = probe.check(f)
        assert len(pair) == 1 and pair[0]['id'] == f['created_pair_id'] and pair[0]['pending'] == 'false'
        f['accepted_pair'] = pair[0]
        store(f)
        print('Initial invites and complete original saves retained; exact new friend pair accepted.')
        return
    f = json.loads(manifest.read_text())
    f['_manifest'] = manifest
    if args.action == 'verify':
        assert (out / 'cleanup.json').exists()
        current, pair = probe.check(f)
        assert not pair and current == friends.baseline(f) and rows(f['players']) == f['before_invites']
        assert battle_events(f['players']) == f['before_battle_events']
        items.save(out / (args.label + '-verified.json'), dict(exact_original_accounts_friends_battles_invites=True))
    else:
        current, pair, invitations, evidence = check(f)
        store(f)
        if args.action == 'observe':
            observe(f, out, args.label, args.duration)
            return
        if args.action == 'acceptance':
            items.save(out / 'acceptance.json', acceptance(f, out))
        elif args.action == 'cleanup':
            assert (out / 'acceptance.json').exists()
            if pair:
                assert pair == [f['accepted_pair']] and pair[0]['id'] == f['created_pair_id']
                probe.social(f, 'remove', 0, 1)
            current, pair = probe.check(f)
            assert not pair and current == friends.baseline(f)
            cleanup_invites(f)
            assert rows(f['players']) == f['before_invites']
            items.save(out / 'cleanup.json', dict(exact_original_accounts_friends_battles_invites=True))
        else:
            items.save(out / (args.label + '-record.json'), dict(accounts=current, pair=pair, invitations=invitations, native_http=evidence))
    if args.screens:
        for role in peers.DEVICES:
            path = out / (args.label + '-' + role + '.png')
            assert not path.exists()
            path.write_bytes(peers.adb(role, 'exec-out', 'screencap', '-p', binary=True, timeout=30))
    print('Complete original account, friend, both-column battle and invitation guards pass.')


if __name__ == '__main__':
    main()

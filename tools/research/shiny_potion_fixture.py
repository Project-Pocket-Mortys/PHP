"""Guarded temporary account potion stock; activation MUST use Android UI.

No API activation, clock changes, original Morty changes, or probability rules.
All raw evidence remains inside ignored .research. Run serially after tests.
"""
import argparse
import base64
import copy
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import uuid

import battle_item_fixture as items
import capture_battle_lifecycle as capture
import status_cure_fixture as guards

ROOT, sql = capture.ROOT, capture.sql
ITEM = 'ItemShinyPotion'
COLUMN = 'shiny_potion_expires_at'


def queries(player):
    return dict(guards.queries(player), potion=f"SELECT player_id,{COLUMN},world_id,streak,xp_lower,xp_upper,decks_owned,player_avatar_id,tags,donation_request FROM users WHERE player_id='{player}'")


def snapshots(players):
    return {p: {k: sql(q) for k, q in queries(p).items()} for p in players}


def event_rows(f):
    return sql(f"SELECT * FROM event_queue WHERE wild_morty_id='{f['wild']}' ORDER BY id")


def locked(expected, changes, spawn=None, event=None):
    payload = base64.b64encode(json.dumps(dict(accounts={p: dict(queries=queries(p), expected=s) for p, s in expected.items()}, changes=changes, spawn=spawn, event=event)).encode()).decode()
    items.locked_php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; $x=json_decode(base64_decode('" + payload + "'),true);" + """
    $pdo->beginTransaction();
    try {
      foreach($x['accounts'] as $p=>$account) {
        foreach($account['queries'] as $k=>$query) {
          if($pdo->query($query.' FOR UPDATE')->fetchAll()!==$account['expected'][$k]) throw new RuntimeException('Concurrent change: '.$k);
        }
        $q=$pdo->prepare("SELECT battle_id FROM battles WHERE player_id=? AND state='ACTIVE' FOR UPDATE");
        $q->execute([$p]); if($q->fetch()) throw new RuntimeException('Active battle');
      }
      if($x['event']) {
        $q=$pdo->prepare('SELECT * FROM event_queue WHERE wild_morty_id=? ORDER BY id FOR UPDATE');
        $q->execute([$x['event']['wild']]);
        if($q->fetchAll()!==$x['event']['expected']) throw new RuntimeException('Private event changed');
      }
      foreach($x['changes'] as $change) {
        $q=$pdo->prepare($change[0]); $q->execute($change[1]);
        if($q->rowCount()!==1) throw new RuntimeException('Expected precisely one changed row');
      }
      if($x['spawn']) {
        require_once '/var/www/html/lib/events.php';
        $s=$x['spawn'];
        $q=$pdo->prepare('SELECT id FROM event_queue WHERE wild_morty_id=? FOR UPDATE');
        $q->execute([$s['wild']]); if($q->fetch()) throw new RuntimeException('Synthetic identity collision');
        publish_event($pdo,$s['room'],'room:wild-morty-added',[
          'wild_morty_id'=>$s['wild'],'morty_id'=>'MortyDefault','placement'=>$s['position'],
          'state'=>'WORLD','division'=>1,'variant'=>'Normal','shiny_if_potion'=>true
        ]);
        $id=$pdo->lastInsertId();
        $q=$pdo->prepare('UPDATE event_queue SET only_show_to_player_id=? WHERE id=? AND wild_morty_id=?');
        $q->execute([$s['player'],$id,$s['wild']]);
        if($q->rowCount()!==1) throw new RuntimeException('Private publication guard failed');
      }
      $pdo->commit();
    } catch(Throwable $e) {if($pdo->inTransaction()) $pdo->rollBack(); throw $e;}
    """)


def log_lines():
    raw = subprocess.run(capture.http.COMPOSE + ['exec', '-T', 'web', 'cat', '/tmp/pocket-research-http.jsonl'], cwd=ROOT, capture_output=True, text=True, check=True, timeout=20).stdout
    return raw.splitlines()


def native(f):
    lines = log_lines()
    assert len(lines) >= f['log_floor'], 'Capture log truncated; preserve fixture'
    return [r for line in lines[f['log_floor']:] if (r := json.loads(line)).get('path', '').rstrip('/') in ('/session/use-shiny-potion', '/session/player-details', '/session/join-room')]


def metadata():
    from export_item_effects import load_text
    rows, mp = load_text('mpdata.assetbundle', 'ItemInfo')
    text, en = load_text('text.assetbundle', 'EN')
    assert mp['bundle_sha256'] == 'f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413'
    assert mp['asset_sha256'] == 'ab713ae7e06f8b492628d10b73580d4016756d57072d04b5be43f271e7305a39'
    assert en['bundle_sha256'] == 'bbe4b3036a907354dd7cad8122c0f557491e3259b6f4f349eda27caa913bc7a8'
    assert en['asset_sha256'] == '841eed65c78a058635eef4993f07b0a5592e8906f77c95027604cc3c57d4e1c4'
    row = next(r for r in rows if r['item_id'] == ITEM)
    assert row['use_account'] and row['use_world'] and not row['use_self'] and not row['use_battle']
    english = text['Item'][ITEM]
    assert english['description'] == 'Increases your chance to encounter Shiny Mortys for 2 hours.'
    return dict(sources=[mp, en], item=row, english=english)


def expected_used(f, prepared, rows):
    # The log is shared with UUID-only protocol fixtures. The native fixture
    # starts with precisely one potion, so only its exact zero-stock result is
    # eligible; the complete persisted account deadline is matched below.
    accepted = [r for r in rows if r['path'].rstrip('/') == '/session/use-shiny-potion' and r['status'] == 200 and r.get('response', {}).get('shiny_potion_active') is True and r['response'].get('quantity') == 0]
    assert len(accepted) == 1, 'Require precisely one captured native activation'
    request, response = accepted[0]['request'], accepted[0]['response']
    assert set(request) == {'session_id'}
    assert response['quantity'] == 0 and response['shiny_potion_item_id'] == ITEM
    deadline = datetime.fromisoformat(response['end_usage_time'].replace('Z', '+00:00'))
    assert deadline.utcoffset().total_seconds() == 0
    started = datetime.fromisoformat(accepted[0]['time_utc'].replace('Z', '+00:00'))
    assert 7190 <= (deadline - started).total_seconds() <= 7210, 'Two hour activation required'
    expected = copy.deepcopy(prepared)
    account = expected[f['player']]
    next(r for r in account['items'] if r['item_id'] == ITEM)['quantity'] = 0
    account['potion'][0][COLUMN] = deadline.astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S.%f')
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'finish-prepare', 'record', 'screen', 'cleanup', 'verify'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--label', default='current')
    parser.add_argument('--used', action='store_true')
    parser.add_argument('--appearance-position', help='Optional reviewed visible empty world tile, x,y; no battle')
    args = parser.parse_args()
    out = args.output.resolve()
    assert out.is_relative_to((ROOT / '.research').resolve())
    assert args.label.replace('-', '').replace('_', '').isalnum()
    assert capture.php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');") == 'db:http://localhost:8087'
    assert capture.adb('emu', 'avd', 'name').decode().splitlines()[0].strip() == 'PocketMortys_API30'
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / 'fixture.json'
    if args.action == 'prepare':
        assert not manifest.exists() and not (out / 'cleanup.json').exists()
        users = sql("SELECT username,player_id,state FROM users WHERE username IN ('PMResearch01','PMResearch02') ORDER BY username")
        assert [r['username'] for r in users] == ['PMResearch01', 'PMResearch02']
        assert all(r['state'] == 'WORLD' for r in users)
        players = [r['player_id'] for r in users]
        assert all(str(uuid.UUID(p)) == p for p in players)
        before = snapshots(players)
        player = players[0]
        assert all(s['potion'][0][COLUMN] is None for s in before.values()), 'Original accounts must be inactive'
        assert not [r for r in before[player]['items'] if r['item_id'] == ITEM], 'Do not replace original potion stock'
        f = dict(players=players, player=player, before=before, metadata=metadata(), log_floor=len(log_lines()), provenance='SYNTHETIC one temporary account item; native UI activation only')
        spawn = None
        if args.appearance_position:
            position = [int(v) for v in args.appearance_position.split(',')]
            assert len(position) == 2 and all(-1000 <= v <= 1000 for v in position)
            room = before[player]['user'][0]['room_id']
            assert room
            f.update(wild=str(uuid.uuid4()), room=room, position=position)
            spawn = dict(wild=f['wild'], room=room, player=player, position=position)
        items.save(manifest, f)
        locked(before, [('INSERT INTO owned_items (player_id,item_id,quantity) VALUES (?,?,1)', [player, ITEM])], spawn=spawn)
        # Recording after commit can be resumed using finish-prepare.
    else:
        f = json.loads(manifest.read_text())
    if args.action in ('prepare', 'finish-prepare'):
        assert not (out / 'prepared.json').exists()
        prepared = snapshots(f['players'])
        restored = copy.deepcopy(prepared)
        potion = [r for r in restored[f['player']]['items'] if r['item_id'] == ITEM]
        assert len(potion) == 1 and potion[0]['quantity'] == 1
        restored[f['player']]['items'].remove(potion[0])
        assert restored == f['before']
        if 'wild' in f:
            events = event_rows(f)
            assert len(events) == 1
            row = events[0]
            assert row['room_id'] == f['room'] and row['only_show_to_player_id'] == f['player']
            assert row['event_name'] == 'room:wild-morty-added' and row['morty_id'] == 'MortyDefault'
            assert row['variant'] == 'Normal' and row['shiny_if_potion'] in (1, '1')
            assert row['placement'] == ','.join(map(str, f['position']))
            items.save(out / 'prepared-event.json', events)
        items.save(out / 'prepared.json', prepared)
        print('One synthetic potion prepared; activate only through Android UI.')
        return
    current = snapshots(f['players'])
    if args.action == 'verify':
        assert (out / 'cleanup.json').exists() and current == f['before']
        assert 'wild' not in f or not event_rows(f)
        items.save(out / (args.label+'-verified.json'), dict(exact_original_accounts=True, snapshots=current))
        print('Both accounts, raw stock and explicit potion expiry match originals.')
        return
    if args.action == 'record':
        items.save(out / (args.label+'-accounts.json'), current)
        items.save(out / (args.label+'-http.json'), native(f))
        if 'wild' in f:
            expected_events = [] if (out / 'cleanup.json').exists() else json.loads((out / 'prepared-event.json').read_text())
            assert event_rows(f) == expected_events
            items.save(out / (args.label+'-event.json'), event_rows(f))
    if args.action == 'cleanup':
        assert not (out / 'cleanup.json').exists()
        prepared = json.loads((out / 'prepared.json').read_text())
        expected = expected_used(f, prepared, native(f)) if args.used else prepared
        assert current == expected, 'Unexplained mutation; preserve fixture'
        row = next(r for r in current[f['player']]['items'] if r['item_id'] == ITEM)
        changes = [('DELETE FROM owned_items WHERE id=? AND player_id=? AND item_id=? AND quantity=?', [row['id'], f['player'], ITEM, 0 if args.used else 1])]
        if args.used:
            changes.append((f'UPDATE users SET {COLUMN}=? WHERE player_id=? AND {COLUMN}=?', [f['before'][f['player']]['potion'][0][COLUMN], f['player'], current[f['player']]['potion'][0][COLUMN]]))
        event = None
        if 'wild' in f:
            events = json.loads((out / 'prepared-event.json').read_text())
            assert event_rows(f) == events
            changes.append(('DELETE FROM event_queue WHERE id=? AND wild_morty_id=? AND only_show_to_player_id=?', [events[0]['id'], f['wild'], f['player']]))
            event = dict(wild=f['wild'], expected=events)
        locked(current, changes, event=event)
        assert snapshots(f['players']) == f['before']
        items.save(out / 'cleanup.json', dict(exact_original_accounts=True, native_activations=int(args.used), restored_original_expiry=True))
        print('Original raw stock and expiry restored under exact two-account locks.')
        return
    if args.action in ('screen', 'record'):
        path = out / (args.label+'.png')
        assert not path.exists()
        path.write_bytes(capture.adb('exec-out', 'screencap', '-p'))
        pid = capture.adb('shell', 'pidof', 'com.turner.pocketmorties').decode().strip()
        assert pid.isdigit()
        (out / (args.label+'-logcat.txt')).write_bytes(capture.adb('logcat', '-d', '--pid='+pid))


if __name__ == '__main__':
    main()

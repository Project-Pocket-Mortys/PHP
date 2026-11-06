"""Manual Android lifecycle capture; synthetic private spawn, real UI moves.

Run prepare once, start RUN/WIN, inspect screenshots and tap the Android UI,
then record and cleanup. Never posts battle moves. Raw artifacts stay ignored.
"""
import argparse
import base64
import importlib.util
import json
from pathlib import Path
import subprocess
import uuid

ROOT = Path(__file__).resolve().parents[2]
ADB = ROOT / '.research/emulator/sdk/platform-tools/adb.exe'
spec = importlib.util.spec_from_file_location('battle_capture_http', ROOT / 'tests/protocol/test_http.py')
http = importlib.util.module_from_spec(spec)
spec.loader.exec_module(http)


def php(code):
    return subprocess.run(http.COMPOSE + ['exec', '-T', 'web', 'php', '-r', code],
                          cwd=ROOT, capture_output=True, text=True, check=True, timeout=20).stdout


http.php = php
sql = http.sql


def adb(*args):
    return subprocess.run([str(ADB), '-P', '5038', '-s', 'emulator-5556', *args],
                          capture_output=True, check=True, timeout=20).stdout


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n', encoding='utf-8')


def snapshot_queries(player):
    return {
        'user': f"SELECT player_id,room_id,state,active_deck_id,level,xp,coins,coupons,permits,wins,losses FROM users WHERE player_id='{player}'",
        'morties': f"SELECT * FROM owned_morties WHERE player_id='{player}' ORDER BY id",
        'attacks': f"SELECT a.* FROM owned_attacks a JOIN owned_morties m ON a.owned_morty_id=m.owned_morty_id WHERE m.player_id='{player}' ORDER BY a.id",
        'items': f"SELECT * FROM owned_items WHERE player_id='{player}' ORDER BY id",
    }


def snapshot(player):
    return {key: sql(query) for key, query in snapshot_queries(player).items()}


def execute(queries):
    data = base64.b64encode(json.dumps(queries).encode()).decode()
    php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; $pdo->beginTransaction(); foreach(json_decode(base64_decode('" + data + "'),true) as $q) $pdo->exec($q); $pdo->commit();")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'start', 'record', 'cleanup', 'screen'])
    parser.add_argument('--case', choices=['RUN', 'WIN'], default='RUN')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', default='screen')
    args = parser.parse_args()
    out = args.output.resolve()
    if not out.is_relative_to((ROOT / '.research').resolve()):
        parser.error('output must be inside .research')
    assert adb('emu', 'avd', 'name').decode().splitlines()[0].strip() == 'PocketMortys_API30'
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / 'fixture.json'
    if args.action == 'prepare':
        assert not manifest.exists(), 'preserve existing capture'
        users = sql("SELECT player_id,room_id,state FROM users WHERE username='PMResearch01'")
        assert len(users) == 1 and users[0]['state'] == 'WORLD'
        user = users[0]
        assert not sql(f"SELECT battle_id FROM battles WHERE player_id='{user['player_id']}' AND state='ACTIVE'")
        fixture = dict(user, cases={}, initiation='synthetic HTTP; battle moves must originate in Android UI')
        save(manifest, fixture)
        save(out / 'before.json', snapshot(user['player_id']))
    else:
        fixture = json.loads(manifest.read_text())
    player, room = fixture['player_id'], fixture['room_id']
    if args.action == 'start':
        assert args.case not in fixture['cases']
        current = sql(f"SELECT room_id,state,session_id FROM users WHERE player_id='{player}'")[0]
        assert current['room_id'] == room and current['state'] == 'WORLD'
        wild = str(uuid.uuid4())
        ceiling = sql('SELECT COALESCE(MAX(id),0) AS id FROM event_queue')[0]['id']
        case = {'wild': wild, 'event_floor': ceiling, 'initiation': 'synthetic HTTP'}
        fixture['cases'][args.case] = case
        save(manifest, fixture)
        sql(f"INSERT INTO event_queue (room_id,event_name,wild_morty_id,morty_id,state,placement,variant,only_show_to_player_id) VALUES ('{room}','room:wild-morty-added','{wild}','MortyDefault','WORLD','0,0','Normal','{player}')")
        status, body = http.post('/session/battle-wild-morty', {'session_id': current['session_id'], 'wild_morty_id': wild})
        save(out / (args.case + '-start-response.json'), {'status': status, 'body': body})
        assert status == 200 and body == {'success': True}
        battles = sql(f"SELECT * FROM battles WHERE player_id='{player}' AND opponent_active_morty='{wild}'")
        assert len(battles) == 1
        case['battle_id'] = battles[0]['battle_id']
        case['source_event_ids'] = [e['id'] for e in sql(f"SELECT id FROM event_queue WHERE id>{int(ceiling)} AND room_id='{room}' AND (wild_morty_id='{wild}' OR (player_id='{player}' AND event_name IN ('battle:start','room:user-state-changed')))")]
        save(manifest, fixture)
    if args.action == 'record':
        case = fixture['cases'][args.case]
        battle = case['battle_id']
        rows = sql(f"SELECT * FROM battles WHERE battle_id='{battle}' AND player_id='{player}'")
        events = sql(f"SELECT * FROM event_queue WHERE id>{int(case['event_floor'])} AND room_id='{room}' AND (wild_morty_id='{case['wild']}' OR (player_id='{player}' AND event_name IN ('battle:start','battle:turn-result','battle:move-timer-started','room:user-state-changed')))")
        case['source_event_ids'] = sorted(set(case.get('source_event_ids', [])) | {e['id'] for e in events})
        save(manifest, fixture)
        save(out / (args.case + '-result.json'), {'battles': rows, 'events': events, 'snapshot': snapshot(player)})
        captured = subprocess.run(http.COMPOSE + ['exec', '-T', 'web', 'cat', '/tmp/pocket-research-http.jsonl'], cwd=ROOT, capture_output=True, text=True, check=True, timeout=20).stdout
        native = []
        for line in captured.splitlines():
            entry = json.loads(line)
            request = entry.get('request')
            if isinstance(request, dict) and request.get('battle_id') == battle:
                request.pop('session_id', None)
                native.append(entry)
        save(out / (args.case + '-http.json'), native)
        print(json.dumps({'case': args.case, 'battle_states': [r['state'] for r in rows], 'outcomes': [json.loads(e['battle_turn_result'])['outcome'] for e in events if e['event_name'] == 'battle:turn-result']}))
    if args.action == 'cleanup':
        before = json.loads((out / 'before.json').read_text())
        now = snapshot(player)
        assert now['morties'] == before['morties'] and now['items'] == before['items'], 'unexpected HP/stats/items changes; do not overwrite'
        assert now['user'] == before['user'], 'unexpected player change; do not overwrite'
        old_attacks = {a['id']: a for a in before['attacks']}
        assert {a['id'] for a in now['attacks']} == set(old_attacks), 'attack ID set changed'
        queries = []
        changed_attacks = []
        for attack in now['attacks']:
            old = old_attacks[attack['id']]
            expected = dict(old, pp=old['pp'] - (1 if args.case == 'WIN' else 0))
            # Only one real attack may have spent PP; zero-spend attacks are unchanged.
            assert attack == old or attack == expected, 'unexpected attack changes'
            if attack != old:
                changed_attacks.append(attack['id'])
                queries.append(f"UPDATE owned_attacks SET pp={int(old['pp'])} WHERE id={int(old['id'])} AND pp={int(attack['pp'])}")
        wins = []
        for case_name in fixture['cases']:
            result_path = out / (case_name + '-result.json')
            if result_path.exists():
                result = json.loads(result_path.read_text())
                wins.extend(e for e in result['events'] if e['event_name'] == 'battle:turn-result' and json.loads(e['battle_turn_result'])['outcome'] == 'WIN')
        assert len(wins) <= 1 and len(changed_attacks) == len(wins), 'PP decrement count must match recorded WIN'
        for case in fixture['cases'].values():
            wild, battle = case['wild'], case.get('battle_id')
            if battle:
                rows = sql(f"SELECT state FROM battles WHERE battle_id='{battle}' AND player_id='{player}'")
                assert len(rows) == 1 and rows[0]['state'] in ('CANCELLED', 'COMPLETED'), 'battle still active; no forced cleanup'
                queries.append(f"DELETE FROM battles WHERE battle_id='{battle}' AND player_id='{player}' AND state IN ('CANCELLED','COMPLETED')")
            for event_id in case.get('source_event_ids', []):
                queries.append(f"DELETE FROM event_queue WHERE id={int(event_id)} AND room_id='{room}' AND (player_id='{player}' OR wild_morty_id='{wild}')")
        # Repeat every preservation guard under row locks, then restore/delete in
        # that same transaction. PP updates additionally require one affected row.
        payload = base64.b64encode(json.dumps({'snapshot': now, 'queries': snapshot_queries(player), 'changes': queries}).encode()).decode()
        php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; $x=json_decode(base64_decode('" + payload + "'),true); $pdo->beginTransaction(); foreach($x['queries'] as $k=>$q) { $rows=$pdo->query($q.' FOR UPDATE')->fetchAll(); if($rows!==$x['snapshot'][$k]) throw new RuntimeException('Concurrent change; abort cleanup'); } foreach($x['changes'] as $q) { $n=$pdo->exec($q); if(str_starts_with($q,'UPDATE owned_attacks') && $n!==1) throw new RuntimeException('PP guard failed'); } $pdo->commit();")
        assert snapshot(player) == before
        save(out / 'cleanup.json', {'restored': True, 'guard': 'exact original HP/items/player stats; PP limited to one decrement'})
        print('Fixture cleanup complete; original player, HP, PP, items and stats verified.')
    if args.action in ('screen', 'start', 'record'):
        label = args.label if args.action == 'screen' else args.case + '-' + args.action
        assert label.replace('-', '').replace('_', '').isalnum()
        (out / (label + '.png')).write_bytes(adb('exec-out', 'screencap', '-p'))
        pid = adb('shell', 'pidof', 'com.turner.pocketmorties').decode().strip()
        assert pid.isdigit()
        (out / (label + '-logcat.txt')).write_bytes(adb('logcat', '-d', '--pid=' + pid))


if __name__ == '__main__':
    main()

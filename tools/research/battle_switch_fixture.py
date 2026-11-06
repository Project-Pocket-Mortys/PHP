"""Guarded synthetic bench/spawn; SWITCH and RUN acceptance uses Android taps."""
import argparse
import base64
import json
from pathlib import Path
import subprocess
import uuid

import capture_battle_lifecycle as capture
import status_cure_fixture as guards

ROOT = capture.ROOT
sql, php = capture.sql, capture.php
# Use the bounded Compose wrapper for every guard query too.
guards.php = php
guards.sql = sql


def save(path, value):
    with path.open('x', encoding='utf-8') as file:
        json.dump(value, file, indent=2)
        file.write('\n')


def locked(fixture, expected, changes, terminal=None, events=None):
    data = dict(queries=guards.queries(fixture['player']), expected=expected,
                changes=changes, player=fixture['player'], terminal=terminal, events=events or [])
    payload = base64.b64encode(json.dumps(data).encode()).decode()
    php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; $x=json_decode(base64_decode('" + payload + "'),true);" + """
    $pdo->beginTransaction();
    try {
      foreach($x['queries'] as $k=>$query) {
        if($pdo->query($query.' FOR UPDATE')->fetchAll()!==$x['expected'][$k]) throw new RuntimeException('Concurrent change: '.$k);
      }
      $q=$pdo->prepare("SELECT * FROM battles WHERE player_id=? AND state='ACTIVE' FOR UPDATE");
      $q->execute([$x['player']]); if($q->fetch()) throw new RuntimeException('Active battle; abort');
      if($x['terminal']) {
        $q=$pdo->prepare('SELECT * FROM battles WHERE battle_id=? AND player_id=? FOR UPDATE');
        $q->execute([$x['terminal']['battle_id'],$x['player']]);
        if($q->fetchAll()!==[$x['terminal']]) throw new RuntimeException('Battle changed');
      }
      foreach($x['events'] as $event) {
        $q=$pdo->prepare('SELECT * FROM event_queue WHERE id=? FOR UPDATE');
        $q->execute([$event['id']]);
        if($q->fetchAll()!==[$event]) throw new RuntimeException('Fixture event changed');
      }
      foreach($x['changes'] as $change) { $q=$pdo->prepare($change[0]); $q->execute($change[1]); }
      $pdo->commit();
    } catch(Throwable $e) { if($pdo->inTransaction()) $pdo->rollBack(); throw $e; }
    """)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['prepare', 'start', 'record', 'screen', 'cleanup', 'recover-run'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', default='current')
    args = parser.parse_args()
    if not args.label.replace('-', '').replace('_', '').isalnum():
        parser.error('--label must contain only letters, digits, hyphens or underscores')
    out = args.output.resolve()
    assert out.is_relative_to((ROOT / '.research').resolve())
    assert php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');") == 'db:http://localhost:8087'
    assert capture.adb('emu', 'avd', 'name').decode().splitlines()[0].strip() == 'PocketMortys_API30'
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / 'fixture.json'
    if args.action == 'prepare':
        assert not manifest.exists() and not (out / 'cleanup.json').exists()
        users = sql("SELECT player_id,room_id,state,active_deck_id FROM users WHERE username='PMResearch01'")
        assert len(users) == 1 and users[0]['state'] == 'WORLD'
        user = users[0]
        assert str(uuid.UUID(user['player_id'])) == user['player_id']
        before = guards.snapshot(user['player_id'])
        decks = [d for d in before['decks'] if d['deck_id'] == user['active_deck_id']]
        assert len(decks) == 1
        deck = decks[0]
        party = json.loads(deck['owned_morty_ids'])
        assert isinstance(party, list) and 0 < len(party) < 5 and len(set(party)) == len(party)
        for member in party:
            assert str(uuid.UUID(member)) == member
            assert len([m for m in before['morties'] if m['owned_morty_id'] == member]) == 1
            assert len(sql(f"SELECT id FROM owned_morties WHERE owned_morty_id='{member}'")) == 1
        primary = next(m for member in party for m in before['morties'] if m['owned_morty_id'] == member and m['hp'] > 0)
        assert primary['hp'] == primary['hp_stat'] and not primary['is_poisoned'] and not primary['is_paralysed']
        bench = str(uuid.uuid4())
        fixture = dict(player=user['player_id'], room=user['room_id'], primary=primary['owned_morty_id'], bench=bench,
                       before=before, deck_id=deck['id'], appended=json.dumps(party + [bench], separators=(',', ':')),
                       provenance='Synthetic clone at HP1 and private spawn; moves must originate in Android')
        save(manifest, fixture)
        # Explicit column lists preserve every stored source value, including bigints.
        morty_columns = ['player_id', 'owned_morty_id', 'morty_id', 'level', 'xp', 'hp', 'hp_stat',
                         'attack_stat', 'defence_stat', 'variant', 'speed_stat', 'is_locked',
                         'is_trading_locked', 'fight_pit_id', 'evolution_points', 'xp_lower',
                         'xp_upper', 'is_poisoned', 'is_paralysed']
        attack_columns = ['owned_morty_id', 'attack_id', 'position', 'amount', 'pp', 'pp_stat',
                          'stat', 'type', 'to_self', 'is_accurate', 'accuracy', 'power']
        assert {c['Field'] for c in sql('SHOW COLUMNS FROM owned_attacks')} == set(attack_columns) | {'id'}
        assert set(morty_columns) == set(primary) - {'id', 'created_at'}
        expressions = ['?' if c == 'owned_morty_id' else '1' if c == 'hp' else '`'+c+'`' for c in morty_columns]
        attack_expressions = ['?' if c == 'owned_morty_id' else '`'+c+'`' for c in attack_columns]
        changes = [
            ('INSERT INTO owned_morties ('+','.join('`'+c+'`' for c in morty_columns)+') SELECT '+','.join(expressions)+' FROM owned_morties WHERE id=? AND player_id=?', [bench, primary['id'], fixture['player']]),
            ('INSERT INTO owned_attacks ('+','.join('`'+c+'`' for c in attack_columns)+') SELECT '+','.join(attack_expressions)+' FROM owned_attacks WHERE owned_morty_id=?', [bench, fixture['primary']]),
            ('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=?', [fixture['appended'], deck['id'], fixture['player']])]
        locked(fixture, before, changes)
        save(out / 'prepared.json', guards.snapshot(fixture['player']))
        print('Prepared bench; restart app for fresh player details before start.')
        return
    fixture = json.loads(manifest.read_text())
    player = fixture['player']
    case_path = out / 'case.json'
    if args.action == 'start':
        assert not case_path.exists()
        user = sql(f"SELECT room_id,state,session_id FROM users WHERE player_id='{player}'")[0]
        assert user['state'] == 'WORLD' and user['room_id'] == fixture['room']
        assert not sql(f"SELECT battle_id FROM battles WHERE player_id='{player}' AND state='ACTIVE'")
        wild = str(uuid.uuid4())
        case = dict(wild=wild, floor=sql('SELECT COALESCE(MAX(id),0) AS id FROM event_queue')[0]['id'])
        save(out / 'start-intent.json', case)
        sql(f"INSERT INTO event_queue (room_id,event_name,wild_morty_id,morty_id,state,placement,variant,only_show_to_player_id) VALUES ('{fixture['room']}','room:wild-morty-added','{wild}','MortyDefault','WORLD','0,0','Normal','{player}')")
        status, body = capture.http.post('/session/battle-wild-morty', dict(session_id=user['session_id'], wild_morty_id=wild))
        save(out / 'start-response.json', dict(status=status, body=body))
        assert status == 200 and body == {'success': True}
        battle = sql(f"SELECT * FROM battles WHERE player_id='{player}' AND opponent_active_morty='{wild}'")
        assert len(battle) == 1
        case['battle_id'] = battle[0]['battle_id']
        save(case_path, case)
    if args.action in ('record', 'cleanup', 'recover-run'):
        case = json.loads(case_path.read_text())
        battle = sql(f"SELECT * FROM battles WHERE battle_id='{case['battle_id']}' AND player_id='{player}'")
        assert len(battle) == 1
        events = sql(f"SELECT * FROM event_queue WHERE id>{int(case['floor'])} AND room_id='{fixture['room']}' AND (wild_morty_id='{case['wild']}' OR (player_id='{player}' AND event_name IN ('battle:start','battle:turn-result','battle:move-timer-started','room:user-state-changed')))")
        current = guards.snapshot(player)
        if args.action == 'recover-run':
            assert battle[0]['state'] == 'ACTIVE'
            session = sql(f"SELECT session_id FROM users WHERE player_id='{player}'")[0]['session_id']
            status, body = capture.http.post('/session/battle/move', dict(session_id=session, battle_id=case['battle_id'], type='RUN', owned_morty_id=battle[0]['player_active_morty'], move_id=None))
            save(out / 'NONNATIVE-recovery-run.json', dict(status=status, body=body))
            return
        if args.action == 'record':
            save(out / (args.label+'-result.json'), dict(battle=battle, events=events, snapshot=current))
            raw = subprocess.run(capture.http.COMPOSE+['exec','-T','web','cat','/tmp/pocket-research-http.jsonl'], cwd=ROOT,capture_output=True,text=True,check=True,timeout=20).stdout
            native = []
            for line in raw.splitlines():
                entry = json.loads(line)
                request = entry.get('request')
                if isinstance(request,dict) and request.get('battle_id') == case['battle_id']:
                    request.pop('session_id',None)
                    native.append(entry)
            save(out / (args.label+'-http.json'), native)
            print(json.dumps(battle))
        else:
            before = fixture['before']
            assert battle[0]['state'] in ('CANCELLED','COMPLETED')
            assert current['user'] == before['user'] and current['items'] == before['items']
            assert [m for m in current['morties'] if m['owned_morty_id'] != fixture['bench']] == before['morties']
            assert [a for a in current['attacks'] if a['owned_morty_id'] != fixture['bench']] == before['attacks']
            prepared = json.loads((out / 'prepared.json').read_text())
            assert current['decks'] == prepared['decks']
            temp = [m for m in current['morties'] if m['owned_morty_id'] == fixture['bench']]
            initial = [m for m in prepared['morties'] if m['owned_morty_id'] == fixture['bench']]
            assert temp == [dict(initial[0], hp=0)] or ((out / 'NONNATIVE-recovery-run.json').exists() and temp == initial)
            assert [a for a in current['attacks'] if a['owned_morty_id'] == fixture['bench']] == [a for a in prepared['attacks'] if a['owned_morty_id'] == fixture['bench']]
            old_deck = next(d for d in before['decks'] if d['id'] == fixture['deck_id'])
            changes = [('DELETE FROM owned_attacks WHERE owned_morty_id=?',[fixture['bench']]),('DELETE FROM owned_morties WHERE player_id=? AND owned_morty_id=?',[player,fixture['bench']]),('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=?',[old_deck['owned_morty_ids'],fixture['deck_id'],player])]
            for event in events:
                changes.append(('DELETE FROM event_queue WHERE id=? AND room_id=? AND (player_id=? OR wild_morty_id=?)',[event['id'],fixture['room'],player,case['wild']]))
            changes.append(('DELETE FROM battles WHERE battle_id=? AND player_id=? AND state IN (\'CANCELLED\',\'COMPLETED\')',[case['battle_id'],player]))
            locked(fixture,current,changes,battle[0],events)
            assert guards.snapshot(player) == before
            save(out / 'cleanup.json',dict(restored=True, original_rows_exact=True, original_deck_raw_restored=True))
            print('Cleanup verified exact original account rows.')
            return
    if args.action in ('screen','start','record'):
        assert args.label.replace('-','').replace('_','').isalnum()
        path = out / (args.label+'.png')
        assert not path.exists()
        path.write_bytes(capture.adb('exec-out','screencap','-p'))


if __name__ == '__main__':
    main()

"""Guarded no-move Android timeout fixture; never posts ready or battle moves.

Synthetic private spawn/start only. Each case gets a fresh full-stat clone.
Raw artifacts must remain inside ignored .research; cleanup refuses active battles.
"""
import argparse
import json
import uuid
from pathlib import Path

import battle_item_fixture as items
import battle_switch_fixture as switch
import capture_battle_lifecycle as capture
import status_cure_fixture as guards

ROOT, sql = capture.ROOT, capture.sql


def state(f, case):
    battle = sql(f"SELECT * FROM battles WHERE battle_id='{case['battle_id']}' AND player_id='{f['player']}'")
    assert len(battle) == 1
    events = sql(f"SELECT * FROM event_queue WHERE id>{int(case['floor'])} AND room_id='{f['room']}' AND (wild_morty_id='{case['wild']}' OR (player_id='{f['player']}' AND event_name IN ('battle:start','battle:turn-result','battle:move-timer-started','room:user-state-changed'))) ORDER BY id")
    return battle[0], events, guards.snapshot(f['player'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'start', 'screen', 'record', 'cleanup', 'discard-unstarted'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', default='current')
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
        users = sql("SELECT player_id,room_id,state,active_deck_id FROM users WHERE username='PMResearch01'")
        assert len(users) == 1 and users[0]['state'] == 'WORLD'
        user = users[0]
        assert str(uuid.UUID(user['player_id'])) == user['player_id']
        before = guards.snapshot(user['player_id'])
        deck = next(d for d in before['decks'] if d['deck_id'] == user['active_deck_id'])
        party = json.loads(deck['owned_morty_ids'])
        assert 0 < len(party) < 5 and len(set(party)) == len(party)
        primary = next(m for m in before['morties'] if m['owned_morty_id'] == party[0])
        assert primary['hp'] > 0 and primary['hp'] == primary['hp_stat']
        assert not primary['is_poisoned'] and not primary['is_paralysed']
        assert set(items.MC) == set(primary) - {'id', 'created_at'}
        assert {c['Field'] for c in sql('SHOW COLUMNS FROM owned_attacks')} == set(items.AC) | {'id'}
        f = dict(player=user['player_id'], room=user['room_id'], active=str(uuid.uuid4()), before=before,
                 deck_id=deck['id'], provenance='SYNTHETIC full-stat/attack clone and private spawn/start; native ready and timer only; no moves')
        items.save(manifest, f)
        mc, ac = items.MC, items.AC
        me = ['?' if c == 'owned_morty_id' else '`'+c+'`' for c in mc]
        ae = ['?' if c == 'owned_morty_id' else '`'+c+'`' for c in ac]
        changes = [
            ('INSERT INTO owned_morties ('+','.join('`'+c+'`' for c in mc)+') SELECT '+','.join(me)+' FROM owned_morties WHERE id=? AND player_id=?', [f['active'], primary['id'], f['player']]),
            ('INSERT INTO owned_attacks ('+','.join('`'+c+'`' for c in ac)+') SELECT '+','.join(ae)+' FROM owned_attacks WHERE owned_morty_id=?', [f['active'], primary['owned_morty_id']]),
            ('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=?', [json.dumps([f['active']] + party, separators=(',', ':')), deck['id'], f['player']]),
        ]
        switch.locked(f, before, changes)
        items.save(out / 'prepared.json', guards.snapshot(f['player']))
        print('Fresh complete clone prepared; restart app for player details. No stock changes.')
        return
    f = json.loads(manifest.read_text())
    prepared = json.loads((out / 'prepared.json').read_text())
    case_path = out / 'case.json'
    if args.action == 'discard-unstarted':
        assert not case_path.exists() and not (out / 'start-intent.json').exists()
        current = guards.snapshot(f['player'])
        assert current == prepared, 'Unstarted fixture changed; preserve for investigation'
        olddeck = next(d for d in f['before']['decks'] if d['id'] == f['deck_id'])
        switch.locked(f, current, [
            ('DELETE FROM owned_attacks WHERE owned_morty_id=?', [f['active']]),
            ('DELETE FROM owned_morties WHERE player_id=? AND owned_morty_id=?', [f['player'], f['active']]),
            ('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=?', [olddeck['owned_morty_ids'], f['deck_id'], f['player']]),
        ])
        assert guards.snapshot(f['player']) == f['before']
        items.save(out / 'cleanup.json', dict(restored=True, exact_original_rows=True, acceptance=False, unstarted=True))
        print('Unstarted fixture discarded under locks; exact account restored. No acceptance claim.')
        return
    if args.action == 'start':
        assert not case_path.exists()
        user = sql(f"SELECT room_id,state,session_id FROM users WHERE player_id='{f['player']}'")[0]
        assert user['state'] == 'WORLD' and user['room_id'] == f['room']
        assert guards.snapshot(f['player']) == prepared
        assert not sql(f"SELECT battle_id FROM battles WHERE player_id='{f['player']}' AND state='ACTIVE'")
        case = dict(wild=str(uuid.uuid4()), floor=sql('SELECT COALESCE(MAX(id),0) AS id FROM event_queue')[0]['id'])
        items.save(out / 'start-intent.json', case)
        sql(f"INSERT INTO event_queue (room_id,event_name,wild_morty_id,morty_id,state,placement,variant,only_show_to_player_id) VALUES ('{f['room']}','room:wild-morty-added','{case['wild']}','MortyDefault','WORLD','0,0','Normal','{f['player']}')")
        status, body = capture.http.post('/session/battle-wild-morty', dict(session_id=user['session_id'], wild_morty_id=case['wild']))
        items.save(out / 'start-response.json', dict(status=status, body=body))
        assert status == 200 and body == {'success': True}
        rows = sql(f"SELECT * FROM battles WHERE player_id='{f['player']}' AND opponent_active_morty='{case['wild']}'")
        assert len(rows) == 1 and rows[0]['player_active_morty'] == f['active']
        case['battle_id'] = rows[0]['battle_id']
        items.save(case_path, case)
    if args.action in ('record', 'cleanup'):
        case = json.loads(case_path.read_text())
        battle, events, current = state(f, case)
        native = items.native(case)
        if args.action == 'record':
            items.save(out / (args.label+'-result.json'), dict(battle=battle, events=events, snapshot=current))
            items.save(out / (args.label+'-http.json'), native)
            print(json.dumps(dict(state=battle['state'], turn_events=len([e for e in events if e['event_name']=='battle:turn-result']))))
        else:
            assert battle['state'] == 'CANCELLED' and battle['winner'] is None and battle['move_deadline'] is None
            assert current == prepared, 'Any account, clone, AP, stock or deck mutation prevents cleanup'
            assert battle['player_active_morty'] == f['active']
            assert battle['player_hp'] == next(m['hp'] for m in prepared['morties'] if m['owned_morty_id'] == f['active'])
            assert battle['opponent_hp'] == 1 and battle['player_streak'] == battle['opponent_streak'] == 0 and battle['move_log'] is None
            assert not [r for r in native if r['path'].rstrip('/') == '/session/battle/move'], 'A move prevents timeout-only acceptance'
            assert [r for r in native if r['path'].rstrip('/') == '/session/battle/ready' and r['status'] == 200]
            results = [json.loads(e['battle_turn_result']) for e in events if e['event_name'] == 'battle:turn-result']
            assert results == [dict(battle_id=battle['battle_id'], outcome='ABANDONED', battle_abandoned=False, turn_datas=[], player_datas=dict(player={}, opponent={}))]
            timers = [json.loads(e['battle_move_timer_started']) for e in events if e['event_name'] == 'battle:move-timer-started']
            assert timers == [dict(battle_id=battle['battle_id'], timeout=30)]
            before = f['before']
            olddeck = next(d for d in before['decks'] if d['id'] == f['deck_id'])
            changes = [
                ('DELETE FROM owned_attacks WHERE owned_morty_id=?', [f['active']]),
                ('DELETE FROM owned_morties WHERE player_id=? AND owned_morty_id=?', [f['player'], f['active']]),
                ('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=?', [olddeck['owned_morty_ids'], f['deck_id'], f['player']]),
            ]
            for event in events:
                changes.append(('DELETE FROM event_queue WHERE id=? AND room_id=? AND (player_id=? OR wild_morty_id=?)', [event['id'], f['room'], f['player'], case['wild']]))
            changes.append(("DELETE FROM battles WHERE battle_id=? AND player_id=? AND state='CANCELLED'", [case['battle_id'], f['player']]))
            switch.locked(f, current, changes, battle, events)
            assert guards.snapshot(f['player']) == before
            items.save(out / 'cleanup.json', dict(restored=True, exact_original_rows=True, clone_and_stock_unchanged=True, outcome='ABANDONED', native_moves=0))
            print('Exact original account rows and raw deck restored; clone/stock unchanged; no moves.')
            return
    if args.action in ('screen', 'start', 'record'):
        path = out / (args.label+'.png')
        assert not path.exists()
        path.write_bytes(capture.adb('exec-out', 'screencap', '-p'))
        pid = capture.adb('shell', 'pidof', 'com.turner.pocketmorties').decode().strip()
        assert pid.isdigit()
        (out / (args.label+'-logcat.txt')).write_bytes(capture.adb('logcat', '-d', '--pid='+pid))


if __name__ == '__main__':
    main()

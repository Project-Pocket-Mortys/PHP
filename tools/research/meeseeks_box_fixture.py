"""Additive PMStartup01 Meeseeks fixture; only Android may submit battle moves.

All output is immutable inside a fresh ignored .research directory. Synthetic
clone/stock/private spawn/start are setup, never native acceptance evidence.
Cleanup accepts one Meeseeks WIN, an untouched timeout, or an unstarted fixture.
It never restores a general save, resets an account, or sends a battle move.
"""
import argparse
import copy
import hashlib
import json
import subprocess
import uuid
from pathlib import Path

import battle_item_fixture as items
import battle_switch_fixture as switch
import battle_timeout_fixture as timeout
import capture_battle_lifecycle as capture
import status_cure_fixture as guards

ROOT, sql = capture.ROOT, capture.sql
ITEM = 'ItemMrMeeseek'
IDENTITY = ROOT / '.research/emulator/paired-selection-complete-20261106/fixture/startup-fixture.json'
DEVICE = dict(serial='emulator-5560', port=5038, avd='PocketMortys_API30_Startup')
BASE_QUERIES = guards.queries
EXCLUDE_BATTLE = None
LOCK_EVENT_QUERY = None


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def adb(*args):
    return subprocess.run([str(capture.ADB), '-P', str(DEVICE['port']), '-s', DEVICE['serial'], *args],
                          check=True, capture_output=True, timeout=20).stdout


def queries(player):
    """Keep complete gameplay and prior startup history under the same locks."""
    q = BASE_QUERIES(player)
    # Operational session/stream counters change during normal native reconnects.
    cols = [r['Field'] for r in sql('SHOW COLUMNS FROM users') if r['Field'] not in
            {'session_id', 'last_event_id', 'last_seen', 'room_membership_generation'}]
    q['user'] = 'SELECT '+','.join('`'+c+'`' for c in cols)+f" FROM users WHERE player_id='{player}'"
    q['memberships'] = f"SELECT * FROM friend_battle_memberships WHERE player_id='{player}' ORDER BY player_id"
    q['avatars'] = f"SELECT * FROM owned_avatars WHERE player_id='{player}' ORDER BY id"
    q['mortydex'] = f"SELECT * FROM mortydex WHERE player_id='{player}' ORDER BY id"
    q['friends'] = f"SELECT * FROM friend_list WHERE player_id_a='{player}' OR player_id_b='{player}' ORDER BY id"
    session_scope = f"sender_id='{player}' OR recipient_id='{player}'"
    q['invites'] = f'SELECT * FROM friend_battle_invites WHERE {session_scope} ORDER BY invite_id'
    q['sessions'] = f'SELECT * FROM friend_battle_sessions WHERE {session_scope} ORDER BY battle_id'
    scope = f"battle_id IN (SELECT battle_id FROM friend_battle_sessions WHERE {session_scope})"
    for table in ('party_snapshots', 'start_views', 'startups', 'start_intents', 'selections', 'selection_pairs'):
        q['history_'+table] = f'SELECT * FROM friend_battle_{table} WHERE {scope} ORDER BY battle_id' + (',player_id' if table in ('party_snapshots', 'start_views', 'start_intents', 'selections') else '')
    exclusion = f" AND battle_id<>'{EXCLUDE_BATTLE}'" if EXCLUDE_BATTLE else ''
    q['battle_history'] = f"SELECT * FROM battles WHERE (player_id='{player}' OR opponent_id='{player}')"+exclusion+' ORDER BY battle_id'
    if LOCK_EVENT_QUERY:
        q['fixture_events'] = LOCK_EVENT_QUERY
    return q


guards.queries = queries


def identity():
    receipt = json.loads(IDENTITY.read_text(encoding='utf-8'))
    rows = [u for u in receipt['before']['accounts'] if u['username'] == 'PMStartup01']
    assert len(rows) == 1
    player = rows[0]['player_id']
    assert str(uuid.UUID(player)) == player
    return player


def preflight():
    assert capture.php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');") == 'db:http://localhost:8087'
    assert adb('emu', 'avd', 'name').decode().splitlines()[0].strip() == DEVICE['avd']
    player = identity()
    rows = sql("SELECT player_id,room_id,state,active_deck_id FROM users WHERE username='PMStartup01'")
    assert len(rows) == 1 and rows[0]['player_id'] == player
    return rows[0]


def native(case):
    """Read native sidecar traffic separately from synthetic web:8087 setup."""
    raw = subprocess.run(capture.http.COMPOSE + ['exec', '-T', 'offline-sdk-web', 'cat',
                         '/tmp/pocket-research-http.jsonl'], cwd=ROOT, capture_output=True,
                         text=True, check=True, timeout=20).stdout
    rows = []
    for line in raw.splitlines():
        row = json.loads(line)
        request = row.get('request')
        if isinstance(request, dict) and request.get('battle_id') == case['battle_id']:
            request.pop('session_id', None)
            row['capture_service'] = 'offline-sdk-web'
            rows.append(row)
    return rows


def validate(f, prepared, current, battle, events, native):
    """Pure strict mutation proof; wire provenance must be checked against PCAP."""
    assert battle['battle_id'] and battle['player_id'] == f['player']
    assert battle['player_active_morty'] == f['active']
    assert battle['opponent_active_morty'] == f['wild']
    assert battle['move_deadline'] is None
    grouped = {}
    for event in events:
        assert event['room_id'] == f['room']
        grouped.setdefault(event['event_name'], []).append(event)
        if event['event_name'].startswith('battle:'):
            assert event['player_id'] == event['only_show_to_player_id'] == f['player']
        elif event['event_name'] == 'room:wild-morty-added':
            assert event['only_show_to_player_id'] == f['player']
            assert event['wild_morty_id'] == f['wild'] and event['state'] == 'WORLD'
        else:
            assert event['only_show_to_player_id'] is None
            if event['event_name'] == 'room:user-state-changed':
                assert event['player_id'] == f['player']
            else:
                assert event['wild_morty_id'] == f['wild']
    win = battle['state'] == 'COMPLETED'
    allowed = {'battle:start', 'battle:turn-result', 'battle:move-timer-started',
               'room:user-state-changed', 'room:wild-morty-state-changed',
               'room:wild-morty-removed' if win else 'room:wild-morty-added'}
    assert set(grouped) <= allowed
    assert len(grouped.get('battle:start', [])) == len(grouped.get('battle:turn-result', [])) == 1
    starts = json.loads(grouped['battle:start'][0]['battle_start'])
    assert starts['battle_id'] == battle['battle_id'] and starts['battle_type'] == 'PvWM'
    assert starts['player']['player_id'] == f['player'] and starts['opponent']['active_owned_morty'] == f['wild']
    timers = grouped.get('battle:move-timer-started', [])
    assert len(timers) == 1 if win else len(timers) <= 1
    for timer in timers:
        assert json.loads(timer['battle_move_timer_started'])['battle_id'] == battle['battle_id']
    assert [e['state'] for e in grouped.get('room:user-state-changed', [])] == ['BATTLE', 'WORLD']
    assert [e['state'] for e in grouped.get('room:wild-morty-state-changed', [])] == (['BATTLE'] if win else ['BATTLE', 'WORLD'])
    assert len(grouped.get('room:wild-morty-removed' if win else 'room:wild-morty-added', [])) == 1
    results = [json.loads(e['battle_turn_result']) for e in events if e['event_name'] == 'battle:turn-result']
    assert len(results) == 1 and results[0]['battle_id'] == battle['battle_id']
    result = results[0]
    expected = copy.deepcopy(prepared)
    moves = [r for r in native if r['path'].rstrip('/') == '/session/battle/move' and r['status'] == 200]
    if battle['state'] == 'COMPLETED':
        assert battle['winner'] == f['player'] and battle['opponent_hp'] == 0 and result['outcome'] == 'WIN'
        acts = result['turn_datas']
        assert len(acts) == 1, 'Exactly one ITEM action and no AI action required'
        act = acts[0]
        assert act['type'] == 'ITEM' and act['item_id'] == ITEM and act['success'] is True
        assert act['owned_morty_id'] == f['active'] and act['attacker_player_id'] == f['player']
        assert act['defender_player_id'] == battle['opponent_id'] and act['effect_value'] == f['enemy_hp']
        assert act['attacker_morty_datas'] == []
        assert act['defender_morty_datas'] == [{'owned_morty_id': f['wild'], 'hp': 0}]
        assert result['player_datas']['player']['rewards'] == []
        assert result['player_datas']['player']['xp_datas'] == []
        assert result['player_datas']['player']['attacks_to_learn'] == []
        assert len(moves) == 1 and moves[0]['response'] == {'success': True}
        request = moves[0]['request']
        assert request['battle_id'] == battle['battle_id'] and request['type'] == 'ITEM'
        assert request['owned_morty_id'] == f['active'] and request['move_id'] == ITEM
        row = next(i for i in expected['items'] if i['id'] == f['stock_id'])
        row['quantity'] -= 1
        assert result['player_datas']['player']['owned_items'] == [{'item_id': ITEM, 'quantity': row['quantity']}]
        count = 1
    else:
        assert battle['state'] == 'CANCELLED' and battle['winner'] is None
        assert result['outcome'] == 'ABANDONED' and result['turn_datas'] == []
        assert result['player_datas']['player'] == {} and not moves
        assert battle['opponent_hp'] == f['enemy_hp']
        count = 0
    clone = next(m for m in prepared['morties'] if m['owned_morty_id'] == f['active'])
    assert battle['player_hp'] == clone['hp']
    assert current == expected, 'Unexplained mutation; preserve fixture for investigation'
    return count


def main():
    global EXCLUDE_BATTLE, LOCK_EVENT_QUERY
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('preflight', 'prepare', 'start', 'screen', 'record', 'cleanup', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--label', default='current')
    args = p.parse_args()
    out = args.output.resolve()
    assert out.is_relative_to((ROOT / '.research').resolve())
    assert args.label.replace('-', '').replace('_', '').isalnum()
    user = preflight()
    if args.action == 'preflight':
        assert user['state'] == 'WORLD'
        assert not sql(f"SELECT battle_id FROM battles WHERE player_id='{user['player_id']}' AND state='ACTIVE'")
        assert not sql(f"SELECT battle_id FROM friend_battle_memberships WHERE player_id='{user['player_id']}'")
        print('Dedicated Android identity, WORLD, and no active/shared claim verified.')
        return
    manifest = out / 'fixture.json'
    if args.action == 'prepare':
        assert not out.exists(), 'Use an entirely fresh research directory'
        assert user['state'] == 'WORLD'
        before = guards.snapshot(user['player_id'])
        assert not before['memberships']
        assert not [b for b in before['battle_history'] if b['state'] == 'ACTIVE']
        decks = [d for d in before['decks'] if d['deck_id'] == user['active_deck_id']]
        assert len(decks) == 1
        deck = decks[0]
        party = json.loads(deck['owned_morty_ids'])
        assert isinstance(party, list) and 0 < len(party) < 5 and len(set(party)) == len(party)
        for owned in party:
            assert str(uuid.UUID(owned)) == owned
            assert len(sql(f"SELECT id FROM owned_morties WHERE owned_morty_id='{owned}'")) == 1
            assert len([m for m in before['morties'] if m['owned_morty_id'] == owned]) == 1
        primary = next(m for m in before['morties'] if m['owned_morty_id'] == party[0])
        assert primary['hp'] > 0 and primary['hp'] == primary['hp_stat']
        assert not primary['is_poisoned'] and not primary['is_paralysed']
        assert set(items.MC) == set(primary) - {'id', 'created_at'}
        assert {c['Field'] for c in sql('SHOW COLUMNS FROM owned_attacks')} == set(items.AC) | {'id'}
        assert [a for a in before['attacks'] if a['owned_morty_id'] == primary['owned_morty_id']]
        stock = [i for i in before['items'] if i['item_id'] == ITEM]
        assert len(stock) <= 1 and (not stock or type(stock[0]['quantity']) is int and 0 <= stock[0]['quantity'] < 2147483647)
        f = dict(player=user['player_id'], room=user['room_id'], active=str(uuid.uuid4()),
                 deck_id=deck['id'], before=before, device=DEVICE,
                 identity_receipt=dict(path=str(IDENTITY.relative_to(ROOT)), sha256=digest(IDENTITY)),
                 provenance='SYNTHETIC full-stat clone, additive one box, private spawn/start; Android moves only')
        out.mkdir(parents=True)
        items.save(manifest, f)
        me = ['?' if c == 'owned_morty_id' else '`'+c+'`' for c in items.MC]
        ae = ['?' if c == 'owned_morty_id' else '`'+c+'`' for c in items.AC]
        changes = [
            ('INSERT INTO owned_morties ('+','.join('`'+c+'`' for c in items.MC)+') SELECT '+','.join(me)+' FROM owned_morties WHERE id=? AND player_id=?', [f['active'], primary['id'], f['player']]),
            ('INSERT INTO owned_attacks ('+','.join('`'+c+'`' for c in items.AC)+') SELECT '+','.join(ae)+' FROM owned_attacks WHERE owned_morty_id=?', [f['active'], primary['owned_morty_id']]),
            ('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=?', [json.dumps([f['active']]+party, separators=(',', ':')), deck['id'], f['player']]),
            ('UPDATE owned_items SET quantity=quantity+1 WHERE id=? AND player_id=?', [stock[0]['id'], f['player']]) if stock else
            ('INSERT INTO owned_items (player_id,item_id,quantity) VALUES (?,?,1)', [f['player'], ITEM])]
        switch.locked(f, before, changes)
        items.save(out / 'prepared.json', guards.snapshot(f['player']))
        print('Synthetic full-stat clone and additive one box prepared; reload Android player details.')
        return
    f = json.loads(manifest.read_text(encoding='utf-8'))
    assert f['player'] == identity() == user['player_id'] and f['device'] == DEVICE
    assert f['identity_receipt']['sha256'] == digest(IDENTITY)
    prepared = json.loads((out / 'prepared.json').read_text(encoding='utf-8'))
    f['stock_id'] = next(i['id'] for i in prepared['items'] if i['item_id'] == ITEM)
    case_path = out / 'case.json'
    if case_path.exists():
        case = json.loads(case_path.read_text(encoding='utf-8'))
        EXCLUDE_BATTLE = case['battle_id']
        f.update(wild=case['wild'], enemy_hp=case['enemy_hp'])
    if args.action == 'start':
        assert not case_path.exists() and not (out / 'start-intent.json').exists()
        assert user['state'] == 'WORLD' and user['room_id'] == f['room']
        assert guards.snapshot(f['player']) == prepared
        case = dict(wild=str(uuid.uuid4()), floor=sql('SELECT COALESCE(MAX(id),0) AS id FROM event_queue')[0]['id'])
        items.save(out / 'start-intent.json', case)
        switch.locked(f, prepared, [('INSERT INTO event_queue (room_id,event_name,wild_morty_id,morty_id,state,placement,variant,only_show_to_player_id) VALUES (?,?,?,?,?,?,?,?)', [f['room'], 'room:wild-morty-added', case['wild'], 'MortyDefault', 'WORLD', '0,0', 'Normal', f['player']])])
        session = sql(f"SELECT session_id FROM users WHERE player_id='{f['player']}'")[0]['session_id']
        status, body = capture.http.post('/session/battle-wild-morty', dict(session_id=session, wild_morty_id=case['wild']))
        items.save(out / 'SYNTHETIC-start-response.json', dict(status=status, body=body))
        assert status == 200 and body == {'success': True}
        rows = sql(f"SELECT * FROM battles WHERE player_id='{f['player']}' AND opponent_active_morty='{case['wild']}'")
        assert len(rows) == 1 and rows[0]['player_active_morty'] == f['active'] and rows[0]['opponent_hp'] > 0
        case.update(battle_id=rows[0]['battle_id'], enemy_hp=rows[0]['opponent_hp'],
                    session_id_sha256=hashlib.sha256(session.encode()).hexdigest())
        items.save(case_path, case)
        print('Synthetic private wild battle started. Submit ITEM through Android only.')
        return
    if args.action == 'verify' and (out / 'cleanup.json').exists():
        assert guards.snapshot(f['player']) == f['before']
        assert not sql(f"SELECT battle_id FROM battles WHERE battle_id='{case['battle_id']}'") if case_path.exists() else True
        print('Exact original gameplay and history verified after cleanup.')
        return
    if args.action in ('record', 'verify', 'cleanup'):
        if case_path.exists():
            battle, events, current = timeout.state(f, case)
            # The timestamp floor is a capture filter; payload battle IDs still
            # have to match our exact fixture battle before anything is deleted.
            for e in events:
                if e['event_name'] in ('battle:start', 'battle:turn-result', 'battle:move-timer-started'):
                    payload = json.loads(e[{'battle:start':'battle_start', 'battle:turn-result':'battle_turn_result', 'battle:move-timer-started':'battle_move_timer_started'}[e['event_name']]])
                    assert payload['battle_id'] == case['battle_id']
            captured = native(case)
        else:
            assert not (out / 'start-intent.json').exists(), 'Interrupted start requires investigation; preserve receipt'
            battle, events, current, captured = None, [], guards.snapshot(f['player']), []
        if args.action == 'record':
            items.save(out / (args.label+'-result.json'), dict(battle=battle, events=events, snapshot=current))
            items.save(out / (args.label+'-http.json'), captured)
            print('Recorded fixture state and scoped HTTP capture; Android provenance requires PCAP review.')
        else:
            count = validate(f, prepared, current, battle, events, captured) if battle else 0
            if not battle:
                assert current == prepared
            if args.action == 'verify':
                print('Strict fixture mutation proof passed; uses='+str(count))
                return
            assert not (out / 'cleanup.json').exists()
            # Preserve evidence before deleting only this fixture's rows.
            items.save(out / 'cleanup-result.json', dict(battle=battle, events=events, snapshot=current))
            items.save(out / 'cleanup-http.json', captured)
            olddeck = next(d for d in f['before']['decks'] if d['id'] == f['deck_id'])
            changes = [('DELETE FROM owned_attacks WHERE owned_morty_id=?', [f['active']]),
                       ('DELETE FROM owned_morties WHERE player_id=? AND owned_morty_id=?', [f['player'], f['active']]),
                       ('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=?', [olddeck['owned_morty_ids'], f['deck_id'], f['player']])]
            oldstock = [i for i in f['before']['items'] if i['item_id'] == ITEM]
            # Successful consumption already removed the additive delta.
            if not count:
                changes.append(('UPDATE owned_items SET quantity=quantity-1 WHERE id=? AND player_id=?', [f['stock_id'], f['player']]))
            if not oldstock:
                changes.append(('DELETE FROM owned_items WHERE id=? AND player_id=? AND quantity=0', [f['stock_id'], f['player']]))
            for e in events:
                changes.append(('DELETE FROM event_queue WHERE id=? AND room_id=? AND (player_id=? OR wild_morty_id=?)', [e['id'], f['room'], f['player'], f.get('wild')]))
            if battle:
                changes.append(("DELETE FROM battles WHERE battle_id=? AND player_id=? AND state IN ('COMPLETED','CANCELLED')", [case['battle_id'], f['player']]))
            locked_current = current
            if battle:
                LOCK_EVENT_QUERY = f"SELECT * FROM event_queue WHERE id>{int(case['floor'])} AND room_id='{f['room']}' AND (wild_morty_id='{case['wild']}' OR (player_id='{f['player']}' AND event_name IN ('battle:start','battle:turn-result','battle:move-timer-started','room:user-state-changed'))) ORDER BY id"
                locked_current = dict(current, fixture_events=events)
            switch.locked(f, locked_current, changes, battle, events)
            LOCK_EVENT_QUERY = None
            restored = guards.snapshot(f['player'])
            assert restored == f['before']
            items.save(out / 'restored.json', restored)
            items.save(out / 'cleanup.json', dict(restored=True, exact_original_rows=True,
                       acceptance=bool(count), meeseeks_uses=count, outcome='WIN' if count else 'ABANDONED' if battle else None,
                       before_sha256=digest(manifest), prepared_sha256=digest(out / 'prepared.json'),
                       restored_snapshot_sha256=digest(out / 'restored.json'), result_sha256=digest(out / 'cleanup-result.json'),
                       case_sha256=digest(case_path) if case_path.exists() else None))
            print('Fixture-only cleanup complete; exact original gameplay/history restored. Acceptance='+str(bool(count)))
            return
    if args.action in ('screen', 'record'):
        path = out / (args.label+'.png')
        assert not path.exists()
        path.write_bytes(adb('exec-out', 'screencap', '-p'))


if __name__ == '__main__':
    main()

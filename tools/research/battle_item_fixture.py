"""Guarded synthetic clone/stock fixture. Acceptance ITEM/RUN requests use Android UI."""
import argparse
import json
import subprocess
import uuid
from pathlib import Path

import battle_switch_fixture as switch
import capture_battle_lifecycle as capture
import status_cure_fixture as guards

ROOT = capture.ROOT
sql = capture.sql
ITEMS = ('ItemSerum', 'ItemPureHalzinger', 'ItemPurePlutonicRock', 'ItemPoisonCure', 'ItemParalysisCure')
MC = ['player_id', 'owned_morty_id', 'morty_id', 'level', 'xp', 'hp', 'hp_stat', 'attack_stat', 'defence_stat', 'variant', 'speed_stat', 'is_locked', 'is_trading_locked', 'fight_pit_id', 'evolution_points', 'xp_lower', 'xp_upper', 'is_poisoned', 'is_paralysed']
AC = ['owned_morty_id', 'attack_id', 'position', 'amount', 'pp', 'pp_stat', 'stat', 'type', 'to_self', 'is_accurate', 'accuracy', 'power']


def locked_php(code):
    # Multiple item result events exceed Windows' command-line limit. Send the
    # existing lock transaction through stdin without changing its safeguards.
    return subprocess.run(capture.http.COMPOSE + ['exec', '-T', 'web', 'php'], input='<?php\n'+code, cwd=ROOT, capture_output=True, text=True, check=True, timeout=20).stdout


switch.php = locked_php


def save(path, value):
    switch.save(path, value)


def native(case):
    raw = subprocess.run(capture.http.COMPOSE + ['exec', '-T', 'web', 'cat', '/tmp/pocket-research-http.jsonl'], cwd=ROOT, capture_output=True, text=True, check=True, timeout=20).stdout
    rows = []
    for line in raw.splitlines():
        row = json.loads(line)
        request = row.get('request')
        if isinstance(request, dict) and request.get('battle_id') == case['battle_id']:
            request.pop('session_id', None)
            rows.append(row)
    return rows


def state(f, case):
    player, room, wild = f['player'], f['room'], case['wild']
    battles = sql(f"SELECT * FROM battles WHERE battle_id='{case['battle_id']}' AND player_id='{player}'")
    assert len(battles) == 1
    events = sql(f"SELECT * FROM event_queue WHERE id>{int(case['floor'])} AND room_id='{room}' AND (wild_morty_id='{wild}' OR (player_id='{player}' AND event_name IN ('battle:start','battle:turn-result','battle:move-timer-started','room:user-state-changed')))")
    return battles[0], events, guards.snapshot(player)


def validate(f, prepared, current, events):
    """Reconstruct the only permitted clone/inventory mutations from recorded acts."""
    import copy
    expected = copy.deepcopy(prepared)
    before = f['before']
    assert current['user'] == before['user'] and current['decks'] == prepared['decks']
    clones = (f['active'], f['bench'])
    assert [m for m in current['morties'] if m['owned_morty_id'] not in clones] == before['morties']
    assert [a for a in current['attacks'] if a['owned_morty_id'] not in clones] == before['attacks']
    counts = {item: 0 for item in ITEMS}
    for event in events:
        if event['event_name'] != 'battle:turn-result':
            continue
        result = json.loads(event['battle_turn_result'])
        # Traverse action records without depending on their enclosing list name.
        def walk(value):
            if isinstance(value, dict):
                if value.get('type') in ('ITEM', 'ATTACK') and 'attacker_morty_datas' in value:
                    yield value
                else:
                    for child in value.values():
                        yield from walk(child)
            elif isinstance(value, list):
                for child in value:
                    yield from walk(child)
        for act in walk(result):
            if act['type'] == 'ITEM':
                assert act['item_id'] in counts and act['owned_morty_id'] in clones and act['success'] is True
                counts[act['item_id']] += 1
                assert counts[act['item_id']] <= 1
            models = act.get('attacker_morty_datas', []) + act.get('defender_morty_datas', [])
            for effect in act.get('effect_datas', []):
                models += effect.get('attacker_morty_datas', []) + effect.get('defender_morty_datas', [])
            for model in models:
                owned = model['owned_morty_id']
                if owned not in clones:
                    continue
                target = next(m for m in expected['morties'] if m['owned_morty_id'] == owned)
                for field in ('hp', 'is_poisoned', 'is_paralysed'):
                    if field in model:
                        target[field] = int(model[field])
                for attack in model.get('owned_attacks', []):
                    row = next(a for a in expected['attacks'] if a['owned_morty_id'] == owned and a['attack_id'] == attack['attack_id'])
                    row['pp'] = attack['pp']
                    if 'pp_stat' in attack:
                        row['pp_stat'] = attack['pp_stat']
    for item, count in counts.items():
        row = next(i for i in expected['items'] if i['item_id'] == item)
        row['quantity'] -= count
    assert current == expected, 'Unexplained account mutation; preserve fixture and investigate'
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'start', 'record', 'screen', 'cleanup', 'recover-run'))
    parser.add_argument('--output', type=Path, default=ROOT / '.research/emulator/battle-items-20261105')
    parser.add_argument('--label', default='current')
    parser.add_argument('--bench-alive', action='store_true', help='Fresh fixture starts bench at HP20 for AP/cure-only cases')
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
        assert 0 < len(party) <= 3 and len(set(party)) == len(party)
        for owned in party:
            assert str(uuid.UUID(owned)) == owned
            assert len(sql(f"SELECT id FROM owned_morties WHERE owned_morty_id='{owned}'")) == 1
        primary = next(m for m in before['morties'] if m['owned_morty_id'] == party[0])
        assert primary['hp'] == primary['hp_stat'] == 20
        attacks = [a for a in before['attacks'] if a['owned_morty_id'] == primary['owned_morty_id']]
        assert len(attacks) == 1 and attacks[0]['attack_id'] == 'AttackOutburst' and attacks[0]['pp'] == attacks[0]['pp_stat'] == 12
        assert set(MC) == set(primary) - {'id', 'created_at'}
        assert {c['Field'] for c in sql('SHOW COLUMNS FROM owned_attacks')} == set(AC) | {'id'}
        f = dict(player=user['player_id'], room=user['room_id'], active=str(uuid.uuid4()), bench=str(uuid.uuid4()), before=before, deck_id=deck['id'], provenance='SYNTHETIC two cloned Morties/private spawn/temporary stock; ITEM and RUN must originate in Android UI')
        save(manifest, f)
        changes = []
        for owned, hp, status, pp in ((f['active'], 10, 0, 12), (f['bench'], 20 if args.bench_alive else 0, 1, 1)):
            expr = ['?' if c == 'owned_morty_id' else str(hp) if c == 'hp' else str(status) if c in ('is_poisoned', 'is_paralysed') else '`'+c+'`' for c in MC]
            ae = ['?' if c == 'owned_morty_id' else str(pp) if c == 'pp' else '`'+c+'`' for c in AC]
            changes += [('INSERT INTO owned_morties ('+','.join('`'+c+'`' for c in MC)+') SELECT '+','.join(expr)+' FROM owned_morties WHERE id=? AND player_id=?', [owned, primary['id'], f['player']]), ('INSERT INTO owned_attacks ('+','.join('`'+c+'`' for c in AC)+') SELECT '+','.join(ae)+' FROM owned_attacks WHERE owned_morty_id=?', [owned, primary['owned_morty_id']])]
        changes.append(('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=?', [json.dumps([f['active'], f['bench']] + party, separators=(',', ':')), deck['id'], f['player']]))
        for item in ITEMS:
            rows = [i for i in before['items'] if i['item_id'] == item]
            assert len(rows) <= 1 and (not rows or 0 <= rows[0]['quantity'] < 10)
            changes.append(('UPDATE owned_items SET quantity=quantity+1 WHERE id=? AND player_id=?', [rows[0]['id'], f['player']]) if rows else ('INSERT INTO owned_items (player_id,item_id,quantity) VALUES (?,?,1)', [f['player'], item]))
        switch.locked(f, before, changes)
        save(out / 'prepared.json', guards.snapshot(f['player']))
        print('Synthetic clones prepared. Restart app for fresh player details.')
        return
    f = json.loads(manifest.read_text())
    player = f['player']
    case_path = out / 'case.json'
    if args.action == 'start':
        assert not case_path.exists()
        user = sql(f"SELECT room_id,state,session_id FROM users WHERE player_id='{player}'")[0]
        assert user['state'] == 'WORLD' and user['room_id'] == f['room']
        assert guards.snapshot(player) == json.loads((out / 'prepared.json').read_text())
        assert not sql(f"SELECT battle_id FROM battles WHERE player_id='{player}' AND state='ACTIVE'")
        wild = str(uuid.uuid4())
        case = dict(wild=wild, floor=sql('SELECT COALESCE(MAX(id),0) AS id FROM event_queue')[0]['id'])
        save(out / 'start-intent.json', case)
        sql(f"INSERT INTO event_queue (room_id,event_name,wild_morty_id,morty_id,state,placement,variant,only_show_to_player_id) VALUES ('{f['room']}','room:wild-morty-added','{wild}','MortyDefault','WORLD','0,0','Normal','{player}')")
        status, body = capture.http.post('/session/battle-wild-morty', dict(session_id=user['session_id'], wild_morty_id=wild))
        save(out / 'start-response.json', dict(status=status, body=body))
        assert status == 200 and body == {'success': True}
        battle = sql(f"SELECT * FROM battles WHERE player_id='{player}' AND opponent_active_morty='{wild}'")
        assert len(battle) == 1 and battle[0]['player_active_morty'] == f['active'] and battle[0]['opponent_hp'] == 1
        case['battle_id'] = battle[0]['battle_id']
        save(case_path, case)
    if args.action in ('record', 'cleanup', 'recover-run'):
        case = json.loads(case_path.read_text())
        battle, events, current = state(f, case)
        if args.action == 'recover-run':
            assert battle['state'] == 'ACTIVE'
            session = sql(f"SELECT session_id FROM users WHERE player_id='{player}'")[0]['session_id']
            status, body = capture.http.post('/session/battle/move', dict(session_id=session, battle_id=case['battle_id'], type='RUN', owned_morty_id=battle['player_active_morty'], move_id=None))
            save(out / 'NONNATIVE-recovery-run.json', dict(status=status, body=body))
            return
        if args.action == 'record':
            save(out / (args.label+'-result.json'), dict(battle=battle, events=events, snapshot=current))
            save(out / (args.label+'-http.json'), native(case))
            print(json.dumps(dict(state=battle['state'], hp=battle['player_hp'], turn_events=len([e for e in events if e['event_name']=='battle:turn-result']))))
        else:
            assert battle['state'] == 'CANCELLED', 'Only ended RUN fixture may be cleaned'
            prepared = json.loads((out / 'prepared.json').read_text())
            counts = validate(f, prepared, current, events)
            before = f['before']
            changes = []
            for owned in (f['active'], f['bench']):
                changes += [('DELETE FROM owned_attacks WHERE owned_morty_id=?', [owned]), ('DELETE FROM owned_morties WHERE player_id=? AND owned_morty_id=?', [player, owned])]
            olddeck = next(d for d in before['decks'] if d['id'] == f['deck_id'])
            changes.append(('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=?', [olddeck['owned_morty_ids'], f['deck_id'], player]))
            for item in ITEMS:
                old = [i for i in before['items'] if i['item_id'] == item]
                row = next(i for i in current['items'] if i['item_id'] == item)
                changes.append(('UPDATE owned_items SET quantity=? WHERE id=? AND player_id=?', [old[0]['quantity'], row['id'], player]) if old else ('DELETE FROM owned_items WHERE id=? AND player_id=?', [row['id'], player]))
            for event in events:
                changes.append(('DELETE FROM event_queue WHERE id=? AND room_id=? AND (player_id=? OR wild_morty_id=?)', [event['id'], f['room'], player, case['wild']]))
            changes.append(("DELETE FROM battles WHERE battle_id=? AND player_id=? AND state='CANCELLED'", [case['battle_id'], player]))
            switch.locked(f, current, changes, battle, events)
            assert guards.snapshot(player) == before
            save(out / 'cleanup.json', dict(restored=True, exact_original_rows=True, item_uses=counts))
            print('Exact original account rows and raw deck restored.')
            return
    if args.action in ('screen', 'record', 'start'):
        path = out / (args.label+'.png')
        assert not path.exists()
        path.write_bytes(capture.adb('exec-out', 'screencap', '-p'))


if __name__ == '__main__':
    main()

"""Clone-only FullRecover fixture; native Android performs every item/exit move.

Use separate fresh directories for world and battle cases. Raw artifacts stay
inside .research; cleanup reconstructs effects and compares rows under locks.
"""
import argparse
import copy
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
ITEM = 'ItemFullRecover'


def native_world(f):
    raw = subprocess.run(capture.http.COMPOSE + ['exec', '-T', 'web', 'cat', '/tmp/pocket-research-http.jsonl'], cwd=ROOT, capture_output=True, text=True, check=True, timeout=20).stdout
    rows = []
    for line in raw.splitlines():
        row = json.loads(line)
        request = row.get('request')
        if isinstance(request, dict) and ITEM in json.dumps(request) and any(clone in json.dumps(request) for clone in (f['active'], f['bench'])):
            request.pop('session_id', None)
            rows.append(row)
    return rows


def actions(events):
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
    for event in events:
        if event['event_name'] == 'battle:turn-result':
            yield from walk(json.loads(event['battle_turn_result']))


def validate(f, prepared, current, events, world_used):
    expected = copy.deepcopy(prepared)
    clones = (f['active'], f['bench'])
    count = 0
    if world_used:
        assert not events and f['mode'] == 'world'
        requests = [r for r in native_world(f) if r['path'].rstrip('/') == '/session/use-item' and r['status'] == 200]
        assert len(requests) == 1, 'Require one captured successful native world request'
        assert f['bench'] in json.dumps(requests[0]['request'])
        assert requests[0]['response']['is_success'] is True and requests[0]['response']['effect_value'] == 0
        target = next(m for m in expected['morties'] if m['owned_morty_id'] == f['bench'])
        target.update(hp=target['hp_stat'], is_poisoned=0, is_paralysed=0)
        count = 1
    for act in actions(events):
        if act['type'] == 'ITEM':
            assert act['item_id'] == ITEM and act['owned_morty_id'] in clones and act['success'] is True
            assert act['effect_value'] == 0
            count += 1
            models = act.get('attacker_morty_datas', [])
            target = next(m for m in models if m['owned_morty_id'] == act['owned_morty_id'])
            original = next(m for m in prepared['morties'] if m['owned_morty_id'] == target['owned_morty_id'])
            assert target['hp'] == original['hp_stat'] and not target['is_poisoned'] and not target['is_paralysed']
        else:
            assert act['attacker_player_id'] != f['player'] and act['defender_player_id'] == f['player'], 'Fixture permits AI attacks only'
            for effect in act.get('effect_datas', []):
                assert effect['type'] == 'Hit' and 1 <= effect['damage'] <= 3
                for model in effect.get('defender_morty_datas', []):
                    assert model['owned_morty_id'] in clones
                    oldhp = next(m['hp'] for m in expected['morties'] if m['owned_morty_id'] == model['owned_morty_id'])
                    assert model['hp'] == max(0, oldhp - effect['damage'])
        models = act.get('attacker_morty_datas', []) + act.get('defender_morty_datas', [])
        for effect in act.get('effect_datas', []):
            models += effect.get('attacker_morty_datas', []) + effect.get('defender_morty_datas', [])
        for model in models:
            if model['owned_morty_id'] not in clones:
                continue
            target = next(m for m in expected['morties'] if m['owned_morty_id'] == model['owned_morty_id'])
            for field in ('hp', 'is_poisoned', 'is_paralysed'):
                if field in model:
                    target[field] = int(model[field])
            for attack in model.get('owned_attacks', []):
                original = next(a for a in prepared['attacks'] if a['owned_morty_id'] == model['owned_morty_id'] and a['attack_id'] == attack['attack_id'])
                assert attack['pp'] == original['pp'] and attack.get('pp_stat', original['pp_stat']) == original['pp_stat'], 'FullRecover must preserve AP'
    assert count <= 1
    next(i for i in expected['items'] if i['item_id'] == ITEM)['quantity'] -= count
    assert current == expected, 'Unexplained mutation; preserve fixture for investigation'
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'start', 'record', 'screen', 'cleanup'))
    parser.add_argument('--mode', choices=('world', 'battle'), default='world')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', default='current')
    parser.add_argument('--world-used', action='store_true')
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
        assert set(items.MC) == set(primary) - {'id', 'created_at'}
        assert {c['Field'] for c in sql('SHOW COLUMNS FROM owned_attacks')} == set(items.AC) | {'id'}
        source_attacks = [a for a in before['attacks'] if a['owned_morty_id'] == primary['owned_morty_id']]
        assert source_attacks and all(a['pp_stat'] > 1 for a in source_attacks)
        f = dict(player=user['player_id'], room=user['room_id'], active=str(uuid.uuid4()), bench=str(uuid.uuid4()), before=before, deck_id=deck['id'], mode=args.mode,
                 provenance='SYNTHETIC complete clones HP10/20, both ailments, AP1; temporary one FullRecover; native Android item and exit only')
        items.save(manifest, f)
        changes = []
        for owned in (f['active'], f['bench']):
            me = ['?' if c == 'owned_morty_id' else '10' if c == 'hp' else '1' if c in ('is_poisoned', 'is_paralysed') else '`'+c+'`' for c in items.MC]
            ae = ['?' if c == 'owned_morty_id' else '1' if c == 'pp' else '`'+c+'`' for c in items.AC]
            changes += [('INSERT INTO owned_morties ('+','.join('`'+c+'`' for c in items.MC)+') SELECT '+','.join(me)+' FROM owned_morties WHERE id=? AND player_id=?', [owned, primary['id'], f['player']]), ('INSERT INTO owned_attacks ('+','.join('`'+c+'`' for c in items.AC)+') SELECT '+','.join(ae)+' FROM owned_attacks WHERE owned_morty_id=?', [owned, primary['owned_morty_id']])]
        changes.append(('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=?', [json.dumps([f['active'], f['bench']] + party, separators=(',', ':')), deck['id'], f['player']]))
        stock = [i for i in before['items'] if i['item_id'] == ITEM]
        assert len(stock) <= 1
        changes.append(('UPDATE owned_items SET quantity=1 WHERE id=? AND player_id=?', [stock[0]['id'], f['player']]) if stock else ('INSERT INTO owned_items (player_id,item_id,quantity) VALUES (?,?,1)', [f['player'], ITEM]))
        switch.locked(f, before, changes)
        items.save(out / 'prepared.json', guards.snapshot(f['player']))
        print('Synthetic clones and exactly one FullRecover prepared; reload app.')
        return
    f = json.loads(manifest.read_text())
    prepared = json.loads((out / 'prepared.json').read_text())
    case_path = out / 'case.json'
    if args.action == 'start':
        assert f['mode'] == 'battle' and not case_path.exists()
        assert guards.snapshot(f['player']) == prepared
        user = sql(f"SELECT room_id,state,session_id FROM users WHERE player_id='{f['player']}'")[0]
        assert user['state'] == 'WORLD' and user['room_id'] == f['room']
        assert not sql(f"SELECT battle_id FROM battles WHERE player_id='{f['player']}' AND state='ACTIVE'")
        case = dict(wild=str(uuid.uuid4()), floor=sql('SELECT COALESCE(MAX(id),0) AS id FROM event_queue')[0]['id'])
        items.save(out / 'start-intent.json', case)
        sql(f"INSERT INTO event_queue (room_id,event_name,wild_morty_id,morty_id,state,placement,variant,only_show_to_player_id) VALUES ('{f['room']}','room:wild-morty-added','{case['wild']}','MortyDefault','WORLD','0,0','Normal','{f['player']}')")
        status, body = capture.http.post('/session/battle-wild-morty', dict(session_id=user['session_id'], wild_morty_id=case['wild']))
        items.save(out / 'start-response.json', dict(status=status, body=body))
        assert status == 200 and body == {'success': True}
        battles = sql(f"SELECT * FROM battles WHERE player_id='{f['player']}' AND opponent_active_morty='{case['wild']}'")
        assert len(battles) == 1 and battles[0]['player_active_morty'] == f['active'] and battles[0]['opponent_hp'] == 1
        case['battle_id'] = battles[0]['battle_id']
        items.save(case_path, case)
    if args.action in ('record', 'cleanup'):
        battle, events, current = timeout.state(f, json.loads(case_path.read_text())) if case_path.exists() else (None, [], guards.snapshot(f['player']))
        if args.action == 'record':
            items.save(out / (args.label+'-result.json'), dict(battle=battle, events=events, snapshot=current))
            items.save(out / (args.label+'-http.json'), items.native(json.loads(case_path.read_text())) if battle else native_world(f))
        else:
            if battle:
                assert battle['state'] == 'CANCELLED' and battle['winner'] is None and battle['player_active_morty'] in (f['active'], f['bench'])
                results = [json.loads(e['battle_turn_result']) for e in events if e['event_name'] == 'battle:turn-result']
                assert results[-1]['outcome'] in ('RUN', 'ABANDONED')
            count = validate(f, prepared, current, events, args.world_used)
            changes = []
            for owned in (f['active'], f['bench']):
                changes += [('DELETE FROM owned_attacks WHERE owned_morty_id=?', [owned]), ('DELETE FROM owned_morties WHERE player_id=? AND owned_morty_id=?', [f['player'], owned])]
            olddeck = next(d for d in f['before']['decks'] if d['id'] == f['deck_id'])
            changes.append(('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=?', [olddeck['owned_morty_ids'], f['deck_id'], f['player']]))
            row = next(i for i in current['items'] if i['item_id'] == ITEM)
            old = [i for i in f['before']['items'] if i['item_id'] == ITEM]
            changes.append(('UPDATE owned_items SET quantity=? WHERE id=? AND player_id=?', [old[0]['quantity'], row['id'], f['player']]) if old else ('DELETE FROM owned_items WHERE id=? AND player_id=?', [row['id'], f['player']]))
            if battle:
                case = json.loads(case_path.read_text())
                for event in events:
                    changes.append(('DELETE FROM event_queue WHERE id=? AND room_id=? AND (player_id=? OR wild_morty_id=?)', [event['id'], f['room'], f['player'], case['wild']]))
                changes.append(("DELETE FROM battles WHERE battle_id=? AND player_id=? AND state='CANCELLED'", [battle['battle_id'], f['player']]))
            switch.locked(f, current, changes, battle, events)
            assert guards.snapshot(f['player']) == f['before']
            items.save(out / 'cleanup.json', dict(restored=True, exact_original_rows=True, full_recover_uses=count, outcome=results[-1]['outcome'] if battle else None, ap_unchanged=True))
            print('Exact original account, raw deck and stock restored under locks.')
            return
    if args.action in ('screen', 'record', 'start'):
        path = out / (args.label+'.png')
        assert not path.exists()
        path.write_bytes(capture.adb('exec-out', 'screencap', '-p'))


if __name__ == '__main__':
    main()

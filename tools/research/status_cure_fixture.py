"""Guarded, reversible ailment fixture; item uses must originate in Android UI."""
import argparse
import base64
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/protocol'))
from test_http import php, sql

OUT = ROOT / '.research/emulator/status-cures'
ITEMS = ('ItemPoisonCure', 'ItemParalysisCure')


def queries(player):
    return {
        'user': f"SELECT player_id,room_id,state,active_deck_id,level,xp,coins,coupons,permits,wins,losses FROM users WHERE player_id='{player}'",
        'morties': f"SELECT * FROM owned_morties WHERE player_id='{player}' ORDER BY id",
        'attacks': f"SELECT a.* FROM owned_attacks a JOIN owned_morties m ON a.owned_morty_id=m.owned_morty_id WHERE m.player_id='{player}' ORDER BY a.id",
        'items': f"SELECT * FROM owned_items WHERE player_id='{player}' ORDER BY id",
        'decks': f"SELECT * FROM decks WHERE player_id='{player}' ORDER BY id",
    }


def snapshot(player):
    return {key: sql(query) for key, query in queries(player).items()}


def save(name, data):
    (OUT / name).write_text(json.dumps(data, indent=2) + '\n', encoding='utf-8')


def mutate(fixture, expected, changes):
    payload = base64.b64encode(json.dumps(dict(f=fixture, expected=expected, queries=queries(fixture['player']), changes=changes)).encode()).decode()
    php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; $x=json_decode(base64_decode('" + payload + "'),true);" + """
    $pdo->beginTransaction();
    try {
        foreach ($x['queries'] as $k=>$query) {
            $rows=$pdo->query($query.' FOR UPDATE')->fetchAll();
            if ($rows!==$x['expected'][$k]) throw new RuntimeException('Concurrent change: '.$k);
        }
        $q=$pdo->prepare("SELECT battle_id FROM battles WHERE player_id=? AND state='ACTIVE' FOR UPDATE");
        $q->execute([$x['f']['player']]);
        if ($q->fetch()) throw new RuntimeException('Active battle prevents fixture');
        foreach ($x['changes'] as $change) { $q=$pdo->prepare($change[0]); $q->execute($change[1]); }
        $pdo->commit();
    } catch (Throwable $e) { if ($pdo->inTransaction()) $pdo->rollBack(); throw $e; }
    """)


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'record', 'restore'))
    parser.add_argument('--poison-used', action='store_true')
    parser.add_argument('--paralysis-used', action='store_true')
    parser.add_argument('--label', default='current')
    parser.add_argument('--output', type=Path, default=OUT, help='fresh capture directory inside .research')
    args = parser.parse_args()
    OUT = args.output.resolve()
    if not OUT.is_relative_to((ROOT / '.research').resolve()):
        parser.error('--output must stay inside the ignored .research workspace')
    assert php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');") == 'db:http://localhost:8087', 'Isolated backend required'
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = OUT / 'fixture.json'
    if args.action == 'prepare':
        assert not (OUT / 'fixture-restored.json').exists(), 'Preserve this capture; select a fresh --output directory'
        assert not manifest.exists(), 'Restore previous fixture first'
        users = sql("SELECT player_id,active_deck_id FROM users WHERE username='PMResearch01' AND state='WORLD'")
        assert len(users) == 1
        player = users[0]['player_id']
        assert str(uuid.UUID(player)) == player
        before = snapshot(player)
        deck = [d for d in before['decks'] if d['deck_id'] == users[0]['active_deck_id']]
        assert len(deck) == 1
        target_id = json.loads(deck[0]['owned_morty_ids'])[0]
        assert str(uuid.UUID(target_id)) == target_id
        targets = [m for m in before['morties'] if m['owned_morty_id'] == target_id]
        assert len(targets) == 1
        target = targets[0]
        assert len(sql(f"SELECT id FROM owned_morties WHERE owned_morty_id='{target_id}'")) == 1
        assert target['morty_id'] == 'MortyDefault' and target['hp'] > 0 and target['hp'] == target['hp_stat']
        fixture = dict(player=player, target=target_id, before=before, prepared=False,
                       provenance='Synthetic database ailments and temporary inventory; Android UI item consumption only')
        with manifest.open('x', encoding='utf-8') as file:
            json.dump(fixture, file, indent=2)
        changes = [('UPDATE owned_morties SET is_poisoned=1,is_paralysed=1 WHERE player_id=? AND owned_morty_id=?', [player, target_id])]
        for item in ITEMS:
            existing = [row for row in before['items'] if row['item_id'] == item]
            assert len(existing) <= 1
            assert not existing or 0 <= existing[0]['quantity'] < 10
            # The schema has no unique (player_id,item_id) key; an upsert would
            # insert a duplicate logical stack instead of incrementing it.
            if existing:
                changes.append(('UPDATE owned_items SET quantity=quantity+1 WHERE id=? AND player_id=?', [existing[0]['id'], player]))
            else:
                changes.append(('INSERT INTO owned_items (player_id,item_id,quantity) VALUES (?,?,1)', [player, item]))
        mutate(fixture, before, changes)
        fixture.update(prepared=True, prepared_snapshot=snapshot(player))
        save('fixture.json', fixture)
        save('before.json', before)
        print('Prepared primary active Morty with both ailments and one temporary cure each')
    else:
        fixture = json.loads(manifest.read_text())
        current = snapshot(fixture['player'])
        assert args.label.replace('-', '').replace('_', '').isalnum()
        save(args.label + '.json', current)
        if args.action == 'record':
            print('Saved scoped account snapshot')
            return
        if not fixture.get('prepared'):
            assert current == fixture['before'], 'Incomplete preparation changed state; inspect before recovery'
            manifest.rename(OUT / 'fixture-restored.json')
            print('Uncommitted fixture archived; original account verified unchanged')
            return
        expected = json.loads(json.dumps(fixture['prepared_snapshot']))
        target = next(m for m in expected['morties'] if m['owned_morty_id'] == fixture['target'])
        target['is_poisoned'] = 0 if args.poison_used else 1
        target['is_paralysed'] = 0 if args.paralysis_used else 1
        for item, used in zip(ITEMS, (args.poison_used, args.paralysis_used)):
            row = next(i for i in expected['items'] if i['item_id'] == item)
            row['quantity'] -= int(used)
        assert current == expected, 'Unexpected account changes; no cleanup performed'
        original = next(m for m in fixture['before']['morties'] if m['owned_morty_id'] == fixture['target'])
        changes = [('UPDATE owned_morties SET is_poisoned=?,is_paralysed=? WHERE player_id=? AND owned_morty_id=?', [original['is_poisoned'], original['is_paralysed'], fixture['player'], fixture['target']])]
        for item in ITEMS:
            rows = [i for i in fixture['before']['items'] if i['item_id'] == item]
            if rows:
                changes.append(('UPDATE owned_items SET quantity=? WHERE player_id=? AND item_id=?', [rows[0]['quantity'], fixture['player'], item]))
            else:
                changes.append(('DELETE FROM owned_items WHERE player_id=? AND item_id=?', [fixture['player'], item]))
        mutate(fixture, expected, changes)
        assert snapshot(fixture['player']) == fixture['before']
        save('restored.json', {'restored': True, 'account': snapshot(fixture['player'])})
        manifest.rename(OUT / 'fixture-restored.json')
        print('Original scoped account snapshot restored exactly')


if __name__ == '__main__':
    main()

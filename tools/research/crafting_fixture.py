#!/usr/bin/env python3
"""Reversible Serum ingredients for the isolated primary Android account."""
import argparse
import base64
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/protocol'))
from test_http import php, sql

SNAPSHOT = ROOT / '.research/emulator/crafting-fixture.json'


def run(code, fixture):
    encoded = base64.b64encode(json.dumps(fixture).encode()).decode()
    return php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
               f"$f=json_decode(base64_decode('{encoded}'),true,512,JSON_THROW_ON_ERROR);" + code)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'restore'))
    args = parser.parse_args()
    if php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');") != 'db:http://localhost:8087':
        raise SystemExit('Isolated research backend required')
    if args.action == 'prepare':
        if SNAPSHOT.exists():
            raise SystemExit('Restore existing crafting fixture first')
        users = sql("SELECT player_id,state,coins,coupons,permits,level,xp,active_deck_id FROM users WHERE username='PMResearch01'")
        if len(users) != 1 or users[0]['state'] != 'WORLD':
            raise SystemExit('Expected one primary research account in WORLD')
        player = users[0]['player_id']
        items = sql(f"SELECT * FROM owned_items WHERE player_id='{player}' AND item_id IN ('ItemBattery','ItemFleeb','ItemSerum') ORDER BY id")
        if any(row['item_id'] != 'ItemSerum' for row in items) or len(items) > 1:
            raise SystemExit('Fixture requires absent Battery/Fleeb stacks and unambiguous Serum')
        if items and not 0 <= items[0]['quantity'] < 10:
            raise SystemExit('Serum inventory must have capacity')
        fixture = {'nonce': str(uuid.uuid4()), 'player': player, 'account': users[0],
                   'original_output': items[0] if items else None}
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        with SNAPSHOT.open('x', encoding='utf-8') as target:
            json.dump(fixture, target, indent=2)
        run("""
$pdo->beginTransaction();
try {
    $q=$pdo->prepare("SELECT player_id FROM users WHERE player_id=? AND username='PMResearch01' AND state='WORLD' FOR UPDATE");
    $q->execute([$f['player']]);
    if (!$q->fetch()) throw new RuntimeException('Account changed');
    $q=$pdo->prepare("SELECT id FROM owned_items WHERE player_id=? AND item_id IN ('ItemBattery','ItemFleeb') FOR UPDATE");
    $q->execute([$f['player']]);
    if ($q->fetch()) throw new RuntimeException('Ingredients changed');
    $q=$pdo->prepare('INSERT INTO owned_items (player_id,item_id,quantity) VALUES (?,?,1)');
    foreach (['ItemBattery','ItemFleeb'] as $item) $q->execute([$f['player'],$item]);
    $pdo->commit();
} catch (Throwable $e) { if ($pdo->inTransaction()) $pdo->rollBack(); throw $e; }
""", fixture)
        print('Prepared one Battery and one Fleeb; existing Serum quantity preserved. Reload Android.')
    else:
        fixture = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
        run("""
$pdo->beginTransaction();
try {
    $q=$pdo->prepare("SELECT player_id FROM users WHERE player_id=? AND username='PMResearch01' FOR UPDATE");
    $q->execute([$f['player']]);
    if (!$q->fetch()) throw new RuntimeException('Account changed');
    $q=$pdo->prepare("SELECT * FROM owned_items WHERE player_id=? AND item_id IN ('ItemBattery','ItemFleeb','ItemSerum') FOR UPDATE");
    $q->execute([$f['player']]); $rows=[];
    foreach ($q as $row) {
        if (isset($rows[$row['item_id']])) throw new RuntimeException('Ambiguous fixture inventory');
        $rows[$row['item_id']]=$row;
    }
    foreach (['ItemBattery','ItemFleeb'] as $item) {
        if (isset($rows[$item]) && !in_array((int)$rows[$item]['quantity'],[0,1],true)) throw new RuntimeException('Ingredient fixture changed');
    }
    $original=$f['original_output']; $current=$rows['ItemSerum']??null;
    if ($original && (!$current || $current['id']!==$original['id'])) throw new RuntimeException('Output row changed');
    $before=(int)($original['quantity']??0); $now=(int)($current['quantity']??0);
    if (!in_array($now,[$before,$before+1],true)) throw new RuntimeException('Output count changed; inspect fixture before restoring');
    $delete=$pdo->prepare('DELETE FROM owned_items WHERE id=? AND player_id=?');
    foreach (['ItemBattery','ItemFleeb'] as $item) if (isset($rows[$item])) $delete->execute([$rows[$item]['id'],$f['player']]);
    if ($original) {
        $q=$pdo->prepare('UPDATE owned_items SET quantity=? WHERE id=? AND player_id=?');
        $q->execute([$before,$original['id'],$f['player']]);
    } elseif ($current) $delete->execute([$current['id'],$f['player']]);
    $pdo->commit();
} catch (Throwable $e) { if ($pdo->inTransaction()) $pdo->rollBack(); throw $e; }
""", fixture)
        SNAPSHOT.rename(SNAPSHOT.with_name(f"crafting-fixture-restored-{fixture['nonce']}.json"))
        print('Removed fixture ingredients and restored prior Serum quantity. Reload Android.')


if __name__ == '__main__':
    main()

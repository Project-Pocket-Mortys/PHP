#!/usr/bin/env python3
"""Reversible extra-Morty fixture for the primary isolated Android account."""
import argparse
import base64
import json
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/protocol'))
from test_http import php, sql

SNAPSHOT = ROOT / '.research/emulator/full-restore-fixture.json'


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
            raise SystemExit('Existing fixture snapshot must be restored first')
        users = sql("SELECT player_id,active_deck_id FROM users WHERE username='PMResearch01' AND state='WORLD'")
        if len(users) != 1:
            raise SystemExit('Expected one primary research account in WORLD')
        player = users[0]['player_id']
        decks = sql(f"SELECT id,owned_morty_ids FROM decks WHERE player_id='{player}' AND deck_id={int(users[0]['active_deck_id'])}")
        morties = sql(f"SELECT * FROM owned_morties WHERE player_id='{player}'")
        items = sql(f"SELECT id FROM owned_items WHERE player_id='{player}' AND item_id IN ('ItemPureHalzinger','ItemPurePlutonicRock')")
        if len(decks) != 1 or len(morties) != 1 or items:
            raise SystemExit('Fixture requires one original Morty/deck and no existing full-restore items')
        ids = json.loads(decks[0]['owned_morty_ids'])
        if ids != [morties[0]['owned_morty_id']]:
            raise SystemExit('Expected unambiguous original active deck')
        fixture = {'player': player, 'deck': decks[0], 'template': morties[0],
                   'morty': str(uuid.uuid4()), 'prepared': False}
        fixture['new_deck'] = json.dumps(ids + [fixture['morty']])
        SNAPSHOT.parent.mkdir(parents=True, exist_ok=True)
        # Write recovery information before making any database changes.
        with SNAPSHOT.open('x', encoding='utf-8') as target:
            json.dump(fixture, target, indent=2)
        run("""
$pdo->beginTransaction();
try {
    $q=$pdo->prepare("SELECT player_id FROM users WHERE player_id=? AND username='PMResearch01' AND state='WORLD' FOR UPDATE");
    $q->execute([$f['player']]);
    if (!$q->fetch()) throw new RuntimeException('Research account changed');
    $q=$pdo->prepare("SELECT battle_id FROM battles WHERE player_id=? AND state='ACTIVE'");
    $q->execute([$f['player']]);
    if ($q->fetch()) throw new RuntimeException('Active battle prevents fixture');
    $q=$pdo->prepare('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=? AND owned_morty_ids=?');
    $q->execute([$f['new_deck'],$f['deck']['id'],$f['player'],$f['deck']['owned_morty_ids']]);
    if ($q->rowCount()!==1) throw new RuntimeException('Original deck changed');
    $m=$f['template'];
    $q=$pdo->prepare("INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,level,xp,hp,hp_stat,attack_stat,defence_stat,speed_stat,variant,is_locked,is_trading_locked,xp_lower,xp_upper,evolution_points) VALUES (?,?,?,?,?,0,?,?,?,?,?,'0','0',?,?,0)");
    $q->execute([$f['player'],$f['morty'],$m['morty_id'],6,$m['xp'],$m['hp_stat'],$m['attack_stat'],$m['defence_stat'],$m['speed_stat'],$m['variant'],$m['xp_lower'],$m['xp_upper']]);
    $q=$pdo->prepare("INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES (?,'AttackOutburst',0,0,8)");
    $q->execute([$f['morty']]);
    $q=$pdo->prepare('INSERT INTO owned_items (player_id,item_id,quantity) VALUES (?,?,1)');
    foreach (['ItemPureHalzinger','ItemPurePlutonicRock'] as $item) $q->execute([$f['player'],$item]);
    $pdo->commit();
} catch (Throwable $e) { if ($pdo->inTransaction()) $pdo->rollBack(); throw $e; }
""", fixture)
        fixture['prepared'] = True
        SNAPSHOT.write_text(json.dumps(fixture, indent=2), encoding='utf-8')
        print('Prepared extra level-6 Morty: HP 0, Outburst AP 0, stored maximum 8; two items at quantity 1')
    else:
        fixture = json.loads(SNAPSHOT.read_text(encoding='utf-8'))
        run("""
$pdo->beginTransaction();
try {
    $q=$pdo->prepare("SELECT player_id FROM users WHERE player_id=? AND username='PMResearch01' FOR UPDATE");
    $q->execute([$f['player']]);
    if (!$q->fetch()) throw new RuntimeException('Research account changed');
    $q=$pdo->prepare('SELECT owned_morty_ids FROM decks WHERE id=? AND player_id=? FOR UPDATE');
    $q->execute([$f['deck']['id'],$f['player']]);
    $raw=$q->fetchColumn();
    if ($raw!==$f['new_deck'] && $raw!==$f['deck']['owned_morty_ids']) throw new RuntimeException('Deck changed; review fixture snapshot before restoring');
    $q=$pdo->prepare("SELECT quantity FROM owned_items WHERE player_id=? AND item_id IN ('ItemPureHalzinger','ItemPurePlutonicRock') FOR UPDATE");
    $q->execute([$f['player']]);
    foreach ($q as $row) if (!in_array((int)$row['quantity'],[0,1],true)) throw new RuntimeException('Fixture stock changed');
    $q=$pdo->prepare('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=?');
    $q->execute([$f['deck']['owned_morty_ids'],$f['deck']['id'],$f['player']]);
    $q=$pdo->prepare('DELETE FROM owned_attacks WHERE owned_morty_id=?'); $q->execute([$f['morty']]);
    $q=$pdo->prepare('DELETE FROM owned_morties WHERE player_id=? AND owned_morty_id=?'); $q->execute([$f['player'],$f['morty']]);
    $q=$pdo->prepare("DELETE FROM owned_items WHERE player_id=? AND item_id IN ('ItemPureHalzinger','ItemPurePlutonicRock')"); $q->execute([$f['player']]);
    $pdo->commit();
} catch (Throwable $e) { if ($pdo->inTransaction()) $pdo->rollBack(); throw $e; }
""", fixture)
        SNAPSHOT.rename(SNAPSHOT.with_name(f"full-restore-fixture-restored-{fixture['morty']}.json"))
        print('Restored original deck and removed extra Morty, attack and fixture items; reload client')


if __name__ == '__main__':
    main()

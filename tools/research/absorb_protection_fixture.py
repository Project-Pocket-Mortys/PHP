"""Clone-only Android absorption fixture. All absorb selections use native UI.

No originals are updated, deleted, or put in a consumable species family. Raw
artifacts stay ignored. Cleanup reconstructs precisely one partial absorption
or no absorption, then removes only surviving fresh clones under row locks.
"""
import argparse
import base64
import copy
import json
import subprocess
import uuid
from pathlib import Path

import battle_item_fixture as items
import capture_battle_lifecycle as capture
import status_cure_fixture as guards

ROOT, sql = capture.ROOT, capture.sql


def snapshots(players):
    return {player: guards.snapshot(player) for player in players}


def locked(expected, changes):
    data = dict(accounts={p: dict(queries=guards.queries(p), expected=s) for p, s in expected.items()}, changes=changes)
    payload = base64.b64encode(json.dumps(data).encode()).decode()
    items.locked_php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; $x=json_decode(base64_decode('" + payload + "'),true);" + """
    $pdo->beginTransaction();
    try {
      foreach($x['accounts'] as $player=>$account) {
        foreach($account['queries'] as $k=>$query) {
          if($pdo->query($query.' FOR UPDATE')->fetchAll()!==$account['expected'][$k]) throw new RuntimeException('Concurrent change: '.$k);
        }
        $q=$pdo->prepare("SELECT battle_id FROM battles WHERE player_id=? AND state='ACTIVE' FOR UPDATE");
        $q->execute([$player]); if($q->fetch()) throw new RuntimeException('Active battle; abort');
      }
      foreach($x['changes'] as $change) {$q=$pdo->prepare($change[0]); $q->execute($change[1]);}
      $pdo->commit();
    } catch(Throwable $e) {if($pdo->inTransaction()) $pdo->rollBack(); throw $e;}
    """)


def native(f):
    raw = subprocess.run(capture.http.COMPOSE + ['exec', '-T', 'web', 'cat', '/tmp/pocket-research-http.jsonl'], cwd=ROOT, capture_output=True, text=True, check=True, timeout=20).stdout
    rows = []
    for line in raw.splitlines():
        row = json.loads(line)
        request = row.get('request')
        if isinstance(request, dict) and '/owned_morties/absorb' in row.get('path', '') and any(owned in json.dumps(request) for owned in f['clones'].values()):
            request.pop('session_id', None)
            rows.append(row)
    return rows


def expected_after(f, prepared, absorbed):
    expected = copy.deepcopy(prepared)
    if not absorbed:
        return expected
    account = expected[f['player']]
    donor = f['clones']['unlocked']
    account['morties'] = [m for m in account['morties'] if m['owned_morty_id'] != donor]
    account['attacks'] = [a for a in account['attacks'] if a['owned_morty_id'] != donor]
    next(m for m in account['morties'] if m['owned_morty_id'] == f['clones']['target'])['evolution_points'] = 1
    # The handler may serialize decks while removing storage donors. Reconstruct
    # that exact serialization; membership and order must remain identical.
    for deck in account['decks']:
        deck['owned_morty_ids'] = json.dumps(json.loads(deck['owned_morty_ids']), separators=(',', ':'))
    return expected


def validate_prepared(f, prepared):
    player, clones, before = f['player'], f['clones'], f['before']
    deck = next(d for d in before[player]['decks'] if d['deck_id'] == before[player]['user'][0]['active_deck_id'])
    primary = next(m for m in before[player]['morties'] if m['owned_morty_id'] == json.loads(deck['owned_morty_ids'])[0])
    source_attacks = [a for a in before[player]['attacks'] if a['owned_morty_id'] == primary['owned_morty_id']]
    assert prepared[f['players'][1]] == before[f['players'][1]]
    original = copy.deepcopy(prepared[player])
    original['morties'] = [m for m in original['morties'] if m['owned_morty_id'] not in clones.values()]
    original['attacks'] = [a for a in original['attacks'] if a['owned_morty_id'] not in clones.values()]
    assert original == before[player]
    assert len(prepared[player]['morties']) == len(before[player]['morties']) + 3
    for role, owned in clones.items():
        clone = next(m for m in prepared[player]['morties'] if m['owned_morty_id'] == owned)
        expected = {c: primary[c] for c in items.MC}
        # This schema stores lock flags as varchar, unlike integer counters.
        expected.update(owned_morty_id=owned, morty_id='MortyScruffy', is_locked=str(int(role == 'locked')), is_trading_locked='0', fight_pit_id=None, evolution_points=0)
        assert {c: clone[c] for c in items.MC} == expected
        actual_attacks = [a for a in prepared[player]['attacks'] if a['owned_morty_id'] == owned]
        assert [{c: a[c] for c in items.AC} for a in actual_attacks] == [dict({c: a[c] for c in items.AC}, owned_morty_id=owned) for a in source_attacks]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'finish-prepare', 'screen', 'record', 'cleanup', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--label', default='current')
    parser.add_argument('--absorbed', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    assert out.is_relative_to((ROOT / '.research').resolve())
    assert args.label.replace('-', '').replace('_', '').isalnum()
    assert capture.php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');") == 'db:http://localhost:8087'
    assert capture.adb('emu', 'avd', 'name').decode().splitlines()[0].strip() == 'PocketMortys_API30'
    out.mkdir(parents=True, exist_ok=True)
    manifest = out / 'fixture.json'
    if args.action == 'prepare':
        from export_item_effects import load_text
        rows, source = load_text('mpdata.assetbundle', 'MortyInfo')
        assert source['asset_sha256'] == '96072cc81591577cc31245c6f0ef7518d6ef1b5b5b47e261fd93163caba5ea99'
        assert source['bundle_sha256'] == 'f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413'
        assert source['path_id'] == -5656435499516812579
        species = next(r for r in rows if r['morty_id'] == 'MortyScruffy')
        assert species['evolution_req'] == 3
        assert not manifest.exists() and not (out / 'cleanup.json').exists()
        users = sql("SELECT username,player_id,state,active_deck_id FROM users WHERE username IN ('PMResearch01','PMResearch02') ORDER BY username")
        assert [u['username'] for u in users] == ['PMResearch01', 'PMResearch02']
        assert all(u['state'] == 'WORLD' for u in users)
        players = [u['player_id'] for u in users]
        assert all(str(uuid.UUID(p)) == p for p in players)
        before = snapshots(players)
        player = players[0]
        assert all(m['morty_id'] != 'MortyScruffy' for m in before[player]['morties']), 'Original same-family members would be consumable'
        deck = next(d for d in before[player]['decks'] if d['deck_id'] == users[0]['active_deck_id'])
        party = json.loads(deck['owned_morty_ids'])
        assert party
        primary = next(m for m in before[player]['morties'] if m['owned_morty_id'] == party[0])
        assert primary['morty_id'] == 'MortyDefault' and primary['hp'] == primary['hp_stat'] and primary['hp'] > 0
        assert primary['variant'] == 'Normal' and not primary['is_poisoned'] and not primary['is_paralysed']
        source_attacks = [a for a in before[player]['attacks'] if a['owned_morty_id'] == primary['owned_morty_id']]
        assert source_attacks
        assert set(items.MC) == set(primary) - {'id', 'created_at'}
        assert {c['Field'] for c in sql('SHOW COLUMNS FROM owned_attacks')} == set(items.AC) | {'id'}
        clones = {role: str(uuid.uuid4()) for role in ('target', 'locked', 'unlocked')}
        f = dict(player=player, players=players, clones=clones, before=before,
                 metadata=dict(source=source, species=species),
                 provenance='SYNTHETIC MortyScruffy storage clones: copied original MortyDefault complete stats/attacks, NOT generated Scruffy stats; evolution_points=0; one locked donor; native partial absorption only')
        items.save(manifest, f)
        changes = []
        for role, owned in clones.items():
            values = {'owned_morty_id': owned, 'morty_id': 'MortyScruffy', 'is_locked': int(role == 'locked'), 'is_trading_locked': 0, 'fight_pit_id': None, 'evolution_points': 0}
            me = ['?' if c in values else '`'+c+'`' for c in items.MC]
            ae = ['?' if c == 'owned_morty_id' else '`'+c+'`' for c in items.AC]
            changes += [('INSERT INTO owned_morties ('+','.join('`'+c+'`' for c in items.MC)+') SELECT '+','.join(me)+' FROM owned_morties WHERE id=? AND player_id=?', [values[c] for c in items.MC if c in values] + [primary['id'], player]), ('INSERT INTO owned_attacks ('+','.join('`'+c+'`' for c in items.AC)+') SELECT '+','.join(ae)+' FROM owned_attacks WHERE owned_morty_id=?', [owned, primary['owned_morty_id']])]
        locked(before, changes)
        prepared = snapshots(players)
        validate_prepared(f, prepared)
        items.save(out / 'prepared.json', prepared)
        print('Three synthetic storage clones prepared. Reload app; use native UI only.')
        return
    f = json.loads(manifest.read_text())
    if args.action == 'finish-prepare':
        assert not (out / 'prepared.json').exists() and not (out / 'cleanup.json').exists()
        prepared = snapshots(f['players'])
        validate_prepared(f, prepared)
        items.save(out / 'prepared.json', prepared)
        print('Interrupted preparation verified exactly; no database changes.')
        return
    if args.action == 'verify':
        assert (out / 'cleanup.json').exists()
        assert snapshots(f['players']) == f['before']
        items.save(out / (args.label+'-verified.json'), dict(exact_original_accounts=True, snapshots=snapshots(f['players'])))
        print('Both accounts exactly match baseline after reload.')
        return
    prepared = json.loads((out / 'prepared.json').read_text())
    current = snapshots(f['players'])
    if args.action == 'record':
        items.save(out / (args.label+'-accounts.json'), current)
        items.save(out / (args.label+'-http.json'), native(f))
    if args.action == 'cleanup':
        assert not (out / 'cleanup.json').exists()
        assert current == expected_after(f, prepared, args.absorbed), 'Unexplained mutation; preserve fixture'
        if args.absorbed:
            requests = [r for r in native(f) if r['status'] == 200 and 'error' not in r.get('response', {})]
            assert len(requests) == 1
            assert requests[0]['request']['owned_morty_id'] == f['clones']['target']
            assert requests[0]['request']['absorb_owned_morty_ids'] == [f['clones']['unlocked']]
        changes = []
        for role, owned in f['clones'].items():
            if role == 'unlocked' and args.absorbed:
                continue
            changes += [('DELETE FROM owned_attacks WHERE owned_morty_id=?', [owned]), ('DELETE FROM owned_morties WHERE player_id=? AND owned_morty_id=?', [f['player'], owned])]
        for deck in f['before'][f['player']]['decks']:
            # Restore formatting only after exact expected effects have matched.
            if next(d for d in current[f['player']]['decks'] if d['id'] == deck['id']) != deck:
                changes.append(('UPDATE decks SET owned_morty_ids=? WHERE id=? AND player_id=?', [deck['owned_morty_ids'], deck['id'], f['player']]))
        locked(current, changes)
        assert snapshots(f['players']) == f['before']
        items.save(out / 'cleanup.json', dict(exact_original_accounts=True, partial_absorptions=int(args.absorbed), only_fresh_clones_deleted=True))
        print('Original accounts exact; only surviving fresh clones removed under locks.')
        return
    if args.action in ('screen', 'record'):
        path = out / (args.label+'.png')
        assert not path.exists()
        path.write_bytes(capture.adb('exec-out', 'screencap', '-p'))


if __name__ == '__main__':
    main()

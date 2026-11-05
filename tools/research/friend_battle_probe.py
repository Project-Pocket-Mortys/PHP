"""Guarded Android missing friend-battle endpoint probe; no battle API synthesis.

prepare creates only a new accepted friend pair through existing social APIs.
The Battle tap must originate in Android. Raw snapshots and wire data stay ignored.
"""
import argparse
import json
import uuid
from pathlib import Path

import friend_lifecycle_fixture as friends
import battle_item_fixture as items
import capture_battle_lifecycle as capture
import probe_android_peers as peers

ROOT, sql = capture.ROOT, capture.sql


def save(path, value):
    if path.name == 'fixture.json' and path.exists():
        previous = json.loads(path.read_text(encoding='utf-8'))
        assert all(previous[key] == value[key]
            for key in ('before', 'players', 'before_battles', 'log_floor', 'names'))
        temporary = path.with_suffix('.next.json')
        items.save(temporary, value)
        temporary.replace(path)
    else:
        items.save(path, value)


def accounts():
    rows = sql("SELECT username,player_id,session_id,state FROM users WHERE username IN ('PMResearch01','PMResearch02') ORDER BY username")
    assert [r['username'] for r in rows] == list(friends.NAMES)
    assert all(str(uuid.UUID(r['player_id'])) == r['player_id'] and r['state'] == 'WORLD' for r in rows)
    assert all(isinstance(r['session_id'], str) and r['session_id'] for r in rows)
    return rows


def battle_rows(players):
    ids = "','".join(players)
    return sql(f"SELECT * FROM battles WHERE player_id IN ('{ids}') OR opponent_id IN ('{ids}') ORDER BY battle_id")


def check(f):
    current = friends.locked_snapshot(f['players'])
    pair = friends.guard(f, current)
    assert battle_rows(f['players']) == f['before_battles'], 'Battle rows changed; preserve evidence'
    return current, pair


def social(f, action, role, target, **extra):
    # Fresh session lookup; never print it or put it in a command-line argument.
    rows = accounts()
    assert [r['player_id'] for r in rows] == f['players']
    body = dict(session_id=rows[role]['session_id'], player_id=f['players'][target], **extra)
    f.setdefault('action_journal', []).append(dict(action=action, actor=f['players'][role],
        target=f['players'][target], extra=extra, phase='before-api'))
    save(f['_manifest'], {k: v for k, v in f.items() if k != '_manifest'})
    status, result = capture.http.post('/session/friend/' + action, body)
    f.setdefault('synthetic_setup_http', []).append(dict(action=action, actor=f['players'][role],
        target=f['players'][target], extra=extra, status=status, response=result))
    save(f['_manifest'], {k: v for k, v in f.items() if k != '_manifest'})
    assert status == 200, (action, status)
    assert not isinstance(result, dict) or 'error' not in result
    if action == 'request':
        assert result['player_id_a'] == f['players'][role] and result['player_id_b'] == f['players'][target]
        assert result['pending'] is True
    elif action == 'response':
        assert result == 1
    else:
        assert result['success'] is True and result['removed_friend_id'] == f['players'][target]
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('preflight', 'prepare', 'resume-setup', 'record', 'cleanup', 'verify'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--label', default='current')
    parser.add_argument('--screens', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    assert out.is_relative_to((ROOT / '.research').resolve())
    assert args.label.replace('-', '').replace('_', '').isalnum()
    assert capture.php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');") == 'db:http://localhost:8087'
    for role, (_, avd) in peers.DEVICES.items():
        assert peers.adb(role, 'emu', 'avd', 'name').splitlines()[0].strip() == avd
    manifest = out / 'fixture.json'
    if args.action in ('preflight', 'prepare'):
        assert not manifest.exists(), 'Use fresh output; preserve existing evidence'
        users = accounts()
        players = [r['player_id'] for r in users]
        before = friends.locked_snapshot(players)
        assert not friends.pair_rows(before['friend_rows'], players), 'Original pair exists; never remove it'
        original_battles = battle_rows(players)
        assert not any(r['state'] == 'ACTIVE' for r in original_battles)
        assert all(before[p+':user'][0]['shiny_potion_expires_at'] is None for p in players)
        if args.action == 'preflight':
            assert peers.adb('primary', 'shell', 'id', '-u').strip() == '0'
            peers.adb('primary', 'shell', 'test', '-x', '/system/bin/tcpdump')
            print('Isolated backend, both WORLD saves, absent original pair, devices and root tcpdump verified; no writes.')
            return
        out.mkdir(parents=True, exist_ok=True)
        f = dict(players=players, names=list(friends.NAMES), before=before,
            before_battles=original_battles, created_pair_id=None,
            log_floor=len(friends.log_lines()),
            provenance='Synthetic social request + recipient approval APIs only; native Android Battle tap required')
        save(manifest, f)  # Save originals before the first API mutation.
        f['_manifest'] = manifest
        social(f, 'request', 0, 1)
        _, pair = check(f)
        assert len(pair) == 1 and pair[0]['pending'] == 'true'
        assert pair[0]['player_id_a'] == players[0] and pair[0]['player_id_b'] == players[1]
        f['created_pair_id'] = pair[0]['id']
        f['created_pair'] = pair[0]
        save(manifest, {k: v for k, v in f.items() if k != '_manifest'})
        # Persist exact new row identity before recipient acceptance.
        social(f, 'response', 1, 0, approve=True)
        current, pair = check(f)
        assert len(pair) == 1 and pair[0]['id'] == f['created_pair_id'] and pair[0]['pending'] == 'false'
        f['accepted_pair'] = pair[0]
        save(manifest, {k: v for k, v in f.items() if k != '_manifest'})
        save(out / 'prepared-accounts.json', current)
        print('Originals retained; exact newly created pair recorded and accepted through synthetic social APIs.')
        return
    f = json.loads(manifest.read_text(encoding='utf-8'))
    f['_manifest'] = manifest
    current, pair = check(f)
    if args.action == 'resume-setup':
        assert f['created_pair_id'] is None and len(pair) == 1 and pair[0]['pending'] == 'true'
        candidates = [r for r in friends.native(f)['pair']
            if r['path'].rstrip('/') == '/session/friend/request' and r['status'] == 200
            and r['request'].get('player_id') == f['players'][1]
            and isinstance(r['response'], dict)
            and r['response'].get('player_id_a') == f['players'][0]
            and r['response'].get('player_id_b') == f['players'][1]
            and r['response'].get('_created') == pair[0]['created']]
        assert len(candidates) == 1, 'Require exact post-baseline request evidence before adopting new pair'
        f['created_pair_id'], f['created_pair'] = pair[0]['id'], pair[0]
        f['setup_recovery'] = dict(reason='Exclusive manifest save failed after request; exact API log verified',
            request_evidence=candidates[0])
        save(manifest, {k: v for k, v in f.items() if k != '_manifest'})
        social(f, 'response', 1, 0, approve=True)
        current, pair = check(f)
        assert len(pair) == 1 and pair[0]['id'] == f['created_pair_id'] and pair[0]['pending'] == 'false'
        f['accepted_pair'] = pair[0]
        save(manifest, {k: v for k, v in f.items() if k != '_manifest'})
        save(out / 'prepared-accounts.json', current)
        print('Exact new pending pair recovered from API evidence and accepted; guards pass.')
    elif args.action == 'cleanup':
        assert f['created_pair_id'] is not None, 'Cannot delete any untracked relationship'
        if pair:
            assert pair == [f.get('accepted_pair', f['created_pair'])], 'Pair changed; refuse cleanup'
            assert pair[0]['id'] == f['created_pair_id']
            social(f, 'remove', 0, 1)
            current, pair = check(f)
        assert not pair and current == friends.baseline(f)
        save(out / 'cleanup.json', dict(original_saves_and_friend_rows_match=True,
            created_pair_id=f['created_pair_id'], snapshots=current))
        print('Only the exact created pair removed via social API; originals match under locks.')
    elif args.action == 'verify':
        assert (out / 'cleanup.json').exists()
        assert not pair and current == friends.baseline(f)
        save(out / (args.label+'-verified.json'), dict(original_saves_and_friend_rows_match=True,
            no_battle_rows_changed=True, snapshots=current))
        print('Original saves, all original touching friend rows and battle rows match; both WORLD.')
    else:
        target = out / (args.label+'-accounts.json')
        assert not target.exists(), 'Preserve records'
        save(target, current)
        save(out / (args.label+'-pair.json'), pair)
        save(out / (args.label+'-http.json'), friends.native(f))
        print('Account save, original friends and battle-row guards passed.')
    if args.screens:
        for role in peers.DEVICES:
            target = out / (args.label+'-'+role+'.png')
            assert not target.exists()
            target.write_bytes(peers.adb(role, 'exec-out', 'screencap', '-p', binary=True, timeout=30))


if __name__ == '__main__':
    main()

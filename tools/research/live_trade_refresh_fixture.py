"""Append-only read-only live refresh receipts anchored after the accepted swap.

Never prepares, resets, or mutates accounts. Failed observations halt the chain.
"""
import argparse
import datetime
import hashlib
import json
import re
import subprocess
import sys

from native_trade_fixture import ACCOUNTS, ROOT, safe_path, write_new
from native_trade_offer_fixture import PHP
from native_trade_decision_fixture import (TABLES, USER_DYNAMICS, need, rows_by_id,
                                           pair_anchor, parent_row, offer_row, presence)

STAGES = ('parent', 'offer', 'rejected', 'accepted')
ALL_TABLES = TABLES | {'trade_refresh_notifications'}
EVENTS = {'offer': 'trade:offer-submit', 'rejected': 'trade:offer-rejected',
          'accepted': 'trade:offer-accepted'}
ANCHOR = ROOT / '.research/emulator/trade-refresh-events-20261107/final-guard.json'
OUTPUT_ROOT = ROOT / '.research/emulator/live-trade-refresh-20261107'


def database():
    # Extend the existing audited SELECT-only capture in its SAME consistent
    # read-only transaction, without changing the old fixture's source/API.
    needle = "    $pdo->commit(); echo json_encode(['snapshot'=>$snapshot],JSON_THROW_ON_ERROR);"
    need(PHP.count(needle) == 1, 'Read-only capture source changed')
    source = PHP.replace(needle, '''    $snapshot['trade_refresh_notifications']=rows("SELECT player_id,CAST(revision AS CHAR) AS revision,event_name FROM trade_refresh_notifications WHERE player_id IN ($ps) ORDER BY BINARY player_id",$players);
''' + needle)
    result = subprocess.run(
        ['docker', 'compose', '-f', str(ROOT / 'compose.research.yaml'),
         'exec', '-T', 'web', 'php', '-r', source], cwd=ROOT,
        input=json.dumps({'action': 'capture'}), text=True,
        capture_output=True, encoding='utf-8', timeout=60)
    need(result.returncode == 0, 'Private live snapshot rejected')
    return json.loads(result.stdout)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def notifications(snapshot, anchor):
    rows = snapshot['trade_refresh_notifications']
    result = {}
    players = {a['player_id'] for a in anchor['accounts'].values()}
    for row in rows:
        need(set(row) == {'player_id', 'revision', 'event_name'})
        need(row['player_id'] in players and row['player_id'] not in result)
        need(type(row['revision']) is str and re.fullmatch('[1-9][0-9]*', row['revision']) is not None
             and int(row['revision']) <= 18446744073709551615)
        need(row['event_name'] in EVENTS.values())
        result[row['player_id']] = row
    return result


def protected(before, snapshot, anchor, accepted=False):
    """Compare exact physical/protected rows; isolate bounded room dynamics."""
    need(set(snapshot) == ALL_TABLES)
    actual, expected = rows_by_id(snapshot['owned_morties']), rows_by_id(before['owned_morties'])
    need(len(actual) == 4 and set(actual) == set(expected))
    swap = {anchor['accounts'][a]['spare_owned_morty_id']:
            anchor['accounts'][b]['player_id'] for a, b in
            (('PMTrade01', 'PMTrade02'), ('PMTrade02', 'PMTrade01'))}
    for row_id, row in expected.items():
        target = dict(row)
        if accepted and row['owned_morty_id'] in swap:
            target['player_id'] = swap[row['owned_morty_id']]
        need(actual[row_id] == target, 'Protected physical inventory changed')
    for table in ('owned_attacks', 'decks', 'owned_items', 'friend_list'):
        need(rows_by_id(before[table]) == rows_by_id(snapshot[table]), 'Protected table changed')
    need(not snapshot['friend_battle_memberships'])
    original, users = rows_by_id(before['users']), rows_by_id(snapshot['users'])
    need(set(original) == set(users) and len(users) == 2)
    dynamics = {}
    for uid, user in users.items():
        need(set(user) == set(original[uid]))
        excluded = USER_DYNAMICS | {'expiry_trade'}
        need({k: v for k, v in user.items() if k not in excluded} ==
             {k: v for k, v in original[uid].items() if k not in excluded}, 'Protected user changed')
        need(isinstance(user['session_id'], str) and bool(user['session_id']))
        dynamics[user['username']] = sorted(k for k in USER_DYNAMICS if user[k] != original[uid][k])
    need(len({u['session_id'] for u in users.values()}) == 2)
    old_events = [r for r in before['event_queue'] if not presence(r, anchor)]
    events = [r for r in snapshot['event_queue'] if not presence(r, anchor)]
    need(rows_by_id(old_events) == rows_by_id(events), 'Nonpresence event changed')
    return dynamics


def validate_baseline(document):
    need(document.get('version') == 1 and document.get('accounts') == list(ACCOUNTS)
         and document.get('private') is True and document.get('action') == 'snapshot')
    source = document['accepted_anchor']
    need(re.fullmatch('[0-9a-f]{64}', source['sha256']) is not None)
    need(source['document'].get('private') is True)
    comparison = source['document'].get('comparison', {})
    need(comparison.get('passed') is True and comparison.get('stage') == 'accepted'
         and comparison.get('exact_spare_swap') is True
         and comparison.get('protected_raw_rows_preserved') is True,
         'Anchor must certify the prior accepted swap')
    old = source['document']['snapshot']
    need(set(old) == TABLES and not old['trades'] and not old['trade_offers']
         and len(old['completed_trades']) == 1 and not old['friend_battle_memberships'])
    anchor = pair_anchor(old)
    need(document['identity'] == anchor and pair_anchor(document['snapshot']) == anchor,
         'Post-accept owner/party identity changed')
    protected(old, document['snapshot'], anchor)
    before = document['snapshot']
    need(not before['trades'] and not before['trade_offers'])
    need(rows_by_id(before['completed_trades']) == rows_by_id(old['completed_trades']))
    for user in before['users']:
        old_user = next(u for u in old['users'] if u['id'] == user['id'])
        need(user['expiry_trade'] == old_user['expiry_trade'], 'Baseline expiry reset')
    n = notifications(before, anchor)
    player = anchor['accounts']['PMTrade01']['player_id']
    need(n == {player: {'player_id': player, 'revision': '1', 'event_name': EVENTS['offer']}},
         'Synthetic baseline publication changed')
    return anchor


def compare_snapshot(baseline, snapshot, stage, previous=None):
    anchor = validate_baseline(baseline)
    before = baseline['snapshot']
    prior = previous['snapshot'] if previous else before
    prior_stage = previous['stage'] if previous else 'baseline'
    transitions = {'baseline': ('parent',), 'parent': ('parent', 'offer'),
                   'offer': ('offer', 'rejected', 'accepted'),
                   'rejected': ('rejected', 'parent', 'offer'), 'accepted': ()}
    need(stage in transitions[prior_stage], 'Unexpected live trade transition')
    dynamics = protected(before, snapshot, anchor, accepted=stage == 'accepted')
    new_parent = not prior['trades'] and bool(snapshot['trades'])
    for user in snapshot['users']:
        old_user = next(u for u in prior['users'] if u['id'] == user['id'])
        if new_parent and user['username'] == 'PMTrade02':
            expiry = datetime.datetime.fromisoformat(user['expiry_trade'].replace('Z', '+00:00'))
            created = datetime.datetime.fromisoformat(snapshot['trades'][0]['created_at']).replace(tzinfo=datetime.UTC)
            need(abs((expiry - created).total_seconds() - 3600) <= 5, 'Unexpected new-parent expiry')
        else:
            need(user['expiry_trade'] == old_user['expiry_trade'], 'Parent expiry was not retained')
    old_completed, completed = rows_by_id(before['completed_trades']), rows_by_id(snapshot['completed_trades'])
    need(all(completed.get(k) == v for k, v in old_completed.items()), 'Prior completion changed')
    if stage != 'accepted':
        need(completed == old_completed, 'Unexpected completion')
        parent = parent_row(snapshot, anchor)
        if prior['trades']:
            need(snapshot['trades'] == prior['trades'], 'Parent row changed')
        if stage == 'offer':
            offer_row(snapshot, anchor, parent)
            if prior['trade_offers']:
                need(snapshot['trade_offers'] == prior['trade_offers'], 'Offer changed')
        else:
            need(not snapshot['trade_offers'])
            if stage == 'rejected':
                need(previous is not None and prior_stage in ('offer', 'rejected'))
                if prior_stage == 'offer':
                    offer_row(prior, anchor, parent)
    else:
        parent = parent_row(prior, anchor)
        offer = offer_row(prior, anchor, parent)
        need(not snapshot['trades'] and not snapshot['trade_offers'] and len(completed) == 2)
        added, = [r for k, r in completed.items() if k not in old_completed]
        need(set(added) == {'id', 'completed_trade_id', 'request_player_id', 'offer_player_id',
             'morty_request_id', 'morty_offer_id', 'trade_request_id', 'trade_offer_id', 'is_free_trade', 'fulfilled_at'})
        for key, value in {'request_player_id': parent['player_id'], 'offer_player_id': offer['player_id'],
             'morty_request_id': parent['morty_trade_id'], 'morty_offer_id': offer['morty_offer_id'],
             'trade_request_id': parent['trade_id'], 'trade_offer_id': offer['trade_offer_id'],
             'is_free_trade': parent['is_free_trade']}.items():
            need(added[key] == value, 'Unexpected completion link')
        need(isinstance(added['completed_trade_id'], str) and bool(added['completed_trade_id'])
             and added['completed_trade_id'] != next(iter(old_completed.values()))['completed_trade_id'])
        need(isinstance(added['fulfilled_at'], str) and bool(added['fulfilled_at']))
    old_n, n = notifications(prior, anchor), notifications(snapshot, anchor)
    publication = None
    if stage in EVENTS and stage != prior_stage:
        recipient_account = 'PMTrade02' if stage == 'offer' else 'PMTrade01'
        actor_account = 'PMTrade01' if stage == 'offer' else 'PMTrade02'
        recipient = anchor['accounts'][recipient_account]['player_id']
        revision = old_n.get(recipient, {}).get('revision', '0')
        expected = dict(old_n)
        expected[recipient] = {'player_id': recipient, 'revision': str(int(revision) + 1), 'event_name': EVENTS[stage]}
        need(n == expected, 'Expected exact recipient-only notification increment')
        publication = {'recipient': recipient, 'actor': anchor['accounts'][actor_account]['player_id'],
                       'event_name': EVENTS[stage], 'previous_revision': revision,
                       'revision': expected[recipient]['revision']}
    else:
        need(n == old_n, 'Unexpected notification publication')
    return {'passed': True, 'stage': stage, 'protected_raw_rows_preserved': True,
            'existing_completion_preserved': True, 'exact_spare_swap': stage == 'accepted',
            'user_dynamic_columns_changed': dynamics, 'notification': publication,
            'free_parent_expiry_change_allowed': new_parent}


def verify_history(baseline, baseline_hash, entries):
    validate_baseline(baseline)
    previous, previous_hash, labels = None, baseline_hash, set()
    for sequence, entry in enumerate(entries, 1):
        document = entry['document']
        need(document.get('version') == 1 and document.get('accounts') == list(ACCOUNTS)
             and document.get('private') is True and document.get('action') == 'observe'
             and document.get('identity') == baseline['identity'])
        need(document['sequence'] == sequence and document['baseline_sha256'] == baseline_hash
             and document['previous_sha256'] == previous_hash, 'Broken append-only history')
        need(document['label'] not in labels and re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', document['label']))
        labels.add(document['label'])
        need(document['comparison'].get('passed') is True, 'Failed observation halts the chain')
        need(document['comparison'] == compare_snapshot(baseline, document['snapshot'], document['stage'], previous))
        previous, previous_hash = document, entry['sha256']
    return previous, previous_hash


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('snapshot', 'observe'))
    parser.add_argument('--output', required=True)
    parser.add_argument('--anchor')
    parser.add_argument('--label')
    parser.add_argument('--stage', choices=STAGES)
    args = parser.parse_args()
    output = safe_path(args.output, fresh=args.action == 'snapshot')
    need(output.is_relative_to(OUTPUT_ROOT) and output != OUTPUT_ROOT)
    if args.action == 'snapshot':
        need(args.anchor and not args.label and not args.stage)
        path = safe_path(args.anchor)
        need(path == ANCHOR, 'Only the immutable accepted-state anchor is allowed')
        anchor = {'document': json.loads(path.read_text(encoding='utf-8')), 'sha256': digest(path)}
        output.mkdir(parents=True, exist_ok=False)
        destination, marker = output / 'baseline.json', output / 'snapshot-attempt.json'
    else:
        need(not args.anchor and args.stage and args.label and re.fullmatch('[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', args.label))
        baseline_path = safe_path(output / 'baseline.json')
        baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
        need(baseline['accepted_anchor']['sha256'] == digest(ANCHOR), 'Accepted-state anchor bytes changed')
        need(baseline['accepted_anchor']['document'] == json.loads(ANCHOR.read_text(encoding='utf-8')),
             'Embedded accepted-state anchor changed')
        entries = []
        for path in output.glob('observe-*.json'):
            if path.name.endswith('-attempt.json'):
                continue
            document = json.loads(safe_path(path).read_text(encoding='utf-8'))
            need(path.name == 'observe-' + document['label'] + '.json')
            entries.append({'document': document, 'sha256': digest(path)})
        # A failed read has only its attempt marker. It also halts the chain;
        # switching labels cannot conceal an unsuccessful observation.
        receipts = {'observe-' + e['document']['label'] + '.json' for e in entries}
        attempts = {p.name.removesuffix('-attempt.json') + '.json'
                    for p in output.glob('observe-*-attempt.json')}
        need(receipts == attempts, 'Unresolved observation attempt halts the chain')
        entries.sort(key=lambda e: e['document']['sequence'])
        previous, previous_hash = verify_history(baseline, digest(baseline_path), entries)
        destination, marker = output / f'observe-{args.label}.json', output / f'observe-{args.label}-attempt.json'
    write_new(safe_path(marker), {'action': args.action, 'private': True})
    need(not safe_path(destination).exists())
    document = {'version': 1, 'accounts': list(ACCOUNTS), 'private': True,
                'action': args.action, 'created_utc': datetime.datetime.now(datetime.UTC).isoformat(), **database()}
    if args.action == 'snapshot':
        write_new(safe_path(output / 'snapshot-raw.json'), document)
        document.update(identity=pair_anchor(document['snapshot']), accepted_anchor=anchor)
        validate_baseline(document)
    else:
        document.update(identity=baseline['identity'], stage=args.stage, label=args.label,
                        sequence=len(entries) + 1, baseline_sha256=digest(baseline_path), previous_sha256=previous_hash)
        try:
            document['comparison'] = compare_snapshot(baseline, document['snapshot'], args.stage, previous)
        except Exception:
            document['comparison'] = {'passed': False, 'private_details_suppressed': True}
            write_new(safe_path(destination), document)
            raise
    write_new(safe_path(destination), document)
    print(f'{args.action}: OK; private read-only live refresh receipt saved')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Live refresh observation rejected; private details suppressed.', file=sys.stderr)
        sys.exit(1)

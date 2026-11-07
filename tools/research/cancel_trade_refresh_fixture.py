"""Append-only SELECT-only cancellation receipts after the two accepted swaps.

PMTrade01 is requester/primary; PMTrade02 is offerer/peer. These receipts
preserve the fixed final guard and never prepare, reset, or mutate accounts.
The peer deliberately cold logs in between cancellation phases; permitted
session/presence dynamics do not certify uninterrupted peer transport.
"""
import argparse
import datetime
import json
import re
import sys

from native_trade_fixture import ACCOUNTS, ROOT, safe_path, write_new
from native_trade_decision_fixture import need, rows_by_id, pair_anchor as old_pair_anchor
from live_trade_refresh_fixture import ALL_TABLES, database, digest, notifications, protected

STAGES = ('parent', 'offer', 'offer-cancelled', 'parent-cancelled')
ANCHOR = ROOT / '.research/emulator/live-trade-refresh-20261107/final-guard.json'
OUTPUT_ROOT = ROOT / '.research/emulator/trade-cancellation-refresh-20261107'


def pair_anchor(snapshot):
    anchor = old_pair_anchor(snapshot)
    anchor['roles'] = {'requester': 'PMTrade01', 'offerer': 'PMTrade02'}
    return anchor


def parent_row(snapshot, anchor):
    need(len(snapshot['trades']) == 1, 'Exactly one dedicated parent required')
    parent = snapshot['trades'][0]
    owner = anchor['accounts']['PMTrade01']
    need(parent['player_id'] == owner['player_id']
         and parent['morty_trade_id'] == owner['spare_owned_morty_id']
         and parent['requested_morty_id'] == 'any' and parent['request_variant'] == 'Normal'
         and type(parent['is_free_trade']) is int and parent['is_free_trade'] == 1)
    need(isinstance(parent['trade_id'], str) and bool(parent['trade_id']))
    return parent


def offer_row(snapshot, anchor, parent):
    need(len(snapshot['trade_offers']) == 1, 'Exactly one dedicated offer required')
    offer = snapshot['trade_offers'][0]
    owner = anchor['accounts']['PMTrade02']
    need(offer['player_id'] == owner['player_id'] and offer['trade_id'] == parent['trade_id']
         and offer['morty_offer_id'] == owner['spare_owned_morty_id'])
    need(isinstance(offer['trade_offer_id'], str) and bool(offer['trade_offer_id']))
    return offer


def timestamp(value):
    parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    return parsed.replace(tzinfo=datetime.UTC) if parsed.tzinfo is None else parsed


def validate_baseline(document):
    need(document.get('version') == 1 and document.get('accounts') == list(ACCOUNTS)
         and document.get('private') is True and document.get('action') == 'snapshot')
    source = document['accepted_anchor']
    need(re.fullmatch('[0-9a-f]{64}', source['sha256']) is not None)
    old_document = source['document']
    comparison = old_document.get('comparison', {})
    need(old_document.get('private') is True and comparison.get('passed') is True
         and comparison.get('stage') == 'accepted' and comparison.get('exact_spare_swap') is True
         and comparison.get('protected_raw_rows_preserved') is True
         and comparison.get('existing_completion_preserved') is True,
         'Anchor must certify the second accepted swap')
    old, snapshot = old_document['snapshot'], document['snapshot']
    need(set(old) == ALL_TABLES and not old['trades'] and not old['trade_offers']
         and len(old['completed_trades']) == 2 and not old['friend_battle_memberships'])
    anchor = pair_anchor(old)
    need(document['identity'] == anchor and pair_anchor(snapshot) == anchor,
         'Accepted owners or party identity changed')
    protected(old, snapshot, anchor)
    need(not snapshot['trades'] and not snapshot['trade_offers'])
    need(rows_by_id(snapshot['completed_trades']) == rows_by_id(old['completed_trades']))
    for user in snapshot['users']:
        original = next(u for u in old['users'] if u['id'] == user['id'])
        need(user['expiry_trade'] == original['expiry_trade'], 'Baseline expiry reset')
    expected = {}
    for account, revision, event in [('PMTrade01', '3', 'trade:offer-accepted'),
                                     ('PMTrade02', '2', 'trade:offer-submit')]:
        player = anchor['accounts'][account]['player_id']
        expected[player] = {'player_id': player, 'revision': revision, 'event_name': event}
    need(notifications(old, anchor) == expected and notifications(snapshot, anchor) == expected,
         'Fixed accepted-state notification baseline changed')
    return anchor


def compare_snapshot(baseline, snapshot, stage, previous=None):
    anchor = validate_baseline(baseline)
    before = baseline['snapshot']
    prior = previous['snapshot'] if previous else before
    prior_stage = previous['stage'] if previous else 'baseline'
    transitions = {'baseline': ('parent',), 'parent': ('parent', 'offer'),
                   'offer': ('offer', 'offer-cancelled', 'parent-cancelled'),
                   'offer-cancelled': ('offer-cancelled', 'offer'),
                   'parent-cancelled': ('parent-cancelled',)}
    need(stage in transitions[prior_stage], 'Unexpected cancellation transition')
    dynamics = protected(before, snapshot, anchor)
    need(rows_by_id(snapshot['completed_trades']) == rows_by_id(before['completed_trades']),
         'Both accepted completions must remain unchanged')
    new_parent = prior_stage == 'baseline'
    for user in snapshot['users']:
        old = next(u for u in prior['users'] if u['id'] == user['id'])
        if new_parent and user['username'] == 'PMTrade01':
            parent = parent_row(snapshot, anchor)
            created = timestamp(parent['created_at'])
            need(old['expiry_trade'] is None or timestamp(old['expiry_trade']) <= created,
                 'Existing requester cooldown must expire naturally')
            need(abs((timestamp(user['expiry_trade']) - created).total_seconds() - 3600) <= 5,
                 'Unexpected new-parent expiry')
        else:
            need(user['expiry_trade'] == old['expiry_trade'], 'Parent expiry was not retained')
    if stage == 'parent-cancelled':
        need(not snapshot['trades'] and not snapshot['trade_offers'], 'Cancelled parent or child survives')
        if prior_stage == 'offer':
            offer_row(prior, anchor, parent_row(prior, anchor))
    else:
        parent = parent_row(snapshot, anchor)
        if prior['trades']:
            need(snapshot['trades'] == prior['trades'], 'Parent row changed')
        if stage == 'offer':
            offer_row(snapshot, anchor, parent)
            if prior['trade_offers']:
                need(snapshot['trade_offers'] == prior['trade_offers'], 'Offer row changed')
        else:
            need(not snapshot['trade_offers'])
            if stage == 'offer-cancelled' and prior_stage == 'offer':
                offer_row(prior, anchor, parent)
    old_n, current = notifications(prior, anchor), notifications(snapshot, anchor)
    publication = None
    if stage != prior_stage and stage != 'parent':
        recipient_account = 'PMTrade02' if stage == 'parent-cancelled' else 'PMTrade01'
        actor_account = 'PMTrade01' if stage == 'parent-cancelled' else 'PMTrade02'
        recipient = anchor['accounts'][recipient_account]['player_id']
        actor = anchor['accounts'][actor_account]['player_id']
        event = 'trade:offer-rejected' if stage == 'parent-cancelled' else 'trade:offer-submit'
        revision = old_n[recipient]['revision']
        expected = dict(old_n)
        expected[recipient] = {'player_id': recipient, 'revision': str(int(revision) + 1), 'event_name': event}
        need(current == expected, 'Expected exact recipient-only notification increment')
        publication = {'recipient': recipient, 'actor': actor, 'event_name': event,
                       'previous_revision': revision, 'revision': expected[recipient]['revision']}
    else:
        need(current == old_n, 'Unexpected notification publication')
    return {'passed': True, 'stage': stage, 'protected_raw_rows_preserved': True,
            'both_existing_completions_preserved': True, 'ownership_unchanged': True,
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
        need(path == ANCHOR, 'Only the immutable two-completion anchor is allowed')
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
    print(f'{args.action}: OK; private read-only cancellation receipt saved')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Cancellation observation rejected; private details suppressed.', file=sys.stderr)
        sys.exit(1)

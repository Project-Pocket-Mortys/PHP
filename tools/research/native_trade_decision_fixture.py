"""Private append-only, read-only receipts for the fixed native trading pair.

The old offer receipt remains owner-bound. This separate observer permits only
the exact two spare physical rows to exchange owners at an accepted decision.
"""
import argparse
import datetime
import hashlib
import json
import re
import sys

from native_trade_fixture import ACCOUNTS, ROOT, safe_path, write_new
from native_trade_offer_fixture import baseline_identity, database, identity


STAGES = ('initial', 'parent', 'offer', 'rejected', 'accepted')
USER_DYNAMICS = frozenset(('session_id', 'room_id', 'state', 'last_seen',
                           'last_event_id', 'room_membership_generation'))
PRESENCE_EVENTS = frozenset(('room:user-added', 'room:user-removed', 'room:user-state-changed'))
PRESENCE_FIELDS = frozenset(('id', 'created_at', 'updated', 'room_id', 'event_name', 'player_id', 'state'))
TABLES = frozenset(('users', 'owned_morties', 'owned_attacks', 'decks', 'owned_items',
                   'trades', 'trade_offers', 'completed_trades', 'friend_list',
                   'event_queue', 'friend_battle_memberships'))


def need(condition, message='Decision receipt invariant rejected'):
    if not condition:
        raise ValueError(message)


def rows_by_id(rows):
    need(isinstance(rows, list))
    result = {row['id']: row for row in rows}
    need(len(result) == len(rows), 'Duplicate physical row')
    return result


def pair_anchor(snapshot):
    old = identity(snapshot)
    result = {'roles': {'requester': 'PMTrade02', 'offerer': 'PMTrade01'}, 'accounts': {},
              'physical_morties': sorted(snapshot['owned_morties'], key=lambda r: str(r['id']))}
    for account in ACCOUNTS:
        owner = old[account]['player_id']
        user = next(u for u in snapshot['users'] if u['username'] == account)
        decks = [d for d in snapshot['decks'] if d['player_id'] == owner]
        need(len(decks) == 1 and str(decks[0]['deck_id']) == '0' and str(user['active_deck_id']) == '0')
        party = json.loads(decks[0]['owned_morty_ids'])
        owned = {m['owned_morty_id'] for m in snapshot['owned_morties'] if m['player_id'] == owner}
        need(isinstance(party, list) and len(party) == 1 and party[0] in owned)
        spare, = owned - set(party)
        result['accounts'][account] = {'user_id': old[account]['user_id'], 'player_id': owner,
            'starter_owned_morty_id': party[0], 'spare_owned_morty_id': spare}
    return result


def parent_row(snapshot, anchor):
    need(len(snapshot['trades']) == 1, 'Exactly one dedicated parent required')
    parent = snapshot['trades'][0]
    requester = anchor['accounts']['PMTrade02']
    need(parent['player_id'] == requester['player_id']
         and parent['morty_trade_id'] == requester['spare_owned_morty_id']
         and parent['requested_morty_id'] == 'any' and parent['request_variant'] == 'Normal'
         and type(parent['is_free_trade']) is int and parent['is_free_trade'] == 1)
    need(isinstance(parent['trade_id'], str) and bool(parent['trade_id']))
    return parent


def offer_row(snapshot, anchor, parent):
    need(len(snapshot['trade_offers']) == 1, 'Exactly one dedicated offer required')
    offer = snapshot['trade_offers'][0]
    offerer = anchor['accounts']['PMTrade01']
    need(offer['player_id'] == offerer['player_id'] and offer['trade_id'] == parent['trade_id']
         and offer['morty_offer_id'] == offerer['spare_owned_morty_id'])
    need(isinstance(offer['trade_offer_id'], str) and bool(offer['trade_offer_id']))
    return offer


def presence(row, anchor):
    if row.get('event_name') not in PRESENCE_EVENTS:
        return False
    need(row.get('player_id') in {a['player_id'] for a in anchor['accounts'].values()})
    # Only native room presence columns vary. Reject battle/inventory contents
    # concealed in a row whose event name happens to be a presence event.
    for key, value in row.items():
        if key in PRESENCE_FIELDS:
            continue
        if key == 'zone_id':
            need(value in (None, '[1,1]'))
        elif key == 'shiny_if_potion':
            need(value in (None, 0, '0', 'false'))
        else:
            need(value is None, 'Unexpected presence event payload')
    return True


def validate_baseline(document):
    need(document.get('version') == 1 and document.get('accounts') == list(ACCOUNTS)
         and document.get('private') is True and document.get('action') == 'snapshot')
    old = document['old_pair_baseline']
    old_identity = baseline_identity(old['document'])
    need(old['identity'] == old_identity)
    need(re.fullmatch('[0-9a-f]{64}', old['sha256']) is not None)
    anchor = pair_anchor(document['snapshot'])
    need(document['identity'] == anchor and identity(document['snapshot']) == old_identity,
         'Old pair baseline identities changed')
    # Preserve both original fixture anchors and the newly observed state.
    for table in ('owned_morties', 'owned_attacks', 'decks', 'owned_items', 'friend_list'):
        need(rows_by_id(document['snapshot'][table]) == rows_by_id(old['document']['snapshot'][table]),
             'Original pair fixture state changed')
    protected_user = lambda user: {k: v for k, v in user.items()
                                   if k not in USER_DYNAMICS and k != 'expiry_trade'}
    old_users = rows_by_id(old['document']['snapshot']['users'])
    for user in document['snapshot']['users']:
        need(protected_user(user) == protected_user(old_users[user['id']]),
             'Original pair protected user state changed')
    need(not document['snapshot']['trades'] and not document['snapshot']['trade_offers']
         and not document['snapshot']['completed_trades'])
    need(not document['snapshot']['friend_battle_memberships'])
    need(set(document['snapshot']) == TABLES)
    return anchor


def compare_snapshot(baseline, snapshot, stage, previous=None):
    """Pure fail-closed comparison. Previous is the last successful raw receipt."""
    need(stage in STAGES)
    anchor = validate_baseline(baseline)
    before = baseline['snapshot']
    prior = previous['snapshot'] if previous else before
    transitions = {'initial': ('initial', 'parent'), 'parent': ('parent', 'offer'),
                   'offer': ('offer', 'rejected', 'accepted'),
                   'rejected': ('rejected', 'parent', 'offer'), 'accepted': ()}
    need(stage in transitions[previous['stage'] if previous else 'initial'], 'Unexpected decision stage transition')
    need(set(snapshot) == TABLES)
    expected = rows_by_id(before['owned_morties'])
    actual = rows_by_id(snapshot['owned_morties'])
    need(set(actual) == set(expected) and len(actual) == 4)
    swap = {anchor['accounts']['PMTrade01']['spare_owned_morty_id']: anchor['accounts']['PMTrade02']['player_id'],
            anchor['accounts']['PMTrade02']['spare_owned_morty_id']: anchor['accounts']['PMTrade01']['player_id']}
    for physical_id, row in expected.items():
        target = dict(row)
        if stage == 'accepted' and row['owned_morty_id'] in swap:
            target['player_id'] = swap[row['owned_morty_id']]
        need(actual[physical_id] == target, 'Unexpected physical inventory change')
    for account in ACCOUNTS:
        owner = anchor['accounts'][account]['player_id']
        need(sum(m['player_id'] == owner for m in actual.values()) == 2)
    for table in ('owned_attacks', 'owned_items', 'decks', 'friend_list'):
        need(rows_by_id(snapshot[table]) == rows_by_id(before[table]), 'Protected table changed: ' + table)
    need(not snapshot['friend_battle_memberships'])
    users = rows_by_id(snapshot['users'])
    original_users = rows_by_id(before['users'])
    need(set(users) == set(original_users) and len(users) == 2)
    dynamics = {}
    new_parent = not before['trades'] and bool(snapshot['trades'])
    for uid, user in users.items():
        expected_user = original_users[uid]
        need(set(user) == set(expected_user))
        changed = sorted(k for k in user if user[k] != expected_user[k])
        dynamics[user['username']] = [k for k in changed if k in USER_DYNAMICS]
        for key in changed:
            if key in USER_DYNAMICS:
                continue
            if key == 'expiry_trade' and user['username'] == 'PMTrade02' and new_parent:
                expiry = datetime.datetime.fromisoformat(user[key].replace('Z', '+00:00'))
                created = datetime.datetime.fromisoformat(snapshot['trades'][0]['created_at']).replace(tzinfo=datetime.UTC)
                need(abs((expiry - created).total_seconds() - 3600) <= 5, 'Unexpected free-parent expiry')
                continue
            # After the free parent is gone acceptance retains that exact expiry.
            if key == 'expiry_trade' and user['username'] == 'PMTrade02' and not before['trades'] and previous:
                prior_user = next(u for u in prior['users'] if u['id'] == uid)
                need(user[key] == prior_user[key])
                continue
            need(False, 'Protected user column changed')
        need(isinstance(user['session_id'], str) and bool(user['session_id']))
        if previous and prior['trades']:
            prior_user = next(u for u in prior['users'] if u['id'] == uid)
            need(user['expiry_trade'] == prior_user['expiry_trade'], 'Parent expiry changed after creation')
    need(len({u['session_id'] for u in users.values()}) == 2)
    base_events = [r for r in before['event_queue'] if not presence(r, anchor)]
    current_events = [r for r in snapshot['event_queue'] if not presence(r, anchor)]
    need(rows_by_id(base_events) == rows_by_id(current_events), 'Nonpresence events changed')
    parent = None
    if stage == 'initial':
        need(not snapshot['trades'] and not snapshot['trade_offers'] and not snapshot['completed_trades'])
    elif stage in ('parent', 'offer', 'rejected'):
        parent = parent_row(snapshot, anchor)
        if prior['trades']:
            need(snapshot['trades'] == prior['trades'], 'Parent changed')
        if before['trades']:
            need(snapshot['trades'] == before['trades'], 'Original parent changed')
        need(not snapshot['completed_trades'])
        if stage == 'offer':
            offer_row(snapshot, anchor, parent)
            if prior['trade_offers']:
                need(snapshot['trade_offers'] == prior['trade_offers'])
        else:
            need(not snapshot['trade_offers'])
            if stage == 'rejected':
                need(previous is not None and previous['stage'] == 'offer')
                offer_row(prior, anchor, parent)
    else:
        need(previous is not None and previous['stage'] == 'offer')
        parent = parent_row(prior, anchor)
        offer = offer_row(prior, anchor, parent)
        need(not snapshot['trades'] and not snapshot['trade_offers'] and len(snapshot['completed_trades']) == 1)
        completed = snapshot['completed_trades'][0]
        need(set(completed) == {'id', 'completed_trade_id', 'request_player_id', 'offer_player_id',
            'morty_request_id', 'morty_offer_id', 'trade_request_id', 'trade_offer_id',
            'is_free_trade', 'fulfilled_at'})
        for key, value in {'request_player_id': parent['player_id'], 'offer_player_id': offer['player_id'],
            'morty_request_id': parent['morty_trade_id'], 'morty_offer_id': offer['morty_offer_id'],
            'trade_request_id': parent['trade_id'], 'trade_offer_id': offer['trade_offer_id'],
            'is_free_trade': parent['is_free_trade']}.items():
            need(completed.get(key) == value, 'Unexpected completion link')
        need(isinstance(completed.get('completed_trade_id'), str) and bool(completed['completed_trade_id'])
             and isinstance(completed.get('fulfilled_at'), str) and bool(completed['fulfilled_at']))
    return {'passed': True, 'stage': stage, 'exact_spare_swap': stage == 'accepted',
            'protected_raw_rows_preserved': True, 'user_dynamic_columns_changed': dynamics,
            'presence_event_counts': [len(before['event_queue']) - len(base_events),
                                      len(snapshot['event_queue']) - len(current_events)],
            'controlled_presence_fields': sorted(PRESENCE_FIELDS),
            'free_parent_expiry_change_allowed': new_parent}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recovery_document(baseline, baseline_hash, failed, failed_hash, previous, previous_hash):
    """Authorize only a missed decision whose actual protected offer is unchanged."""
    need(previous is not None and previous['stage'] == 'offer'
         and failed['stage'] in ('rejected', 'accepted'), 'Failed transition is not a missed decision')
    try:
        compare_snapshot(baseline, failed['snapshot'], failed['stage'], previous)
    except ValueError:
        pass
    else:
        need(False, 'Failed marker conceals a successful expected transition')
    comparison = compare_snapshot(baseline, failed['snapshot'], previous['stage'], previous)
    return {'version': 1, 'accounts': list(ACCOUNTS), 'private': True,
            'action': 'resume-failed', 'label': failed['label'], 'identity': baseline['identity'],
            'baseline_sha256': baseline_hash, 'failed_sha256': failed_hash,
            'failed_sequence': failed['sequence'], 'previous_successful_sha256': previous_hash,
            'previous_successful_sequence': previous['sequence'], 'resume_stage': previous['stage'],
            'comparison': comparison}


def verify_history(baseline, baseline_hash, entries, resumptions=None, resumable_label=None):
    """Pure full-chain verification, including explicitly resumed failed receipts.

    Each entry contains document/sha256. Resumptions map labels to the same
    pair. Failed observations retain their physical sequence and hash, while
    successful comparison uses the preceding successful logical state.
    """
    validate_baseline(baseline)
    resumptions = resumptions or {}
    previous = None
    previous_hash = baseline_hash
    successful_hash = baseline_hash
    failed_observations, consumed = [], set()
    pending = None
    for sequence, entry in enumerate(entries, 1):
        document, captured_hash = entry['document'], entry['sha256']
        need(document['sequence'] == sequence)
        need(document.get('version') == 1 and document.get('accounts') == list(ACCOUNTS)
             and document.get('private') is True and document.get('action') == 'observe'
             and document.get('identity') == baseline['identity'])
        need(document['baseline_sha256'] == baseline_hash
             and document['previous_sha256'] == previous_hash)
        if document['comparison'].get('passed') is False:
            need(document['comparison'] == {'passed': False, 'private_details_suppressed': True})
            proposed = recovery_document(baseline, baseline_hash, document, captured_hash,
                                         previous, successful_hash)
            resumption = resumptions.get(document['label'])
            if resumption is None:
                need(sequence == len(entries) and document['label'] == resumable_label,
                     'Unresumed failed observation halts the chain')
                pending = proposed
            else:
                stored = dict(resumption['document'])
                created = stored.pop('created_utc')
                need(isinstance(created, str) and bool(datetime.datetime.fromisoformat(created)))
                need(stored == proposed, 'Resumption does not bind the exact failed observation')
                consumed.add(document['label'])
            failed_observations.append({'label': document['label'], 'sequence': sequence,
                'sha256': captured_hash, 'resumption_sha256': resumption['sha256'] if resumption else None})
        else:
            need(document['comparison'] == compare_snapshot(baseline, document['snapshot'], document['stage'], previous))
            previous, successful_hash = document, captured_hash
        previous_hash = captured_hash
    need(set(resumptions) == consumed, 'Orphan resumption receipt')
    return {'previous': previous, 'previous_sha256': previous_hash, 'last_sequence': len(entries),
            'failed_observations': failed_observations, 'pending_resumption': pending}


def verified_history(output, baseline, resumable_label=None):
    entries, resumptions = [], {}
    for path in output.glob('observe-*.json'):
        if path.name.endswith('-attempt.json'):
            continue
        document = json.loads(safe_path(path).read_text(encoding='utf-8'))
        need(path.name == 'observe-' + document['label'] + '.json')
        entries.append({'document': document, 'sha256': digest(path)})
    entries.sort(key=lambda row: row['document']['sequence'])
    for path in output.glob('resume-*.json'):
        document = json.loads(safe_path(path).read_text(encoding='utf-8'))
        label = document['label']
        need(path.name == 'resume-' + label + '.json' and label not in resumptions)
        resumptions[label] = {'document': document, 'sha256': digest(path)}
    return verify_history(baseline, digest(output / 'baseline.json'), entries, resumptions, resumable_label)


def load_history(output, baseline):
    state = verified_history(output, baseline)
    return state['previous'], state['previous_sha256']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('snapshot', 'observe', 'resume-failed'))
    parser.add_argument('--output', required=True)
    parser.add_argument('--pair-baseline')
    parser.add_argument('--label')
    parser.add_argument('--stage', choices=STAGES)
    args = parser.parse_args()
    if args.action == 'snapshot':
        need(args.pair_baseline and not args.label and not args.stage)
    elif args.action == 'observe':
        need(not args.pair_baseline and args.stage and args.label
             and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', args.label))
    else:
        need(not args.pair_baseline and not args.stage and args.label
             and re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}', args.label))
    output = safe_path(args.output, fresh=args.action == 'snapshot')
    allowed = ROOT / '.research/emulator/native-trade-decisions-20261106'
    need(output.is_relative_to(allowed) and output != allowed, 'Decision receipt directory outside approved root')
    if args.action == 'snapshot':
        old_path = safe_path(args.pair_baseline)
        old_document = json.loads(old_path.read_text(encoding='utf-8'))
        old_identity = baseline_identity(old_document)
        output.mkdir(parents=True, exist_ok=False)
        destination, marker = output / 'baseline.json', output / 'snapshot-attempt.json'
        previous = None
    else:
        baseline_path = safe_path(output / 'baseline.json')
        baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
        validate_baseline(baseline)
        state = verified_history(output, baseline, args.label if args.action == 'resume-failed' else None)
        if args.action == 'resume-failed':
            resumption = state['pending_resumption']
            need(resumption is not None, 'No matching terminal failed observation')
            resumption['created_utc'] = datetime.datetime.now(datetime.UTC).isoformat()
            write_new(safe_path(output / f'resume-{args.label}.json'), resumption)
            print('resume-failed: OK; private unchanged-offer resumption recorded offline')
            return
        previous, previous_hash = state['previous'], state['previous_sha256']
        destination, marker = output / f'observe-{args.label}.json', output / f'observe-{args.label}-attempt.json'
    write_new(safe_path(marker), {'action': args.action, 'private': True})
    need(not safe_path(destination).exists(), 'Private receipt already exists')
    receipt = database()  # Existing read-only PDO consistent-snapshot transaction.
    document = {'version': 1, 'accounts': list(ACCOUNTS), 'private': True, 'action': args.action,
                'created_utc': datetime.datetime.now(datetime.UTC).isoformat(), **receipt}
    if args.action == 'snapshot':
        # Preserve the read-only evidence even if an immutable prior anchor
        # rejects it, without publishing a baseline that failed validation.
        write_new(safe_path(output / 'snapshot-raw.json'), document)
        document.update(identity=pair_anchor(receipt['snapshot']), old_pair_baseline={
            'sha256': digest(old_path), 'identity': old_identity, 'document': old_document})
        validate_baseline(document)
    else:
        document.update(identity=baseline['identity'], stage=args.stage, label=args.label,
                        sequence=state['last_sequence'] + 1,
                        baseline_sha256=digest(baseline_path), previous_sha256=previous_hash)
        try:
            document['comparison'] = compare_snapshot(baseline, receipt['snapshot'], args.stage, previous)
        except Exception:
            document['comparison'] = {'passed': False, 'private_details_suppressed': True}
            write_new(safe_path(destination), document)
            raise
    write_new(safe_path(destination), document)
    print(f'{args.action}: OK; private read-only decision receipt saved')


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Decision observation rejected; private details suppressed.', file=sys.stderr)
        sys.exit(1)

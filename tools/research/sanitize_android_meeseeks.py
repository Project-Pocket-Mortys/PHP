"""Read-only native Meeseeks acceptance exporter; private inputs never escape.

One exact Android ITEM request, a committed fixture result, reviewed screenshots,
and verified restoration are all required. Synthetic battle setup is explicit.
No database, Android, HTTP, or original-service operations are performed here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from capture_friend_battle_http import ROOT, message, packets, runs
from sanitize_native_trade_decisions import capture_packet_times, strict_json


ITEM = 'ItemMrMeeseek'
MOVE = '/session/battle/move'
SCREEN_ROLES = {'bag-item-visible', 'item-animation', 'terminal-win'}


def need(condition):
    if not condition:
        raise ValueError('Native Meeseeks proof invariant rejected')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return strict_json(path.read_text(encoding='utf-8'))


def exchanges(pcap):
    """Decode just battle moves, retaining exact ACK and packet time evidence."""
    captured = list(packets(pcap))
    times = capture_packet_times(pcap)
    need(len(captured) == len(times))
    flows, positions = {}, {}
    for index, (key, seq, ack, payload) in enumerate(captured):
        flows.setdefault(key, []).append((seq, ack, payload))
        positions.setdefault((key, seq), index)

    def position(key, absolute):
        values = [positions[(key, seq)] for seq, _, body in flows[key]
                  if seq <= absolute < seq + len(body)]
        need(bool(values))
        return min(values)

    found, used = [], set()
    for key, segments in flows.items():
        if key[3] != 8087:
            continue
        for start, stream, _ in runs(segments):
            finish = 0
            for hit in re.finditer(rb'POST /[^ ?\r\n]+ HTTP/1\.1\r\n', stream):
                if hit.start() < finish:
                    continue
                line, headers, body, finish = message(stream, hit.start())
                path = line.split()[1]
                if path.rstrip('/') != MOVE:
                    continue
                need(path in (MOVE, MOVE + '/'))
                need(headers.get('user-agent') == 'UnityApp/2.41.0 (Android)')
                need(type(headers.get('x-pmclient')) is str and bool(headers['x-pmclient']))
                need(headers.get('content-type', '').split(';')[0].strip() == 'application/json')
                reverse = (key[2], key[3], key[0], key[1])
                replies = []
                for rstart, response_stream, spans in runs(flows.get(reverse, [])):
                    rfinish = 0
                    for response in re.finditer(rb'HTTP/1\.[01] [0-9]{3} [^\r\n]*\r\n', response_stream):
                        if response.start() < rfinish:
                            continue
                        absolute = rstart + response.start()
                        acks = {ack for lo, hi, ack in spans if lo <= absolute < hi}
                        if start + finish not in acks:
                            continue
                        need(acks == {start + finish})
                        status, _, reply, rfinish = message(response_stream, response.start())
                        replies.append((int(status.split()[1]), strict_json(reply),
                                        position(reverse, absolute), (reverse, absolute)))
                need(len(replies) == 1)
                status, reply, reply_index, reply_key = replies[0]
                need(reply_key not in used)
                used.add(reply_key)
                request_index = position(key, start + hit.start())
                request_end_index = position(key, start + finish - 1)
                need(reply_index > request_end_index and times[reply_index] > times[request_end_index])
                found.append(dict(path=path, request=strict_json(body), status=status,
                    response=reply, request_packet_index=request_index,
                    response_packet_index=reply_index, request_time=times[request_index],
                    response_time=times[reply_index]))
    need(len(found) == 1)
    return found


def wire(row, fixture, case):
    """Bind the five native fields to the guarded synthetic actor and battle."""
    session = row['request'].get('session_id')
    need(type(session) is str and bool(session))
    need(hashlib.sha256(session.encode()).hexdigest() == case['session_id_sha256'])
    expected = dict(session_id=session, battle_id=case['battle_id'],
        type='ITEM', owned_morty_id=fixture['active'], move_id=ITEM)
    need(type(row['request']) is dict and row['request'] == expected)
    need(set(row['request']) == set(expected))
    need(row['status'] == 200 and type(row['status']) is int)
    need(type(row['response']) is dict and set(row['response']) == {'success'}
         and row['response']['success'] is True)


def screenshots(capture, manifest, review, pcap_hash):
    """Export only role labels and hashes after checking private review bindings."""
    need(review['private'] is True and review['pcap_sha256'] == pcap_hash)
    need(review['native_item_selection'] is True and review['battle_start'] == 'synthetic-http')
    need(review['item_request'] == 'native-ui' and review['original_service_evidence'] is False)
    samples = {sample['file']: sample for sample in manifest['screenshots'] if 'file' in sample}
    need(len(samples) == len([s for s in manifest['screenshots'] if 'file' in s]))
    selected, seen_files, seen_roles = [], set(), set()
    for screen in review['screenshots']:
        name, role = screen['file'], screen['role']
        need(type(name) is str and Path(name).name == name and name not in seen_files)
        need(role in SCREEN_ROLES and screen['reviewed'] is True)
        need(name in samples and samples[name]['sha256'] == screen['sha256'])
        path = capture / name
        need(path.resolve().parent == capture.resolve())
        need(path.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'))
        need(digest(path) == screen['sha256'])
        selected.append(dict(role=role, sha256=screen['sha256'], reviewed=True))
        seen_files.add(name)
        seen_roles.add(role)
    need(seen_roles == SCREEN_ROLES)
    return selected


def stock_quantities(fixture, prepared):
    before, allocated = fixture['before']['items'], prepared['items']
    old = [item for item in before if item['item_id'] == ITEM]
    new = [item for item in allocated if item['item_id'] == ITEM]
    need(len(old) <= 1 and len(new) == 1)
    initial = old[0]['quantity'] if old else 0
    need(type(initial) is int and initial >= 0)
    need(type(new[0]['quantity']) is int and new[0]['quantity'] == initial + 1)
    need([item for item in before if item['item_id'] != ITEM]
         == [item for item in allocated if item['item_id'] != ITEM])
    if old:
        need(dict(old[0], quantity=initial + 1) == new[0])
    return new[0]['quantity'], initial


def inspect(fixture_dir, capture_dir, review_path, label='native-item'):
    # Import the guarded fixture's pure verifier only when inspecting; no setup.
    from meeseeks_box_fixture import validate
    need(__debug__)  # The shared pure fixture verifier uses Python assertions.
    names = ['fixture', 'prepared', 'case', label + '-result', label + '-http', 'cleanup',
             'restored', 'cleanup-result', 'cleanup-http']
    paths = {name: fixture_dir / (name + '.json') for name in names}
    documents = {name: load(path) for name, path in paths.items()}
    fixture, prepared, case = (documents[name] for name in names[:3])
    result, native, cleanup = (documents[name] for name in names[3:6])
    quantity_before, quantity_after = stock_quantities(fixture, prepared)
    bound_fixture = dict(fixture, wild=case['wild'], enemy_hp=case['enemy_hp'],
                         stock_id=next(i['id'] for i in prepared['items'] if i['item_id'] == ITEM))
    need(validate(bound_fixture, prepared, result['snapshot'], result['battle'], result['events'], native) == 1)
    need(result['battle']['battle_id'] == case['battle_id'])
    need(cleanup['restored'] is True and cleanup['exact_original_rows'] is True)
    need(cleanup['acceptance'] is True and cleanup['meeseeks_uses'] == 1 and cleanup['outcome'] == 'WIN')
    need(type(cleanup['meeseeks_uses']) is int)
    need(documents['restored'] == fixture['before'])
    need(documents['cleanup-result'] == result and documents['cleanup-http'] == native)
    for field, name in [('before_sha256', 'fixture'), ('prepared_sha256', 'prepared'),
                        ('restored_snapshot_sha256', 'restored'), ('result_sha256', 'cleanup-result'),
                        ('case_sha256', 'case')]:
        need(cleanup[field] == digest(paths[name]))
    manifest_path = capture_dir / 'manifest.json'
    manifest = load(manifest_path)
    need(manifest['failure'] is None and manifest['pull_exit_code'] == 0)
    need(manifest['tcpdump_exit_code'] in (0, 124, 130))
    need(manifest['role'] == 'primary' and manifest['serial'] == 'emulator-5560'
         and manifest['avd'] == 'PocketMortys_API30_Startup')
    apk = manifest['apk']
    need(apk['version'] == '2.41.0')
    source_hashes, installed_hashes = apk['source_apk_sha256'].values(), apk['installed_apk_sha256'].values()
    need(len(source_hashes) == len(installed_hashes) == 2)
    need(sorted(source_hashes) == sorted(installed_hashes))
    need(all(type(value) is str and re.fullmatch('[0-9a-f]{64}', value) is not None for value in source_hashes))
    need(fixture['device']['serial'] == manifest['serial'] and fixture['device']['avd'] == manifest['avd'])
    pcap = capture_dir / 'primary-http.pcap'
    pcap_hash = digest(pcap)
    need(manifest['pcap_sha256'] == pcap_hash and manifest['pcap_size_bytes'] == pcap.stat().st_size)
    rows = exchanges(pcap)
    wire(rows[0], fixture, case)
    # The server logger and on-device PCAP must describe the same sole operation.
    moves = [row for row in native if row['path'].rstrip('/') == MOVE]
    need(len(moves) == 1)
    need(moves[0]['capture_service'] == 'offline-sdk-web')
    need(moves[0]['path'] == rows[0]['path'])
    need(moves[0]['request'] == {k: v for k, v in rows[0]['request'].items() if k != 'session_id'})
    need(all(moves[0][key] == rows[0][key] for key in ('status', 'response')))
    reviewed = screenshots(capture_dir, manifest, load(review_path), pcap_hash)
    return dict(schema='android-meeseeks-box-acceptance-v1',
        evidence_kind='Observed Android 2.41.0 request to isolated replacement server',
        original_service_evidence=False, native_android_acceptance=True,
        setup=dict(battle_start='synthetic-http', actor='synthetic-owned-clone',
                   inventory='one-temporary-box', item_selection='native-ui'),
        request=dict(method='POST', path=rows[0]['path'], fields=['session_id', 'battle_id', 'type',
            'owned_morty_id', 'move_id'], type='ITEM', owned_morty_id='fixture-active-actor', move_id=ITEM),
        response=dict(status=200, success=True),
        proof=dict(exact_tcp_ack_pair=True, native_headers_present=True,
            committed_outcome='WIN', item_action_count=1, enemy_hp=0,
            attacker_morty_datas=[], ai_action_count=0, boxes_consumed=1,
            quantity_before=quantity_before, absolute_quantity_after=quantity_after,
            owned_hp_ap_status_resources_unchanged=True, public_wild_cleanup=True,
            private_terminal_event=True, original_rows_restored=True),
        screenshots=reviewed, artifacts=dict(pcap_sha256=pcap_hash,
            apk_sha256=sorted(source_hashes),
            capture_manifest_sha256=digest(manifest_path), screenshot_review_sha256=digest(review_path),
            fixture_sha256={name: digest(path) for name, path in paths.items()}))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture', required=True, type=Path)
    parser.add_argument('--capture', required=True, type=Path)
    parser.add_argument('--review', required=True, type=Path)
    parser.add_argument('--label', default='native-item')
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    try:
        private = (ROOT / '.research').resolve()
        need(re.fullmatch('[a-z0-9-]+', args.label) is not None)
        need(all(path.resolve().is_relative_to(private) for path in
                 (args.fixture, args.capture, args.review, args.output)))
        need(not args.output.exists())
        result = inspect(args.fixture.resolve(), args.capture.resolve(), args.review.resolve(), args.label)
        with args.output.open('x', encoding='utf-8') as handle:
            json.dump(result, handle, indent=2)
            handle.write('\n')
    except Exception as error:
        raise SystemExit('Android Meeseeks proof failed: ' + type(error).__name__) from None
    print('Sanitized Android Meeseeks acceptance written')


if __name__ == '__main__':
    main()

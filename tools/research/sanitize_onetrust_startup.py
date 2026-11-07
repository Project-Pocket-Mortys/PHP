"""Read completed private startup captures; emit allowlisted recovery evidence only.

No device, server, DB, network, or credential reconstruction files are touched.
JWT claims are compared locally; this is not JWT signature verification.
"""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

import export_android_startup as wire
from sanitize_trade_cookie_handoff import ROOT, primary_account, returned_session


PATHS = {'/_research/online', '/user/login', '/session/player-details', '/session/join-room'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inspect(capture, fixture):
    manifest = json.loads((capture / 'manifest.json').read_text(encoding='utf-8'))
    assert manifest.get('finished_utc') and manifest.get('capture_ended_utc'), 'Capture must be finished'
    assert manifest.get('failure') is None, 'Require successful capture completion'
    assert manifest['role'] == 'primary' and manifest['pull_exit_code'] == manifest['logcat_exit_code'] == 0
    pcap = capture / 'primary-http.pcap'
    assert digest(pcap) == manifest['pcap_sha256'], 'Capture digest mismatch'
    account = primary_account(fixture)
    flows, zero = wire.flows(pcap)
    exchanges, sse_tokens = [], []
    for key, rows in flows.items():
        if key[3] not in (8087, 8089):
            continue
        for start, stream, _ in wire.runs([(p['seq'], p['ack'], p['payload']) for p in rows if p['payload']]):
            for request in wire.messages(stream):
                method, target, _ = request['line'].split(' ')
                path = urlsplit(target).path.rstrip('/')
                if method == 'GET' and path == '/sse':
                    sse_tokens.extend(parse_qs(urlsplit(target).query).get('token', []))
                if path not in PATHS:
                    continue
                assert method == ('GET' if path == '/_research/online' else 'POST'), 'Unexpected target HTTP method'
                assert request['finish'] is not None, 'Incomplete target request'
                reverse = (key[2], key[3], key[0], key[1])
                responses = []
                for rstart, data, spans in wire.runs([(p['seq'], p['ack'], p['payload'])
                                                    for p in flows.get(reverse, []) if p['payload']]):
                    for response in wire.messages(data):
                        absolute = rstart + response['start']
                        acks = {ack for lo, hi, ack in spans if lo <= absolute < hi}
                        if start + request['finish'] not in acks:
                            continue
                        assert acks == {start + request['finish']}, 'Ambiguous response TCP acknowledgement'
                        assert response['finish'] is not None, 'Incomplete target response'
                        responses.append((response, wire.at(flows[reverse], absolute)))
                assert len(responses) == 1, 'Require exactly one complete ACK-paired response'
                response, reply_time = responses[0]
                request_time = wire.at(rows, start + request['start'])
                assert reply_time >= request_time, 'Response precedes request'
                headers = request['headers']
                native = 'x-pmclient' in headers and headers.get('user-agent') == 'UnityApp/2.41.0 (Android)'
                if path != '/_research/online':
                    assert native, 'Require native application headers'
                exchanges.append(dict(path=path, method=method, status=int(response['line'].split()[1]),
                                      time=request_time, reply_time=reply_time, native=native,
                                      request=request['body'], response=response['body']))
    exchanges.sort(key=lambda row: row['time'])
    probes = [row for row in exchanges if row['path'] == '/_research/online']
    probe_statuses = [row['status'] for row in probes]
    assert len(probe_statuses) >= 2 and probe_statuses[0] == 503 and all(status == 204 for status in probe_statuses[1:]), 'Require one offline probe followed only by online probes'
    logins = [row for row in exchanges if row['path'] == '/user/login'
              and json.loads(row['request']).get('secret') == account['secret']]
    assert len(logins) == 1 and logins[0]['status'] == 200, 'Require one successful immutable-primary login'
    login = logins[0]
    token, claims = returned_session(json.loads(login['response']))
    assert claims.get('player_id') == account['player_id'] and claims.get('username') == account['username'], 'Login claims must match fixture'
    assert isinstance(claims.get('session_id'), str) and claims['session_id'], 'Require returned session identity'
    assert token in sse_tokens, 'Returned token must appear in captured native session request'
    assert probes[0]['reply_time'] < probes[1]['time'] < login['time'], 'Require ordered probe recovery then login'
    details, joins = [], []
    for row in exchanges:
        if row['path'] not in ('/session/player-details', '/session/join-room'):
            continue
        body, reply = json.loads(row['request']), json.loads(row['response'])
        assert body.get('session_id') == claims['session_id'], 'Authenticated request must match login session'
        assert row['status'] == 200 and row['time'] > login['reply_time'], 'Authenticated request must follow successful login'
        if row['path'] == '/session/player-details':
            assert reply.get('player_id') == account['player_id'] and reply.get('username') == account['username'], 'Player details identity mismatch'
            details.append(row)
        else:
            assert 'room_id' in reply and 'users' in reply and 'error' not in reply, 'Require successful world-room response'
            joins.append(row)
    assert details and joins, 'Require authenticated player details and world join'
    logcat = capture / 'logcat-private.txt'
    began = datetime.fromisoformat(manifest['started_utc']).timestamp()
    ended = datetime.fromisoformat(manifest['capture_ended_utc']).timestamp()
    entries = []
    for line in logcat.read_text(encoding='utf-8', errors='replace').splitlines():
        match = re.match(r'\s*(\d{10}\.\d+)\s', line)
        if match:
            entries.append((float(match[1]), line))
    assert entries and min(t for t, _ in entries) <= probes[0]['time'], 'Logcat must cover first probe'
    assert max(t for t, _ in entries) >= max(row['reply_time'] for row in exchanges), 'Logcat must cover recovered exchanges'
    fresh = [line for stamp, line in entries if began <= stamp <= ended]
    failure_count = sum('OneTrust.CMPSDK.get_domainData_Groups' in line for line in fresh)
    null_reference_count = sum('NullReferenceException' in line for line in fresh)
    onetrust_stack_count = sum('at OneTrust' in line for line in fresh)
    assert failure_count == 0, 'Fresh OneTrust domain-data exception observed'
    assert null_reference_count == 0, 'Fresh null-reference exception observed'
    sources = manifest['apk']['source_apk_sha256']
    installed = manifest['apk']['installed_apk_sha256']
    assert set(sources.values()) == set(installed.values()), 'Installed APK differs from recorded source'
    return dict(evidence_kind='Observed native Android startup against isolated replacement server; not original-service evidence',
                pcap_sha256=digest(pcap), fixture_sha256=digest(fixture), logcat_sha256=digest(logcat),
                client_version=manifest['apk']['version'], installed_apk_matches_source=True,
                source_apk_sha256=sorted(sources.values()),
                online_probe_statuses=probe_statuses, exact_tcp_ack_pairs=True,
                primary_login_status=200, login_secret_matches_immutable_fixture=True,
                login_jwt_claims_match_immutable_fixture=True, returned_token_matches_native_session_request=True,
                authenticated_requests_match_returned_session=True,
                player_details_count=len(details), world_join_count=len(joins),
                fresh_onetrust_domain_data_exception_count=failure_count,
                fresh_nullreference_exception_count=null_reference_count,
                fresh_onetrust_stack_line_count=onetrust_stack_count,
                logcat_covers_recovered_exchanges=True,
                timeline=[dict(method=row['method'], path=row['path'], status=row['status'],
                               seconds=round(row['time'] - zero, 6), exact_tcp_ack_pair=True,
                               native_application_headers=row['native']) for row in exchanges],
                redaction='No raw secret, session, JWT, cookie, player ID, room ID, address, or request/response body emitted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--capture', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--compare', nargs=3, action='append', default=[], metavar=('LABEL', 'BEFORE', 'AFTER'),
                        help='Optional local invariant comparison; output hashes and equality only')
    args = parser.parse_args()
    try:
        private = (ROOT / '.research').resolve()
        for path in (args.capture, args.fixture, args.output):
            assert path.resolve().is_relative_to(private), 'Artifacts must remain ignored'
        assert not args.output.exists(), 'Require fresh output'
        result = inspect(args.capture.resolve(), args.fixture.resolve())
        comparisons = {}
        for label, before, after in args.compare:
            assert label in {'sdk_server_data', 'sdk_active_profile', 'original_userdata_guard', 'retained_apk_guard'}
            assert label not in comparisons, 'Duplicate invariant label'
            paths = [Path(before).resolve(), Path(after).resolve()]
            assert all(path.is_relative_to(private) for path in paths)
            hashes = [digest(path) for path in paths]
            comparisons[label] = dict(before_sha256=hashes[0], after_sha256=hashes[1], unchanged=hashes[0] == hashes[1])
        result['local_file_invariants'] = comparisons
    except Exception as error:
        raise SystemExit('Startup recovery proof failed: ' + type(error).__name__) from None
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

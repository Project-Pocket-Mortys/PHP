"""Read-only PCAP proof of native login -> scoped trading cookie handoff.

Reuses the strict classic-PCAP/TCP/Content-Length parser. Never contacts a
device/server/database, sends requests, or writes reconstructed credentials.
Output is sanitized and must be created inside ignored .research.
"""
import argparse
import base64
import hashlib
from http.cookies import SimpleCookie
import json
from pathlib import Path
import re
from urllib.parse import parse_qs, urlsplit

from capture_friend_battle_http import ROOT, message, packets, runs


def primary_account(fixture):
    account_rows = json.loads(fixture.read_text(encoding='utf-8'))['before']['accounts']
    account = [row for row in account_rows if row['username'] == 'PMStartup01']
    assert len(account) == 1, 'Require one immutable primary fixture identity'
    return account[0]


def returned_session(payload):
    query = parse_qs(urlsplit(payload['session_url']).query)
    assert len(query.get('token', [])) == 1, 'Require one returned session token'
    token = query['token'][0]
    pieces = token.split('.')
    assert len(pieces) == 3, 'Require returned JWT-shaped session token'
    claims = json.loads(base64.urlsafe_b64decode(pieces[1] + '=' * (-len(pieces[1]) % 4)))
    return token, claims


def inspect(pcap, fixture):
    account = primary_account(fixture)
    flows, packet_order = {}, {}
    for ordinal, (key, seq, ack, payload) in enumerate(packets(pcap)):
        flows.setdefault(key, []).append((seq, ack, payload))
        packet_order.setdefault((key, seq), ordinal)

    def first_packet(key, absolute):
        positions = [packet_order[(key, seq)] for seq, _, payload in flows[key]
                     if seq <= absolute < seq + len(payload)]
        assert positions, 'No captured packet covers message start'
        return min(positions)

    def paired_response(key, start, finish):
        reverse = (key[2], key[3], key[0], key[1])
        responses = []
        for rstart, stream, spans in runs(flows.get(reverse, [])):
            for match in re.finditer(rb'HTTP/1\.[01] [0-9]{3} [^\r\n]*\r\n', stream):
                absolute = rstart + match.start()
                acks = {ack for lo, hi, ack in spans if lo <= absolute < hi}
                if start + finish not in acks:
                    continue
                assert acks == {start + finish}, 'Ambiguous response TCP acknowledgement'
                line, headers, body, _ = message(stream, match.start())
                responses.append((line, headers, body, first_packet(reverse, absolute)))
        assert len(responses) == 1, 'Require one response acknowledging exactly this request'
        return responses[0]

    requests = []
    for key, segments in flows.items():
        if key[3] != 8087:
            continue
        for start, stream, _ in runs(segments):
            for match in re.finditer(rb'POST /(user/login/?|trading/[^ ?\r\n]+) HTTP/1\.1\r\n', stream):
                line, headers, body, finish = message(stream, match.start())
                requests.append((key, start, finish, line.split(' ')[1], headers, body,
                                 first_packet(key, start + match.start())))

    logins = []
    for key, start, finish, path, headers, body, ordinal in requests:
        if path.rstrip('/') != '/user/login':
            continue
        login = json.loads(body)
        if login.get('secret') != account['secret']:
            continue
        assert 'x-pmclient' in headers and headers.get('user-agent') == 'UnityApp/2.41.0 (Android)', 'Require native login headers'
        line, response_headers, response_body, response_ordinal = paired_response(key, start, finish)
        assert line.split(' ')[1] == '200', 'Primary login must succeed'
        cookie = SimpleCookie()
        cookie.load(response_headers.get('set-cookie', ''))
        assert set(cookie) == {'session_id'}, 'Require an unambiguous login session cookie'
        morsel = cookie['session_id']
        assert morsel.value and morsel['path'] == '/trading/' and morsel['httponly'] and morsel['samesite'].lower() == 'lax', 'Require scoped HttpOnly SameSite=Lax session cookie'
        payload = json.loads(response_body)
        _, claims = returned_session(payload)
        assert claims.get('player_id') == account['player_id'] and claims.get('username') == account['username'], 'Login response identity must match immutable fixture'
        assert claims.get('session_id') == morsel.value, 'Cookie must match the login-returned session'
        logins.append((morsel.value, response_ordinal, bool(morsel['secure'])))
    assert logins, 'No complete acknowledged primary login with session cookie observed'

    observed = []
    for key, start, finish, path, headers, body, ordinal in requests:
        if not path.startswith('/trading/'):
            continue
        cookie = SimpleCookie()
        cookie.load(headers.get('cookie', ''))
        if 'session_id' not in cookie:
            continue
        matches = [row for row in logins if row[0] == cookie['session_id'].value and row[1] < ordinal]
        if not matches:
            continue
        assert 'x-pmclient' in headers and headers.get('user-agent') == 'UnityApp/2.41.0 (Android)', 'Require native outgoing trading headers'
        line, _, _, response_ordinal = paired_response(key, start, finish)
        assert response_ordinal > ordinal, 'Response must follow native trading request'
        request_body = json.loads(body)
        assert isinstance(request_body, dict), 'Require trading JSON object'
        observed.append(dict(method='POST', path=path, response_status=int(line.split(' ')[1]),
                             body_keys=sorted(request_body), cookie_matches_primary_login=True,
                             exact_tcp_ack_pair=True, native_headers_present=True))
    assert observed, 'No acknowledged outgoing native trading request returning the primary login cookie'
    return dict(evidence_kind='Observed native Android replacement-server cookie handoff; not original-service evidence',
                fixture_identity='PMStartup01', fixture_sha256=hashlib.sha256(fixture.read_bytes()).hexdigest(),
                pcap_sha256=hashlib.sha256(pcap.read_bytes()).hexdigest(), primary_login_count=len(logins),
                login_secret_matches_immutable_fixture=True, login_claims_match_immutable_fixture=True,
                set_cookie=dict(name='session_id', path='/trading/', httponly=True, samesite='Lax',
                                secure_values=sorted({row[2] for row in logins})),
                trading_requests=observed,
                redaction='No raw secret, session, JWT, cookie value, player ID, or trade ID emitted')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pcap', type=Path, required=True)
    parser.add_argument('--fixture', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    private = (ROOT / '.research').resolve()
    for path in (args.pcap, args.fixture, args.output):
        assert path.resolve().is_relative_to(private), 'All artifacts must remain inside ignored .research'
    assert not args.output.exists(), 'Use a fresh sanitized output file'
    try:
        result = inspect(args.pcap.resolve(), args.fixture.resolve())
    except Exception as error:
        # JSON/parser exceptions can include credential fragments; omit details.
        raise SystemExit('Cookie handoff proof failed: ' + type(error).__name__) from None
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()

"""Summarize captured native trading reads without copying any payload values.

Uses strict classic-PCAP/TCP/Content-Length parsing and exact response ACK pairing.
Does not contact a server/device. Unknown selected wire shapes fail closed.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re

from capture_friend_battle_http import ROOT, message, packets, runs

SHAPES = {
    '/trading/config': ({'session_id'}, {'config_id', 'premium_trade_cost', 'max_trades', 'trade_cooldown_minutes'}),
    '/trading/get-trades': ({'session_id', 'player_id'}, {'completed_trades', 'player_cooldown_data',
        'trade_attacks', 'trade_mortys', 'trade_offers', 'trade_requests'}),
}


def shape(request, response, path):
    expected_request, expected_response = SHAPES[path]
    assert isinstance(request, dict) and set(request) == expected_request, 'Unexpected request shape'
    assert isinstance(response, dict) and set(response) == expected_response, 'Unexpected response shape'
    # Key sets are allowlisted. Nested values, IDs, headers and strings never leave memory.
    return {'request_types': {k: type(request[k]).__name__ for k in sorted(expected_request)},
            'response_types': {k: type(response[k]).__name__ for k in sorted(expected_response)},
            'response_list_counts': {k: len(response[k]) for k in sorted(expected_response)
                                     if isinstance(response[k], list)}}


def inspect(pcap):
    flows = {}
    for key, seq, ack, payload in packets(pcap):
        flows.setdefault(key, []).append((seq, ack, payload))
    observed, other = [], 0
    for key, segments in flows.items():
        if key[3] != 8087:
            continue
        for start, stream, _ in runs(segments):
            for match in re.finditer(rb'POST /trading/[^ ?\r\n]+ HTTP/1\.1\r\n', stream):
                line, headers, body, finish = message(stream, match.start())
                path = line.split()[1]
                if path not in SHAPES:
                    other += 1
                    continue
                assert headers.get('user-agent') == 'UnityApp/2.41.0 (Android)' and 'x-pmclient' in headers, 'Native headers required'
                responses = []
                reverse = (key[2], key[3], key[0], key[1])
                for rstart, buf, spans in runs(flows.get(reverse, [])):
                    for hit in re.finditer(rb'HTTP/1\.[01] [0-9]{3} [^\r\n]*\r\n', buf):
                        absolute = rstart + hit.start()
                        acks = {ack for lo, hi, ack in spans if lo <= absolute < hi}
                        if start + finish not in acks:
                            continue
                        assert acks == {start + finish}, 'Ambiguous response acknowledgement'
                        responses.append(message(buf, hit.start()))
                assert len(responses) == 1, 'One complete acknowledged response required'
                status, _, response_body, _ = responses[0]
                assert status.split()[1] == '200', 'Successful read required'
                observed.append(dict(method='POST', path=path, status=200,
                    native_headers=True, exact_tcp_ack_pair=True,
                    **shape(json.loads(body), json.loads(response_body), path)))
    return {'schema_version': 1,
            'evidence_kind': 'Observed Android reads from isolated replacement server; not original-service evidence',
            'pcap_sha256': hashlib.sha256(pcap.read_bytes()).hexdigest(),
            'reads': observed, 'other_trading_post_count': other,
            'limits': 'No cookie identity, listing creation, cancellation, transfer or lock-refresh acceptance proved'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pcap', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    private = (ROOT / '.research').resolve()
    assert all(p.resolve().is_relative_to(private) for p in (args.pcap, args.output)), 'Ignored artifacts required'
    assert not args.output.exists(), 'Fresh output required'
    try:
        result = inspect(args.pcap)
    except Exception as error:
        raise SystemExit('Trading read summary failed: ' + type(error).__name__) from None
    with args.output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2)
        handle.write('\n')
    print(f"Sanitized {len(result['reads'])} native reads; other trading POSTs: {result['other_trading_post_count']}")


if __name__ == '__main__':
    main()

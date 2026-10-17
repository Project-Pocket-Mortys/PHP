"""Summarize the fixed-coordinate two-role synthetic quiet UDP probe capture."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

from compare_udp_hops import _read_udp
from udp_codec import decode_datagram


def summarize(path):
    path = Path(path)
    origin, packet_count, packets = _read_udp(path)
    current, endpoints, identities = {}, {}, {}
    changes = {'role0': 0, 'role1': 0}
    events = []
    totals = Counter({f'{kind}_{role}': 0 for kind in ('ingress', 'egress')
                      for role in changes})
    for packet in packets:
        records = decode_datagram(packet['payload'])
        if len(records) != 1:
            raise ValueError('Expected one placement record per probe datagram')
        record = records[0]
        if record['x'] not in (29, 35) or record['y'] != 35:
            raise ValueError('Unexpected synthetic probe coordinates')
        role = 'role0' if record['x'] == 29 else 'role1'
        ingress = packet['destination'][1] == 5055
        if ingress:
            prefix = packet['payload'][:16]
            if role in identities and identities[role] != prefix:
                raise ValueError('Multiple probe identities observed for one synthetic role')
            identities[role] = prefix
            endpoint = packet['source']
            changes[role] += int(role in current and current[role] != endpoint)
            current[role] = endpoint
            endpoints.setdefault(endpoint, set()).add(role)
            target = 'relay'
        else:
            candidates = endpoints.get(packet['destination'], set())
            target = next(iter(candidates)) if len(candidates) == 1 else 'unknown'
        kind = 'ingress' if ingress else 'egress'
        totals[f'{kind}_{role}'] += 1
        # Never serialize decoder dictionaries, raw bytes or endpoint tuples.
        events.append({'t': (packet['timestamp'] - origin) / 1_000_000,
                       'kind': kind, 'sender': role, 'target': target,
                       'sequence': record['sequence'], 'xy': [record['x'], record['y']]})
    return {
        'input_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'capture_packet_count': packet_count,
        'source_endpoint_changes': changes,
        'totals': dict(totals), 'events': events,
        'limitations': 'Synthetic roles are inferred from fixed coordinates: role0 x=29, '
                       'role1 x=35, both y=35. Each role must retain the same internal '
                       'ingress identity throughout the capture; mixed probe identities '
                       'are rejected. Endpoint changes describe relay-observed '
                       'source tuples, not local socket changes or their cause. Targets '
                       'use previously observed ingress endpoints, including historical '
                       'ones; missing or ambiguous mappings remain unknown. Times are '
                       'relative to the first capture packet. Egress observation does '
                       'not establish socket delivery. Correlate independent probe '
                       'receipts by target, sender, sequence and coordinates; repeated '
                       'records do not establish latency. Capture coverage and drops '
                       'require separate evidence. Checksums are not checked. '
                       'Only port-5055 UDP is summarized. Identifiers, endpoint '
                       'addresses/ports, payload bytes and payload hashes are omitted. '
                       'The input SHA-256 identifies the complete capture artifact.'
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pcap', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = summarize(args.pcap)
    except ValueError as error:
        parser.exit(2, f'{error}\n')
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"Exported {len(report['events'])} sanitized probe events")


if __name__ == '__main__':
    main()

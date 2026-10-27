"""Compare private relay/primary/peer UDP PCAPs and export role labels only.

Accepts classic little-endian microsecond PCAP with Linux cooked v1 IPv4.
Session/player prefixes, endpoint addresses and ports remain internal.
"""
import argparse
import json
from pathlib import Path
import struct

from udp_codec import decode_datagram


ROLES = ('primary', 'peer')
LIMITATIONS = (
    'Exactly two peers are assumed: guest outbound record prefixes identify its '
    'session role; guest inbound prefixes identify the opposite player role. '
    'Conflicting prefix or endpoint mappings remain unknown. Relay destination '
    'roles use previously observed ingress endpoints, including historical ones. '
    'Endpoint changes describe observed relay source tuples, not local socket or '
    'FD changes, NAT lifetime, or the cause of a mapping change. Receipt means '
    'an identical complete UDP payload appears in the destination capture; a '
    'replay may match an earlier packet. No clock alignment or latency is inferred. '
    'False means absent from the supplied destination capture, not proof of '
    'network loss; null means unknown destination or ingress. Capture coverage '
    'and drops require separate verification. Packet observation does not prove '
    'application processing. Times are relative to the first relay capture packet. '
    'Malformed/truncated capture headers, lengths and IPv4 fragments are rejected. '
    'Non-placement UDP payloads are counted and omitted. Checksums are not checked. '
    'Identifiers, addresses, ports, payload bytes and payload hashes are omitted.'
)


def _read_udp(path):
    data = Path(path).read_bytes()
    if len(data) < 24:
        raise ValueError('Truncated PCAP global header')
    if data[:4] != b'\xd4\xc3\xb2\xa1':
        raise ValueError('Expected classic little-endian microsecond PCAP')
    _, major, minor, _, _, snaplen, linktype = struct.unpack_from('<IHHIIII', data)
    if (major, minor) != (2, 4) or linktype != 113 or snaplen == 0:
        raise ValueError('Expected PCAP 2.4 with Linux cooked link type 113 and positive snaplen')
    pos, origin, rows, count = 24, None, [], 0
    while pos < len(data):
        if len(data) - pos < 16:
            raise ValueError('Truncated PCAP packet header')
        sec, usec, included, original = struct.unpack_from('<IIII', data, pos)
        pos += 16
        if usec >= 1_000_000:
            raise ValueError('Invalid PCAP microsecond timestamp')
        if included != original or included > snaplen or included > len(data) - pos:
            raise ValueError('Truncated packet or invalid PCAP packet length')
        frame = data[pos:pos + included]
        pos += included
        timestamp = sec * 1_000_000 + usec
        count += 1
        if origin is None:
            origin = timestamp
        if len(frame) < 16:
            raise ValueError('Truncated Linux cooked header')
        if frame[14:16] != b'\x08\x00':
            continue
        ip = frame[16:]
        if len(ip) < 20 or ip[0] >> 4 != 4:
            raise ValueError('Malformed or truncated IPv4 header')
        ihl = (ip[0] & 15) * 4
        total = int.from_bytes(ip[2:4], 'big')
        if ihl < 20 or total < ihl or total > len(ip):
            raise ValueError('Invalid IPv4 header or total length')
        if int.from_bytes(ip[6:8], 'big') & 0x3fff:
            raise ValueError('Fragmented IPv4 is unsupported')
        if ip[9] != 17:
            continue
        udp = ip[ihl:total]
        if len(udp) < 8:
            raise ValueError('Truncated UDP header')
        source, destination, length = struct.unpack_from('>HHH', udp)
        if length < 8 or length != len(udp):
            raise ValueError('Invalid UDP length')
        if source == 5055 or destination == 5055:
            rows.append({'timestamp': timestamp,
                         'source': (ip[12:16], source),
                         'destination': (ip[16:20], destination), 'payload': udp[8:]})
    return origin, count, rows


def _prefixes(payload):
    return [payload[offset:offset + 16] for offset in range(0, len(payload), 24)]


def _unique(mapping, key):
    values = mapping.get(key, set())
    return next(iter(values)) if len(values) == 1 else 'unknown'


def compare(relay, primary, peer):
    captures = {'relay': _read_udp(relay), 'primary': _read_udp(primary), 'peer': _read_udp(peer)}
    sessions, players = {}, {}
    received = {role: set() for role in ROLES}
    malformed = {name: 0 for name in captures}
    valid = {}
    for name, (_, _, rows) in captures.items():
        valid[name] = []
        for row in rows:
            try:
                records = decode_datagram(row['payload'])
            except ValueError:
                malformed[name] += 1
                continue
            valid[name].append((row, records))
    for role, other in (('primary', 'peer'), ('peer', 'primary')):
        for row, _ in valid[role]:
            if row['destination'] == (b'\x0a\x00\x02\x02', 5055):
                for prefix in _prefixes(row['payload']):
                    sessions.setdefault(prefix, set()).add(role)
            elif row['source'][1] == 5055:
                received[role].add(row['payload'])
                for prefix in _prefixes(row['payload']):
                    players.setdefault(prefix, set()).add(other)

    current_endpoints, endpoint_roles = {}, {}
    changes = {role: 0 for role in ROLES}
    report = []
    origin = captures['relay'][0]
    for row, decoded in valid['relay']:
        ingress = row['destination'][1] == 5055
        prefixes = _prefixes(row['payload'])
        senders = [_unique(sessions if ingress else players, prefix) for prefix in prefixes]
        if ingress:
            # Only a datagram with one unambiguous sender can establish a tuple.
            sender_roles = set(senders)
            if len(sender_roles) == 1 and 'unknown' not in sender_roles:
                sender = senders[0]
                endpoint = row['source']
                if sender in current_endpoints and current_endpoints[sender] != endpoint:
                    changes[sender] += 1
                current_endpoints[sender] = endpoint
                endpoint_roles.setdefault(endpoint, set()).add(sender)
            target, seen = 'relay', None
        else:
            target = _unique(endpoint_roles, row['destination'])
            seen = row['payload'] in received[target] if target in ROLES else None
        for sender, record in zip(senders, decoded):
            # Explicit allowlist; no raw decoder dictionaries escape this scope.
            report.append({'t': (row['timestamp'] - origin) / 1_000_000,
                           'kind': 'ingress' if ingress else 'egress',
                           'sender': sender, 'target': target,
                           'sequence': record['sequence'], 'xy': [record['x'], record['y']],
                           'seen_in_destination_capture': seen})
    return {'capture_packet_counts': {name: capture[1] for name, capture in captures.items()},
            'source_endpoint_changes': changes,
            'malformed_payload_counts': malformed,
            'records': report, 'limitations': LIMITATIONS}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('relay', type=Path)
    parser.add_argument('primary', type=Path)
    parser.add_argument('peer', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        report = compare(args.relay, args.primary, args.peer)
    except ValueError as error:
        parser.exit(2, f'{error}\n')
    args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"Exported {len(report['records'])} sanitized relay records")


if __name__ == '__main__':
    main()

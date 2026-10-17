"""Summarize classic little-endian Linux-cooked IPv4 UDP captures safely.

Exports timing, direction, sequence numbers and coordinates only. Original
captures contain credentials and must remain private. No fragment reassembly,
checksum validation, delivery inference or identity correlation is performed.
"""
import argparse
import json
from pathlib import Path
import struct

from udp_codec import decode_datagram


LIMITATIONS = (
    'Classic little-endian microsecond PCAP, Linux cooked v1 (113), IPv4 only. '
    'Malformed/truncated headers and IP fragments are rejected; malformed '
    'placement payloads are counted without decoding. Checksums are not checked. '
    'Only UDP involving port 5055 is listed; outbound requires the emulator host '
    'destination and inbound requires source port 5055. Other matching traffic '
    'is labeled other. Times are relative to the first captured packet, including '
    'unlisted traffic. Empty captures do not establish idle behavior. Capture '
    'observation does not prove application receipt or peer visibility. '
    'Identifiers, payload bytes and addresses are omitted; records are not '
    'correlated across packets or peers.'
)


def summarize(path):
    data = Path(path).read_bytes()
    if len(data) < 24:
        raise ValueError('Truncated PCAP global header')
    if data[:4] != b'\xd4\xc3\xb2\xa1':
        raise ValueError('Expected classic little-endian microsecond PCAP')
    _, major, minor, _, _, snaplen, linktype = struct.unpack_from('<IHHIIII', data)
    if (major, minor) != (2, 4) or linktype != 113 or snaplen == 0:
        raise ValueError('Expected PCAP 2.4 with Linux cooked link type 113 and positive snaplen')

    directions = {name: {'packet_count': 0, 'record_count': 0,
                         'malformed_payload_count': 0,
                         'first_offset_seconds': None, 'last_offset_seconds': None}
                  for name in ('outbound', 'inbound', 'other')}
    packets = []
    pos, times = 24, []
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
        times.append(timestamp)
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
        if source != 5055 and destination != 5055:
            continue
        direction = ('outbound' if destination == 5055 and ip[16:20] == b'\x0a\x00\x02\x02'
                     else 'inbound' if source == 5055 else 'other')
        offset = (timestamp - times[0]) / 1_000_000
        stats = directions[direction]
        stats['packet_count'] += 1
        if stats['first_offset_seconds'] is None:
            stats['first_offset_seconds'] = offset
        stats['last_offset_seconds'] = offset
        try:
            records = decode_datagram(udp[8:])
        except ValueError:
            stats['malformed_payload_count'] += 1
            records = []
        stats['record_count'] += len(records)
        # Explicit allowlist: never serialize decoder dictionaries or raw data.
        packets.append({'t': offset, 'direction': direction,
                        'sequence': [row['sequence'] for row in records],
                        'xy': [[row['x'], row['y']] for row in records]})
    return {'capture_packet_count': len(times),
            'capture_span_seconds': (max(times) - min(times)) / 1_000_000 if times else 0,
            'directions': directions, 'packets': packets, 'limitations': LIMITATIONS}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pcap', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        report = json.dumps(summarize(args.pcap), indent=2) + '\n'
    except ValueError as error:
        parser.exit(2, f'{error}\n')
    if args.output:
        args.output.write_text(report, encoding='utf-8', newline='\n')
    print(report, end='')

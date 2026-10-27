"""Read-only Android 2.41.0 UDP placement decoder; no listener or relay."""
import argparse
import json
from pathlib import Path
import struct
import uuid


def history_coords(x, y, raw):
    bits = int.from_bytes(raw, 'little')
    count = bits >> 12
    # The client returns an empty history for counts above six.
    if count > 6:
        return []
    history = []
    for index in range(count):
        step = (bits >> (2 * index)) & 3
        delta = -1 if step & 1 else 1
        if step & 2:
            y += delta
        else:
            x += delta
        history.append([x, y])
    return history


def is_newer(new, old):
    if not (0 <= new <= 255 and 0 <= old <= 255):
        raise ValueError('Sequence numbers must be bytes')
    # Preserve the client's asymmetric half-range boundary (max=255).
    return (new > old and new - old <= 127) or (old > new and old - new > 127)


def decode_datagram(data):
    if not data or len(data) % 24:
        raise ValueError('Expected one or more 24-byte placement records')
    records = []
    for offset in range(0, len(data), 24):
        raw = bytes(data[offset:offset + 24])
        seq, x, y = struct.unpack_from('>BHH', raw, 16)
        records.append({'net_id': str(uuid.UUID(bytes=raw[:16])), 'sequence': seq,
                        'x': x, 'y': y, 'history_bytes': raw[21:23].hex(),
                        'history': history_coords(x, y, raw[21:23]), 'direction': raw[23]})
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('datagram', type=Path, help='Raw UDP payload file, not a PCAP')
    args = parser.parse_args()
    records = decode_datagram(args.datagram.read_bytes())
    # Outbound IDs are session credentials, so CLI output never includes them.
    for record in records:
        record['net_id'] = '<redacted>'
    print(json.dumps(records, indent=2))

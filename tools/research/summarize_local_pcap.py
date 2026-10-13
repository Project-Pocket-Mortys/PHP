"""Sanitized HTTP/SSE summary of bounded emulator Linux-cooked IPv4 PCAPs.

Not a general TCP analyzer: rejects fragmented IP and gaps between payload
segments. Sequence wrap is unsupported. Keep original captures ignored.
"""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import struct
from urllib.parse import urlsplit


def summarize(path):
    data = path.read_bytes()
    if data[:4] != b'\xd4\xc3\xb2\xa1' or struct.unpack_from('<I', data, 20)[0] != 113:
        raise ValueError('Expected little-endian PCAP with Linux cooked link type 113')
    streams = defaultdict(list)
    pos, times = 24, []
    while pos < len(data):
        sec, usec, length, original = struct.unpack_from('<IIII', data, pos)
        pos += 16
        packet = data[pos:pos+length]; pos += length
        if length != original or len(packet) != length:
            raise ValueError('Truncated packet')
        times.append(sec + usec / 1e6)
        if packet[14:16] != b'\x08\x00':
            continue
        ip = packet[16:]
        if ip[9] != 6:
            continue
        if int.from_bytes(ip[6:8], 'big') & 0x3fff:
            raise ValueError('Fragmented IPv4 is unsupported')
        total = int.from_bytes(ip[2:4], 'big')
        tcp = ip[(ip[0] & 15)*4:total]
        src, dst, seq = struct.unpack_from('>HHI', tcp)
        payload = tcp[(tcp[12] >> 4)*4:]
        if payload:
            key = (ip[12:16], ip[16:20], src, dst)
            streams[key].append((seq, payload))
    result = []
    for key, chunks in streams.items():
        chunks.sort(key=lambda row: row[0])
        base = chunks[0][0]; merged = bytearray()
        for seq, payload in chunks:
            offset = seq - base
            if offset > len(merged):
                raise ValueError('TCP payload gap; extend capture or inspect raw PCAP locally')
            overlap = min(len(payload), len(merged) - offset)
            if merged[offset:offset+overlap] != payload[:overlap]:
                raise ValueError('Conflicting retransmission')
            merged.extend(payload[overlap:])
        text = bytes(merged).decode('latin1')
        requests = []
        for match in re.finditer(r'(GET|POST|OPTIONS) ([^\r\n ]+) HTTP/1\.[01]\r\n(.*?)\r\n\r\n', text, re.S):
            headers = match[3].lower()
            requests.append({'method': match[1], 'path': urlsplit(match[2]).path,
                             'has_last_event_id': '\r\nlast-event-id:' in '\r\n'+headers,
                             'has_since_query': bool(re.search(r'[?&]since=', match[2]))})
        events = re.findall(r'(?:^|\n)event: ([a-zA-Z0-9:_-]+)\r?\n', text)
        if requests or events:
            result.append({'direction': 'to_backend' if key[3] == 8087 else 'from_backend',
                           'requests': requests, 'events': events,
                           'has_sse_id_field': bool(re.search(r'(?:^|\n)id:', text))})
    stamp = lambda t: datetime.fromtimestamp(t, timezone.utc).isoformat()
    return {'capture_start_utc': stamp(min(times)) if times else None,
            'capture_end_utc': stamp(max(times)) if times else None,
            'streams': result,
            'limitations': 'Per-direction TCP order only; partial initial streams possible. Query strings, header values, bodies, addresses and identifiers omitted.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('pcap', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = json.dumps(summarize(args.pcap), indent=2) + '\n'
    if args.output:
        args.output.write_text(report, newline='\n')
    print(report)

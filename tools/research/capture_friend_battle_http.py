"""Capture or decode a real Android friend Battle request; never sends invitations.

PCAPs, reconstructed streams and account identifiers stay in ignored .research.
Only the sanitized observed contract is printed. Classic PCAP, IPv4 TCP and
Ethernet/Linux cooked links are supported; ambiguous overlaps/gaps fail closed.
"""
import argparse
import hashlib
import ipaddress
import json
import re
import struct
import subprocess
import uuid
from pathlib import Path

import probe_android_peers as peers

ROOT = peers.ROOT
TARGET = b'POST /session/battle-invite/create HTTP/1.1\r\n'


def packets(path):
    data = path.read_bytes()
    assert len(data) >= 24, 'Truncated PCAP'
    magic = data[:4]
    assert magic in (b'\xd4\xc3\xb2\xa1', b'\xa1\xb2\xc3\xd4', b'\x4d\x3c\xb2\xa1', b'\xa1\xb2\x3c\x4d'), 'Require classic PCAP'
    endian = '<' if magic in (b'\xd4\xc3\xb2\xa1', b'\x4d\x3c\xb2\xa1') else '>'
    link = struct.unpack_from(endian+'I', data, 20)[0]
    assert link in (1, 113, 276), 'Unsupported PCAP link type'
    pos = 24
    while pos < len(data):
        assert pos+16 <= len(data), 'Truncated packet header'
        _, _, size, original = struct.unpack_from(endian+'IIII', data, pos)
        pos += 16
        assert size == original and pos+size <= len(data), 'Truncated capture packet'
        packet = data[pos:pos+size]
        pos += size
        offset = {1: 14, 113: 16, 276: 20}[link]
        protocol = packet[12:14] if link == 1 else packet[14:16] if link == 113 else packet[:2]
        if protocol != b'\x08\x00':
            continue
        ip = packet[offset:]
        assert len(ip) >= 20 and ip[0] >> 4 == 4
        if ip[9] != 6:
            continue
        assert struct.unpack_from('!H', ip, 6)[0] & 0x3fff == 0, 'IP fragmentation unsupported'
        ihl, total = (ip[0] & 15)*4, struct.unpack_from('!H', ip, 2)[0]
        assert len(ip) >= total and ihl >= 20
        tcp = ip[ihl:total]
        assert len(tcp) >= 20
        source, target, seq, ack = struct.unpack_from('!HHII', tcp)
        header = (tcp[12] >> 4)*4
        assert 20 <= header <= len(tcp)
        if source != 8087 and target != 8087:
            continue
        payload = tcp[header:]
        if payload:
            key = (str(ipaddress.ip_address(ip[12:16])), source, str(ipaddress.ip_address(ip[16:20])), target)
            yield key, seq, ack, payload


def runs(segments):
    """Yield contiguous TCP byte runs; verify retransmissions instead of joining gaps."""
    ordered = sorted(segments, key=lambda row: row[0])
    start, content, spans = None, bytearray(), []
    for seq, ack, payload in ordered:
        if start is None or seq > start+len(content):
            if start is not None:
                yield start, bytes(content), spans
            start, content, spans = seq, bytearray(), []
        offset = seq-start
        overlap = min(len(payload), len(content)-offset)
        assert bytes(content[offset:offset+overlap]) == payload[:overlap], 'Contradictory TCP overlap'
        content.extend(payload[overlap:])
        spans.append((seq, seq+len(payload), ack))
    if start is not None:
        yield start, bytes(content), spans


def message(data, offset):
    end = data.find(b'\r\n\r\n', offset)
    assert end >= 0, 'Incomplete HTTP headers'
    lines = data[offset:end].decode('ascii').split('\r\n')
    headers = {}
    for line in lines[1:]:
        key, value = line.split(':', 1)
        key = key.lower()
        assert key not in headers, 'Duplicate HTTP header'
        headers[key] = value.strip()
    assert 'transfer-encoding' not in headers, 'Target message must use Content-Length'
    size = int(headers['content-length'])
    finish = end+4+size
    assert finish <= len(data), 'Incomplete HTTP body'
    return lines[0], headers, data[end+4:finish], finish


def decode(path, output):
    flows = {}
    for key, seq, ack, payload in packets(path):
        flows.setdefault(key, []).append((seq, ack, payload))
    found = []
    raw = []
    for key, segments in flows.items():
        if key[3] != 8087:
            continue
        for start, stream, _ in runs(segments):
            raw.append(stream.decode('latin1'))
            for match in re.finditer(re.escape(TARGET), stream):
                _, headers, body, finish = message(stream, match.start())
                request = json.loads(body)
                assert set(request) == {'session_id', 'opponent_player_id', 'battle_type'}
                assert request['battle_type'] == 'PvF'
                assert all(isinstance(request[k], str) and request[k] for k in request)
                responses = []
                reverse = (key[2], key[3], key[0], key[1])
                for rstart, response_stream, spans in runs(flows.get(reverse, [])):
                    raw.append(response_stream.decode('latin1'))
                    for response in re.finditer(rb'HTTP/1\.[01] [0-9]{3} [^\r\n]*\r\n', response_stream):
                        absolute = rstart+response.start()
                        acks = {ack for lo, hi, ack in spans if lo <= absolute < hi}
                        if start+finish not in acks:
                            continue
                        assert acks == {start+finish}, 'Ambiguous response TCP acknowledgement'
                        status, response_headers, response_body, _ = message(response_stream, response.start())
                        responses.append((status, response_headers, response_body))
                assert len(responses) == 1, 'Require one complete response acknowledging exactly this request'
                status, response_headers, response_body = responses[0]
                assert status == 'HTTP/1.1 404 Not Found'
                assert response_headers['content-type'] == 'text/html; charset=iso-8859-1'
                assert b'The requested URL was not found on this server.' in response_body
                found.append(dict(evidence_kind='Observed Android request to isolated replacement server; not original-server evidence',
                    request=dict(method='POST', path='/session/battle-invite/create',
                        headers={k: headers[k] for k in ('x-pmclient', 'user-agent', 'content-type', 'host')},
                        original_wire_body_size_bytes=len(body),
                        body=dict(session_id='<redacted-session-id>', opponent_player_id='<redacted-opponent-player-id>', battle_type='PvF')),
                    response=dict(status=404, status_line=status,
                        content_type=response_headers['content-type'], body_size_bytes=len(response_body)),
                    pcap_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    assert len(found) == 1, 'Require exactly one native create request in capture'
    with (output/'reconstructed-http-private.txt').open('x', encoding='utf-8') as file:
        file.write('\n\n'.join(raw))
    with (output/'observed-sanitized.json').open('x', encoding='utf-8') as file:
        json.dump(found[0], file, indent=2)
        file.write('\n')
    return found[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--pcap', type=Path, help='Analyze existing capture without touching Android or database')
    source.add_argument('--capture', action='store_true', help='Capture primary; operator manually taps native Battle')
    parser.add_argument('--duration', type=int, default=45)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    assert 10 <= args.duration <= 45, 'Capture must remain bounded to at most 45 seconds'
    output = args.output.resolve()
    assert output.is_relative_to((ROOT/'.research').resolve()), 'Private artifacts must remain ignored'
    assert not output.exists(), 'Use fresh output directory'
    if args.pcap:
        path = args.pcap.resolve()
        assert path.is_relative_to((ROOT/'.research').resolve())
        output.mkdir(parents=True)
    else:
        assert peers.adb('primary', 'emu', 'avd', 'name').splitlines()[0].strip() == peers.DEVICES['primary'][1]
        assert peers.adb('primary', 'shell', 'id', '-u').strip() == '0'
        peers.adb('primary', 'shell', 'test', '-x', '/system/bin/tcpdump')
        output.mkdir(parents=True)
        remote = '/data/local/tmp/friend-battle-http-'+uuid.uuid4().hex+'.pcap'
        print('Capture starting: manually tap the native Friends Battle button now.', flush=True)
        result = subprocess.run(peers.adb_args('primary', 'shell', 'timeout', '-s', 'INT', str(args.duration),
            '/system/bin/tcpdump', '-i', 'any', '-s', '0', '-U', '-w', remote, 'tcp', 'port', '8087'),
            capture_output=True, timeout=args.duration+15, creationflags=peers.FLAGS)
        (output/'capture-status-private.txt').write_bytes(result.stdout+result.stderr)
        assert result.returncode in (0, 1, 124, 130), 'Capture failed; private status retained'
        path = output/'primary-http.pcap'
        peers.adb('primary', 'pull', remote, str(path))
    print(json.dumps(decode(path, output), indent=2))


if __name__ == '__main__':
    main()

import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/research'))
from summarize_udp_pcap import summarize


def placement(sequence=7, x=30, y=35):
    return bytes.fromhex('ffeeddccbbaa99887766554433221100') + struct.pack('>BHH', sequence, x, y) + bytes(3)


def frame(payload=None, source=40000, destination=5055, host=True, fragment=0, options=b''):
    payload = placement() if payload is None else payload
    ip = bytearray(20 + len(options))
    ip[0] = 0x40 | (len(ip) // 4)
    ip[9] = 17
    ip[2:4] = (len(ip) + 8 + len(payload)).to_bytes(2, 'big')
    ip[6:8] = fragment.to_bytes(2, 'big')
    ip[12:16] = b'\x0a\x00\x02\x0f'
    ip[16:20] = b'\x0a\x00\x02\x02' if host else b'\x0a\x00\x02\x03'
    ip[20:] = options
    return bytes(14) + b'\x08\x00' + ip + struct.pack('>HHHH', source, destination, 8 + len(payload), 0) + payload


def pcap(rows):
    data = struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 262144, 113)
    for usec, packet in rows:
        data += struct.pack('<IIII', 100 + usec // 1_000_000, usec % 1_000_000,
                            len(packet), len(packet)) + packet
    return data


class UdpPcapTests(unittest.TestCase):
    def summarize_bytes(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'capture.pcap'
            path.write_bytes(data)
            return summarize(path)

    def test_directions_timing_multiple_records_and_redaction(self):
        data = pcap([(0, frame(destination=53)),
                     (250000, frame(options=bytes(4))),
                     (750000, frame(placement(8) + placement(9, 31, 35), source=5055, destination=40000)),
                     (1000000, frame(host=False))])
        result = self.summarize_bytes(data)
        self.assertEqual(result['capture_packet_count'], 4)
        self.assertEqual(result['capture_span_seconds'], 1)
        self.assertEqual(result['packets'], [
            {'t': 0.25, 'direction': 'outbound', 'sequence': [7], 'xy': [[30, 35]]},
            {'t': 0.75, 'direction': 'inbound', 'sequence': [8, 9], 'xy': [[30, 35], [31, 35]]},
            {'t': 1, 'direction': 'other', 'sequence': [7], 'xy': [[30, 35]]}])
        self.assertEqual(result['directions']['inbound']['record_count'], 2)
        self.assertEqual(result['directions']['outbound']['first_offset_seconds'], 0.25)
        self.assertEqual(result['directions']['outbound']['last_offset_seconds'], 0.25)
        serialized = json.dumps(result)
        for secret in ('ffeeddcc', 'ffeeddcc-bbaa-9988-7766-554433221100', 'net_id', 'history_bytes', '10.0.2.'):
            self.assertNotIn(secret, serialized)

    def test_empty_capture_and_malformed_placement_are_explicit(self):
        empty = self.summarize_bytes(pcap([]))
        self.assertEqual(empty['capture_packet_count'], 0)
        self.assertEqual(empty['packets'], [])
        self.assertIsNone(empty['directions']['outbound']['first_offset_seconds'])
        result = self.summarize_bytes(pcap([(0, frame(b'secret payload')), (1, frame(b''))]))
        self.assertEqual(result['directions']['outbound']['malformed_payload_count'], 2)
        self.assertEqual(result['directions']['outbound']['packet_count'], 2)
        self.assertNotIn('secret', json.dumps(result))

    def test_rejects_unsupported_and_truncated_capture_containers(self):
        good = pcap([(0, frame())])
        variants = [b'', good[:23], b'\x0a\x0d\x0d\x0a' + good[4:],
                    good[:20] + struct.pack('<I', 1) + good[24:],
                    good[:24] + b'\x00', good[:-1]]
        bad_original = bytearray(good)
        struct.pack_into('<I', bad_original, 36, 999)
        variants.append(bad_original)
        bad_timestamp = bytearray(good)
        struct.pack_into('<I', bad_timestamp, 28, 1_000_000)
        variants.append(bad_timestamp)
        for data in variants:
            with self.subTest(length=len(data)), self.assertRaises(ValueError):
                self.summarize_bytes(data)

    def test_rejects_malformed_headers_lengths_and_fragments(self):
        packets = [b'', bytes(15), frame()[:30], frame(fragment=0x2000), frame(fragment=1)]
        for offset, replacement in ((16, b'\x44'), (18, b'\x00\x10'),
                                    (18, b'\xff\xff'), (40, b'\x00\x07'),
                                    (40, b'\x00\x09')):
            broken = bytearray(frame())
            broken[offset:offset + len(replacement)] = replacement
            packets.append(broken)
        for packet in packets:
            with self.subTest(length=len(packet)), self.assertRaises(ValueError):
                self.summarize_bytes(pcap([(0, packet)]))

    def test_cli_output_is_same_sanitized_report(self):
        with tempfile.TemporaryDirectory() as directory:
            capture, output = Path(directory) / 'input.pcap', Path(directory) / 'summary.json'
            capture.write_bytes(pcap([(0, frame())]))
            run = subprocess.run([sys.executable, str(ROOT / 'tools/research/summarize_udp_pcap.py'),
                                  str(capture), '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(run.stdout), json.loads(output.read_text()))
            self.assertNotIn('ffeeddcc', run.stdout)


if __name__ == '__main__':
    unittest.main()

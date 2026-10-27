import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/research'))
from compare_udp_hops import compare


def record(identity, seq=7):
    return bytes([identity]) * 16 + struct.pack('>BHH', seq, 30, 35) + bytes(3)


def frame(payload, source, destination, fragment=0):
    ip = bytearray(20)
    ip[0], ip[9] = 0x45, 17
    ip[2:4] = (28 + len(payload)).to_bytes(2, 'big')
    ip[6:8] = fragment.to_bytes(2, 'big')
    ip[12:16], ip[16:20] = source[0], destination[0]
    return bytes(14) + b'\x08\x00' + ip + struct.pack('>HHHH', source[1], destination[1], 8 + len(payload), 0) + payload


def pcap(rows):
    data = struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 262144, 113)
    for second, packet in rows:
        data += struct.pack('<IIII', 1000 + second, 0, len(packet), len(packet)) + packet
    return data


HOST = (b'\x0a\x00\x02\x02', 5055)
GUEST = (b'\x0a\x00\x02\x0f', 20123)
RELAY = (b'\xac\x15\x00\x02', 5055)
PRIMARY = (b'\xac\x15\x00\x01', 41001)
CHANGED = (PRIMARY[0], 41002)
PEER = (PRIMARY[0], 42001)


class UdpHopTests(unittest.TestCase):
    def compare_bytes(self, relay, primary=None, peer=None):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('relay.pcap', 'primary.pcap', 'peer.pcap')]
            for path, data in zip(paths, (relay, pcap([]) if primary is None else primary,
                                         pcap([]) if peer is None else peer)):
                path.write_bytes(data)
            return compare(*paths)

    def test_changed_source_stale_destination_and_private_export(self):
        first, second = record(0xaa), record(0xbb)
        player_primary, player_peer = record(0xcc), record(0xdd)
        primary = pcap([(0, frame(first, GUEST, HOST)), (1, frame(player_peer, HOST, GUEST))])
        peer = pcap([(0, frame(second, GUEST, HOST)), (1, frame(player_primary, HOST, GUEST))])
        relay = pcap([(0, frame(first, PRIMARY, RELAY)), (1, frame(second, PEER, RELAY)),
                      (2, frame(player_peer, RELAY, PRIMARY)),
                      (3, frame(first, CHANGED, RELAY)),
                      (4, frame(player_primary, RELAY, PEER)),
                      (5, frame(record(0xdd, 8), RELAY, PRIMARY))])
        report = self.compare_bytes(relay, primary, peer)
        self.assertEqual(report['source_endpoint_changes'], {'primary': 1, 'peer': 0})
        self.assertEqual([row['target'] for row in report['records']],
                         ['relay', 'relay', 'primary', 'relay', 'peer', 'primary'])
        self.assertEqual([row['sender'] for row in report['records']],
                         ['primary', 'peer', 'peer', 'primary', 'primary', 'peer'])
        self.assertEqual([row['seen_in_destination_capture'] for row in report['records']],
                         [None, None, True, None, True, False])
        self.assertEqual(report['records'][-1]['t'], 5)
        text = json.dumps(report)
        for secret in ('aaaaaaaa', 'bbbbbbbb', 'cccccccc', 'dddddddd', '10.0.2.',
                       '41001', '41002', '42001', 'payload_hash', 'net_id'):
            self.assertNotIn(secret, text)

    def test_unknown_or_conflicting_identity_does_not_invent_target_or_loss(self):
        known = record(0xaa)
        relay = pcap([(0, frame(known, PRIMARY, RELAY)), (1, frame(record(0xee), RELAY, PRIMARY))])
        shared = pcap([(0, frame(known, GUEST, HOST))])
        report = self.compare_bytes(relay, shared, shared)
        self.assertEqual(report['records'][0]['sender'], 'unknown')
        self.assertEqual(report['records'][1]['target'], 'unknown')
        self.assertIsNone(report['records'][1]['seen_in_destination_capture'])
        self.assertEqual(report['source_endpoint_changes'], {'primary': 0, 'peer': 0})

    def test_multiple_records_and_malformed_payloads(self):
        payload = record(0xaa) + record(0xaa, 8)
        report = self.compare_bytes(pcap([(0, frame(payload, PRIMARY, RELAY)),
                                          (1, frame(b'private invalid', PRIMARY, RELAY))]),
                                    pcap([(0, frame(payload, GUEST, HOST))]))
        self.assertEqual([row['sequence'] for row in report['records']], [7, 8])
        self.assertEqual(report['malformed_payload_counts']['relay'], 1)
        self.assertNotIn('private invalid', json.dumps(report))

    def test_invalid_capture_fails_for_any_input(self):
        valid = pcap([(0, frame(record(0xaa), PRIMARY, RELAY))])
        bad_length = bytearray(valid)
        struct.pack_into('>H', bad_length, 80, 7)  # UDP length in first frame.
        invalid = [b'', valid[:23], valid[:-1], valid[:24] + b'\x00',
                   valid[:20] + struct.pack('<I', 1) + valid[24:],
                   pcap([(0, frame(record(0xaa), PRIMARY, RELAY, fragment=0x2000))]),
                   pcap([(0, frame(record(0xaa), PRIMARY, RELAY, fragment=1))]), bad_length]
        for data in invalid:
            for position in range(3):
                captures = [valid, valid, valid]
                captures[position] = data
                with self.subTest(position=position, length=len(data)), self.assertRaises(ValueError):
                    self.compare_bytes(*captures)

    def test_cli_outputs_sanitized_report(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = [Path(directory) / name for name in ('relay.pcap', 'primary.pcap', 'peer.pcap')]
            for path in paths:
                path.write_bytes(pcap([]))
            output = Path(directory) / 'summary.json'
            run = subprocess.run([sys.executable, str(ROOT / 'tools/research/compare_udp_hops.py'),
                                  *map(str, paths), '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(output.read_text())['records'], [])


if __name__ == '__main__':
    unittest.main()

import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/research'))
from summarize_quiet_udp import summarize


def payload(x=29, y=35, sequence=0):
    return b'private-session!' + struct.pack('>BHH', sequence, x, y) + bytes(3)


def frame(data, source, destination):
    ip = bytearray(20)
    ip[0], ip[9] = 0x45, 17
    ip[2:4] = (28 + len(data)).to_bytes(2, 'big')
    ip[12:16], ip[16:20] = b'\xac\x14\x00\x01', b'\xac\x14\x00\x02'
    return bytes(14) + b'\x08\x00' + ip + struct.pack('>HHHH', source, destination, 8 + len(data), 0) + data


def pcap(rows):
    data = struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 262144, 113)
    for second, packet in rows:
        data += struct.pack('<IIII', 1000 + second, 0, len(packet), len(packet)) + packet
    return data


class QuietUdpPcapTests(unittest.TestCase):
    def summarize_bytes(self, data):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'probe.pcap'
            path.write_bytes(data)
            return summarize(path)

    def test_endpoint_change_totals_timeline_and_privacy(self):
        # Keep relay/client IPs consistent between ingress and egress.
        def egress(data, destination):
            packet = bytearray(frame(data, 5055, destination))
            packet[28:32], packet[32:36] = packet[32:36], packet[28:32]
            return packet
        data = pcap([(0, frame(payload(), 41001, 5055)),
                     (1, frame(payload(35), 42001, 5055)),
                     (1, egress(payload(35), 41001)),
                     (126, frame(payload(35, sequence=1), 42001, 5055)),
                     (126, egress(payload(35, sequence=1), 41001)),
                     (127, frame(payload(sequence=1), 41002, 5055)),
                     (127, egress(payload(sequence=1), 42001)),
                     (128, frame(payload(35, sequence=2), 42001, 5055)),
                     (128, egress(payload(35, sequence=2), 41002))])
        report = self.summarize_bytes(data)
        self.assertEqual(report['input_sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(report['source_endpoint_changes'], {'role0': 1, 'role1': 0})
        self.assertEqual(report['totals'], {'ingress_role0': 2, 'ingress_role1': 3,
                                          'egress_role0': 1, 'egress_role1': 3})
        self.assertEqual(report['events'][-1], {'t': 128, 'kind': 'egress', 'sender': 'role1',
                                               'target': 'role0', 'sequence': 2, 'xy': [35, 35]})
        text = json.dumps(report)
        for secret in ('private-session!', '70726976', '41001', '41002', '42001', 'net_id', '172.20.'):
            self.assertNotIn(secret, text)

    def test_rejects_unexpected_coordinates_partial_and_multiple_records(self):
        for packet in (payload(30), payload(y=34), payload()[:-1], b'', payload() * 2):
            with self.subTest(length=len(packet)), self.assertRaises(ValueError):
                self.summarize_bytes(pcap([(0, frame(packet, 41001, 5055))]))

    def test_rejects_overlapping_fixture_identity_instead_of_counting_endpoint_change(self):
        first = payload()
        replacement = b'another-session!' + first[16:]
        for source in (41001, 41002):
            with self.subTest(source=source), self.assertRaisesRegex(ValueError, 'Multiple probe identities') as error:
                self.summarize_bytes(pcap([(0, frame(first, 41001, 5055)),
                                           (125, frame(replacement, source, 5055))]))
            self.assertNotIn('private-session', str(error.exception))
            self.assertNotIn('another-session', str(error.exception))

    def test_strict_parser_rejects_truncation_and_unknown_target_stays_unknown(self):
        with self.assertRaises(ValueError):
            self.summarize_bytes(pcap([])[:-1])
        report = self.summarize_bytes(pcap([(0, frame(payload(), 5055, 41001))]))
        self.assertEqual(report['events'][0]['target'], 'unknown')

    def test_cli_and_empty_capture(self):
        with tempfile.TemporaryDirectory() as directory:
            capture, output = Path(directory) / 'input.pcap', Path(directory) / 'summary.json'
            capture.write_bytes(pcap([]))
            run = subprocess.run([sys.executable, str(ROOT / 'tools/research/summarize_quiet_udp.py'),
                                  str(capture), '--output', str(output)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertEqual(json.loads(output.read_text())['events'], [])


if __name__ == '__main__':
    unittest.main()

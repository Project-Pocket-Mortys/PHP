import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/research'))
from udp_codec import decode_datagram, is_newer
from sanitize_udp_trace import sanitize


class UdpCodecTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixture = json.loads((ROOT / 'tests/protocol/fixtures/udp-movement.json').read_text())
        cls.packets = [bytes.fromhex(row['hex']) for row in fixture['packets']]

    def test_recorded_movement_has_network_order_coordinates_and_guid(self):
        rows = decode_datagram(b''.join(self.packets))
        self.assertEqual([r['sequence'] for r in rows], list(range(2, 17)))
        self.assertEqual([(r['x'], r['y']) for r in rows],
                         [(30,35),(31,35),(31,34),(31,33),(31,32),(31,31),(31,30),
                          (30,30),(29,30),(28,30),(27,30),(27,31),(27,32),(27,33),(27,34)])
        self.assertEqual(rows[0]['net_id'], '00112233-4455-6677-8899-aabbccddeeff')
        self.assertEqual([r['direction'] for r in rows], [1,1,4,4,4,4,4,2,2,2,2,3,3,3,3])

    def test_history_recovers_previous_observed_positions(self):
        rows = decode_datagram(b''.join(self.packets))
        for index, row in enumerate(rows):
            count = min(index, len(row['history']))
            expected = [[r['x'], r['y']] for r in reversed(rows[index-count:index])]
            self.assertEqual(row['history'][:count], expected)

    def test_invalid_history_count_is_empty_as_in_client(self):
        raw = bytearray(self.packets[0]); raw[22] = 0xf0
        self.assertEqual(decode_datagram(raw)[0]['history'], [])

    def test_receiver_rejects_partial_or_empty_records(self):
        for raw in (b'', self.packets[0][:-1], self.packets[0] + b'\x00'):
            with self.assertRaises(ValueError):
                decode_datagram(raw)

    def test_sequence_wrap_duplicate_and_half_range(self):
        for new, old, expected in ((0,255,True),(255,0,False),(4,4,False),
                                   (127,0,True),(128,0,False),(0,128,True),(0,127,False)):
            self.assertEqual(is_newer(new, old), expected, (new, old))

    def test_trace_export_replaces_entire_session_guid(self):
        raw = bytes.fromhex('ffeeddccbbaa99887766554433221100') + self.packets[0][16:]
        encoded = ''.join('\\x%02x' % value for value in raw)
        result = sanitize(f'42 sendto(201, "{encoded}", 24, 0, NULL, 0) = -1 EPERM')
        self.assertEqual(bytes.fromhex(result['packets'][0]['hex']), self.packets[0])


if __name__ == '__main__':
    unittest.main()

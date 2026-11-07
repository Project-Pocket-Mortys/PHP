"""Boundary tests for private native startup capture decoding."""
import importlib.util
from pathlib import Path
import struct
import sys
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / 'tools/research/export_android_startup.py'
sys.path.insert(0, str(SOURCE.parent))
SPEC = importlib.util.spec_from_file_location('export_android_startup', SOURCE)
decoder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(decoder)


class StartupDecodeTests(unittest.TestCase):
    def test_sll_ipv4_both_ports_and_timestamp(self):
        data = struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 113)
        for port in (8087, 8089, 80):
            tcp = struct.pack('!HHIIBBHHH', 12345, port, 100, 200, 0x50, 0x18, 8192, 0, 0) + b'test'
            ip = bytearray(20)
            ip[0], ip[9] = 0x45, 6
            struct.pack_into('!H', ip, 2, 20 + len(tcp))
            ip[12:16], ip[16:20] = b'\x7f\0\0\1', b'\x7f\0\0\1'
            packet = bytes(14) + b'\x08\x00' + ip + tcp
            data += struct.pack('<IIII', 100, 250000, len(packet), len(packet)) + packet
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'test.pcap'
            path.write_bytes(data)
            rows = list(decoder.packets(path))
        self.assertEqual([row['key'][3] for row in rows], [8087, 8089])
        self.assertEqual(rows[0]['time'], 100.25)
        self.assertEqual(rows[0]['payload'], b'test')

    def test_reassembly_deduplicates_reorders_and_rejects_gaps_or_conflicts(self):
        def segment(seq, payload):
            return dict(seq=seq, ack=0, payload=payload)
        result = decoder.assemble([segment(103, b'def'), segment(100, b'abcd'), segment(100, b'abcd')])
        self.assertEqual(result[1], b'abcdef')
        with self.assertRaisesRegex(AssertionError, 'gap'):
            decoder.assemble([segment(100, b'ab'), segment(103, b'd')])
        with self.assertRaisesRegex(AssertionError, 'Contradictory'):
            decoder.assemble([segment(100, b'abc'), segment(101, b'XX')])

    def test_chunks_never_promote_truncated_chunk(self):
        body, _, terminal = decoder.chunks(b'3\r\nabc\r\n4\r\nde')
        self.assertEqual(body, b'abc')
        self.assertIsNone(terminal)
        self.assertEqual(decoder.chunks(b'3\r\nabc\r\n0\r\n\r\n')[2], 13)
        with self.assertRaisesRegex(AssertionError, 'boundary'):
            decoder.chunks(b'3\r\nabcXX')

    def test_midstream_first_frame_and_partial_trailing_frame_unobserved(self):
        body = b'event: battle:start\ndata: {}\n\nevent: session:end\ndata: {}\n\nevent: battle:start\ndata: {'
        frames = list(decoder.frames(body, skip_first=True))
        self.assertEqual([(row[2], row[3]) for row in frames], [('session:end', {})])

    def test_http_chunked_sse_and_incomplete_json(self):
        body = b'event: session:end\ndata: {}\n\n'
        wire = b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n'
        wire += f'{len(body):x}\r\n'.encode() + body + b'\r\n0\r\n\r\n'
        message = list(decoder.messages(wire))[0]
        self.assertTrue(message['sse'])
        self.assertEqual(list(decoder.frames(message['body']))[0][2], 'session:end')
        self.assertEqual(list(decoder.messages(b'HTTP/1.1 200 OK\r\nContent-Length: 5\r\n\r\n{}')), [])


if __name__ == '__main__':
    unittest.main()

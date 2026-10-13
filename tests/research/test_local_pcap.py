from pathlib import Path
import json
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/research'))
from summarize_local_pcap import summarize


def pcap(segments):
    output = struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 262144, 113)
    for sequence, payload in segments:
        link = bytes(14) + b'\x08\x00'
        ip = bytearray(20); ip[0] = 0x45; ip[9] = 6
        ip[2:4] = (40 + len(payload)).to_bytes(2, 'big')
        tcp = bytearray(20); struct.pack_into('>HHI', tcp, 0, 40000, 8087, sequence); tcp[12] = 0x50
        frame = link + ip + tcp + payload
        output += struct.pack('<IIII', 1, 0, len(frame), len(frame)) + frame
    return output


class CaptureSummaryTests(unittest.TestCase):
    def summarize(self, segments):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'capture.pcap'; path.write_bytes(pcap(segments))
            return summarize(path)

    def test_split_request_redacts_credentials_and_detects_resume(self):
        request = b'GET /sse/?token=private-token&since=123 HTTP/1.1\r\nAuthorization: private-auth\r\nLast-Event-ID: 123\r\n\r\n'
        report = self.summarize([(100,request[:40]), (140,request[40:])])
        serialized = json.dumps(report)
        self.assertNotIn('private-', serialized)
        self.assertNotIn('123', serialized)
        self.assertEqual(report['streams'][0]['requests'],
                         [{'method':'GET','path':'/sse/','has_last_event_id':True,'has_since_query':True}])

    def test_retransmission_is_not_counted_twice(self):
        data = b'GET /time HTTP/1.1\r\nHost: localhost\r\n\r\n'
        report = self.summarize([(100,data),(100,data)])
        self.assertEqual(len(report['streams'][0]['requests']), 1)

    def test_missing_payload_is_reported_not_silently_joined(self):
        with self.assertRaisesRegex(ValueError, 'gap'):
            self.summarize([(100,b'GET '),(110,b'/time')])


if __name__ == '__main__':
    unittest.main()

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/research'))
from summarize_udp_syscalls import summarize


class UdpSyscallTests(unittest.TestCase):
    def test_raw_lengths_relative_origin_and_descriptor_filter(self):
        report = summarize('\n'.join([
            '4801 1792252730.000000 recvfrom(0xbe, 0xdeadbeef, 0xfa0, 0x40, 0, 0) = 0x28',
            '4802 1792252865.125000 recvfrom(0xc9, 0xdeadbeef, 0xfa0, 0x40, 0, 0) = 0x18',
            '4802 1792252866.250000 sendto(201, 0xdeadbeef, 24, 0, 0, 0) = 24',
            '4802 1792252867.000000 recvfrom(201, 0xdeadbeef, 24, 0, 0, 0) = -1 EAGAIN (Try again)',
        ]), 201)
        self.assertEqual(report['events'], [
            {'offset_seconds': 135.125, 'syscall': 'recvfrom', 'bytes': 24},
            {'offset_seconds': 136.25, 'syscall': 'sendto', 'bytes': 24}])
        self.assertEqual(report['packet_events'], report['events'])
        self.assertEqual(report['summary']['recvfrom'], {
            'count': 1, 'bytes': 24, 'first_offset_seconds': 135.125, 'last_offset_seconds': 135.125})
        self.assertEqual(report['observed_span_seconds'], 137)
        exported = json.dumps(report)
        for secret in ('deadbeef', '1792252730', '4801', '0xc9', 'EAGAIN'):
            self.assertNotIn(secret, exported)

    def test_interleaved_unfinished_calls_matched_by_thread(self):
        report = summarize('\n'.join([
            '[pid 77] 1000.000000 recvfrom(0xc9, 0xabc, 24, 0, 0, 0 <unfinished ...>',
            '[pid 78] 1000.100000 recvfrom(0xbe, 0xdef, 24, 0, 0, 0 <unfinished ...>',
            '[pid 78] 1000.200000 <... recvfrom resumed>) = 0x18',
            '[pid 77] 1000.300000 <... recvfrom resumed>) = 0x18',
            '[pid 79] 1000.400000 <... recvfrom resumed>) = 0x18',
        ]), 201)
        self.assertEqual(report['events'], [
            {'offset_seconds': 0.3, 'syscall': 'recvfrom', 'bytes': 24}])

    def test_message_calls_are_counts_only_and_nonpositive_results_omitted(self):
        report = summarize('\n'.join([
            '1 1000.0 recvmsg(201, 0xabc, 0) = 24',
            '1 1001.0 recvmmsg(201, 0xabc, 2, 0, 0) = 2',
            '1 1002.0 sendmsg(201, 0xabc, 0) = 24',
            '1 1003.0 recvfrom(201, 0xabc, 24, 0, 0, 0) = 0',
            '1 1004.0 sendto(201, 0xabc, 24, 0, 0, 0) = -1 EPERM (Operation not permitted)',
            '1 1005.0 recvfrom(201, 0xabc, 40, 0, 0, 0) = 0x28',
        ]), 201)
        self.assertEqual(report['other_positive_completions'],
                         {'recvmsg': 1, 'sendmsg': 1, 'recvmmsg': 1})
        self.assertEqual(len(report['events']), 1)
        self.assertEqual(report['packet_events'], [])
        self.assertEqual(report['summary']['recvfrom']['bytes'], 40)

    def test_unprefixed_trace_and_empty_input(self):
        report = summarize('1000.000001 recvfrom(201, 0xabc, 24, 0, 0, 0) = 24', 201)
        self.assertEqual(report['events'][0]['offset_seconds'], 0)
        self.assertEqual(summarize('', 201)['events'], [])

    def test_negative_descriptor_rejected(self):
        with self.assertRaises(ValueError):
            summarize('', -1)


if __name__ == '__main__':
    unittest.main()

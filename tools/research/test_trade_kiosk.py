"""Pure synthetic-PCAP privacy and evidence-boundary checks; no DB/device."""
import json
from pathlib import Path
import struct
import tempfile
import unittest

import sanitize_trade_kiosk as kiosk
import test_trade_cookie_handoff as fixtures

http = fixtures.TradeCookieHandoffTests.http
packet = fixtures.TradeCookieHandoffTests.packet


class TradeKioskTests(unittest.TestCase):
    def capture(self, *, path='/trading/get-trades', native=True, status=200,
                ack_offset=0, duplicate=False, unexpected=False):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        private = 'private-player-and-session-marker'
        headers = {'Cookie': 'session_id=' + private}
        if native:
            headers.update({'X-PMClient': private, 'User-Agent': 'UnityApp/2.41.0 (Android)'})
        body = {'session_id': private, 'player_id': private}
        if unexpected:
            body[private] = private
        request = http(f'POST {path} HTTP/1.1', body, headers)
        response = http(f'HTTP/1.1 {status} Synthetic', {
            'trade_requests': [{'player_id': private}], 'trade_offers': [],
            'trade_mortys': [], 'trade_attacks': [], 'completed_trades': [],
            'player_cooldown_data': {'expiry': private}})
        frames = [packet(43000, 100, 500, request),
                  packet(43000, 500, 100 + len(request) + ack_offset, response, response=True)]
        if duplicate:
            frames.append(packet(43000, 500 + len(response), 100 + len(request), response, response=True))
        pcap = Path(directory.name) / 'synthetic.pcap'
        pcap.write_bytes(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1) + b''.join(frames))
        return pcap, private

    def test_nested_identifiers_and_headers_are_never_published(self):
        pcap, private = self.capture()
        result = kiosk.inspect(pcap)
        self.assertNotIn(private, json.dumps(result))
        self.assertEqual(result['reads'][0]['response_list_counts']['trade_requests'], 1)
        self.assertTrue(result['reads'][0]['exact_tcp_ack_pair'])

    def test_unexpected_keys_cannot_escape_as_output_keys(self):
        pcap, _ = self.capture(unexpected=True)
        with self.assertRaises(AssertionError):
            kiosk.inspect(pcap)

    def test_failed_or_unpaired_responses_cannot_prove_success(self):
        for kwargs in ({'status': 401}, {'ack_offset': 1}, {'duplicate': True}):
            with self.subTest(kwargs=kwargs):
                pcap, _ = self.capture(**kwargs)
                with self.assertRaises(AssertionError):
                    kiosk.inspect(pcap)

    def test_scripted_headers_cannot_prove_native_reads(self):
        pcap, _ = self.capture(native=False)
        with self.assertRaises(AssertionError):
            kiosk.inspect(pcap)

    def test_other_trading_posts_are_counted_without_payloads(self):
        pcap, private = self.capture(path='/trading/cancel-trade')
        result = kiosk.inspect(pcap)
        self.assertEqual(result['reads'], [])
        self.assertEqual(result['other_trading_post_count'], 1)
        self.assertNotIn(private, json.dumps(result))


if __name__ == '__main__':
    unittest.main()

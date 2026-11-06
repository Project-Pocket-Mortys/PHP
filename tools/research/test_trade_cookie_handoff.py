"""Pure local synthetic-PCAP checks; no device, capture, network, or DB access."""
import base64
import json
from pathlib import Path
import struct
import tempfile
import unittest

import sanitize_trade_cookie_handoff as handoff


class TradeCookieHandoffTests(unittest.TestCase):
    SECRET = 'synthetic-private-secret'
    SESSION = 'synthetic-private-session'
    PLAYER = 'synthetic-private-primary-player'
    TRADE = 'synthetic-private-trade-id'

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.fixture = self.directory / 'fixture.json'
        self.fixture.write_text(json.dumps({'before': {'accounts': [
            {'username': 'PMStartup01', 'player_id': self.PLAYER, 'secret': self.SECRET},
            {'username': 'PMStartup02', 'player_id': 'synthetic-secondary-player', 'secret': 'synthetic-secondary-secret'},
        ]}}), encoding='utf-8')

    @staticmethod
    def http(line, body, headers=None):
        payload = json.dumps(body).encode()
        fields = {'Content-Type': 'application/json', 'Content-Length': str(len(payload))}
        fields.update(headers or {})
        return (line + '\r\n' + ''.join(f'{key}: {value}\r\n' for key, value in fields.items()) + '\r\n').encode() + payload

    @staticmethod
    def packet(port, seq, ack, payload, response=False):
        client, server = b'\x0a\x00\x00\x02', b'\x0a\x00\x00\x01'
        source, target = (server, client) if response else (client, server)
        tcp = struct.pack('!HHIIBBHHH', *( (8087, port) if response else (port, 8087)),
                          seq, ack, 0x50, 0x18, 65535, 0, 0)
        ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20 + len(tcp) + len(payload),
                         0, 0, 64, 6, 0, source, target)
        ethernet = bytes(12) + b'\x08\x00'
        frame = ethernet + ip + tcp + payload
        return struct.pack('<IIII', 0, 0, len(frame), len(frame)) + frame

    def capture(self, *, outbound=True, cookie=True, trade_session=None, claim_session=None,
                claim_player=None, claim_username='PMStartup01', login_status=200,
                login_ack_offset=0, duplicate_response=False, native_headers=True, trading_status=200):
        claims = {'player_id': claim_player or self.PLAYER, 'username': claim_username,
                  'session_id': claim_session or self.SESSION}
        encoded = base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')
        token = 'synthetic-header.' + encoded + '.synthetic-signature'
        native = {'X-PMClient': 'synthetic-client', 'User-Agent': 'UnityApp/2.41.0 (Android)'}
        login = self.http('POST /user/login/ HTTP/1.1', {'secret': self.SECRET}, native)
        reply = self.http(f'HTTP/1.1 {login_status} Synthetic',
                          {'session_url': 'http://synthetic.invalid/sse/?token=' + token},
                          {'Set-Cookie': 'session_id=' + self.SESSION + '; Path=/trading/; HttpOnly; SameSite=Lax'})
        frames = [self.packet(42000, 100, 500, login),
                  self.packet(42000, 500, 100 + len(login) + login_ack_offset, reply, response=True)]
        if duplicate_response:
            frames.append(self.packet(42000, 500 + len(reply), 100 + len(login), reply, response=True))
        if outbound:
            headers = dict(native) if native_headers else {}
            if cookie:
                headers['Cookie'] = 'session_id=' + (trade_session or self.SESSION)
            trade = self.http('POST /trading/cancel-trade HTTP/1.1', {'trade_id': self.TRADE}, headers)
            response = self.http(f'HTTP/1.1 {trading_status} Synthetic', {'error': 'None'})
            frames.extend([self.packet(42001, 2000, 9000, trade),
                           self.packet(42001, 9000, 2000 + len(trade), response, response=True)])
        path = self.directory / 'synthetic.pcap'
        path.write_bytes(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1) + b''.join(frames))
        return path, token

    def test_complete_native_handoff_outputs_only_redacted_proof(self):
        pcap, token = self.capture()
        result = handoff.inspect(pcap, self.fixture)
        serialized = json.dumps(result)
        for private in (self.SECRET, self.SESSION, self.PLAYER, self.TRADE, token):
            self.assertNotIn(private, serialized)
        self.assertEqual(result['primary_login_count'], 1)
        self.assertEqual(result['set_cookie'], {'name': 'session_id', 'path': '/trading/', 'httponly': True,
                                             'samesite': 'Lax', 'secure_values': [False]})
        self.assertEqual(result['trading_requests'], [
            {'method': 'POST', 'path': '/trading/cancel-trade', 'response_status': 200,
             'body_keys': ['trade_id'], 'cookie_matches_primary_login': True,
             'exact_tcp_ack_pair': True, 'native_headers_present': True}])

    def test_login_without_outgoing_trading_cookie_is_insufficient(self):
        for options in ({'outbound': False}, {'cookie': False}):
            with self.subTest(options=options):
                pcap, _ = self.capture(**options)
                with self.assertRaises(AssertionError):
                    handoff.inspect(pcap, self.fixture)

    def test_wrong_primary_identity_or_session_is_rejected(self):
        for options in ({'claim_player': 'synthetic-secondary-player'}, {'claim_username': 'PMStartup02'},
                        {'claim_session': 'other-login-session'}, {'trade_session': 'other-outbound-session'}):
            with self.subTest(options=options):
                pcap, _ = self.capture(**options)
                with self.assertRaises(AssertionError):
                    handoff.inspect(pcap, self.fixture)

    def test_failed_unacknowledged_or_ambiguous_login_is_rejected(self):
        for options in ({'login_status': 401}, {'login_ack_offset': 1}, {'duplicate_response': True}):
            with self.subTest(options=options):
                pcap, _ = self.capture(**options)
                with self.assertRaises(AssertionError):
                    handoff.inspect(pcap, self.fixture)

    def test_scripted_trading_headers_cannot_prove_native_handoff(self):
        pcap, _ = self.capture(native_headers=False)
        with self.assertRaises(AssertionError):
            handoff.inspect(pcap, self.fixture)

    def test_trading_rejection_still_proves_outgoing_cookie_transport(self):
        # This helper proves cookie transport; authorization is separate evidence.
        pcap, _ = self.capture(trading_status=401)
        result = handoff.inspect(pcap, self.fixture)
        self.assertEqual(result['trading_requests'][0]['response_status'], 401)
        self.assertTrue(result['trading_requests'][0]['cookie_matches_primary_login'])


if __name__ == '__main__':
    unittest.main()

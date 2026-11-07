"""Synthetic read-only proof checks; no live capture, device, server, or DB."""
import base64
from datetime import datetime, timezone
import hashlib
import json
import struct
import tempfile
from pathlib import Path
import unittest

import sanitize_onetrust_startup as receipt
import test_trade_cookie_handoff as synthetic


class OnetrustStartupSanitizerTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.fixture = self.directory / 'fixture.json'
        self.fixture.write_text(json.dumps({'before': {'accounts': [dict(
            username='PMStartup01', player_id=synthetic.TradeCookieHandoffTests.PLAYER, secret=synthetic.TradeCookieHandoffTests.SECRET)]}}))

    def capture(self, *, ack_offset=0, player=synthetic.TradeCookieHandoffTests.PLAYER, fresh_failure=False, statuses=(503, 204)):
        claims = dict(player_id=player, username='PMStartup01', session_id=synthetic.TradeCookieHandoffTests.SESSION)
        token = 'synthetic.' + base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=') + '.signature'
        native = {'X-PMClient': 'synthetic', 'User-Agent': 'UnityApp/2.41.0 (Android)'}
        frames = []

        def exchange(path, request, reply, status=200, headers=native, offset=0):
            port = 42000 + len(frames)
            data = synthetic.TradeCookieHandoffTests.http('POST ' + path + ' HTTP/1.1', request, headers)
            response = synthetic.TradeCookieHandoffTests.http('HTTP/1.1 ' + str(status) + ' Synthetic', reply)
            frames.extend([synthetic.TradeCookieHandoffTests.packet(port, 100, 1000, data),
                           synthetic.TradeCookieHandoffTests.packet(port, 1000, 100 + len(data) + offset, response, response=True)])

        for status in statuses:
            port = 42000 + len(frames)
            request = b'GET /_research/online HTTP/1.1\r\nHost: synthetic.invalid\r\n\r\n'
            response = ('HTTP/1.1 ' + str(status) + ' Synthetic\r\nContent-Length: 0\r\n\r\n').encode()
            frames.extend([synthetic.TradeCookieHandoffTests.packet(port, 100, 1000, request),
                           synthetic.TradeCookieHandoffTests.packet(port, 1000, 100 + len(request), response, response=True)])
        exchange('/user/login/', dict(secret=synthetic.TradeCookieHandoffTests.SECRET),
                 dict(session_url='http://synthetic.invalid/sse/?token=' + token), offset=ack_offset)
        exchange('/session/player-details', dict(session_id=synthetic.TradeCookieHandoffTests.SESSION),
                 dict(player_id=synthetic.TradeCookieHandoffTests.PLAYER, username='PMStartup01'))
        exchange('/session/join-room', dict(session_id=synthetic.TradeCookieHandoffTests.SESSION, world_id='synthetic-world'),
                 dict(room_id='synthetic-room', users=[]))
        session = synthetic.TradeCookieHandoffTests.http('GET /sse/?token=' + token + ' HTTP/1.1', {}, native)
        frames.append(synthetic.TradeCookieHandoffTests.packet(45000, 100, 1000, session))
        epoch = 1794000000
        frames = [struct.pack('<II', epoch + i, 0) + frame[8:] for i, frame in enumerate(frames)]
        pcap = self.directory / 'primary-http.pcap'
        pcap.write_bytes(struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1) + b''.join(frames))
        stamp = lambda second: datetime.fromtimestamp(second, timezone.utc).isoformat()
        manifest = dict(role='primary', finished_utc=stamp(epoch + 30), failure=None,
                        started_utc=stamp(epoch - 1), capture_ended_utc=stamp(epoch + 20),
                        pull_exit_code=0, logcat_exit_code=0,
                        pcap_sha256=hashlib.sha256(pcap.read_bytes()).hexdigest(),
                        apk=dict(version='2.41.0', source_apk_sha256={'base.apk': 'a' * 64},
                                 installed_apk_sha256={'base.apk': 'a' * 64}))
        (self.directory / 'manifest.json').write_text(json.dumps(manifest))
        lines = [f'{epoch - 2}.000 1 1 I Synthetic: capture coverage',
                 f'{epoch + 20}.000 1 1 I Synthetic: capture coverage']
        if fresh_failure:
            lines.append(f'{epoch + 1}.000 1 1 E Unity: at OneTrust.CMPSDK.get_domainData_Groups ()')
        else:
            lines.append(f'{epoch - 5}.000 1 1 E Unity: at OneTrust.CMPSDK.get_domainData_Groups ()')
        (self.directory / 'logcat-private.txt').write_text('\n'.join(lines))
        return token

    def test_complete_recovery_receipt_is_redacted_and_old_exceptions_are_excluded(self):
        token = self.capture()
        report = receipt.inspect(self.directory, self.fixture)
        encoded = json.dumps(report)
        for private in (synthetic.TradeCookieHandoffTests.SECRET, synthetic.TradeCookieHandoffTests.SESSION, synthetic.TradeCookieHandoffTests.PLAYER, token, 'synthetic-room', 'synthetic-world'):
            self.assertNotIn(private, encoded)
        self.assertEqual(report['online_probe_statuses'], [503, 204])
        self.assertEqual(report['fresh_onetrust_domain_data_exception_count'], 0)
        self.assertEqual(report['player_details_count'], 1)
        self.assertEqual(report['world_join_count'], 1)

    def test_mismatched_ack_or_identity_and_wrong_probe_sequence_are_rejected(self):
        for options in ({'ack_offset': 1}, {'player': 'wrong-player'}, {'statuses': (204, 204)}):
            with self.subTest(options=options):
                self.capture(**options)
                with self.assertRaises(AssertionError):
                    receipt.inspect(self.directory, self.fixture)

    def test_later_native_connectivity_check_preserves_exact_observed_sequence(self):
        self.capture(statuses=(503, 204, 204))
        self.assertEqual(receipt.inspect(self.directory, self.fixture)['online_probe_statuses'],
                         [503, 204, 204])

    def test_fresh_exception_and_incomplete_manifest_are_rejected(self):
        self.capture(fresh_failure=True)
        with self.assertRaises(AssertionError):
            receipt.inspect(self.directory, self.fixture)
        self.capture()
        path = self.directory / 'manifest.json'
        manifest = json.loads(path.read_text())
        manifest.pop('finished_utc')
        path.write_text(json.dumps(manifest))
        with self.assertRaises(AssertionError):
            receipt.inspect(self.directory, self.fixture)


if __name__ == '__main__':
    unittest.main()

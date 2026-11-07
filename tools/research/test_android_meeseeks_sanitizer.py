"""Synthetic exporter checks; no database, Android, server, or original service."""
import copy
import json
from pathlib import Path
import socket
import struct
import tempfile
import unittest
from unittest.mock import patch

import sanitize_android_meeseeks as proof


class AndroidMeeseeksProofTests(unittest.TestCase):
    def setUp(self):
        self.fixture = dict(before=dict(user=dict(session_id='private-session'), items=[]),
                            active='private-clone')
        self.case = dict(battle_id='private-battle',
                         session_id_sha256=proof.hashlib.sha256(b'private-session').hexdigest())
        self.body = dict(session_id='private-session', battle_id='private-battle',
                         type='ITEM', owned_morty_id='private-clone', move_id=proof.ITEM)

    def wire_packets(self, body=None, headers=None):
        body = json.dumps(self.body).encode() if body is None else body
        headers = (b'User-Agent: UnityApp/2.41.0 (Android)\r\nX-PMClient: private-value\r\n'
                   b'Content-Type: application/json\r\n') if headers is None else headers
        request = b'POST /session/battle/move HTTP/1.1\r\n' + headers
        request += b'Content-Length: ' + str(len(body)).encode() + b'\r\n\r\n' + body
        response = b'HTTP/1.1 200 OK\r\nContent-Length: 16\r\n\r\n{"success":true}'
        key = ('192.0.2.1', 50000, '192.0.2.2', 8087)
        reverse = (key[2], key[3], key[0], key[1])
        return [(key, 100, 1, request), (reverse, 200, 100 + len(request), response)]

    def parse(self, packets):
        with patch.object(proof, 'packets', return_value=packets), \
             patch.object(proof, 'capture_packet_times', return_value=list(range(len(packets)))):
            return proof.exchanges(Path('unused'))

    def test_native_request_is_exactly_bound_to_fixture(self):
        row = self.parse(self.wire_packets())[0]
        proof.wire(row, self.fixture, self.case)
        mutations = [lambda r: r['request'].update(session_id='foreign'),
                     lambda r: r['request'].update(battle_id='foreign'),
                     lambda r: r['request'].update(owned_morty_id='enemy'),
                     lambda r: r['request'].update(move_id='ItemAttack'),
                     lambda r: r['request'].update(type=2),
                     lambda r: r['request'].update(nonce='extra'),
                     lambda r: r.update(status=True),
                     lambda r: r['response'].update(success=1),
                     lambda r: r['response'].update(extra='private')]
        for number, mutate in enumerate(mutations):
            with self.subTest(case=number):
                changed = copy.deepcopy(row)
                mutate(changed)
                with self.assertRaises(ValueError): proof.wire(changed, self.fixture, self.case)

    def test_parser_rejects_missing_headers_duplicate_moves_ack_ambiguity_and_bad_json(self):
        packets = self.wire_packets()
        key, seq, ack, response = packets[1]
        bad = [packets[:1], packets[:1] + [(key, seq, ack + 1, response)],
               packets + [(key, seq, ack + 1, response)],
               packets + [(key, seq + len(response), ack, response)], list(reversed(packets)),
               self.wire_packets(headers=b'Content-Type: application/json\r\n'),
               self.wire_packets(body=b'{"type":"ITEM","type":"ATTACK"}'),
               self.wire_packets(body=b'{"value":NaN}')]
        qkey, qseq, qack, request = packets[0]
        bad.append(packets + [(qkey, qseq + len(request), qack, request),
                              (key, seq + len(response), qseq + 2 * len(request), response)])
        split = len(request) // 2
        bad.append([(qkey, qseq, qack, request[:split]), packets[1],
                    (qkey, qseq + split, qack, request[split:])])
        for number, changed in enumerate(bad):
            with self.subTest(case=number):
                with self.assertRaises((ValueError, AssertionError)): self.parse(changed)

    def test_real_classic_pcap_path_preserves_native_packet_proof(self):
        header = struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1)
        frames = []
        for seconds, (key, seq, ack, body) in enumerate(self.wire_packets(), 1):
            tcp = struct.pack('!HHIIBBHHH', key[1], key[3], seq, ack, 0x50, 0x18, 65535, 0, 0) + body
            ip = struct.pack('!BBHHHBBH4s4s', 0x45, 0, 20 + len(tcp), 1, 0, 64, 6, 0,
                             socket.inet_aton(key[0]), socket.inet_aton(key[2])) + tcp
            frame = b'\0' * 12 + b'\x08\x00' + ip
            frames.append(struct.pack('<IIII', seconds, 0, len(frame), len(frame)) + frame)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'synthetic.pcap'
            path.write_bytes(header + b''.join(frames))
            row = proof.exchanges(path)[0]
            proof.wire(row, self.fixture, self.case)
            self.assertEqual((row['request_time'], row['response_time']), (10**9, 2 * 10**9))

    def test_additive_inventory_allocation_and_absolute_remainder(self):
        allocated = dict(items=[dict(id=1, item_id=proof.ITEM, quantity=1)])
        self.assertEqual(proof.stock_quantities(self.fixture, allocated), (1, 0))
        fixture = copy.deepcopy(self.fixture)
        fixture['before']['items'] = [dict(id=1, item_id=proof.ITEM, quantity=4)]
        allocated['items'][0]['quantity'] = 5
        self.assertEqual(proof.stock_quantities(fixture, allocated), (5, 4))
        for quantity in (4, 6, True):
            allocated['items'][0]['quantity'] = quantity
            with self.assertRaises(ValueError): proof.stock_quantities(fixture, allocated)

    def review_fixture(self, directory):
        manifest, screens = dict(screenshots=[]), []
        for index, role in enumerate(sorted(proof.SCREEN_ROLES)):
            path = directory / ('frame-' + str(index) + '.png')
            path.write_bytes(b'\x89PNG\r\n\x1a\n' + bytes([index]))
            sample = dict(file=path.name, sha256=proof.digest(path))
            manifest['screenshots'].append(sample)
            screens.append(dict(**sample, role=role, reviewed=True))
        review = dict(private=True, pcap_sha256='a' * 64, native_item_selection=True,
            battle_start='synthetic-http', item_request='native-ui', original_service_evidence=False,
            screenshots=screens)
        return manifest, review

    def test_screenshot_attestation_is_bound_to_manifest_bytes_and_role(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            manifest, review = self.review_fixture(directory)
            result = proof.screenshots(directory, manifest, review, 'a' * 64)
            self.assertEqual({r['role'] for r in result}, proof.SCREEN_ROLES)
            self.assertNotIn('frame-', json.dumps(result))
            mutations = [lambda r: r.update(pcap_sha256='b' * 64),
                         lambda r: r.update(item_request='synthetic-http'),
                         lambda r: r.update(original_service_evidence=True),
                         lambda r: r['screenshots'].pop(),
                         lambda r: r['screenshots'][0].update(reviewed=False),
                         lambda r: r['screenshots'][0].update(sha256='b' * 64),
                         lambda r: r['screenshots'][0].update(file='../outside.png'),
                         lambda r: r['screenshots'].append(copy.deepcopy(r['screenshots'][0]))]
            for number, mutate in enumerate(mutations):
                with self.subTest(case=number):
                    changed = copy.deepcopy(review)
                    mutate(changed)
                    with self.assertRaises(ValueError): proof.screenshots(directory, manifest, changed, 'a' * 64)
            (directory / review['screenshots'][0]['file']).write_bytes(b'tampered')
            with self.assertRaises(ValueError): proof.screenshots(directory, manifest, review, 'a' * 64)

    def test_export_contains_only_safe_values_and_requires_bound_restoration(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            fixture_dir, capture_dir = directory / 'fixture', directory / 'capture'
            fixture_dir.mkdir()
            capture_dir.mkdir()
            def save(name, value):
                path = fixture_dir / (name + '.json')
                path.write_text(json.dumps(value), encoding='utf-8')
                return path
            fixture = dict(self.fixture, device=dict(serial='emulator-5560', avd='PocketMortys_API30_Startup'))
            prepared = dict(items=[dict(id=1, item_id=proof.ITEM, quantity=1)])
            case = dict(self.case, wild='private-wild', enemy_hp=23)
            row = self.parse(self.wire_packets())[0]
            native = [dict(path=proof.MOVE, status=200, response=dict(success=True), capture_service='offline-sdk-web',
                           request={k: v for k, v in row['request'].items() if k != 'session_id'})]
            result = dict(snapshot=prepared, battle=dict(battle_id=case['battle_id']), events=[])
            for name, value in [('fixture', fixture), ('prepared', prepared), ('case', case),
                                ('native-item-result', result), ('native-item-http', native),
                                ('restored', fixture['before']), ('cleanup-result', result), ('cleanup-http', native)]:
                save(name, value)
            cleanup = dict(restored=True, exact_original_rows=True, acceptance=True, meeseeks_uses=1, outcome='WIN')
            for field, name in [('before_sha256', 'fixture'), ('prepared_sha256', 'prepared'),
                                ('restored_snapshot_sha256', 'restored'), ('result_sha256', 'cleanup-result'),
                                ('case_sha256', 'case')]:
                cleanup[field] = proof.digest(fixture_dir / (name + '.json'))
            save('cleanup', cleanup)
            manifest, review = self.review_fixture(capture_dir)
            pcap = capture_dir / 'primary-http.pcap'
            pcap.write_bytes(b'private-synthetic-pcap')
            pcap_hash = proof.digest(pcap)
            manifest.update(failure=None, pull_exit_code=0, tcpdump_exit_code=0, role='primary',
                serial='emulator-5560', avd='PocketMortys_API30_Startup', pcap_sha256=pcap_hash,
                pcap_size_bytes=pcap.stat().st_size, apk=dict(version='2.41.0',
                    source_apk_sha256={'private-base': 'a' * 64, 'private-split': 'b' * 64},
                    installed_apk_sha256={'private-path1': 'a' * 64, 'private-path2': 'b' * 64}))
            (capture_dir / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            review['pcap_sha256'] = pcap_hash
            review_path = directory / 'review.json'
            review_path.write_text(json.dumps(review), encoding='utf-8')
            with patch('meeseeks_box_fixture.validate', return_value=1) as validate, \
                 patch.object(proof, 'exchanges', return_value=[row]):
                exported = proof.inspect(fixture_dir, capture_dir, review_path)
                self.assertTrue(exported['native_android_acceptance'])
                self.assertFalse(exported['original_service_evidence'])
                self.assertNotIn('private-', json.dumps(exported))
                self.assertEqual(validate.call_args.args[0]['stock_id'], 1)
                cleanup['case_sha256'] = '0' * 64
                save('cleanup', cleanup)
                with self.assertRaises(ValueError): proof.inspect(fixture_dir, capture_dir, review_path)
                cleanup['case_sha256'] = proof.digest(fixture_dir / 'case.json')
                save('cleanup', cleanup)
                save('restored', dict(unexplained='private-value'))
                with self.assertRaises(ValueError): proof.inspect(fixture_dir, capture_dir, review_path)


if __name__ == '__main__':
    unittest.main()

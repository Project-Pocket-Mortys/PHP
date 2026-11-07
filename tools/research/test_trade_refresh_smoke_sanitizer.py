"""Synthetic-only fail-closed tests; no database, emulator or HTTP calls."""
import base64
import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import sanitize_trade_refresh_smoke as proof


class TradeRefreshSmokeTests(unittest.TestCase):
    def setUp(self):
        self.user = dict(username='PMTrade01', player_id='secret-player',
                         session_id='secret-new-session', secret='secret-account')
        self.current = dict(private=True, snapshot=dict(users=[self.user]))
        self.anchor = copy.deepcopy(self.current)
        self.anchor['snapshot']['users'][0]['session_id'] = 'secret-old-session'
        encoded = base64.urlsafe_b64encode(json.dumps(self.user).encode()).decode().rstrip('=')
        self.token = 'a.'+encoded+'.b'
        self.publication = dict(private=True, synthetic=True, event='trade:offer-submit',
            player_id=self.user['player_id'], session_id=self.user['session_id'],
            revision='1', published_utc='1970-01-01T00:00:10+00:00')
        identity = {k: self.user[k] for k in ('player_id', 'username')}
        details = dict(**identity, owned_morties=[], decks=[], mortydex=[])
        def row(path, request, response, time):
            return dict(path=path, request=request, response=response, headers={'x-pmclient':'secret-client'},
                        response_headers={}, request_time=time, response_time=time+1)
        self.rows = [
            row('/user/login', dict(secret=self.user['secret']),
                dict(session_url='https://example.invalid/sse/?token='+self.token), 0),
            row('/session/player-details', dict(session_id=self.user['session_id'],
                include=proof.INCLUDE+['currency']), details, 3),
            row('/session/join-room', dict(session_id=self.user['session_id']), dict(room_id='private-room'), 5),
            row('/trading/get-trades', dict(session_id=self.user['session_id'], player_id=self.user['player_id']),
                dict(trade_requests=[], trade_offers=[], competed_trades=[]), 12),
            row('/session/player-details', dict(session_id=self.user['session_id'], include=proof.INCLUDE), details, 12.1),
        ]
        self.rows[0]['response_headers']['set-cookie'] = ('session_id='+self.user['session_id']+
            '; Path=/trading/; HttpOnly; SameSite=Lax')
        self.rows[3]['headers']['cookie'] = 'session_id='+self.user['session_id']
        self.events = [dict(event='session:start', payload=self.user, token=self.token, time=2, client='secret-client'),
                       dict(event='trade:offer-submit', payload={}, token=self.token, time=11, client='secret-client')]

    def validate(self, rows=None, events=None, publication=None):
        return proof.validate(self.rows if rows is None else rows,
            self.events if events is None else events, self.anchor, self.current,
            self.publication if publication is None else publication, 0)

    def test_consumer_only_claim_is_redacted(self):
        result = self.validate()
        self.assertTrue(result['native_consumer_smoke_proved'])
        self.assertFalse(result['actual_trade_mutation_publication_proved'])
        self.assertFalse(result['immediate_offer_cancellation_unlock_proved'])
        self.assertNotIn('secret-', json.dumps(result))
        self.assertEqual(result['details_mask'], '0x78')

    def test_identity_cookie_mask_startup_and_competing_request_rejected(self):
        changes = [
            lambda rows: rows[0]['request'].update(secret='different'),
            lambda rows: rows[0]['response_headers'].update({'set-cookie':'session_id=other; Path=/trading/; HttpOnly; SameSite=Lax'}),
            lambda rows: rows[1]['request'].update(include=proof.INCLUDE),
            lambda rows: rows[1].update(response_time=7),
            lambda rows: rows[2].update(response_time=11.5),
            lambda rows: rows[3]['request'].update(session_id='other'),
            lambda rows: rows[3]['request'].update(player_id='other'),
            lambda rows: rows[3]['headers'].update(cookie='session_id=other'),
            lambda rows: rows[3]['response'].pop('competed_trades'),
            lambda rows: rows[3].update(request_time=9),
            lambda rows: rows[4]['request'].update(include=proof.INCLUDE+['currency']),
            lambda rows: rows[4]['request'].update(include=['morties', 'attacks', 'decks', 'decks']),
            lambda rows: rows[4]['response'].update(player_id='other'),
            lambda rows: rows.append(copy.deepcopy(rows[4])),
        ]
        for change in changes:
            with self.subTest(change=changes.index(change)):
                rows = copy.deepcopy(self.rows)
                change(rows)
                with self.assertRaises(ValueError):
                    self.validate(rows=rows)
        for change in (lambda events: events[1].update(time=1),
                       lambda events: events[1].update(payload={'player_id':'other'}),
                       lambda events: events[1].update(token='different'),
                       lambda events: events.append(copy.deepcopy(events[1]))):
            events = copy.deepcopy(self.events)
            change(events)
            with self.assertRaises(ValueError):
                self.validate(events=events)

    def test_reordered_tcp_completion_uses_all_bytes(self):
        rows = [dict(seq=10, payload=b'abc', time=3), dict(seq=13, payload=b'def', time=2)]
        self.assertEqual(proof.completed_time(rows, 10, 16), 3)
        with self.assertRaises(ValueError):
            proof.completed_time(rows, 9, 16)

    def test_independent_publication_clock_is_disclosed_without_inventing_offset(self):
        publication = copy.deepcopy(self.publication)
        publication['published_utc'] = '2036-11-07T00:00:00+00:00'
        result = self.validate(publication=publication)
        self.assertFalse(result['publication_clock_order_proved'])
        self.assertFalse(result['publication_to_sse_latency_proved'])
        self.assertNotIn('synthetic_publication', [row['action'] for row in result['timestamps']])
        self.assertIn('independent clock', result['timing_scope'])
        events = copy.deepcopy(self.events)
        events[1]['time'] = 5.5
        with self.assertRaises(ValueError):
            self.validate(events=events, publication=publication)

    def wire(self, bad_json=False, bad_overlap=False):
        native = b'User-Agent: com.Tivadar.Best.HTTP v3.0.17.0/Unity 2022.3.62f2\r\nX-PMClient: synthetic\r\n'
        request = b'GET /sse/?token=a.b.c HTTP/1.1\r\n'+native+b'\r\n'
        frame = b'event: trade:offer-submit\ndata: '+(b'{"x":1,"x":2}' if bad_json else b'{}')+b'\n\n'
        response = b'HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\nTransfer-Encoding: chunked\r\n\r\n'
        response += hex(len(frame))[2:].encode()+b'\r\n'+frame+b'\r\n'
        key = ('192.0.2.1', 5000, '192.0.2.2', 8087)
        reverse = (key[2], key[3], key[0], key[1])
        flows = {key:[dict(seq=10, ack=20, payload=request, time=1)],
                 reverse:[dict(seq=20, ack=10+len(request), payload=response, time=2)]}
        if bad_overlap:
            flows[reverse].append(dict(seq=20, ack=10+len(request), payload=b'WRONG', time=3))
        return flows

    def test_sse_chunk_offsets_exact_ack_overlap_and_strict_json(self):
        for bad_json, bad_overlap in ((False, False), (True, False), (False, True)):
            with self.subTest(bad_json=bad_json, bad_overlap=bad_overlap), \
                 patch.object(proof, 'capture_packet_times', return_value=[]), \
                 patch.object(proof, 'flows', return_value=(self.wire(bad_json, bad_overlap), 1)):
                if bad_json or bad_overlap:
                    with self.assertRaises((ValueError, AssertionError)):
                        proof.wire_observations(Path('unused'))
                else:
                    rows, events, _ = proof.wire_observations(Path('unused'))
                    self.assertEqual(rows, [])
                    self.assertEqual(events[0]['time'], 2)
                    self.assertEqual(events[0]['payload'], {})

    def test_wrong_sse_ack_or_user_agent_rejected(self):
        for wrong in ('ack', 'agent'):
            flow = self.wire()
            if wrong == 'ack':
                reply = next(rows for key, rows in flow.items() if key[1] == 8087)
                reply[0]['ack'] += 1
            else:
                request = next(rows for key, rows in flow.items() if key[3] == 8087)
                request[0]['payload'] = request[0]['payload'].replace(b'Best.HTTP', b'Wrong.HTTP')
            with self.subTest(wrong=wrong), \
                 patch.object(proof, 'capture_packet_times', return_value=[]), \
                 patch.object(proof, 'flows', return_value=(flow, 1)):
                with self.assertRaises(ValueError):
                    proof.wire_observations(Path('unused'))


if __name__ == '__main__':
    unittest.main()

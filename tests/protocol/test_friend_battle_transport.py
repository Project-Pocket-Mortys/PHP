"""Opt-in, at-most-once PvF SSE attempts using additive UUID fixtures only."""
import base64
import hashlib
import json
import queue
import subprocess
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid

from test_http import COMPOSE, ROOT, php, post, sql
import test_friend_battle_startup as startup


def gated_php(code):
    return subprocess.check_output(COMPOSE + ['exec', '-T', '-e',
        'PM_RESEARCH_SHARED_BATTLE_STREAM=1', 'web', 'php', '-r', code],
        text=True, cwd=ROOT)


def research_post(path, data):
    request = urllib.request.Request('http://127.0.0.1:8089' + path + '/',
        json.dumps(data).encode(), {'Content-Type': 'application/json'}, method='POST')
    try:
        response = urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())


class SSEReader:
    def __init__(self, player, port):
        token = base64.urlsafe_b64encode(json.dumps({'session_id': player}).encode()).decode().rstrip('=')
        self.response = urllib.request.urlopen(
            f'http://127.0.0.1:{port}/sse/?token=e30.{token}.test', timeout=5)
        self.events = queue.Queue()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def read(self):
        event = None
        try:
            while not self.stopped.is_set():
                line = self.response.readline()
                if not line:
                    self.events.put(('EOF', None))
                    return
                line = line.decode().strip()
                if line.startswith('event: '):
                    event = line[7:]
                elif line.startswith('data: '):
                    self.events.put((event, json.loads(line[6:])))
        except (OSError, ValueError):
            self.events.put(('EOF', None))

    def wait(self, wanted, timeout=5):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            event, payload = self.events.get(timeout=max(.01, deadline - time.monotonic()))
            if event == wanted:
                return payload
        raise queue.Empty(wanted)

    def close(self):
        self.stopped.set()
        self.response.close()


class FriendBattleTransportTests(unittest.TestCase):
    def setUp(self):
        self.s = startup.FriendBattleStartupTests(methodName='runTest')
        self.addCleanup(self.s.doCleanups)
        self.s.setUp()
        self.a, self.b, self.c = self.s.a, self.s.b, self.s.c
        self.battle, self.f = self.s.battle, self.s.f
        self.streams = {}
        self.addCleanup(self.cleanup_transport)

    def cleanup_transport(self):
        self.f.execute([
            f"DELETE FROM friend_battle_start_attempts WHERE battle_id='{self.battle}'",
            f"DELETE FROM friend_battle_stream_bindings WHERE battle_id='{self.battle}'",
            f"DELETE FROM friend_battle_streams WHERE player_id IN ('{self.f.ids}')",
        ])

    def call(self, expression, gated=True):
        runner = gated_php if gated else php
        return json.loads(runner(
            "require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "require '/var/www/html/lib/friend_battle_startup.php';"
            "require_once '/var/www/html/lib/friend_battle_transport.php';"
            "try{echo json_encode(['ok'=>" + expression + "]);}"
            "catch(Throwable $e){echo json_encode(['status'=>$e instanceof FriendError?$e->status:500]);}"))

    def invoke(self, action='activate', actor=None, gated=True):
        actor = self.b if actor is None else actor
        return self.call(f"friend_battle_startup_{action}($pdo,'{actor}','{self.battle}')", gated)

    def open(self, player, session=None):
        result = self.call(f"friend_battle_transport_open($pdo,'{player if session is None else session}','{player}')")
        self.assertIn('ok', result, result)
        uuid.UUID(result['ok'])
        self.streams[player] = result['ok']
        return result['ok']

    def poll(self, player, stream=None, session=None):
        return self.call(f"friend_battle_transport_poll($pdo,'{player if session is None else session}',"
                         f"'{player}','{self.streams[player] if stream is None else stream}')")

    def open_pair(self):
        self.open(self.a)
        self.open(self.b)
        for actor in (self.a, self.b):
            self.assertEqual(self.poll(actor), {'ok': {'close': False, 'events': []}})

    def activate(self):
        result = self.invoke()
        self.assertEqual(result.get('ok', {}).get('state'), 'STARTING', result)
        return result

    def transport_rows(self):
        return {name: sql(query) for name, query in {
            'streams': f"SELECT * FROM friend_battle_streams WHERE player_id IN ('{self.f.ids}') ORDER BY player_id",
            'bindings': f"SELECT * FROM friend_battle_stream_bindings WHERE battle_id='{self.battle}' ORDER BY player_id",
            'attempts': f"SELECT * FROM friend_battle_start_attempts WHERE battle_id='{self.battle}' ORDER BY player_id",
        }.items()}

    def assert_cancelled(self):
        rows = self.s.rows()
        self.assertEqual(rows['sessions'][0]['state'], 'CANCELLED')
        self.assertEqual(rows['claims'], [])
        self.assertTrue(rows['startup'][0]['cancelled_at'])
        self.assertTrue(all(r['retired_at'] for r in rows['intents']))
        self.assertTrue(all(r['state'] == 'WORLD' for r in rows['users']))
        self.assertEqual(rows['events'], [])

    def assert_ended(self, result):
        self.assertEqual(result, {'ok': {'close': True,
            'events': [{'event': 'session:end', 'payload': {}}]}})

    def test_gate_off_has_no_transport_effects(self):
        before = self.transport_rows()
        self.assertEqual(self.call(f"friend_battle_transport_open($pdo,'invalid','{self.a}')", False), {'ok': ''})
        self.assertEqual(self.call(f"friend_battle_transport_poll($pdo,'invalid','{self.a}','invalid')", False),
                         {'ok': {'close': False, 'events': []}})
        result = self.invoke(gated=False)
        self.assertIn('ok', result)
        self.assertEqual(self.transport_rows(), before)
        self.assertEqual(post('/session/battle/ready', {'session_id': self.a, 'battle_id': self.battle})[0], 404)

    def test_authentication_and_recipient_role_reject_without_binding(self):
        for actor, status in (('', 401), (str(uuid.uuid4()), 401), (self.c, 403), (self.a, 403)):
            self.assertEqual(self.invoke(actor=actor).get('status'), status)
        self.assertEqual(self.call(f"friend_battle_transport_open($pdo,'invalid','{self.a}')").get('status'), 401)
        self.assertEqual(self.call(f"friend_battle_transport_open($pdo,'{self.a}','{self.b}')").get('status'), 403)
        self.assertEqual(self.transport_rows(), {'streams': [], 'bindings': [], 'attempts': []})

    def test_missing_peer_stream_rolls_back_activation(self):
        self.open(self.a)
        before = self.s.rows()
        self.assertEqual(self.invoke().get('status'), 409)
        self.assertEqual(self.s.rows(), before)
        self.assertEqual(self.transport_rows()['bindings'], [])

    def test_stale_peer_stream_rolls_back_activation(self):
        self.open_pair()
        sql(f"UPDATE friend_battle_streams SET heartbeat_at=UTC_TIMESTAMP(6)-INTERVAL 11 SECOND WHERE player_id='{self.b}'")
        before = self.s.rows()
        self.assertEqual(self.invoke().get('status'), 409)
        self.assertEqual(self.s.rows(), before)
        self.assertEqual(self.transport_rows()['bindings'], [])

    def test_activation_binds_exact_pair_once_with_session_hashes(self):
        self.open_pair()
        first = self.activate()
        bindings = self.transport_rows()['bindings']
        self.assertEqual(len(bindings), 2)
        for row in bindings:
            self.assertEqual(row['stream_id'], self.streams[row['player_id']])
            self.assertEqual(row['session_sha256'], hashlib.sha256(row['player_id'].encode()).hexdigest())
        self.assertEqual(self.invoke(), first)
        self.assertEqual(self.transport_rows()['bindings'], bindings)
        self.assertEqual(self.transport_rows()['attempts'], [])

    def test_poll_attempts_only_own_private_start_once_without_event_queue(self):
        self.open_pair()
        self.open(self.c)
        self.activate()
        for actor in (self.a, self.b):
            result = self.poll(actor)['ok']
            self.assertFalse(result['close'])
            self.assertEqual(len(result['events']), 1)
            event = result['events'][0]
            self.assertEqual(event['event'], 'battle:start')
            self.assertEqual(event['payload']['player']['player_id'], actor)
            self.assertNotIn('coins', event['payload']['opponent'])
            self.assertEqual(event['payload'], json.loads(next(r for r in self.s.rows()['intents'] if r['player_id'] == actor)['payload_json']))
            self.assertEqual(self.poll(actor)['ok']['events'], [])
        self.assertEqual(self.poll(self.c)['ok']['events'], [])
        rows = self.transport_rows()
        self.assertEqual(len(rows['attempts']), 2)
        self.assertEqual({r['delivery_id'] for r in rows['attempts']}, {r['delivery_id'] for r in self.s.rows()['intents']})
        self.assertEqual(self.s.rows()['events'], [])

    def test_ready_requires_own_attempt_and_both_acknowledgements(self):
        self.open_pair()
        self.activate()
        self.assertEqual(self.invoke('ready', self.a).get('status'), 409)
        self.assertEqual(research_post('/session/battle/ready',
            {'session_id': self.a, 'battle_id': self.battle})[0], 409)
        self.poll(self.b)
        self.assertEqual(self.invoke('ready', self.a).get('status'), 409)
        self.assertEqual(self.invoke('ready', self.b)['ok']['state'], 'STARTING')
        self.poll(self.a)
        self.assertEqual(research_post('/session/battle/ready',
            {'session_id': self.a, 'battle_id': self.battle})[0], 200)
        self.assertEqual(self.invoke('ready', self.a)['ok']['state'], 'READY')
        self.assertEqual(self.s.rows()['events'], [])

    def test_reconnect_cancels_pair_and_never_replays(self):
        self.open_pair()
        self.activate()
        self.poll(self.a)
        old = self.streams[self.a]
        self.assertNotEqual(self.open(self.a), old)
        self.assert_cancelled()
        self.assertTrue(self.poll(self.a, old)['ok']['close'])
        self.assertEqual(self.poll(self.a)['ok']['events'], [])
        self.assert_ended(self.poll(self.b))

    def test_superseded_preparation_stream_cannot_abort_newer_startup(self):
        self.open_pair()
        old = self.streams[self.a]
        self.open(self.a)
        self.activate()
        before = self.s.rows()
        self.assertTrue(self.poll(self.a, old)['ok']['close'])
        self.assertEqual(self.s.rows(), before)
        self.assertEqual(self.transport_rows()['attempts'], [])
        self.assertEqual(len(self.poll(self.a)['ok']['events']), 1)

    def test_revoked_peer_session_cleans_both_participants(self):
        self.open_pair()
        self.activate()
        sql(f"UPDATE users SET session_id='revoked-{self.b}' WHERE player_id='{self.b}'")
        self.assert_ended(self.poll(self.a))
        self.assert_cancelled()

    def test_stale_peer_stream_cleans_both_participants(self):
        self.open_pair()
        self.activate()
        sql(f"UPDATE friend_battle_streams SET heartbeat_at=UTC_TIMESTAMP(6)-INTERVAL 11 SECOND WHERE player_id='{self.b}'")
        self.assert_ended(self.poll(self.a))
        self.assert_cancelled()

    def test_expired_own_stream_cannot_be_revived_by_poll(self):
        self.open_pair()
        self.activate()
        sql(f"UPDATE friend_battle_streams SET heartbeat_at=UTC_TIMESTAMP(6)-INTERVAL 11 SECOND WHERE player_id='{self.a}'")
        self.assert_ended(self.poll(self.a))
        self.assert_cancelled()

    def test_startup_deadline_cleans_pair_without_start_attempt(self):
        self.open_pair()
        self.activate()
        self.s.make_due()
        self.assert_ended(self.poll(self.a))
        self.assert_cancelled()
        self.assertEqual(self.transport_rows()['attempts'], [])

    def test_attempt_insert_failure_rolls_back_and_allows_one_retry(self):
        self.open_pair()
        self.activate()
        trigger = self.s.fault('INSERT', 'friend_battle_start_attempts', f"NEW.battle_id='{self.battle}'")
        before = self.s.rows()
        self.assertEqual(self.poll(self.a).get('status'), 500)
        self.assertEqual(self.s.rows(), before)
        self.assertEqual(self.transport_rows()['attempts'], [])
        sql(f'DROP TRIGGER IF EXISTS {trigger}')
        self.assertEqual(len(self.poll(self.a)['ok']['events']), 1)
        self.assertEqual(self.poll(self.a)['ok']['events'], [])

    def test_real_cross_room_streams_private_start_and_public_accept_stays_disabled(self):
        sql(f"UPDATE users SET room_id='transport-room-a' WHERE player_id='{self.a}'")
        sql(f"UPDATE users SET room_id='transport-room-b' WHERE player_id='{self.b}'")
        readers = {}
        for actor in (self.a, self.b, self.c):
            reader = readers[actor] = SSEReader(actor, 8089)
            self.addCleanup(reader.close)
            reader.wait('session:start')
        primary = SSEReader(self.a, 8087)
        self.addCleanup(primary.close)
        primary.wait('session:start')
        self.f.error(self.f.call('response', self.b, token=self.s.invite['recipient_token'], accept=True), 501, 'FAILED')
        self.assertEqual(research_post('/session/battle-invite/response',
            {'session_id': self.b, 'token': self.s.invite['recipient_token'], 'accept': True}),
            (501, {'error': {'code': 'FAILED'}}))
        self.activate()
        for actor in (self.a, self.b):
            payload = readers[actor].wait('battle:start')
            self.assertEqual(payload['player']['player_id'], actor)
            self.assertEqual(payload['battle_id'], self.battle)
        with self.assertRaises(queue.Empty):
            readers[self.c].wait('battle:start', timeout=.5)
        with self.assertRaises(queue.Empty):
            primary.wait('battle:start', timeout=.5)
        self.assertEqual(len(self.transport_rows()['attempts']), 2)
        self.assertEqual(self.s.rows()['events'], [])

    def test_real_reconnect_ends_peer_stream_with_server_ended_event(self):
        readers = {}
        for actor in (self.a, self.b):
            reader = readers[actor] = SSEReader(actor, 8089)
            self.addCleanup(reader.close)
            reader.wait('session:start')
        self.activate()
        for reader in readers.values():
            reader.wait('battle:start')
        replacement = SSEReader(self.a, 8089)
        self.addCleanup(replacement.close)
        replacement.wait('session:start')
        self.assertEqual(readers[self.b].wait('session:end'), {})
        self.assertIsNone(readers[self.b].wait('EOF'))
        self.assert_cancelled()
        with self.assertRaises(queue.Empty):
            replacement.wait('battle:start', timeout=.5)


if __name__ == '__main__':
    unittest.main()

"""Research initial RUN terminals; additive UUID fixtures, never reseed accounts."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import queue
import socket
import subprocess
import threading
import time
import unittest
import urllib.request
import uuid

import test_friend_battle_selections as selections
from test_friend_battle_transport import SSEReader, gated_php, research_post
from test_http import COMPOSE, ROOT, php, post, sql


quoted = selections.quoted
TABLES = ('friend_battle_forfeits', 'friend_battle_terminal_intents',
          'friend_battle_terminal_attempts')


class TerminalSSEReader(SSEReader):
    def __init__(self, player, port):
        token = base64.urlsafe_b64encode(json.dumps({'session_id': player}).encode()).decode().rstrip('=')
        # Set the timeout before the first background read starts. Changing a
        # socket timeout later cannot extend a read already waiting for data.
        self.response = urllib.request.urlopen(
            f'http://127.0.0.1:{port}/sse/?token=e30.{token}.test', timeout=40)
        self.events = queue.Queue()
        self.stopped = threading.Event()
        self.thread = threading.Thread(target=self.read, daemon=True)
        self.thread.start()

    def close(self):
        self.stopped.set()
        stream = self.response.fp
        if stream is not None:
            try:
                stream.raw._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
        self.thread.join(timeout=2)
        self.response.close()


class FriendBattleForfeitTests(unittest.TestCase):
    def setUp(self):
        # Compose the existing isolated fixture without importing its TestCase
        # into this module's unittest discovery namespace.
        self.q = selections.FriendBattleSelectionTests(methodName='runTest')
        self.addCleanup(self.q.doCleanups)
        self.q.setUp()
        self.s, self.p, self.v, self.f = self.q.s, self.q.p, self.q.v, self.q.f
        self.a, self.b, self.c, self.d = self.f.players
        self.battle, self.ids = self.q.battle, self.q.ids
        self.streams = {}
        self.addCleanup(self.cleanup_transport)

    def cleanup_transport(self):
        self.f.execute([
            *[f"DELETE FROM {table} WHERE battle_id='{self.battle}'" for table in reversed(TABLES)],
            f"DELETE FROM friend_battle_start_attempts WHERE battle_id='{self.battle}'",
            f"DELETE FROM friend_battle_stream_bindings WHERE battle_id='{self.battle}'",
            f"DELETE FROM friend_battle_streams WHERE player_id IN ('{self.f.ids}')",
        ])

    def call(self, expression, gated=True):
        runner = gated_php if gated else php
        return json.loads(runner(
            "require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "require_once '/var/www/html/lib/friend_battle_startup.php';"
            "require_once '/var/www/html/lib/friend_battle_forfeit.php';"
            "try{echo json_encode(['ok'=>" + expression + "]);}"
            "catch(Throwable $e){echo json_encode(['status'=>$e instanceof FriendError?$e->status:500,"
            "'error'=>$e instanceof FriendError?$e->getMessage():'FAILED']);}"))

    def data(self, actor=None, **changes):
        result = self.q.data(self.a if actor is None else actor, type='RUN', move_id=None)
        result.update(changes)
        return result

    def submit(self, actor=None, data=None, gated=True):
        actor = self.a if actor is None else actor
        encoded = base64.b64encode(json.dumps([self.data(actor) if data is None else data, actor]).encode()).decode()
        return self.call("friend_battle_forfeit_submit($pdo,...json_decode(base64_decode('" + encoded + "'),true))", gated)

    def open(self, actor, session=None):
        result = self.call(f"friend_battle_transport_open($pdo,'{session or actor}','{actor}')")
        self.assertIn('ok', result, result)
        self.streams[actor] = result['ok']
        return result['ok']

    def poll(self, actor, stream=None, session=None):
        return self.call(f"friend_battle_transport_poll($pdo,'{session or actor}','{actor}',"
                         f"'{stream or self.streams[actor]}')")

    def prepare(self, ready=(True, True), attempts=(True, True)):
        for actor in (self.a, self.b):
            self.open(actor)
        self.assertIn('ok', self.s.invoke('activate', prefix="putenv('PM_RESEARCH_SHARED_BATTLE_STREAM=1');putenv('PM_FRIEND_BATTLE_STARTUP_SECONDS=120');"))
        for actor, attempted, acknowledged in zip((self.a, self.b), attempts, ready):
            if attempted:
                result = self.poll(actor)
                self.assertEqual(result['ok']['events'][0]['event'], 'battle:start')
            if acknowledged:
                result = self.s.invoke('ready', actor, prefix="putenv('PM_RESEARCH_SHARED_BATTLE_STREAM=1');")
                self.assertIn('ok', result, result)
        self.refresh_streams()

    def read_queries(self, queries):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        return json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "$out=[];foreach(json_decode(base64_decode('" + encoded + "'),true) as $key=>$query)"
            "$out[$key]=$pdo->query($query)->fetchAll();echo json_encode($out);"))

    def rows(self):
        return self.read_queries({table: f"SELECT * FROM {table} WHERE battle_id='{self.battle}' ORDER BY 1,2"
                                  for table in TABLES})

    def transport_rows(self):
        return self.read_queries(dict(
            streams=f"SELECT * FROM friend_battle_streams WHERE player_id IN ('{self.f.ids}') ORDER BY player_id",
            bindings=f"SELECT * FROM friend_battle_stream_bindings WHERE battle_id='{self.battle}' ORDER BY player_id",
            attempts=f"SELECT * FROM friend_battle_start_attempts WHERE battle_id='{self.battle}' ORDER BY player_id"))

    def snapshot(self):
        # One read process keeps verification itself below the fixed stream lease.
        tables = (*TABLES, 'friend_battle_sessions', 'friend_battle_startups',
                  'friend_battle_start_intents', 'friend_battle_start_views',
                  'friend_battle_party_snapshots', 'friend_battle_selections',
                  'friend_battle_selection_pairs', 'friend_battle_stream_bindings',
                  'friend_battle_start_attempts')
        queries = {table: f"SELECT * FROM {table} WHERE battle_id='{self.battle}' ORDER BY 1,2" for table in tables}
        queries.update({table: f"SELECT * FROM {table} WHERE player_id IN ('{self.f.ids}') ORDER BY 1,2"
                        for table in ('users', 'decks', 'owned_items', 'owned_morties',
                                      'friend_battle_memberships', 'friend_battle_streams')})
        ids = ','.join(map(quoted, (*self.ids, *self.f.players)))
        queries['attacks'] = f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ({ids}) ORDER BY id"
        queries['events'] = f"SELECT * FROM event_queue WHERE player_id IN ('{self.f.ids}') OR only_show_to_player_id IN ('{self.f.ids}') ORDER BY id"
        queries['invites'] = f"SELECT * FROM friend_battle_invites WHERE sender_id IN ('{self.f.ids}') OR recipient_id IN ('{self.f.ids}') ORDER BY invite_id"
        queries['legacy'] = f"SELECT * FROM battles WHERE player_id IN ('{self.f.ids}') OR opponent_id IN ('{self.f.ids}') ORDER BY battle_id"
        return self.read_queries(queries)

    def refresh_streams(self):
        sql(f"UPDATE friend_battle_streams SET heartbeat_at=UTC_TIMESTAMP(6) WHERE player_id IN ('{self.a}','{self.b}')")

    def reject(self, actor=None, data=None, status=409, gated=True, refresh=True):
        if refresh:
            self.refresh_streams()
        before = self.snapshot()
        result = self.submit(actor, data, gated)
        self.assertEqual(result.get('status'), status, result)
        self.assertEqual(self.snapshot(), before)

    def assert_ack(self, result):
        self.assertEqual(set(result), {'ok'}, result)
        self.assertEqual(set(result['ok']), {'decision_id'})
        uuid.UUID(result['ok']['decision_id'])

    def assert_terminal(self, actor):
        self.s.assert_cancelled('STARTUP_RUN')
        rows = self.rows()
        self.assertEqual([len(rows[t]) for t in TABLES], [1, 2, 0])
        intents = rows[TABLES[1]]
        self.assertEqual({r['player_id'] for r in intents}, {self.a, self.b})
        self.assertEqual(len({r['delivery_id'] for r in intents}), 2)
        for intent in intents:
            uuid.UUID(intent['delivery_id'])
            self.assertEqual(hashlib.sha256(intent['payload_json'].encode()).hexdigest(), intent['payload_sha256'])
            payload = json.loads(intent['payload_json'])
            self.assertEqual(payload['battle_id'], self.battle)
            self.assertEqual(payload['outcome'], 'RUN' if intent['player_id'] == actor else 'WIN')
            self.assertIs(payload['battle_abandoned'], intent['player_id'] != actor)
            self.assertEqual(payload['turn_datas'], [])
            self.assertEqual(payload['player_datas'], {'player': {}, 'opponent': {}})
        self.assertEqual(self.s.rows()['events'], [])
        self.assertTrue(all(r['retired_at'] for rows in self.q.rows().values() for r in rows))

    def assert_gameplay_preserved(self, before):
        for row in before['users']:
            if row['player_id'] in (self.a, self.b):
                row['state'] = 'WORLD'
        self.assertEqual(self.p.gameplay(), before)

    def simultaneous(self, functions):
        barrier = threading.Barrier(len(functions))
        def run(function):
            barrier.wait(timeout=10)
            return function()
        with ThreadPoolExecutor(max_workers=len(functions)) as pool:
            return list(pool.map(run, functions))

    def slow_insert(self, table, seconds=2):
        name = 'run_delay_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {name}'))
        sql(f"CREATE TRIGGER {name} BEFORE INSERT ON {table} FOR EACH ROW BEGIN IF NEW.battle_id='{self.battle}' THEN DO SLEEP({seconds}); END IF; END")
        return name

    def test_default_gate_and_public_invite_accept_stay_closed(self):
        self.prepare()
        self.reject(gated=False, status=501)
        before = self.snapshot()
        self.assertEqual(post('/session/battle/move', self.data())[0], 404)
        self.assertEqual(research_post('/session/battle-invite/response',
            {'session_id': self.b, 'token': self.s.invite['recipient_token'], 'accept': True})[0], 409)
        self.assertEqual(self.snapshot(), before)

    def test_native_sender_run_has_atomic_private_terminal_and_no_spend(self):
        self.prepare()
        gameplay, party, views = self.p.gameplay(), self.p.rows(), self.v.rows()
        self.assertEqual(research_post('/session/battle/move', self.data()), (200, {'success': True}))
        self.assert_terminal(self.a)
        self.assert_gameplay_preserved(gameplay)
        self.assertEqual((self.p.rows(), self.v.rows()), (party, views))

    def test_native_recipient_run_after_peer_pending_attack_retires_without_spend(self):
        self.prepare()
        self.assertIn('ok', self.q.submit(self.a))
        gameplay, deadline = self.p.gameplay(), self.s.rows()['startup'][0]['ready_deadline']
        self.assertEqual(research_post('/session/battle/move', self.data(self.b)), (200, {'success': True}))
        self.assert_terminal(self.b)
        self.assertEqual(len(self.q.rows()['selections']), 1)
        self.assert_gameplay_preserved(gameplay)
        self.assertEqual(self.s.rows()['startup'][0]['ready_deadline'], deadline)

    def test_run_schema_requires_exact_five_fields_and_literal_null(self):
        self.prepare()
        for key in self.data():
            data = self.data()
            del data[key]
            with self.subTest(missing=key):
                self.reject(data=data, status=400)
        for key, value in (('extra', True), ('move_id', ''), ('move_id', 'AttackLick'),
                           ('move_id', []), ('move_id', False), ('owned_morty_id', []), ('type', [])):
            data = self.data()
            data[key] = value
            with self.subTest(key=key, value=value):
                self.reject(data=data, status=400)

    def test_authentication_session_match_and_third_account_are_rejected(self):
        self.prepare()
        for actor, status in (('', 400), (str(uuid.uuid4()), 401), (self.c, 403)):
            self.reject(actor, status=status)
        self.reject(data=self.data(session_id=self.b), status=403)

    def test_run_requires_both_ready_and_both_start_attempts(self):
        self.prepare(ready=(True, False))
        self.reject()
        self.assertIn('ok', self.s.invoke('ready', self.b, prefix="putenv('PM_RESEARCH_SHARED_BATTLE_STREAM=1');"))
        original = self.transport_rows()['attempts']
        for actor in (self.a, self.b):
            sql(f"DELETE FROM friend_battle_start_attempts WHERE battle_id='{self.battle}' AND player_id='{actor}'")
            self.reject()
            self.q.restore('friend_battle_start_attempts', original)

    def test_initial_active_actor_must_be_owned_living_and_unchanged(self):
        self.prepare()
        for morty in (self.ids[0], self.ids[2], str(uuid.uuid4())):
            self.reject(data=self.data(owned_morty_id=morty))
        sql(f"UPDATE owned_morties SET hp=0 WHERE owned_morty_id='{self.ids[1]}'")
        self.reject()

    def test_own_attack_blocks_run_and_paired_attacks_block_both(self):
        self.prepare()
        self.assertIn('ok', self.q.submit())
        self.reject()
        self.assertIn('ok', self.q.submit(self.b))
        self.reject(self.b)

    def test_live_original_bindings_and_fixed_startup_lease_are_required(self):
        self.prepare()
        for actor in (self.a, self.b):
            sql(f"UPDATE friend_battle_streams SET heartbeat_at=UTC_TIMESTAMP(6)-INTERVAL 11 SECOND WHERE player_id='{actor}'")
            self.reject(refresh=False)
            sql(f"UPDATE friend_battle_streams SET heartbeat_at=UTC_TIMESTAMP(6) WHERE player_id='{actor}'")
        bindings = self.transport_rows()['bindings']
        sql(f"DELETE FROM friend_battle_stream_bindings WHERE battle_id='{self.battle}' AND player_id='{self.b}'")
        self.reject()
        self.q.restore('friend_battle_stream_bindings', bindings)
        sql(f"UPDATE friend_battle_stream_bindings SET stream_id='{uuid.uuid4()}' WHERE battle_id='{self.battle}' AND player_id='{self.b}'")
        self.reject()
        self.q.restore('friend_battle_stream_bindings', bindings)
        self.s.make_due()
        self.reject(refresh=False)

    def test_exact_own_retry_never_changes_intents_attempts_or_deadline(self):
        self.prepare()
        first = self.submit()
        self.assert_ack(first)
        for actor in (self.a, self.b):
            self.assertEqual(len(self.poll(actor)['ok']['events']), 1)
        before = self.snapshot()
        self.assertEqual(self.submit(), first)
        self.assertEqual(self.snapshot(), before)
        self.reject(self.b)
        self.reject(data=self.data(owned_morty_id=self.ids[0]))

    def test_duplicate_simultaneous_run_creates_one_immutable_decision(self):
        self.prepare()
        results = self.simultaneous((lambda: self.submit(), lambda: self.submit()))
        self.assert_ack(results[0])
        self.assertEqual(results[0], results[1])
        self.assert_terminal(self.a)

    def test_opposing_simultaneous_runs_choose_only_one_actor(self):
        self.prepare()
        results = self.simultaneous((lambda: self.submit(), lambda: self.submit(self.b)))
        self.assertEqual(sum('ok' in r for r in results), 1, results)
        self.assertEqual(next(r['status'] for r in results if 'status' in r), 409)
        self.assert_terminal(self.a if 'ok' in results[0] else self.b)

    def test_same_actor_attack_run_race_cannot_commit_both(self):
        self.prepare()
        result = self.simultaneous((lambda: self.submit(), lambda: self.q.submit()))
        self.assertEqual(sum('ok' in r for r in result), 1, result)
        self.assertEqual(next(r['status'] for r in result if 'status' in r), 409)
        if 'ok' in result[0]:
            self.assert_terminal(self.a)
        else:
            self.assertEqual(self.rows()[TABLES[0]], [])
            self.assertEqual(len(self.q.rows()['selections']), 1)

    def test_peer_attack_run_race_keeps_inert_peer_history_or_rejects_it(self):
        self.prepare()
        result = self.simultaneous((lambda: self.submit(), lambda: self.q.submit(self.b)))
        self.assert_ack(result[0])
        self.assertTrue('ok' in result[1] or result[1].get('status') == 409, result)
        self.assert_terminal(self.a)

    def test_expiry_race_cannot_create_terminal_after_startup_timeout(self):
        self.prepare()
        self.s.make_due()
        result = self.simultaneous((lambda: self.submit(), lambda: self.s.expire_candidate()))
        self.assertEqual(result[0].get('status'), 409)
        self.assertEqual(result[1], 1)
        self.assertEqual(self.rows()[TABLES[0]], [])
        self.s.assert_cancelled('STARTUP_TIMEOUT')

    def test_decision_and_both_intent_insert_faults_roll_back_every_effect(self):
        self.prepare()
        for table, condition in ((TABLES[0], f"NEW.battle_id='{self.battle}'"),
                                 (TABLES[1], f"NEW.battle_id='{self.battle}' AND NEW.player_id='{self.b}'")):
            name = self.s.fault('INSERT', table, condition)
            self.reject(status=500)
            sql(f'DROP TRIGGER {name}')
        self.assert_ack(self.submit())

    def test_cleanup_fault_rolls_back_terminal_and_peer_attack_retirement(self):
        self.prepare()
        self.assertIn('ok', self.q.submit(self.b))
        for table, timing, condition in (
            ('friend_battle_selections', 'UPDATE', f"NEW.battle_id='{self.battle}' AND NEW.retired_at IS NOT NULL"),
            ('friend_battle_memberships', 'DELETE', f"OLD.battle_id='{self.battle}'"),
            ('users', 'UPDATE', f"NEW.player_id='{self.a}' AND NEW.state='WORLD'")):
            name = self.s.fault(timing, table, condition)
            self.reject(status=500)
            sql(f'DROP TRIGGER {name}')
        self.assert_ack(self.submit())

    def test_final_database_clock_rejects_insert_crossing_startup_deadline(self):
        self.prepare()
        self.slow_insert(TABLES[0], seconds=4)
        sql(f"UPDATE friend_battle_startups SET ready_deadline=started_at+INTERVAL 10 SECOND WHERE battle_id='{self.battle}'")
        remaining = sql(f"SELECT TIMESTAMPDIFF(MICROSECOND,UTC_TIMESTAMP(6),ready_deadline)/1000000 AS seconds FROM friend_battle_startups WHERE battle_id='{self.battle}'")[0]['seconds']
        time.sleep(max(0, float(remaining) - 3))
        self.refresh_streams()
        started = time.monotonic()
        self.reject(refresh=False)
        self.assertGreaterEqual(time.monotonic() - started, 4)

    def test_final_database_clock_rejects_insert_crossing_peer_stream_lease(self):
        self.prepare()
        self.slow_insert(TABLES[0], seconds=4)
        sql(f"UPDATE friend_battle_streams SET heartbeat_at=UTC_TIMESTAMP(6)-INTERVAL 7 SECOND WHERE player_id='{self.b}'")
        started = time.monotonic()
        self.reject(refresh=False)
        self.assertGreaterEqual(time.monotonic() - started, 4)

    def test_terminal_anchor_loss_hash_corruption_and_extra_recipient_fail_closed(self):
        self.prepare()
        self.assert_ack(self.submit())
        original = self.rows()
        for table in TABLES[:2]:
            sql(f"DELETE FROM {table} WHERE battle_id='{self.battle}'")
            self.reject()
            self.assertEqual(self.poll(self.a).get('status'), 409)
            self.q.restore(table, original[table])
        sql(f"UPDATE {TABLES[1]} SET payload_sha256=REPEAT('0',64) WHERE battle_id='{self.battle}' AND player_id='{self.a}'")
        self.reject()
        self.q.restore(TABLES[1], original[TABLES[1]])
        extra = dict(original[TABLES[1]][0], player_id=self.c, delivery_id=str(uuid.uuid4()))
        self.q.restore(TABLES[1], original[TABLES[1]] + [extra])
        self.reject()

    def test_missing_attempt_or_mirrored_anchor_never_replays_terminal(self):
        self.prepare()
        self.assert_ack(self.submit())
        self.assertEqual(len(self.poll(self.a)['ok']['events']), 1)
        original = self.rows()
        sql(f"DELETE FROM {TABLES[2]} WHERE battle_id='{self.battle}'")
        before = self.snapshot()
        self.assertEqual(self.poll(self.a).get('status'), 409)
        self.assertEqual(self.snapshot(), before)
        self.q.restore(TABLES[2], original[TABLES[2]])
        sql(f"UPDATE {TABLES[1]} SET attempted_at=NULL WHERE battle_id='{self.battle}' AND player_id='{self.a}'")
        before = self.snapshot()
        self.assertEqual(self.poll(self.a).get('status'), 409)
        self.assertEqual(self.snapshot(), before)

    def test_terminal_poll_attempt_once_then_empty_and_only_own_heartbeat_changes(self):
        self.prepare()
        self.assert_ack(self.submit())
        for actor in (self.a, self.b):
            intent = next(r for r in self.rows()[TABLES[1]] if r['player_id'] == actor)
            before = self.rows()
            result = self.poll(actor)
            self.assertEqual(result, {'ok': {'close': False, 'events': [
                {'event': 'battle:turn-result', 'payload': json.loads(intent['payload_json'])}]}})
            attempts = self.rows()[TABLES[2]]
            attempt = next(r for r in attempts if r['player_id'] == actor)
            self.assertEqual(attempt['delivery_id'], intent['delivery_id'])
            self.assertEqual(attempt['stream_id'], self.streams[actor])
            sql(f"UPDATE friend_battle_streams SET heartbeat_at=UTC_TIMESTAMP(6)-INTERVAL 2 SECOND WHERE player_id='{actor}'")
            peer = next(r for r in self.transport_rows()['streams'] if r['player_id'] != actor)
            ledger = self.rows()
            self.assertEqual(self.poll(actor), {'ok': {'close': False, 'events': []}})
            self.assertEqual(self.rows(), ledger)
            self.assertEqual(next(r for r in self.transport_rows()['streams'] if r['player_id'] != actor), peer)
            self.assertEqual(self.rows()[TABLES[0]], before[TABLES[0]])

    def test_terminal_poll_attempt_fault_is_atomic_and_retry_still_attempts_once(self):
        self.prepare()
        self.assert_ack(self.submit())
        name = self.s.fault('INSERT', TABLES[2], f"NEW.battle_id='{self.battle}'")
        before = self.snapshot()
        self.assertEqual(self.poll(self.a).get('status'), 500)
        self.assertEqual(self.snapshot(), before)
        sql(f'DROP TRIGGER {name}')
        # A publication that outlives its freshly refreshed ten-second lease
        # must roll back both the immutable attempt and the mirrored anchor.
        slow = self.slow_insert(TABLES[2], seconds=11)
        self.refresh_streams()
        before = self.snapshot()
        self.assertEqual(self.poll(self.a).get('status'), 409)
        self.assertEqual(self.snapshot(), before)
        sql(f'DROP TRIGGER {slow}')
        self.refresh_streams()
        self.assertEqual(len(self.poll(self.a)['ok']['events']), 1)
        self.assertEqual(self.poll(self.a), {'ok': {'close': False, 'events': []}})

    def test_third_account_and_fresh_stream_never_receive_old_terminal(self):
        self.prepare()
        self.open(self.c)
        self.assert_ack(self.submit())
        self.assertEqual(self.poll(self.c), {'ok': {'close': False, 'events': []}})
        old = self.streams[self.a]
        self.open(self.a)
        self.assertEqual(self.poll(self.a), {'ok': {'close': False, 'events': []}})
        self.assertEqual(self.poll(self.a, old), {'ok': {'close': True, 'events': []}})
        self.assertEqual(self.rows()[TABLES[2]], [])
        self.assertEqual(len(self.poll(self.b)['ok']['events']), 1)

    def test_rotated_session_fences_original_terminal_without_peer_lease_requirement(self):
        self.prepare()
        self.assert_ack(self.submit())
        rotated = str(uuid.uuid4())
        sql(f"UPDATE users SET session_id='{rotated}' WHERE player_id='{self.a}'")
        before = self.rows()
        self.assertEqual(self.poll(self.a).get('status'), 401)
        self.assertEqual(self.poll(self.a, session=rotated), {'ok': {'close': True, 'events': []}})
        self.assertEqual(self.rows(), before)
        sql(f"DELETE FROM friend_battle_streams WHERE player_id='{self.a}'")
        self.assertEqual(len(self.poll(self.b)['ok']['events']), 1)

    def test_own_retry_preserves_new_claims_and_never_resets_attempts(self):
        self.prepare()
        first = self.submit()
        self.assert_ack(first)
        self.assertEqual(len(self.poll(self.a)['ok']['events']), 1)
        self.f.befriend(self.c, self.b)
        self.assertEqual(self.f.create(self.c, self.b)[0], 200)
        invite = next(row for row in self.f.rows() if row['sender_id'] == self.c)
        newer = self.s.m.reserve(invite)['ok']
        self.s.m.assert_pair(newer, self.c, self.b)
        before = self.snapshot()
        self.assertEqual(self.submit(), first)
        self.assertEqual(self.snapshot(), before)
        self.s.m.assert_pair(newer, self.c, self.b)

    def wild_fixture(self):
        room, wild = str(uuid.uuid4()), str(uuid.uuid4())
        self.addCleanup(lambda: self.f.execute([
            f"DELETE FROM event_queue WHERE room_id='{room}'",
            f"DELETE FROM battles WHERE player_id='{self.a}'",
            f"DELETE FROM room_ids WHERE room_id='{room}'"]))
        self.f.execute([
            f"INSERT INTO room_ids(room_id,world_id,zone_id) VALUES('{room}','run-fixture','[1,1]')",
            f"UPDATE users SET room_id='{room}' WHERE player_id='{self.a}'",
            f"INSERT INTO event_queue(room_id,event_name,wild_morty_id,morty_id,state,placement,variant) VALUES('{room}','room:wild-morty-added','{wild}','Morty','WORLD','0,0','Normal')"])
        return dict(session_id=self.a, wild_morty_id=wild)

    def test_new_wild_start_waits_for_original_terminal_attempt_then_never_replays_it(self):
        self.prepare()
        self.assert_ack(self.submit())
        data = self.wild_fixture()
        before = self.snapshot()
        for request in (post, research_post):
            self.assertEqual(request('/session/battle-wild-morty', data)[0], 409)
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(len(self.poll(self.a)['ok']['events']), 1)
        self.assertEqual(post('/session/battle-wild-morty', data), (200, {'success': True}))
        attempts = self.rows()[TABLES[2]]
        self.assertEqual(self.poll(self.a), {'ok': {'close': False, 'events': []}})
        self.assertEqual(self.rows()[TABLES[2]], attempts)

    def test_contended_terminal_history_rejects_wild_start_promptly_without_writes(self):
        self.prepare()
        self.assert_ack(self.submit())
        data = self.wild_fixture()
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "$pdo->beginTransaction();"
            f"$pdo->query(\"SELECT battle_id FROM friend_battle_sessions WHERE battle_id='{self.battle}' FOR UPDATE\")->fetchAll();"
            "echo \"LOCKED\\n\";flush();fgets(STDIN);$pdo->rollBack();")
        holder = subprocess.Popen(COMPOSE + ['exec', '-T', 'web', 'php', '-r', code],
            cwd=ROOT, text=True, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            self.assertEqual(holder.stdout.readline().strip(), 'LOCKED')
            before = self.snapshot()
            for request in (post, research_post):
                started = time.monotonic()
                self.assertEqual(request('/session/battle-wild-morty', data)[0], 409)
                self.assertLess(time.monotonic() - started, 3)
            self.assertEqual(self.snapshot(), before)
        finally:
            holder.communicate('release\n', timeout=10)
        self.assertEqual(holder.returncode, 0)
        self.assertEqual(len(self.poll(self.a)['ok']['events']), 1)
        self.assertEqual(research_post('/session/battle-wild-morty', data), (200, {'success': True}))

    def test_superseded_stream_allows_new_wild_but_cannot_deliver_old_terminal(self):
        self.prepare()
        self.assert_ack(self.submit())
        old = self.streams[self.a]
        self.open(self.a)
        data = self.wild_fixture()
        self.assertEqual(research_post('/session/battle-wild-morty', data), (200, {'success': True}))
        self.assertEqual(self.poll(self.a, old), {'ok': {'close': True, 'events': []}})
        self.assertEqual(self.poll(self.a), {'ok': {'close': False, 'events': []}})
        self.assertEqual(self.rows()[TABLES[2]], [])

    def test_real_private_sse_terminal_once_keeps_stream_open_through_heartbeat(self):
        readers = {}
        for actor in (self.a, self.b, self.c):
            reader = readers[actor] = TerminalSSEReader(actor, 8089)
            self.addCleanup(reader.close)
            reader.wait('session:start')
        self.assertEqual(research_post('/session/battle-invite/response',
            {'session_id': self.b, 'token': self.s.invite['recipient_token'], 'accept': True}),
            (501, {'error': {'code': 'FAILED'}}))
        self.assertIn('ok', self.s.invoke('activate', prefix="putenv('PM_RESEARCH_SHARED_BATTLE_STREAM=1');"))
        for actor in (self.a, self.b):
            self.assertEqual(readers[actor].wait('battle:start')['player']['player_id'], actor)
            self.assertEqual(research_post('/session/battle/ready', {'session_id': actor, 'battle_id': self.battle}),
                             (200, {'success': True}))
        self.assertEqual(research_post('/session/battle/move', self.data()), (200, {'success': True}))
        for actor in (self.a, self.b):
            payload = readers[actor].wait('battle:turn-result')
            self.assertEqual(payload['outcome'], 'RUN' if actor == self.a else 'WIN')
            self.assertIs(payload['battle_abandoned'], actor != self.a)
        self.assertEqual(len(self.rows()[TABLES[2]]), 2)
        for actor in (self.a, self.b):
            deadline = time.monotonic() + 35
            while True:
                event, payload = readers[actor].events.get(timeout=max(.01, deadline - time.monotonic()))
                self.assertNotIn(event, ('battle:turn-result', 'session:end', 'EOF'))
                if event == 'session:keep-alive':
                    self.assertEqual(payload, 0)
                    break
        for reader in readers.values():
            remaining = []
            while not reader.events.empty():
                remaining.append(reader.events.get_nowait()[0])
            self.assertNotIn('battle:turn-result', remaining)
            self.assertNotIn('session:end', remaining)
            self.assertNotIn('EOF', remaining)


class FriendBattleForfeitMigrationTests(unittest.TestCase):
    def test_migration_016_is_additive_and_repeatable_on_connection_local_copies_only(self):
        result = json.loads(php("""
require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';
$tables=['friend_battle_forfeits','friend_battle_terminal_intents','friend_battle_terminal_attempts'];
$before=[];
$liveTables=$pdo->query('SHOW TABLES')->fetchAll(PDO::FETCH_COLUMN);
foreach ($liveTables as $table) $before[$table]=$pdo->query('SHOW CREATE TABLE `'.str_replace('`','``',$table).'`')->fetchAll(PDO::FETCH_ASSOC);
$migration=file_get_contents('/var/www/html/tools/research/server/migrations/016-shared-battle-forfeit.sql');
// Apply the exact DDL only to temporary copies. Never remove a live table or
// migrate the application's database backwards to manufacture an old schema.
foreach ($tables as $index=>$table) {
    $copy='run_migration_copy_'.$index;
    $migration=str_replace('CREATE TABLE IF NOT EXISTS '.$table.' (',
        'CREATE TEMPORARY TABLE IF NOT EXISTS '.$copy.' (',$migration,$count);
    if ($count!==1) throw new RuntimeException('Unexpected migration target');
}
try {
    $pdo->exec($migration);
    $pdo->exec("INSERT INTO run_migration_copy_0 VALUES('11111111-1111-4111-8111-111111111111','22222222-2222-4222-8222-222222222222','fixture','morty','{}',REPEAT('0',64),UTC_TIMESTAMP(6))");
    $once=[];
    foreach ($tables as $index=>$table) $once[$table]=$pdo->query('SELECT * FROM run_migration_copy_'.$index)->fetchAll(PDO::FETCH_ASSOC);
    $pdo->exec($migration);
    foreach ($tables as $index=>$table) {
        if ($once[$table]!==$pdo->query('SELECT * FROM run_migration_copy_'.$index)->fetchAll(PDO::FETCH_ASSOC)) throw new RuntimeException('Repeat migration changed rows');
    }
    if ($liveTables!==$pdo->query('SHOW TABLES')->fetchAll(PDO::FETCH_COLUMN)) throw new RuntimeException('Live tables changed');
    foreach ($before as $table=>$schema) if ($schema!==$pdo->query('SHOW CREATE TABLE `'.str_replace('`','``',$table).'`')->fetchAll(PDO::FETCH_ASSOC)) throw new RuntimeException('Live schema changed');
    echo json_encode(['repeatable'=>true,'live_schema_unchanged'=>true]);
} finally {
    foreach ($tables as $index=>$table) $pdo->exec('DROP TEMPORARY TABLE IF EXISTS run_migration_copy_'.$index);
}
"""))
        self.assertEqual(result, {'repeatable': True, 'live_schema_unchanged': True})


if __name__ == '__main__':
    unittest.main()

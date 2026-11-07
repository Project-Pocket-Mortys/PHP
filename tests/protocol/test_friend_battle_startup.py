"""Internal PvF startup against additive UUID fixtures; never reseed accounts."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import threading
import unittest
import urllib.error
import urllib.request
import uuid

import test_friend_battle_start_views as views
from test_http import php, post, sql


class FriendBattleStartupTests(unittest.TestCase):
    def setUp(self):
        self.v = views.FriendBattleStartViewTests(methodName='runTest')
        self.addCleanup(self.v.doCleanups)
        self.v.setUp()
        self.p, self.m, self.f = self.v.p, self.v.m, self.v.f
        self.a, self.b, self.c, self.d = self.f.players
        self.battle, self.invite = self.v.battle, self.v.invite
        self.addCleanup(lambda: self.f.execute([
            f"DELETE FROM friend_battle_start_intents WHERE battle_id='{self.battle}'",
            f"DELETE FROM friend_battle_startups WHERE battle_id='{self.battle}'",
        ]))
        self.assertIn('ok', self.v.build())

    def invoke(self, action, actor=None, battle=None, prefix=''):
        args = [self.b if actor is None else actor, battle or self.battle]
        encoded = base64.b64encode(json.dumps(args).encode()).decode()
        return json.loads(php(
            "require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "require '/var/www/html/lib/friend_battle_startup.php';" + prefix +
            "$a=json_decode(base64_decode('" + encoded + "'),true);"
            "try{echo json_encode(['ok'=>friend_battle_startup_" + action + "($pdo,$a[0],$a[1])]);}"
            "catch(Throwable $e){echo json_encode(['status'=>$e instanceof FriendError?$e->status:500,"
            "'error'=>$e instanceof FriendError?$e->getMessage():'FAILED']);}"
        ))

    def rows(self):
        queries = {
            'startup': f"SELECT * FROM friend_battle_startups WHERE battle_id='{self.battle}'",
            'intents': f"SELECT * FROM friend_battle_start_intents WHERE battle_id='{self.battle}' ORDER BY player_id",
            'sessions': f"SELECT * FROM friend_battle_sessions WHERE battle_id='{self.battle}'",
            'claims': f"SELECT * FROM friend_battle_memberships WHERE player_id IN ('{self.f.ids}') ORDER BY player_id",
            'invites': f"SELECT * FROM friend_battle_invites WHERE invite_id='{self.invite['invite_id']}'",
            'users': f"SELECT * FROM users WHERE player_id IN ('{self.f.ids}') ORDER BY player_id",
            'events': f"SELECT * FROM event_queue WHERE player_id IN ('{self.f.ids}') OR only_show_to_player_id IN ('{self.f.ids}') ORDER BY id",
        }
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        return json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "$o=[];foreach(json_decode(base64_decode('" + encoded + "'),true) as $k=>$q)"
            "$o[$k]=$pdo->query($q)->fetchAll();echo json_encode($o);"))

    def reject(self, action='activate', actor=None, status=409):
        before, gameplay, stored = self.rows(), self.p.gameplay(), self.v.rows()
        self.assertEqual(self.invoke(action, actor).get('status'), status)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.p.gameplay(), gameplay)
        self.assertEqual(self.v.rows(), stored)

    def activate(self):
        result = self.invoke('activate')
        self.assertIn('ok', result, result)
        self.assertEqual(result['ok']['state'], 'STARTING')
        self.assertEqual(result['ok']['battle_id'], self.battle)
        return result

    def expire_candidate(self, **changes):
        candidate = dict(battle_id=self.battle, sender_id=self.a, recipient_id=self.b)
        candidate.update(changes)
        encoded = base64.b64encode(json.dumps([candidate]).encode()).decode()
        return json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "require '/var/www/html/lib/friend_battle_startup.php';"
            "echo json_encode(friend_battle_startup_expire_candidates($pdo,json_decode(base64_decode('" + encoded + "'),true)));"))

    def make_due(self):
        sql(f"UPDATE friend_battle_startups SET started_at=UTC_TIMESTAMP(6)-INTERVAL 40 SECOND,ready_deadline=UTC_TIMESTAMP(6)-INTERVAL 10 SECOND,sender_ready_at=IF(sender_ready_at IS NULL,NULL,UTC_TIMESTAMP(6)-INTERVAL 35 SECOND),recipient_ready_at=IF(recipient_ready_at IS NULL,NULL,UTC_TIMESTAMP(6)-INTERVAL 35 SECOND),ready_at=IF(ready_at IS NULL,NULL,UTC_TIMESTAMP(6)-INTERVAL 35 SECOND) WHERE battle_id='{self.battle}'")

    def assert_cancelled(self, reason):
        rows = self.rows()
        self.assertEqual(rows['sessions'][0]['state'], 'CANCELLED')
        self.assertEqual(rows['sessions'][0]['cancel_reason'], reason)
        self.assertEqual(rows['claims'], [])
        self.assertTrue(rows['startup'][0]['cancelled_at'])
        self.assertEqual(len(rows['intents']), 2)
        self.assertTrue(all(row['retired_at'] for row in rows['intents']))
        self.assertTrue(all(row['state'] == 'WORLD' for row in rows['users']))
        self.assertEqual(rows['invites'][0]['state'], 'ACCEPTED')

    def fault(self, timing, table, condition):
        name = 'startup_fault_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {name}'))
        sql(f"CREATE TRIGGER {name} BEFORE {timing} ON {table} FOR EACH ROW BEGIN IF {condition} THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID startup fault'; END IF; END")
        return name

    def test_recipient_activation_authentication_and_exact_private_intents(self):
        for actor, status in (('', 401), (str(uuid.uuid4()), 401), (self.c, 403), (self.a, 403)):
            self.reject(actor=actor, status=status)
        gameplay, stored, parties = self.p.gameplay(), self.v.rows(), self.p.rows()
        result = self.activate()
        self.assertEqual(set(result['ok']), {'battle_id', 'state', 'ready_deadline'})
        rows = self.rows()
        self.assertEqual(rows['sessions'][0]['state'], 'STARTING')
        self.assertEqual(rows['events'], [])
        self.assertEqual(rows['invites'][0]['state'], 'ACCEPTED')
        self.m.assert_pair(self.battle)
        for user in gameplay['users']:
            if user['player_id'] in (self.a, self.b):
                user['state'] = 'BATTLE'
        self.assertEqual(self.p.gameplay(), gameplay)
        self.assertEqual(self.v.rows(), stored)
        self.assertEqual(self.p.rows(), parties)
        self.assertEqual(len(rows['intents']), 2)
        self.assertEqual(len({r['delivery_id'] for r in rows['intents']}), 2)
        for intent in rows['intents']:
            uuid.UUID(intent['delivery_id'])
            source = next(v for v in stored if v['player_id'] == intent['player_id'])
            self.assertEqual(intent['payload_json'], source['view_json'])
            self.assertEqual(intent['payload_sha256'], hashlib.sha256(intent['payload_json'].encode()).hexdigest())
            payload = json.loads(intent['payload_json'])
            self.assertEqual(payload['player']['player_id'], intent['player_id'])
            self.assertNotIn('coins', payload['opponent'])
            self.assertIsNone(intent['retired_at'])

    def test_replay_keeps_delivery_ids_deadline_and_frozen_views(self):
        first = self.activate()
        rows, stored = self.rows(), self.v.rows()
        self.assertEqual(self.invoke('activate'), first)
        self.assertEqual(self.rows(), rows)
        self.reject(actor=self.a, status=403)
        self.assertEqual(self.invoke('ready', self.a)['ok']['state'], 'STARTING')
        self.assertEqual(self.invoke('activate'), first)
        self.assertEqual(self.rows()['intents'], rows['intents'])
        self.assertEqual(self.rows()['startup'][0]['ready_deadline'], rows['startup'][0]['ready_deadline'])
        self.assertEqual(self.v.rows(), stored)

    def test_intent_reads_only_callers_view_and_rejects_expired_or_retired(self):
        self.reject('intent', self.b)
        self.activate()
        for actor, status in (('', 401), (str(uuid.uuid4()), 401), (self.c, 403)):
            self.reject('intent', actor, status)
        before = self.rows()
        for actor in (self.a, self.b):
            result = self.invoke('intent', actor)
            self.assertIn('ok', result, result)
            intent = next(row for row in before['intents'] if row['player_id'] == actor)
            self.assertEqual(result['ok'], dict(battle_id=self.battle, state='STARTING',
                delivery_id=intent['delivery_id'], payload=json.loads(intent['payload_json'])))
            self.assertNotIn('coins', result['ok']['payload']['opponent'])
        self.assertEqual(self.rows(), before)
        self.make_due()
        self.reject('intent', self.a)
        self.reject('intent', self.b)
        self.assertEqual(self.invoke('cancel', self.a), {'ok': None})
        self.reject('intent', self.a)
        self.reject('intent', self.b)

    def test_before_activation_revalidates_context_claims_and_sources(self):
        own_view = next(row for row in self.v.rows() if row['player_id'] == self.a)
        original_deck = views.quoted(json.dumps(self.v.ids[:2]))
        for mutation, restore in (
            (f"UPDATE users SET coins=30 WHERE player_id='{self.a}'", f"UPDATE users SET coins=29 WHERE player_id='{self.a}'"),
            (f"UPDATE owned_morties SET hp=1 WHERE owned_morty_id='{self.v.ids[1]}'", f"UPDATE owned_morties SET hp=37 WHERE owned_morty_id='{self.v.ids[1]}'"),
            (f"UPDATE decks SET owned_morty_ids='invalid JSON' WHERE player_id='{self.a}'", f"UPDATE decks SET owned_morty_ids={original_deck} WHERE player_id='{self.a}'"),
            (f"UPDATE friend_list SET pending='true' WHERE player_id_a='{self.a}' AND player_id_b='{self.b}'", f"UPDATE friend_list SET pending='false' WHERE player_id_a='{self.a}' AND player_id_b='{self.b}'"),
            (f"DELETE FROM friend_battle_memberships WHERE player_id='{self.a}'", f"INSERT INTO friend_battle_memberships(player_id,battle_id) VALUES('{self.a}','{self.battle}')"),
            (f"UPDATE friend_battle_sessions SET prepare_deadline=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE battle_id='{self.battle}'", f"UPDATE friend_battle_sessions SET prepare_deadline=UTC_TIMESTAMP(6)+INTERVAL 120 SECOND WHERE battle_id='{self.battle}'"),
            (f"UPDATE friend_battle_start_views SET view_sha256=REPEAT('0',64) WHERE battle_id='{self.battle}' AND player_id='{self.a}'", f"UPDATE friend_battle_start_views SET view_sha256='{own_view['view_sha256']}' WHERE battle_id='{self.battle}' AND player_id='{self.a}'"),
        ):
            with self.subTest(mutation=mutation):
                sql(mutation)
                self.reject()
                self.assertEqual(self.rows()['startup'], [])
                sql(restore)

    def test_startup_configuration_rejects_invalid_and_pins_valid_lifetime(self):
        for value in ('0', '9', '121', 'invalid'):
            with self.subTest(value=value):
                before = self.rows()
                result = self.invoke('activate', prefix="putenv('PM_FRIEND_BATTLE_STARTUP_SECONDS=" + value + "');")
                self.assertEqual(result.get('status'), 500, result)
                self.assertEqual(self.rows(), before)
        result = self.invoke('activate', prefix="putenv('PM_FRIEND_BATTLE_STARTUP_SECONDS=10');")
        self.assertIn('ok', result, result)
        interval = sql(f"SELECT TIMESTAMPDIFF(MICROSECOND,started_at,ready_deadline) AS duration FROM friend_battle_startups WHERE battle_id='{self.battle}'")[0]['duration']
        self.assertEqual(int(interval), 10000000)
        before = self.rows()
        self.assertEqual(self.invoke('activate', prefix="putenv('PM_FRIEND_BATTLE_STARTUP_SECONDS=120');"), result)
        self.assertEqual(self.rows(), before)
        self.assertIn('ok', self.invoke('ready', self.a))
        self.assertEqual(self.rows()['startup'][0]['ready_deadline'], before['startup'][0]['ready_deadline'])

    def test_ready_barrier_duplicate_requests_and_both_orders(self):
        self.activate()
        initial = self.rows()
        for actor in ('', self.c):
            self.reject('ready', actor, 401 if not actor else 403)
        first = self.invoke('ready', self.b)
        self.assertEqual(first['ok'], {'battle_id': self.battle, 'state': 'STARTING', 'ready': False})
        after = self.rows()
        self.assertTrue(after['startup'][0]['recipient_ready_at'])
        self.assertIsNone(after['startup'][0]['sender_ready_at'])
        self.assertEqual(self.invoke('ready', self.b), first)
        self.assertEqual(self.rows(), after)
        final = self.invoke('ready', self.a)
        self.assertEqual(final['ok'], {'battle_id': self.battle, 'state': 'READY', 'ready': True})
        ready = self.rows()
        self.assertTrue(ready['startup'][0]['ready_at'])
        self.assertEqual(self.invoke('ready', self.a), final)
        self.assertEqual(self.invoke('ready', self.b), final)
        self.assertEqual(self.rows(), ready)
        self.assertEqual(ready['intents'], initial['intents'])
        self.assertEqual(ready['startup'][0]['ready_deadline'], initial['startup'][0]['ready_deadline'])

    def test_simultaneous_ready_requests_commit_one_barrier(self):
        self.activate()
        barrier = threading.Barrier(2)
        def ready(actor):
            barrier.wait(timeout=10)
            return self.invoke('ready', actor)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(ready, (self.a, self.b)))
        self.assertTrue(all('ok' in r for r in results), results)
        self.assertEqual(sorted(r['ok']['state'] for r in results), ['READY', 'STARTING'])
        self.assertEqual(self.rows()['sessions'][0]['state'], 'READY')
        self.assertEqual(self.invoke('ready', self.a)['ok']['ready'], True)

    def test_expired_deadline_rejects_ready_and_activation_replay(self):
        self.activate()
        self.assertIn('ok', self.invoke('ready', self.a))
        self.make_due()
        self.reject('ready', self.a)
        self.reject('ready', self.b)
        self.reject()

    def test_either_role_cancel_and_old_retry_preserves_newer_claims(self):
        self.activate()
        saved, views_before = self.p.gameplay(), self.v.rows()
        self.reject('cancel', self.c, 403)
        self.assertEqual(self.invoke('cancel', self.b), {'ok': None})
        self.assert_cancelled('STARTUP_CANCELLED')
        for user in saved['users']:
            if user['player_id'] in (self.a, self.b):
                user['state'] = 'WORLD'
        self.assertEqual(self.p.gameplay(), saved)
        self.assertEqual(self.v.rows(), views_before)
        terminal = self.rows()
        self.assertEqual(self.invoke('cancel', self.a), {'ok': None})
        self.assertEqual(self.rows(), terminal)
        self.f.befriend(self.c, self.b)
        self.assertEqual(self.f.create(self.c, self.b)[0], 200)
        invite = next(r for r in self.f.rows() if r['sender_id'] == self.c)
        newer = self.m.reserve(invite)['ok']
        sql(f"UPDATE users SET state='BATTLE' WHERE player_id IN ('{self.b}','{self.c}')")
        before, sessions = self.rows(), self.m.sessions()
        self.assertEqual(self.invoke('cancel', self.a), {'ok': None})
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.m.sessions(), sessions)
        self.m.assert_pair(newer, self.c, self.b)

    def test_sender_can_cancel_after_both_ready(self):
        self.activate()
        self.invoke('ready', self.a)
        self.invoke('ready', self.b)
        self.assertEqual(self.invoke('cancel', self.a), {'ok': None})
        self.assert_cancelled('STARTUP_CANCELLED')

    def test_expiry_revalidates_stale_candidate_and_concurrent_workers(self):
        self.activate()
        before = self.rows()
        self.assertEqual(self.expire_candidate(), 0)
        self.assertEqual(self.rows(), before)
        self.make_due()
        before = self.rows()
        self.assertEqual(self.expire_candidate(sender_id=self.c), 0)
        self.assertEqual(self.rows(), before)
        sql(f"DELETE FROM friend_battle_memberships WHERE player_id='{self.a}'")
        malformed = self.rows()
        self.assertEqual(self.expire_candidate(), 0)
        self.assertEqual(self.rows(), malformed)
        sql(f"INSERT INTO friend_battle_memberships(player_id,battle_id) VALUES('{self.a}','{self.battle}')")
        barrier = threading.Barrier(2)
        def expire(_):
            barrier.wait(timeout=10)
            return self.expire_candidate()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(expire, range(2)))
        self.assertEqual(sorted(results), [0, 1])
        self.assert_cancelled('STARTUP_TIMEOUT')
        terminal = self.rows()
        self.assertEqual(self.expire_candidate(), 0)
        self.assertEqual(self.rows(), terminal)

    def test_ready_expiry_and_corrupt_startup_fail_closed(self):
        self.activate()
        self.invoke('ready', self.a)
        self.invoke('ready', self.b)
        original = self.rows()['startup'][0]
        for mutation in ('ready_deadline=NULL', 'ready_deadline=started_at-INTERVAL 1 SECOND'):
            with self.subTest(mutation=mutation):
                sql(f"UPDATE friend_battle_startups SET {mutation} WHERE battle_id='{self.battle}'")
                before = self.rows()
                self.assertEqual(self.expire_candidate(), 0)
                self.assertEqual(self.rows(), before)
                self.reject('ready', self.a)
                sql(f"UPDATE friend_battle_startups SET ready_deadline='{original['ready_deadline']}' WHERE battle_id='{self.battle}'")
        self.make_due()
        self.assertEqual(self.expire_candidate(), 1)
        self.assert_cancelled('STARTUP_TIMEOUT')

    def test_second_intent_failure_rolls_back_entire_activation(self):
        trigger = self.fault('INSERT', 'friend_battle_start_intents',
            f"NEW.battle_id='{self.battle}' AND EXISTS(SELECT 1 FROM friend_battle_start_intents WHERE battle_id=NEW.battle_id)")
        self.reject(status=500)
        self.assertEqual(self.rows()['intents'], [])
        sql(f'DROP TRIGGER IF EXISTS {trigger}')
        self.activate()

    def test_second_user_update_failure_rolls_back_activation(self):
        second = sorted((self.a, self.b))[1]
        trigger = self.fault('UPDATE', 'users', f"OLD.player_id='{second}' AND NEW.state='BATTLE'")
        self.reject(status=500)
        sql(f'DROP TRIGGER IF EXISTS {trigger}')
        self.activate()

    def test_preparation_expiring_during_intent_write_rolls_back_activation(self):
        trigger = 'startup_slow_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON friend_battle_start_intents FOR EACH ROW BEGIN IF NEW.battle_id='{self.battle}' AND NOT EXISTS(SELECT 1 FROM friend_battle_start_intents WHERE battle_id=NEW.battle_id) THEN UPDATE friend_battle_sessions SET prepare_deadline=UTC_TIMESTAMP(6)+INTERVAL 1 SECOND WHERE battle_id=NEW.battle_id; DO SLEEP(2); END IF; END")
        self.reject(status=409)
        self.assertEqual(self.rows()['startup'], [])
        self.assertEqual(self.rows()['intents'], [])
        sql(f'DROP TRIGGER IF EXISTS {trigger}')
        self.activate()

    def test_ready_expiring_during_timestamp_write_rolls_back(self):
        self.activate()
        sql(f"UPDATE friend_battle_startups SET started_at=UTC_TIMESTAMP(6)-INTERVAL 25 SECOND,ready_deadline=UTC_TIMESTAMP(6)+INTERVAL 5 SECOND WHERE battle_id='{self.battle}'")
        trigger = 'startup_slow_ready_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE UPDATE ON friend_battle_startups FOR EACH ROW BEGIN IF OLD.battle_id='{self.battle}' AND OLD.sender_ready_at IS NULL AND NEW.sender_ready_at IS NOT NULL THEN DO SLEEP(6); END IF; END")
        self.reject('ready', self.a)
        self.assertIsNone(self.rows()['startup'][0]['sender_ready_at'])

    def test_keyset_sweep_and_cli_once_are_internal_and_revalidate_future_lease(self):
        self.activate()
        unrelated = sql(f"SELECT battle_id FROM friend_battle_sessions WHERE state IN ('STARTING','READY') AND battle_id<>'{self.battle}'")
        self.assertEqual(unrelated, [], 'CLI sweep requires this fixture to be the only active startup')
        before = self.rows()
        result = json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "require '/var/www/html/lib/friend_battle_startup.php';"
            "$cursor='';$first=friend_battle_startup_sweep($pdo,1,$cursor);$after=$cursor;"
            "$second=friend_battle_startup_sweep($pdo,1,$cursor);echo json_encode([$first,$after,$second,$cursor]);"))
        self.assertEqual(result, [0, self.battle, 0, None])
        self.assertEqual(self.rows(), before)
        try:
            response = urllib.request.urlopen('http://127.0.0.1:8087/tools/research/server/friend-battle-startups.php', timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            self.assertIn(response.status, (403, 404))
        self.assertEqual(self.rows(), before)
        self.make_due()
        output = php("$argv=['--once'];require '/var/www/html/tools/research/server/friend-battle-startups.php';")
        self.assertEqual(output.strip(), 'Expired 1 friend battle startups')
        self.assert_cancelled('STARTUP_TIMEOUT')

    def test_cleanup_failure_rolls_back_users_claims_and_intents(self):
        self.activate()
        trigger = self.fault('UPDATE', 'friend_battle_start_intents', f"OLD.battle_id='{self.battle}' AND NEW.retired_at IS NOT NULL")
        self.reject('cancel', self.a, 500)
        sql(f'DROP TRIGGER IF EXISTS {trigger}')
        self.assertEqual(self.invoke('cancel', self.a), {'ok': None})
        self.assert_cancelled('STARTUP_CANCELLED')

    def test_public_accept_and_legacy_routes_do_not_publish_shared_start(self):
        self.f.error(self.f.call('response', self.b, token=self.invite['recipient_token'], accept=True), 501, 'FAILED')
        self.assertEqual(self.rows()['startup'], [])
        self.activate()
        before, gameplay = self.rows(), self.p.gameplay()
        for actor in (self.a, self.b):
            for route in ('/session/heal', '/session/leave-room'):
                self.assertEqual(post(route, {'session_id': actor})[0], 409)
            self.assertEqual(post('/session/battle-wild-morty', {'session_id': actor, 'wild_morty_id': str(uuid.uuid4())})[0], 409)
            self.assertEqual(post('/session/battle/ready', {'session_id': actor, 'battle_id': self.battle})[0], 404)
        self.assertEqual(self.rows(), before)
        self.assertEqual(self.p.gameplay(), gameplay)


if __name__ == '__main__':
    unittest.main()

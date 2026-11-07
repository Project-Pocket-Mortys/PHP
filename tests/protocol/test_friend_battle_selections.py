"""Internal paired PvF selection storage using additive, isolated UUID fixtures."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import threading
import unittest
from unittest.mock import patch
import uuid

import test_friend_battle_startup as startup
from test_friend_battle_transport import gated_php, research_post
from test_http import php, post, sql


quoted = startup.views.quoted


class FriendBattleSelectionTests(unittest.TestCase):
    def setUp(self):
        # Give these fixture attacks PP before their first immutable snapshot.
        party_class = startup.views.parties.FriendBattlePartySnapshotTests
        original_freeze = party_class.freeze

        def freeze_with_pp(party, *args, **kwargs):
            ids = ','.join(map(quoted, party.ids))
            sql(f"UPDATE owned_attacks SET pp=3 WHERE owned_morty_id IN ({ids})")
            sql("INSERT INTO owned_attacks(owned_morty_id,attack_id,position,amount,pp,pp_stat,stat,type,to_self,is_accurate,accuracy,power) "
                f"VALUES('{party.ids[1]}','AttackFlail',2,7,3,11,'Attack','Normal',0,1,1,19)")
            return original_freeze(party, *args, **kwargs)

        self.s = startup.FriendBattleStartupTests(methodName='runTest')
        self.addCleanup(self.s.doCleanups)
        with patch.object(party_class, 'freeze', freeze_with_pp):
            self.s.setUp()
        self.p, self.v, self.f = self.s.p, self.s.v, self.s.f
        self.a, self.b, self.c, self.d = self.f.players
        self.battle, self.ids = self.s.battle, self.v.ids
        # LIFO cleanup removes children before startup and reservation fixtures.
        self.addCleanup(lambda: self.f.execute([
            f"DELETE FROM friend_battle_selection_pairs WHERE battle_id='{self.battle}'",
            f"DELETE FROM friend_battle_selections WHERE battle_id='{self.battle}'",
        ]))

    def data(self, actor=None, **changes):
        actor = self.a if actor is None else actor
        result = dict(session_id=actor, battle_id=self.battle, type='ATTACK',
                      owned_morty_id=self.ids[2] if actor == self.b else self.ids[1],
                      move_id='AttackLick')
        result.update(changes)
        return result

    def submit(self, actor=None, data=None):
        actor = self.a if actor is None else actor
        encoded = base64.b64encode(json.dumps([self.data(actor) if data is None else data, actor]).encode()).decode()
        return json.loads(php(
            "require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "require_once '/var/www/html/lib/friend_battle_startup.php';"
            "require_once '/var/www/html/lib/friend_battle_selections.php';"
            "$a=json_decode(base64_decode('" + encoded + "'),true);"
            "try{echo json_encode(['ok'=>friend_battle_selection_submit($pdo,$a[0],$a[1])]);}"
            "catch(Throwable $e){echo json_encode(['status'=>$e instanceof FriendError?$e->status:500,"
            "'error'=>$e instanceof FriendError?$e->getMessage():'FAILED']);}"))

    def rows(self):
        return dict(selections=sql(f"SELECT * FROM friend_battle_selections WHERE battle_id='{self.battle}' ORDER BY player_id"),
                    pairs=sql(f"SELECT * FROM friend_battle_selection_pairs WHERE battle_id='{self.battle}'"))

    def snapshot(self):
        return self.rows(), self.s.rows(), self.p.gameplay(), self.p.rows(), self.v.rows()

    def reject(self, actor=None, data=None, status=409):
        before = self.snapshot()
        result = self.submit(actor, data)
        self.assertEqual(result.get('status'), status, result)
        self.assertEqual(self.snapshot(), before)

    def ready(self, *actors):
        self.s.activate()
        for actor in actors or (self.a, self.b):
            result = self.s.invoke('ready', actor)
            self.assertIn('ok', result, result)

    def assert_selection(self, result, paired):
        self.assertEqual(set(result), {'ok'}, result)
        self.assertEqual(set(result['ok']), {'selection_id', 'paired'})
        uuid.UUID(result['ok']['selection_id'])
        self.assertIs(result['ok']['paired'], paired)

    def restore(self, table, rows):
        sql(f"DELETE FROM {table} WHERE battle_id='{self.battle}'")
        for row in rows:
            columns = ','.join(row)
            values = ','.join('NULL' if value is None else quoted(value) for value in row.values())
            sql(f"INSERT INTO {table} ({columns}) VALUES ({values})")

    def test_authentication_session_match_roles_readiness_and_live_lease(self):
        self.reject()
        self.s.activate()
        self.reject()
        self.ready(self.a)
        for actor, status in (('', 400), (str(uuid.uuid4()), 401), (self.c, 403)):
            self.reject(actor, status=status)
        self.reject(data=self.data(session_id=self.b), status=403)
        self.reject(self.b)
        self.s.make_due()
        self.reject()

    def test_native_input_schema_is_exact_and_attack_only(self):
        self.ready()
        for change in ({'extra': True}, {'move_id': None}, {'owned_morty_id': []}):
            with self.subTest(change=change):
                self.reject(data=self.data(**change), status=400)
        for move_type in ('RUN', 'SWITCH', 'ITEM'):
            self.reject(data=self.data(type=move_type), status=501)
        data = self.data()
        del data['move_id']
        self.reject(data=data, status=400)

    def test_first_own_ready_selection_precedes_peer_intro_without_pairing(self):
        self.ready(self.a)
        before = self.snapshot()
        result = self.submit()
        self.assert_selection(result, False)
        rows = self.rows()
        self.assertEqual(len(rows['selections']), 1)
        self.assertEqual(rows['pairs'], [])
        self.assertEqual(self.s.rows()['sessions'][0]['state'], 'STARTING')
        self.assertTrue(self.s.rows()['startup'][0]['selection_started_at'])
        self.assertEqual(self.p.gameplay(), before[2])
        self.assertEqual(self.p.rows(), before[3])
        self.assertEqual(self.v.rows(), before[4])
        row = rows['selections'][0]
        self.assertEqual(row['selection_id'], result['ok']['selection_id'])
        self.assertEqual(hashlib.sha256(row['selection_json'].encode()).hexdigest(), row['selection_sha256'])
        self.assertIsNone(row['retired_at'])
        self.assertEqual(self.submit(), result)
        self.assertEqual(self.rows(), rows)

    def test_sender_then_recipient_pairs_once_and_replays_keep_ids(self):
        self.ready(self.a)
        first = self.submit()
        self.assert_selection(first, False)
        self.assertIn('ok', self.s.invoke('ready', self.b))
        second = self.submit(self.b)
        self.assert_selection(second, True)
        self.assert_pair(first, second)

    def test_recipient_then_sender_pairs_once_and_replays_keep_ids(self):
        self.ready()
        first = self.submit(self.b)
        second = self.submit(self.a)
        self.assert_selection(first, False)
        self.assert_selection(second, True)
        self.assert_pair(second, first)

    def assert_pair(self, sender, recipient):
        before = self.snapshot()
        rows = self.rows()
        self.assertEqual(len(rows['selections']), 2)
        self.assertEqual(len(rows['pairs']), 1)
        pair = rows['pairs'][0]
        self.assertEqual(pair['sender_selection_id'], sender['ok']['selection_id'])
        self.assertEqual(pair['recipient_selection_id'], recipient['ok']['selection_id'])
        self.assertIsNone(pair['retired_at'])
        for actor, result in ((self.a, sender), (self.b, recipient)):
            self.assertEqual(self.submit(actor), {'ok': dict(result['ok'], paired=True)})
        self.assertEqual(self.snapshot(), before)

    def test_simultaneous_distinct_inputs_commit_exactly_one_pair(self):
        self.ready()
        barrier = threading.Barrier(2)
        def send(actor):
            barrier.wait(timeout=10)
            return self.submit(actor)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, (self.a, self.b)))
        self.assertEqual(sorted(r['ok']['paired'] for r in results), [False, True])
        self.assert_pair(*results)

    def test_simultaneous_duplicate_input_keeps_one_immutable_selection(self):
        self.ready()
        barrier = threading.Barrier(2)
        def send(_):
            barrier.wait(timeout=10)
            return self.submit()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(send, range(2)))
        self.assert_selection(results[0], False)
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(self.rows()['selections']), 1)
        self.assertEqual(self.rows()['pairs'], [])

    def test_foreign_inactive_unknown_and_fainted_actor_or_attack_rejected(self):
        self.ready()
        for changes in ({'owned_morty_id': self.ids[2]}, {'owned_morty_id': self.ids[0]},
                        {'owned_morty_id': str(uuid.uuid4())}, {'move_id': 'AttackMissing'}):
            with self.subTest(changes=changes):
                self.reject(data=self.data(**changes))
        self.reject(self.b, self.data(self.b, move_id='AttackFlail'))

    def test_live_party_hp_pp_and_attack_ambiguity_drift_fail_closed(self):
        self.ready()
        for statement, restore in (
            (f"UPDATE owned_morties SET hp=0 WHERE owned_morty_id='{self.ids[1]}'",
             f"UPDATE owned_morties SET hp=37 WHERE owned_morty_id='{self.ids[1]}'"),
            (f"UPDATE owned_attacks SET pp=0 WHERE owned_morty_id='{self.ids[1]}'",
             f"UPDATE owned_attacks SET pp=3 WHERE owned_morty_id='{self.ids[1]}'"),
            (f"INSERT INTO owned_attacks(owned_morty_id,attack_id,position,pp,pp_stat) VALUES('{self.ids[1]}','AttackLick',1,3,11)",
             f"DELETE FROM owned_attacks WHERE owned_morty_id='{self.ids[1]}' AND position=1"),
        ):
            sql(statement)
            self.reject()
            sql(restore)

    def test_conflicting_retry_does_not_replace_first_selection(self):
        self.ready()
        first = self.submit()
        self.assert_selection(first, False)
        self.reject(data=self.data(move_id='AttackFlail'))
        self.assertEqual(self.submit(), first)

    def test_hash_and_schema_corruption_are_rejected_without_repair(self):
        self.ready()
        self.assert_selection(self.submit(), False)
        original = self.rows()['selections']
        bad_json = json.dumps({'schema_version': 999}, separators=(',', ':'))
        for updates in ("selection_sha256=REPEAT('0',64)",
                        f"selection_json={quoted(bad_json)},selection_sha256='{hashlib.sha256(bad_json.encode()).hexdigest()}'"):
            sql(f"UPDATE friend_battle_selections SET {updates} WHERE battle_id='{self.battle}'")
            self.reject()
            self.reject(self.b)
            self.restore('friend_battle_selections', original)

    def test_marker_row_loss_extra_role_and_orphan_pair_fail_closed(self):
        self.ready()
        self.submit()
        original = self.rows()['selections']
        sql(f"DELETE FROM friend_battle_selections WHERE battle_id='{self.battle}'")
        self.reject()
        self.restore('friend_battle_selections', original)
        marker = self.s.rows()['startup'][0]['selection_started_at']
        sql(f"UPDATE friend_battle_startups SET selection_started_at=NULL WHERE battle_id='{self.battle}'")
        self.reject()
        sql(f"UPDATE friend_battle_startups SET selection_started_at={quoted(marker)} WHERE battle_id='{self.battle}'")
        ready_at = self.s.rows()['startup'][0]['sender_ready_at']
        sql(f"UPDATE friend_battle_startups SET sender_ready_at=NULL WHERE battle_id='{self.battle}'")
        self.reject()
        sql(f"UPDATE friend_battle_startups SET sender_ready_at={quoted(ready_at)} WHERE battle_id='{self.battle}'")
        row = dict(original[0], player_id=self.c, selection_id=str(uuid.uuid4()))
        self.restore('friend_battle_selections', original + [row])
        self.reject()
        self.restore('friend_battle_selections', original)
        sql(f"INSERT INTO friend_battle_selection_pairs(battle_id,sender_selection_id,recipient_selection_id,paired_at) VALUES('{self.battle}','{original[0]['selection_id']}','{uuid.uuid4()}',UTC_TIMESTAMP(6))")
        self.reject()
        sql(f"DELETE FROM friend_battle_selection_pairs WHERE battle_id='{self.battle}'")
        self.assert_selection(self.submit(self.b), True)
        sql(f"DELETE FROM friend_battle_selection_pairs WHERE battle_id='{self.battle}'")
        self.reject()
        self.reject(self.b)

    def test_second_selection_and_pair_insert_are_one_transaction(self):
        self.ready()
        self.assert_selection(self.submit(), False)
        name = self.s.fault('INSERT', 'friend_battle_selection_pairs', f"NEW.battle_id='{self.battle}'")
        self.reject(self.b, status=500)
        sql(f'DROP TRIGGER {name}')
        self.assert_selection(self.submit(self.b), True)

    def test_first_selection_marker_update_is_atomic(self):
        self.ready()
        name = self.s.fault('UPDATE', 'friend_battle_startups',
            f"NEW.battle_id='{self.battle}' AND OLD.selection_started_at IS NULL AND NEW.selection_started_at IS NOT NULL")
        self.reject(status=500)
        sql(f'DROP TRIGGER {name}')
        self.assert_selection(self.submit(), False)

    def test_cancel_retires_pair_and_inputs_without_spend_or_events(self):
        self.ready()
        self.submit()
        self.submit(self.b)
        gameplay, source, deadline = self.p.gameplay(), self.p.rows(), self.s.rows()['startup'][0]['ready_deadline']
        self.assertEqual(self.s.invoke('cancel', self.a), {'ok': None})
        self.s.assert_cancelled('STARTUP_CANCELLED')
        self.assertTrue(all(row['retired_at'] for rows in self.rows().values() for row in rows))
        self.assertEqual(self.p.rows(), source)
        for row in gameplay['users']:
            if row['player_id'] in (self.a, self.b):
                row['state'] = 'WORLD'
        self.assertEqual(self.p.gameplay(), gameplay)
        self.assertEqual(self.s.rows()['startup'][0]['ready_deadline'], deadline)
        self.reject()
        self.f.befriend(self.c, self.b)
        self.assertEqual(self.f.create(self.c, self.b)[0], 200)
        invite = next(row for row in self.f.rows() if row['sender_id'] == self.c)
        newer = self.s.m.reserve(invite)['ok']
        self.s.m.assert_pair(newer, self.c, self.b)
        before = self.snapshot()
        self.assertEqual(self.s.invoke('cancel', self.a), {'ok': None})
        self.assertEqual(self.snapshot(), before)
        self.s.m.assert_pair(newer, self.c, self.b)

    def test_expiry_worker_retires_inputs_with_transport_disabled(self):
        self.ready(self.a)
        self.submit()
        self.s.make_due()
        self.assertEqual(self.s.expire_candidate(), 1)
        self.s.assert_cancelled('STARTUP_TIMEOUT')
        self.assertTrue(self.rows()['selections'][0]['retired_at'])
        self.assertEqual(self.rows()['pairs'], [])
        self.reject()

    def test_retirement_failure_rolls_back_whole_cancellation(self):
        self.ready()
        self.submit()
        self.submit(self.b)
        name = self.s.fault('UPDATE', 'friend_battle_selection_pairs',
            f"NEW.battle_id='{self.battle}' AND NEW.retired_at IS NOT NULL")
        before = self.snapshot()
        self.assertEqual(self.s.invoke('cancel', self.a).get('status'), 500)
        self.assertEqual(self.snapshot(), before)
        sql(f'DROP TRIGGER {name}')
        self.assertEqual(self.s.invoke('cancel', self.a), {'ok': None})

    def test_research_http_stores_pair_with_native_ack_and_default_gate_stays_closed(self):
        self.assertEqual(research_post('/session/battle-invite/response',
            {'session_id': self.b, 'token': self.s.invite['recipient_token'], 'accept': True}),
            (501, {'error': {'code': 'FAILED'}}))
        self.addCleanup(lambda: self.f.execute([
            f"DELETE FROM friend_battle_start_attempts WHERE battle_id='{self.battle}'",
            f"DELETE FROM friend_battle_stream_bindings WHERE battle_id='{self.battle}'",
            f"DELETE FROM friend_battle_streams WHERE player_id IN ('{self.f.ids}')",
        ]))

        def transport(expression):
            return json.loads(gated_php(
                "require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
                "require '/var/www/html/lib/friend_battle_startup.php';"
                "echo json_encode(" + expression + ");"))

        streams = {actor: transport(f"friend_battle_transport_open($pdo,'{actor}','{actor}')")
                   for actor in (self.a, self.b)}
        self.assertIn('ok', self.s.invoke('activate', prefix="putenv('PM_RESEARCH_SHARED_BATTLE_STREAM=1');"))
        for actor, stream in streams.items():
            result = transport(f"friend_battle_transport_poll($pdo,'{actor}','{actor}','{stream}')")
            self.assertEqual(len(result['events']), 1)
        for actor in (self.a, self.b):
            self.assertEqual(research_post('/session/battle/ready',
                {'session_id': actor, 'battle_id': self.battle}), (200, {'success': True}))
        before = self.p.gameplay(), self.p.rows(), self.s.rows()['events']
        self.assertEqual(post('/session/battle/move', self.data()),
                         (404, {'error': {'code': 'FAILED'}, 'success': False}))
        self.assertEqual(self.rows(), {'selections': [], 'pairs': []})
        for actor in (self.a, self.b):
            self.assertEqual(research_post('/session/battle/move', self.data(actor)),
                             (200, {'success': True}))
        self.assertEqual(len(self.rows()['selections']), 2)
        self.assertEqual(len(self.rows()['pairs']), 1)
        self.assertEqual((self.p.gameplay(), self.p.rows(), self.s.rows()['events']), before)
        self.assertEqual(research_post('/session/battle-invite/response',
            {'session_id': self.b, 'token': self.s.invite['recipient_token'], 'accept': True}),
            (409, {'error': {'code': 'TOKEN_NOTVALID'}}))


if __name__ == '__main__':
    unittest.main()

"""Internal shared reservations using additive UUID fixtures; never reseed accounts."""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import unittest
import uuid

import test_friend_battle_invites as invitations
from test_http import php, post, sql


class FriendBattleMembershipTests(unittest.TestCase):
    def setUp(self):
        self.f = invitations.FriendBattleInviteTests(methodName='runTest')
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.a, self.b, self.c, self.d = self.f.players
        self.addCleanup(self.cleanup_membership)

    def cleanup_membership(self):
        self.f.execute([
            f"DELETE FROM friend_battle_memberships WHERE player_id IN ('{self.f.ids}')",
            f"DELETE FROM friend_battle_sessions WHERE sender_id IN ('{self.f.ids}') OR recipient_id IN ('{self.f.ids}')",
        ])

    def invoke(self, action, session, value):
        encoded = base64.b64encode(json.dumps([action, session, value]).encode()).decode()
        return json.loads(php(
            "require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "require '/var/www/html/lib/friend_battle_membership.php';"
            "$args=json_decode(base64_decode('" + encoded + "'),true);"
            "try {$result=$args[0]==='reserve' ? friend_battle_reserve($pdo,$args[1],$args[2]) : "
            "friend_battle_cancel_reservation($pdo,$args[1],$args[2]); echo json_encode(['ok'=>$result]);}"
            "catch(Throwable $e) {echo json_encode(['status'=>$e instanceof FriendError ? $e->status : 500,"
            "'error'=>$e instanceof FriendError ? $e->getMessage() : 'FAILED']);}"
        ))

    def reserve(self, row, actor=None, token=None):
        return self.invoke('reserve', actor or self.b, token or row['recipient_token'])

    def cancel(self, battle, actor=None):
        return self.invoke('cancel', actor or self.a, battle)

    def sessions(self):
        return sql(f"SELECT * FROM friend_battle_sessions WHERE sender_id IN ('{self.f.ids}') OR recipient_id IN ('{self.f.ids}') ORDER BY battle_id")

    def claims(self):
        return sql(f"SELECT * FROM friend_battle_memberships WHERE player_id IN ('{self.f.ids}') ORDER BY player_id")

    def assert_error(self, result, status=409, error='FAILED'):
        self.assertEqual(result, {'status': status, 'error': error})

    def pending(self):
        return self.f.pending()[1]

    def assert_pair(self, battle, first=None, second=None):
        self.assertEqual(self.claims(), sorted([
            {'player_id': first or self.a, 'battle_id': battle},
            {'player_id': second or self.b, 'battle_id': battle},
        ], key=lambda row: row['player_id']))

    def test_reserve_both_claims_replay_and_preserve_gameplay_and_invite(self):
        row = self.pending()
        before = self.f.snapshot()
        result = self.reserve(row)
        self.assertEqual(set(result), {'ok'}, result)
        battle = result['ok']
        self.assertEqual(str(uuid.UUID(battle)), battle)
        self.assert_pair(battle)
        sessions = self.sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual((sessions[0]['battle_id'], sessions[0]['invite_id'], sessions[0]['sender_id'],
                          sessions[0]['recipient_id'], sessions[0]['state']),
                         (battle, row['invite_id'], self.a, self.b, 'PREPARING'))
        self.assertEqual(self.reserve(row), result)
        self.assertEqual(self.sessions(), sessions)
        self.assert_pair(battle)
        self.assertEqual(self.f.rows(), [row])
        self.assertEqual(self.f.snapshot(), before)
        self.f.error(self.f.call('response', self.b, token=row['recipient_token'], accept=True), 501, 'FAILED')
        self.assertEqual(self.sessions(), sessions)

    def test_authentication_roles_and_unknown_tokens_cannot_claim(self):
        row = self.pending()
        for actor, token in ((self.a, row['recipient_token']), (self.a, row['sender_token']),
                             (self.b, row['sender_token']), (self.c, row['recipient_token']),
                             (self.b, 'a' * 64)):
            self.assert_error(self.reserve(row, actor, token), 403, 'TOKEN_NOTVALID')
        for actor in ('', str(uuid.uuid4())):
            self.assert_error(self.invoke('reserve', actor, row['recipient_token']), 401)
        sql(f"UPDATE users SET session_id='{self.b}' WHERE player_id='{self.c}'")
        self.assert_error(self.reserve(row), 401)
        self.assertEqual(self.sessions(), [])
        self.assertEqual(self.claims(), [])
        self.assertEqual(self.f.rows(), [row])

    def test_expired_and_closed_invites_cannot_claim(self):
        row = self.pending()
        for state in ('DECLINED', 'REVOKED', 'EXPIRED'):
            sql(f"UPDATE friend_battle_invites SET state='{state}' WHERE invite_id='{row['invite_id']}'")
            self.assert_error(self.reserve(row))
            self.assertEqual(self.sessions(), [])
            self.assertEqual(self.claims(), [])
        sql(f"UPDATE friend_battle_invites SET state='PENDING',expires_at=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE invite_id='{row['invite_id']}'")
        before = self.f.rows()
        self.assert_error(self.reserve(row))
        self.assertEqual(self.f.rows(), before)
        self.assertEqual(self.sessions(), [])

    def test_replay_revalidates_invite_and_preserves_existing_claims(self):
        row = self.pending()
        battle = self.reserve(row)['ok']
        sessions = self.sessions()
        before = self.f.snapshot()
        for mutation in ("state='REVOKED'", "state='PENDING',expires_at=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND"):
            sql(f"UPDATE friend_battle_invites SET {mutation} WHERE invite_id='{row['invite_id']}'")
            invites = self.f.rows()
            self.assert_error(self.reserve(row))
            self.assert_pair(battle)
            self.assertEqual(self.sessions(), sessions)
            self.assertEqual(self.f.rows(), invites)
            self.assertEqual(self.f.snapshot(), before)
        sql(f"UPDATE friend_battle_invites SET state='PENDING',expires_at=UTC_TIMESTAMP(6)+INTERVAL 60 SECOND WHERE invite_id='{row['invite_id']}'")
        self.assertEqual(self.reserve(row), {'ok': battle})
        self.assertEqual(self.cancel(battle), {'ok': None})

    def test_world_and_legacy_battle_checks_cover_both_participants_and_columns(self):
        row = self.pending()
        for player in (self.a, self.b):
            sql(f"UPDATE users SET state='BATTLE' WHERE player_id='{player}'")
            self.assert_error(self.reserve(row))
            sql(f"UPDATE users SET state='WORLD' WHERE player_id='{player}'")
            for column in ('player_id', 'opponent_id'):
                battle = str(uuid.uuid4())
                owner, opponent = (player, self.c) if column == 'player_id' else (self.c, player)
                sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,state) VALUES ('{battle}','{owner}','{opponent}','ACTIVE')")
                self.assert_error(self.reserve(row))
                sql(f"DELETE FROM battles WHERE battle_id='{battle}'")
        self.assertEqual(self.claims(), [])
        self.assertEqual(self.sessions(), [])

    def test_friendship_must_still_be_accepted_and_unambiguous(self):
        row = self.pending()
        sql(f"UPDATE friend_list SET pending='true' WHERE player_id_a='{self.a}' AND player_id_b='{self.b}'")
        self.assert_error(self.reserve(row))
        sql(f"UPDATE friend_list SET pending='false' WHERE player_id_a='{self.a}' AND player_id_b='{self.b}'")
        self.f.befriend(self.b, self.a)
        self.assert_error(self.reserve(row))
        self.assertEqual(self.claims(), [])

    def test_overlapping_concurrent_reservations_have_one_winner(self):
        row = self.pending()
        self.f.befriend(self.c, self.b)
        status, created = self.f.create(self.c, self.b)
        self.assertEqual(status, 200, created)
        other = next(r for r in self.f.rows() if r['invite_id'] == created['battle_invite_id'])
        before = self.f.snapshot()
        barrier = threading.Barrier(2)
        def reserve(invite):
            barrier.wait(timeout=5)
            return self.reserve(invite)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, [row, other]))
        winners = [r['ok'] for r in results if 'ok' in r]
        self.assertEqual(len(winners), 1, results)
        self.assert_error(next(r for r in results if 'ok' not in r))
        self.assertEqual(len(self.sessions()), 1)
        session = self.sessions()[0]
        self.assert_pair(winners[0], session['sender_id'], self.b)
        self.assertEqual(self.f.snapshot(), before)

    def test_concurrent_same_reservation_replays_one_id(self):
        row = self.pending()
        barrier = threading.Barrier(2)
        def reserve(_):
            barrier.wait(timeout=5)
            return self.reserve(row)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(reserve, range(2)))
        self.assertEqual(results[0], results[1])
        self.assertIn('ok', results[0])
        self.assertEqual(len(self.sessions()), 1)
        self.assert_pair(results[0]['ok'])

    def test_second_claim_failure_rolls_back_session_and_first_claim(self):
        row = self.pending()
        before = self.f.snapshot()
        trigger = 'membership_fault_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        # The fault is confined to this UUID pair, including concurrent test runs.
        second = sorted([self.a, self.b])[1]
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON friend_battle_memberships FOR EACH ROW BEGIN IF NEW.player_id='{second}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID second claim failure'; END IF; END")
        try:
            self.assert_error(self.reserve(row), 500)
            self.assertEqual(self.claims(), [])
            self.assertEqual(self.sessions(), [])
            self.assertEqual(self.f.rows(), [row])
            self.assertEqual(self.f.snapshot(), before)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')
        self.assertIn('ok', self.reserve(row))

    def test_either_participant_can_cancel_and_retries_preserve_newer_claims(self):
        row = self.pending()
        before = self.f.snapshot()
        battle = self.reserve(row)['ok']
        self.assert_error(self.cancel(battle, self.c), 403, 'TOKEN_NOTVALID')
        self.assert_pair(battle)
        self.assertEqual(self.cancel(battle, self.b), {'ok': None})
        self.assertEqual(self.claims(), [])
        self.assertEqual(self.sessions()[0]['state'], 'CANCELLED')
        terminal = self.sessions()
        self.assertEqual(self.cancel(battle), {'ok': None})
        self.assertEqual(self.sessions(), terminal)
        self.assert_error(self.reserve(row))
        self.f.befriend(self.c, self.b)
        self.assertEqual(self.f.create(self.c, self.b)[0], 200)
        other = next(r for r in self.f.rows() if r['sender_id'] == self.c)
        newer = self.reserve(other)['ok']
        sessions = self.sessions()
        self.assertEqual(self.cancel(battle), {'ok': None})
        self.assertEqual(self.sessions(), sessions)
        self.assert_pair(newer, self.c, self.b)
        self.assertEqual(self.cancel(newer, self.c), {'ok': None})
        self.assertEqual(self.claims(), [])
        after = self.f.snapshot()
        after.pop('friends')
        before.pop('friends')
        self.assertEqual(after, before)

    def test_missing_or_tampered_claim_fails_closed_without_repair(self):
        row = self.pending()
        battle = self.reserve(row)['ok']
        sql(f"DELETE FROM friend_battle_memberships WHERE player_id='{self.a}'")
        claims = self.claims()
        self.assert_error(self.reserve(row))
        self.assert_error(self.cancel(battle))
        self.assertEqual(self.claims(), claims)
        self.assertEqual(self.sessions()[0]['state'], 'PREPARING')
        sql(f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{self.a}','{battle}')")
        sql(f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{self.c}','{battle}')")
        claims = self.claims()
        self.assert_error(self.reserve(row))
        self.assert_error(self.cancel(battle))
        self.assertEqual(self.claims(), claims)
        self.assertEqual(self.sessions()[0]['state'], 'PREPARING')
        wrong = str(uuid.uuid4())
        sql(f"DELETE FROM friend_battle_memberships WHERE player_id='{self.c}'")
        sql(f"UPDATE friend_battle_memberships SET battle_id='{wrong}' WHERE player_id='{self.a}'")
        claims = self.claims()
        self.assert_error(self.reserve(row))
        self.assert_error(self.cancel(battle))
        self.assertEqual(self.claims(), claims)
        self.assertEqual(self.sessions()[0]['state'], 'PREPARING')

    def test_cancellation_update_failure_restores_both_claims(self):
        row = self.pending()
        battle = self.reserve(row)['ok']
        before = self.f.snapshot()
        sessions = self.sessions()
        for actor in ('', str(uuid.uuid4())):
            self.assert_error(self.invoke('cancel', actor, battle), 401)
        self.assert_error(self.cancel(str(uuid.uuid4())), 403, 'TOKEN_NOTVALID')
        trigger = 'membership_cancel_fault_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE UPDATE ON friend_battle_sessions FOR EACH ROW BEGIN IF OLD.battle_id='{battle}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID cancellation rollback'; END IF; END")
        try:
            self.assert_error(self.cancel(battle), 500)
            self.assert_pair(battle)
            self.assertEqual(self.sessions(), sessions)
            self.assertEqual(self.f.snapshot(), before)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')
        self.assertEqual(self.cancel(battle), {'ok': None})
        self.assertEqual(self.claims(), [])

    def test_reservation_blocks_world_actions_wild_start_and_new_invites(self):
        room, wild = str(uuid.uuid4()), str(uuid.uuid4())
        self.addCleanup(lambda: self.f.execute([
            f"DELETE FROM event_queue WHERE room_id='{room}'",
            f"DELETE FROM room_ids WHERE room_id='{room}'",
        ]))
        self.f.execute([
            f"INSERT INTO room_ids (room_id,world_id,zone_id) VALUES ('{room}','membership-test','[1,1]')",
            f"UPDATE users SET room_id='{room}',active_deck_id=1 WHERE player_id IN ('{self.a}','{self.b}')",
            f"INSERT INTO event_queue (room_id,event_name,wild_morty_id,morty_id,state,placement,variant) VALUES ('{room}','room:wild-morty-added','{wild}','Morty','WORLD','0,0','Normal')",
        ])
        self.f.befriend(self.a, self.c)
        self.f.befriend(self.c, self.b)
        row = self.pending()
        battle = self.reserve(row)['ok']
        before = self.f.snapshot()
        spawn = sql(f"SELECT * FROM event_queue WHERE room_id='{room}' ORDER BY id")
        for actor in (self.a, self.b):
            for path, body in (('/session/heal', {}), ('/session/leave-room', {}),
                               ('/session/battle-wild-morty', {'wild_morty_id': wild})):
                result = post(path, dict(session_id=actor, **body))
                self.assertEqual(result[0], 409, (path, result))
                self.assertEqual(self.f.snapshot(), before)
                self.assertEqual(sql(f"SELECT * FROM event_queue WHERE room_id='{room}' ORDER BY id"), spawn)
        self.f.error(self.f.create(self.a, self.c), 409, 'FAILED')
        self.f.error(self.f.create(self.c, self.b), 409, 'OPPONENT_STATE_INVALID')
        self.assert_pair(battle)
        self.assertEqual(self.cancel(battle), {'ok': None})
        self.assertEqual(post('/session/heal', {'session_id': self.a})[0], 200)
        self.assertEqual(post('/session/battle-wild-morty', {'session_id': self.a, 'wild_morty_id': wild}),
                         (200, {'success': True}))


if __name__ == '__main__':
    unittest.main()

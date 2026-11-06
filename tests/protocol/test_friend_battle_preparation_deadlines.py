"""Preparation expiry against additive UUID fixtures; never reseed accounts."""
import base64
import json
import unittest
import uuid

import test_friend_battle_membership as membership
from test_http import php, sql


class FriendBattlePreparationDeadlineTests(unittest.TestCase):
    def setUp(self):
        self.m = membership.FriendBattleMembershipTests(methodName='runTest')
        self.addCleanup(self.m.doCleanups)
        self.m.setUp()
        self.f = self.m.f
        self.a, self.b, self.c, self.d = self.f.players

    def reserved(self):
        row = self.m.pending()
        result = self.m.reserve(row)
        self.assertIn('ok', result)
        return row, result['ok']

    def candidate(self, battle):
        return {'battle_id': battle, 'sender_id': self.a, 'recipient_id': self.b}

    def worker(self, candidates, session=None, player=None):
        return self.invoke('candidates', [candidates, session, player])['count']

    def invoke(self, action, args):
        encoded = base64.b64encode(json.dumps([action, args]).encode()).decode()
        return json.loads(php(
            "require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "require '/var/www/html/lib/friend_battle_preparations.php';"
            "$v=json_decode(base64_decode('" + encoded + "'),true);$a=$v[1];"
            "if($v[0]==='candidates'){$n=friend_battle_prepare_expire_candidates($pdo,$a[0],$a[1],$a[2]);}"
            "elseif($v[0]==='player'){$n=friend_battle_prepare_expire_player($pdo,$a[0],$a[1],$a[2]);}"
            "else{$cursor=$a[1];$n=friend_battle_prepare_sweep($pdo,$a[0],$cursor);}"
            "echo json_encode(['count'=>$n,'cursor'=>$cursor??null,'transaction'=>$pdo->inTransaction()]);"
        ))

    def deadline(self, battle, expression):
        sql(f"UPDATE friend_battle_sessions SET prepare_deadline={expression} WHERE battle_id='{battle}'")

    def due(self, battle):
        self.deadline(battle, 'UTC_TIMESTAMP(6)-INTERVAL 1 SECOND')

    def state(self, battle):
        return next(r for r in self.m.sessions() if r['battle_id'] == battle)

    def assert_cancelled(self, battle, reason):
        row = self.state(battle)
        self.assertEqual((row['state'], row['cancel_reason']), ('CANCELLED', reason))
        self.assertEqual(self.m.claims(), [])

    def test_due_releases_both_claims_without_gameplay_invite_or_event_changes(self):
        invite, battle = self.reserved()
        self.due(battle)
        before = self.f.snapshot()
        self.assertEqual(self.worker([self.candidate(battle)]), 1)
        self.assert_cancelled(battle, 'PREPARATION_TIMEOUT')
        self.assertEqual(self.f.rows(), [invite])
        self.assertEqual(self.f.snapshot(), before)

    def test_default_deadline_replay_never_extends_and_future_worker_is_noop(self):
        invite, battle = self.reserved()
        remaining = sql(f"SELECT TIMESTAMPDIFF(SECOND,UTC_TIMESTAMP(6),prepare_deadline) AS remaining FROM friend_battle_sessions WHERE battle_id='{battle}'")[0]['remaining']
        self.assertGreaterEqual(int(remaining), 20)
        self.assertLessEqual(int(remaining), 30)
        sessions = self.m.sessions()
        self.assertEqual(self.m.reserve(invite), {'ok': battle})
        self.assertEqual(self.worker([self.candidate(battle)]), 0)
        self.assertEqual(self.m.sessions(), sessions)
        self.m.assert_pair(battle)

    def test_configured_deadline_accepts_only_bounded_integer_seconds(self):
        for configured, expected in [('10', 10), ('120', 120), ('', 30), ('9', None), ('121', None), ('bad', None), ('10.5', None)]:
            with self.subTest(configured=configured):
                fixture = membership.FriendBattleMembershipTests(methodName='runTest')
                fixture.setUp()
                try:
                    invite = fixture.pending()
                    encoded = base64.b64encode(json.dumps([configured, fixture.b, invite['recipient_token']]).encode()).decode()
                    result = json.loads(php(
                        "$a=json_decode(base64_decode('" + encoded + "'),true);"
                        "putenv('PM_FRIEND_BATTLE_PREPARE_SECONDS='.$a[0]);"
                        "require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
                        "require '/var/www/html/lib/friend_battle_membership.php';"
                        "try{$battle=friend_battle_reserve($pdo,$a[1],$a[2]);"
                        "$q=$pdo->prepare('SELECT TIMESTAMPDIFF(SECOND,created_at,prepare_deadline) AS seconds FROM friend_battle_sessions WHERE battle_id=?');"
                        "$q->execute([$battle]);echo json_encode($q->fetch());}"
                        "catch(Throwable $e){echo json_encode(['status'=>$e instanceof FriendError?$e->status:500,'error'=>$e instanceof FriendError?$e->getMessage():'FAILED']);}"
                    ))
                    if expected is None:
                        self.assertEqual(result, {'status': 500, 'error': 'FAILED'})
                        self.assertEqual(fixture.sessions(), [])
                        self.assertEqual(fixture.claims(), [])
                    else:
                        self.assertEqual(int(result['seconds']), expected)
                finally:
                    fixture.doCleanups()

    def test_due_and_historical_null_replays_fail_without_changing_claims(self):
        invite, battle = self.reserved()
        for expression in ('UTC_TIMESTAMP(6)-INTERVAL 1 SECOND', 'NULL'):
            with self.subTest(deadline=expression):
                self.deadline(battle, expression)
                sessions = self.m.sessions()
                self.m.assert_error(self.m.reserve(invite))
                self.assertEqual(self.m.sessions(), sessions)
                self.m.assert_pair(battle)

    def test_historical_null_is_preserved_even_with_closed_invite_and_removed_friend(self):
        invite, battle = self.reserved()
        self.deadline(battle, 'NULL')
        sql(f"UPDATE friend_battle_invites SET state='REVOKED' WHERE invite_id='{invite['invite_id']}'")
        sql(f"DELETE FROM friend_list WHERE player_id_a='{self.a}' AND player_id_b='{self.b}'")
        sessions = self.m.sessions()
        self.assertEqual(self.worker([self.candidate(battle)]), 0)
        self.assertEqual(self.m.sessions(), sessions)
        self.m.assert_pair(battle)

    def test_closed_expired_and_missing_invites_cancel_known_deadline(self):
        # Each iteration owns an independent additive fixture, avoiding terminal replays.
        for mutation in ('DECLINED', 'REVOKED', 'EXPIRED', 'expired-time', 'missing'):
            with self.subTest(mutation=mutation):
                fixture = membership.FriendBattleMembershipTests(methodName='runTest')
                fixture.setUp()
                try:
                    invite = fixture.pending()
                    battle = fixture.reserve(invite)['ok']
                    sql(f"UPDATE friend_battle_sessions SET prepare_deadline=UTC_TIMESTAMP(6)+INTERVAL 1 MINUTE WHERE battle_id='{battle}'")
                    if mutation == 'missing':
                        sql(f"DELETE FROM friend_battle_invites WHERE invite_id='{invite['invite_id']}'")
                    elif mutation == 'expired-time':
                        sql(f"UPDATE friend_battle_invites SET expires_at=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE invite_id='{invite['invite_id']}'")
                    else:
                        sql(f"UPDATE friend_battle_invites SET state='{mutation}' WHERE invite_id='{invite['invite_id']}'")
                    before, invites = fixture.f.snapshot(), fixture.f.rows()
                    candidate = {'battle_id': battle, 'sender_id': fixture.a, 'recipient_id': fixture.b}
                    self.assertEqual(self.worker([candidate]), 1)
                    self.assertEqual(fixture.sessions()[0]['cancel_reason'], 'INVITE_CLOSED')
                    self.assertEqual(fixture.claims(), [])
                    self.assertEqual(fixture.f.snapshot(), before)
                    self.assertEqual(fixture.f.rows(), invites)
                finally:
                    fixture.doCleanups()

    def test_removed_friend_cancels_before_future_deadline(self):
        invite, battle = self.reserved()
        self.deadline(battle, 'UTC_TIMESTAMP(6)+INTERVAL 1 MINUTE')
        sql(f"DELETE FROM friend_list WHERE player_id_a='{self.a}' AND player_id_b='{self.b}'")
        before = self.f.snapshot()
        self.assertEqual(self.worker([self.candidate(battle)]), 1)
        self.assert_cancelled(battle, 'FRIEND_REMOVED')
        self.assertEqual(self.f.rows(), [invite])
        self.assertEqual(self.f.snapshot(), before)

    def test_duplicate_stale_hint_and_refreshed_deadline_revalidate_locked_rows(self):
        _, battle = self.reserved()
        self.due(battle)
        stale = dict(self.candidate(battle), sender_id=self.c)
        sessions = self.m.sessions()
        self.assertEqual(self.worker([stale]), 0)
        self.assertEqual(self.m.sessions(), sessions)
        candidate = dict(self.candidate(battle), prepare_deadline='2000-01-01 00:00:00.000000')
        self.deadline(battle, 'UTC_TIMESTAMP(6)+INTERVAL 1 MINUTE')
        self.assertEqual(self.worker([candidate, candidate]), 0)
        self.m.assert_pair(battle)
        self.due(battle)
        self.assertEqual(self.worker([candidate, candidate]), 1)
        self.assert_cancelled(battle, 'PREPARATION_TIMEOUT')

    def test_missing_extra_and_redirected_claims_fail_closed(self):
        _, battle = self.reserved()
        self.due(battle)
        mutations = [
            f"DELETE FROM friend_battle_memberships WHERE player_id='{self.a}'",
            f"INSERT INTO friend_battle_memberships(player_id,battle_id) VALUES('{self.c}','{battle}')",
            f"UPDATE friend_battle_memberships SET battle_id='{uuid.uuid4()}' WHERE player_id='{self.a}'",
        ]
        for index, mutation in enumerate(mutations):
            with self.subTest(mutation=index):
                sql(mutation)
                sessions, claims = self.m.sessions(), self.m.claims()
                self.assertEqual(self.worker([self.candidate(battle)]), 0)
                self.assertEqual(self.m.sessions(), sessions)
                self.assertEqual(self.m.claims(), claims)
                sql(f"DELETE FROM friend_battle_memberships WHERE player_id IN ('{self.f.ids}')")
                self.f.execute([f"INSERT INTO friend_battle_memberships(player_id,battle_id) VALUES('{p}','{battle}')" for p in (self.a, self.b)])

    def test_old_worker_does_not_delete_newer_claims(self):
        _, battle = self.reserved()
        self.due(battle)
        candidate = self.candidate(battle)
        self.assertEqual(self.worker([candidate]), 1)
        self.f.befriend(self.c, self.b)
        self.assertEqual(self.f.create(self.c, self.b)[0], 200)
        invite = next(r for r in self.f.rows() if r['sender_id'] == self.c)
        newer = self.m.reserve(invite)['ok']
        sessions, claims = self.m.sessions(), self.m.claims()
        self.assertEqual(self.worker([candidate]), 0)
        self.assertEqual(self.m.sessions(), sessions)
        self.assertEqual(self.m.claims(), claims)
        self.m.assert_pair(newer, self.c, self.b)

    def test_update_failure_rolls_back_claim_deletion_and_closes_transaction(self):
        _, battle = self.reserved()
        self.due(battle)
        sessions, before = self.m.sessions(), self.f.snapshot()
        trigger = 'preparation_fault_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE UPDATE ON friend_battle_sessions FOR EACH ROW BEGIN IF OLD.battle_id='{battle}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID preparation rollback'; END IF; END")
        try:
            result = self.invoke('candidates', [[self.candidate(battle)], None, None])
            self.assertEqual(result['count'], 0)
            self.assertFalse(result['transaction'])
            self.assertEqual(self.m.sessions(), sessions)
            self.m.assert_pair(battle)
            self.assertEqual(self.f.snapshot(), before)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')
        self.assertEqual(self.worker([self.candidate(battle)]), 1)

    def test_player_lookup_skips_revoked_session_and_unrelated_player(self):
        _, battle = self.reserved()
        self.due(battle)
        sessions = self.m.sessions()
        sql(f"UPDATE users SET session_id='{uuid.uuid4()}' WHERE player_id='{self.a}'")
        self.assertEqual(self.invoke('player', [self.a, 8, self.a])['count'], 0)
        self.assertEqual(self.invoke('player', [self.c, 8, None])['count'], 0)
        self.assertEqual(self.m.sessions(), sessions)
        self.m.assert_pair(battle)
        self.assertEqual(self.invoke('player', [self.b, 8, self.b])['count'], 1)
        self.assert_cancelled(battle, 'PREPARATION_TIMEOUT')

    def test_sweep_keyset_advances_past_inconsistent_future_rows(self):
        invite, battle = self.reserved()
        # A unique contiguous UUID range lets the scheduler test stay additive.
        prefix = uuid.uuid4().hex[:8]
        ids = [f'{prefix}-0000-4000-8000-{i:012x}' for i in range(4)]
        self.f.execute([
            f"UPDATE friend_battle_memberships SET battle_id='{ids[3]}' WHERE battle_id='{battle}'",
            f"UPDATE friend_battle_sessions SET battle_id='{ids[3]}',prepare_deadline=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE battle_id='{battle}'",
            *[f"INSERT INTO friend_battle_sessions(battle_id,invite_id,sender_id,recipient_id,state,prepare_deadline,created_at,updated_at) VALUES('{ids[i]}','{uuid.uuid4()}','{self.a}','{self.b}','PREPARING',UTC_TIMESTAMP(6)+INTERVAL 1 MINUTE,UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))" for i in (1, 2)],
        ])
        cursor = ids[0]
        for expected in ids[1:]:
            result = self.invoke('sweep', [1, cursor])
            self.assertEqual(result['cursor'], expected)
            self.assertEqual(result['count'], int(expected == ids[3]))
            cursor = result['cursor']
        self.assert_cancelled(ids[3], 'PREPARATION_TIMEOUT')
        self.assertEqual([self.state(i)['state'] for i in ids[1:3]], ['PREPARING', 'PREPARING'])
        reset = self.invoke('sweep', [1, 'ffffffff-ffff-ffff-ffff-ffffffffffff'])
        self.assertIsNone(reset['cursor'])
        self.assertEqual(reset['count'], 0)


if __name__ == '__main__':
    unittest.main()

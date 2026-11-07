"""Shared reservation exclusion using additive UUID fixtures, never account reseeds."""
import json
import unittest
import uuid

import test_battle_lifecycle as lifecycle
from test_http import php, post, sql


class SharedBattleGuardTests(unittest.TestCase):
    def setUp(self):
        self.f = lifecycle.BattleLifecycleTests()
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        self.shared = str(uuid.uuid4())
        self.invite = str(uuid.uuid4())
        self.donors = {self.f.morty: str(uuid.uuid4()), self.f.other_morty: str(uuid.uuid4())}
        self.addCleanup(self.cleanup_shared)
        self.f.execute([
            f"INSERT INTO friend_list (player_id_a,player_id_b,pending,direction,created,modified) VALUES ('{self.f.player}','{self.f.other_player}','false','true',NOW(),NOW())",
            f"UPDATE owned_morties SET hp=10 WHERE player_id IN ('{self.f.player}','{self.f.other_player}')",
            f"UPDATE owned_attacks SET pp=1 WHERE owned_morty_id IN ('{self.f.morty}','{self.f.other_morty}')",
            *[f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat,variant,is_locked,is_trading_locked) VALUES ('{self.donors[morty]}','{player}','Morty',100,100,'Normal','false','false')"
              for player, morty in ((self.f.player, self.f.morty), (self.f.other_player, self.f.other_morty))],
        ])

    def cleanup_shared(self):
        self.f.execute([
            f"DELETE FROM friend_battle_memberships WHERE player_id IN ('{self.f.player}','{self.f.other_player}')",
            f"DELETE FROM friend_battle_sessions WHERE sender_id IN ('{self.f.player}','{self.f.other_player}') OR recipient_id IN ('{self.f.player}','{self.f.other_player}')",
            f"DELETE FROM friend_battle_invites WHERE sender_id IN ('{self.f.player}','{self.f.other_player}') OR recipient_id IN ('{self.f.player}','{self.f.other_player}')",
            f"DELETE FROM friend_list WHERE player_id_a IN ('{self.f.player}','{self.f.other_player}') OR player_id_b IN ('{self.f.player}','{self.f.other_player}')",
            f"DELETE FROM battles WHERE opponent_id IN ('{self.f.player}','{self.f.other_player}')",
        ])

    def claim(self, player, battle=None):
        battle = self.shared if battle is None else battle
        sql(f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{player}','{battle}')")

    def snapshot(self):
        result = self.f.snapshot()
        for table in ('friend_battle_memberships', 'friend_battle_invites'):
            predicate = (f"player_id IN ('{self.f.player}','{self.f.other_player}')" if table.endswith('memberships')
                         else f"sender_id IN ('{self.f.player}','{self.f.other_player}') OR recipient_id IN ('{self.f.player}','{self.f.other_player}')")
            result[table] = sql(f"SELECT * FROM {table} WHERE {predicate}")
        result['friend_battle_sessions'] = sql(f"SELECT * FROM friend_battle_sessions WHERE sender_id IN ('{self.f.player}','{self.f.other_player}') OR recipient_id IN ('{self.f.player}','{self.f.other_player}')")
        return result

    def actions(self, session, morty):
        return [
            ('heal', {'session_id': session}),
            ('join-room', {'session_id': session, 'world_id': 'battle-test'}),
            ('leave-room', {'session_id': session}),
            ('owned_morties/absorb', {'session_id': session, 'owned_morty_id': morty,
                                     'absorb_owned_morty_ids': [self.donors[morty]]}),
            ('battle-wild-morty', {'session_id': session, 'wild_morty_id': self.f.wild}),
        ]

    def assert_actions_blocked(self, session, morty):
        before = self.snapshot()
        for action, request in self.actions(session, morty):
            with self.subTest(action=action, session=session):
                response = post('/session/' + action, request)
                self.assertEqual(response[0], 409, response)
                self.assertEqual(self.snapshot(), before)

    def test_both_participants_block_world_writes_without_legacy_battle(self):
        sql(f"INSERT INTO friend_battle_sessions (battle_id,invite_id,sender_id,recipient_id,state,created_at,updated_at) VALUES ('{self.shared}','{self.invite}','{self.f.player}','{self.f.other_player}','PREPARING',UTC_TIMESTAMP(6),UTC_TIMESTAMP(6))")
        for player in (self.f.player, self.f.other_player):
            self.claim(player)
        self.assertEqual(self.f.snapshot()['battles'], [])
        for session, morty in ((self.f.session, self.f.morty),
                               (self.f.other_session, self.f.other_morty)):
            self.assert_actions_blocked(session, morty)

    def test_orphaned_and_malformed_claims_remain_busy(self):
        # The guard must not join away orphaned claims or validate them into absence.
        for battle in (str(uuid.uuid4()), ''):
            with self.subTest(battle=battle):
                self.claim(self.f.player, battle)
                self.assert_actions_blocked(self.f.session, self.f.morty)
                sql(f"DELETE FROM friend_battle_memberships WHERE player_id='{self.f.player}'")

    def test_legacy_opponent_claim_also_blocks_world_actions(self):
        sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,state) VALUES ('{self.shared}','{self.f.other_player}','{self.f.player}','ACTIVE')")
        self.assert_actions_blocked(self.f.session, self.f.morty)

    def poll(self, player, session):
        return json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                              "require '/var/www/html/lib/friend_invite_stream.php'; $seen=[]; "
                              f"echo json_encode(friend_battle_invite_events($pdo,'{player}','{session}',$seen));"))

    def test_claim_on_either_side_suppresses_pending_stream_without_terminal(self):
        sql(f"INSERT INTO friend_battle_invites (invite_id,sender_id,recipient_id,sender_token,recipient_token,state,created_at,expires_at,updated_at) "
            f"VALUES ('{self.invite}','{self.f.player}','{self.f.other_player}','{'a' * 64}','{'b' * 64}','PENDING',UTC_TIMESTAMP(6),DATE_ADD(UTC_TIMESTAMP(6),INTERVAL 60 SECOND),UTC_TIMESTAMP(6))")
        self.assertEqual(self.poll(self.f.other_player, self.f.other_session)[0]['event'], 'battle-invite:received')
        for player in (self.f.player, self.f.other_player):
            with self.subTest(player=player):
                self.claim(player)
                before = self.snapshot()
                self.assertEqual(self.poll(self.f.other_player, self.f.other_session), [])
                self.assertEqual(self.poll(self.f.player, self.f.session), [])
                self.assertEqual(self.snapshot(), before)
                sql(f"DELETE FROM friend_battle_memberships WHERE player_id='{player}'")
        self.assertEqual(self.poll(self.f.other_player, self.f.other_session)[0]['event'], 'battle-invite:received')

    def test_invite_create_rejects_claimed_sender_or_recipient(self):
        for player, code in ((self.f.player, 'FAILED'), (self.f.other_player, 'OPPONENT_STATE_INVALID')):
            with self.subTest(player=player):
                self.claim(player)
                before = self.snapshot()
                response = post('/session/battle-invite/create', {
                    'session_id': self.f.session, 'opponent_player_id': self.f.other_player,
                    'battle_type': 'PvF'})
                self.assertEqual(response, (409, {'error': {'code': code}}))
                self.assertEqual(self.snapshot(), before)
                sql(f"DELETE FROM friend_battle_memberships WHERE player_id='{player}'")


if __name__ == '__main__':
    unittest.main()

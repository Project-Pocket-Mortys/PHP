"""Internal PvF start projections against additive UUID fixtures; never reseed."""
import base64
import hashlib
import json
import unittest
import uuid

import test_friend_battle_party_snapshots as parties
from test_http import php, sql

quoted = parties.quoted


class FriendBattleStartViewTests(unittest.TestCase):
    def setUp(self):
        self.p = parties.FriendBattlePartySnapshotTests(methodName='runTest')
        self.addCleanup(self.p.doCleanups)
        self.p.setUp()
        self.m, self.f = self.p.m, self.p.f
        self.a, self.b, self.c, self.d = self.f.players
        self.battle, self.invite, self.ids = self.p.battle, self.p.invite, self.p.ids
        self.addCleanup(lambda: sql(f"DELETE FROM friend_battle_start_views WHERE battle_id='{self.battle}'"))
        self.f.execute([
            f"UPDATE users SET username='Trainer A',player_avatar_id='AvatarRickDefault',level=12,streak=3,xp=417,xp_lower=400,xp_upper=500,coins=29,coupons=7,permits=2 WHERE player_id='{self.a}'",
            f"UPDATE users SET username='Trainer B',player_avatar_id='AvatarRickDefault',level=17,streak=4,xp=819,xp_lower=800,xp_upper=900,coins=83,coupons=11,permits=5 WHERE player_id='{self.b}'",
        ])
        self.assertIn('ok', self.p.freeze())

    def build(self, actor=None, battle=None):
        encoded = base64.b64encode(json.dumps([self.a if actor is None else actor, battle or self.battle]).encode()).decode()
        return json.loads(php(
            "require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "require '/var/www/html/lib/friend_battle_start_views.php';"
            "$a=json_decode(base64_decode('" + encoded + "'),true);"
            "try{echo json_encode(['ok'=>friend_battle_build_start_views($pdo,$a[0],$a[1])]);}"
            "catch(Throwable $e){echo json_encode(['status'=>$e instanceof FriendError?$e->status:500,"
            "'error'=>$e instanceof FriendError?$e->getMessage():'FAILED']);}"
        ))

    def rows(self):
        return sql(f"SELECT * FROM friend_battle_start_views WHERE battle_id='{self.battle}' ORDER BY player_id")

    def reject(self, status=409, actor=None, battle=None):
        rows, source = self.rows(), self.p.rows()
        gameplay, sessions, claims, invites = self.p.gameplay(), self.m.sessions(), self.m.claims(), self.f.rows()
        self.assertEqual(self.build(actor, battle).get('status'), status)
        self.assertEqual(self.rows(), rows)
        self.assertEqual(self.p.rows(), source)
        self.assertEqual(self.p.gameplay(), gameplay)
        self.assertEqual(self.m.sessions(), sessions)
        self.assertEqual(self.m.claims(), claims)
        self.assertEqual(self.f.rows(), invites)

    def rewrite(self, table, column, owner, value):
        encoded = json.dumps(value, separators=(',', ':'))
        digest = hashlib.sha256(encoded.encode()).hexdigest()
        sql(f"UPDATE {table} SET {column}_json={quoted(encoded)},{column}_sha256='{digest}' WHERE battle_id='{self.battle}' AND player_id='{owner}'")

    def test_two_perspectives_typed_private_projection_and_object_dictionaries(self):
        sql(f"INSERT INTO owned_items(player_id,item_id,quantity) VALUES('{self.a}','ItemAcetaldehyde',0)")
        before, sessions, invites, source = self.p.gameplay(), self.m.sessions(), self.f.rows(), self.p.rows()
        result = self.build()
        self.assertEqual(set(result), {'ok'}, result)
        self.assertEqual(set(result['ok']), {'sender', 'recipient'})
        for role, owner, opponent, ids, active, coins in (
            ('sender', self.a, self.b, self.ids[:2], self.ids[1], 29),
            ('recipient', self.b, self.a, self.ids[2:], self.ids[2], 83),
        ):
            view = result['ok'][role]
            self.assertEqual(set(view), {'battle_id', 'battle_type', 'player', 'opponent', 'meta'})
            self.assertEqual((view['battle_id'], view['battle_type'], view['meta']), (self.battle, 'PvF', {}))
            player, peer = view['player'], view['opponent']
            self.assertEqual((player['player_id'], player['type'], player['state']), (owner, 'PLAYER', 'BATTLE'))
            self.assertEqual((peer['player_id'], peer['type'], peer['state']), (opponent, 'USER', 'BATTLE'))
            self.assertEqual(player['coins'], coins)
            stock = [{'item_id': 'ItemSerum', 'quantity': 3}]
            if owner == self.a:
                stock.insert(0, {'item_id': 'ItemAcetaldehyde', 'quantity': 0})
            self.assertEqual(player['owned_items'], stock)
            self.assertEqual([m['owned_morty_id'] for m in player['owned_morties']], ids)
            self.assertEqual(player['active_owned_morty'], active)
            self.assertIs(type(peer['active_owned_morty']), str)
            self.assertEqual(player['move_log'], {'cooldown': {}, 'cooldown_next': {}, 'count': {}})
            for field in ('level', 'streak', 'xp', 'xp_lower', 'xp_upper', 'coins', 'coupons', 'permits'):
                self.assertIs(type(player[field]), int)
            for morty in player['owned_morties']:
                self.assertIs(type(morty['is_locked']), bool)
                self.assertIs(type(morty['is_trading_locked']), bool)
                for field in ('level', 'hp', 'hp_stat', 'attack_stat', 'defence_stat', 'speed_stat', 'xp'):
                    self.assertIs(type(morty[field]), int)
                self.assertEqual(morty['owned_attacks'], [{'attack_id': 'AttackLick', 'position': 0, 'pp': 0, 'pp_stat': 11}])
            for field in ('owned_items', 'coins', 'coupons', 'permits', 'xp', 'xp_lower', 'xp_upper', 'secret', 'session_id', 'password', 'tags', '_meta', 'id'):
                self.assertNotIn(field, peer)
            for morty in peer['owned_morties']:
                for field in ('xp', 'xp_lower', 'xp_upper', 'evolution_points', 'is_locked', 'is_trading_locked', 'player_id', 'id', 'tags'):
                    self.assertNotIn(field, morty)
            serialized = json.dumps(view)
            for field in ('secret', 'session_id', 'password', 'sender_token', 'recipient_token', 'active_deck_id'):
                self.assertNotIn('"' + field + '"', serialized)
        self.assertEqual(result['ok']['sender']['player']['owned_morties'][0]['variant'], 'Normal')
        self.assertEqual(self.p.gameplay(), before)
        captured_sessions = self.m.sessions()
        self.assertIsNone(sessions[0]['start_views_created_at'])
        self.assertTrue(captured_sessions[0]['start_views_created_at'])
        self.assertEqual(
            [{k: v for k, v in row.items() if k != 'start_views_created_at'} for row in captured_sessions],
            [{k: v for k, v in row.items() if k != 'start_views_created_at'} for row in sessions],
        )
        self.assertEqual(self.f.rows(), invites)
        self.assertEqual(self.p.rows(), source)
        for row in self.rows():
            for field in ('context', 'view'):
                self.assertEqual(hashlib.sha256(row[field + '_json'].encode()).hexdigest(), row[field + '_sha256'])
            self.assertEqual(json.loads(row['view_json']), result['ok']['sender' if row['player_id'] == self.a else 'recipient'])
            context = json.loads(row['context_json'])
            for field in ('secret', 'session_id', 'password', 'tags', 'id', 'sender_token', 'recipient_token'):
                self.assertNotIn('"' + field + '"', json.dumps(context))
        self.assertEqual(len(self.rows()), 2)

    def test_roles_replay_and_live_party_changes_do_not_resnapshot(self):
        original = self.build()
        self.assertIn('ok', original, original)
        rows = self.rows()
        self.f.execute([
            f"UPDATE owned_morties SET hp=1,level=99 WHERE owned_morty_id='{self.ids[1]}'",
            f"UPDATE owned_attacks SET pp=3 WHERE owned_morty_id='{self.ids[1]}'",
            f"UPDATE decks SET owned_morty_ids='[]' WHERE player_id='{self.a}'",
        ])
        self.assertEqual(self.build(self.a), original)
        self.assertEqual(self.build(self.b), original)
        self.assertEqual(self.rows(), rows)

    def test_current_profile_and_stock_drift_reject_without_resnapshot(self):
        self.assertIn('ok', self.build())
        for mutation, restore in (
            (f"UPDATE users SET username='Changed' WHERE player_id='{self.a}'", f"UPDATE users SET username='Trainer A' WHERE player_id='{self.a}'"),
            (f"UPDATE users SET coins=30 WHERE player_id='{self.a}'", f"UPDATE users SET coins=29 WHERE player_id='{self.a}'"),
            (f"UPDATE owned_items SET quantity=4 WHERE player_id='{self.b}'", f"UPDATE owned_items SET quantity=3 WHERE player_id='{self.b}'"),
        ):
            with self.subTest(mutation=mutation):
                sql(mutation)
                self.reject()
                sql(restore)

    def test_invalid_profile_numbers_and_avatar_fail_closed(self):
        for column, value, restore in (
            ('player_avatar_id', "'UnknownStartViewAvatar'", "'AvatarRickDefault'"),
            ('xp', '-1', '417'), ('xp_upper', '2147483648', '500'),
            ('coins', '-1', '29'), ('level', '0', '12'),
        ):
            with self.subTest(column=column, value=value):
                sql(f"UPDATE users SET {column}={value} WHERE player_id='{self.a}'")
                self.reject()
                self.assertEqual(self.rows(), [])
                sql(f"UPDATE users SET {column}={restore} WHERE player_id='{self.a}'")

    def test_invalid_stock_unknown_negative_and_duplicate_fail_closed(self):
        for mutation, restore in (
            (f"UPDATE owned_items SET quantity=-1 WHERE player_id='{self.b}'", f"UPDATE owned_items SET quantity=3 WHERE player_id='{self.b}'"),
            (f"UPDATE owned_items SET quantity=32768 WHERE player_id='{self.b}'", f"UPDATE owned_items SET quantity=3 WHERE player_id='{self.b}'"),
            (f"UPDATE owned_items SET item_id='UnknownStartViewItem' WHERE player_id='{self.b}'", f"UPDATE owned_items SET item_id='ItemSerum' WHERE player_id='{self.b}'"),
            (f"INSERT INTO owned_items(player_id,item_id,quantity) VALUES('{self.b}','ItemSerum',1)", f"DELETE FROM owned_items WHERE player_id='{self.b}' AND quantity=1"),
        ):
            with self.subTest(mutation=mutation):
                sql(mutation)
                self.reject()
                self.assertEqual(self.rows(), [])
                sql(restore)

    def test_legacy_null_xp_and_flags_are_projected_with_strict_types(self):
        sql(f"UPDATE users SET xp=NULL,xp_lower=NULL,xp_upper=NULL WHERE player_id='{self.a}'")
        source = json.loads(next(row['snapshot_json'] for row in self.p.rows() if row['player_id'] == self.a))
        for morty in source['owned_morties']:
            morty.update(xp=None, xp_lower=None, xp_upper=None, is_locked=None, is_trading_locked=None)
        self.rewrite('friend_battle_party_snapshots', 'snapshot', self.a, source)
        result = self.build()
        self.assertIn('ok', result, result)
        player = result['ok']['sender']['player']
        for field in ('xp', 'xp_lower', 'xp_upper'):
            self.assertEqual(player[field], 0)
        for morty in player['owned_morties']:
            self.assertEqual(morty['xp'], 0)
            self.assertIs(morty['is_locked'], False)
            self.assertIs(morty['is_trading_locked'], False)

    def test_malformed_source_flags_and_private_xp_reject(self):
        original = json.loads(next(row['snapshot_json'] for row in self.p.rows() if row['player_id'] == self.a))
        for field, value in (('is_locked', 'not-a-boolean'), ('is_trading_locked', 'maybe'), ('xp', -1),
                             ('missing_xp', None), ('unknown_attack', None)):
            with self.subTest(field=field):
                source = json.loads(json.dumps(original))
                if field == 'missing_xp':
                    del source['owned_morties'][0]['xp']
                elif field == 'unknown_attack':
                    source['owned_morties'][0]['owned_attacks'][0]['attack_id'] = 'UnknownStartViewAttack'
                else:
                    source['owned_morties'][0][field] = value
                self.rewrite('friend_battle_party_snapshots', 'snapshot', self.a, source)
                self.reject()
                self.assertEqual(self.rows(), [])

    def test_context_and_view_hash_or_valid_hash_bad_schema_fail_closed(self):
        self.assertIn('ok', self.build())
        original = next(row for row in self.rows() if row['player_id'] == self.a)
        for column in ('context', 'view'):
            with self.subTest(column=column):
                sql(f"UPDATE friend_battle_start_views SET {column}_sha256=REPEAT('0',64) WHERE battle_id='{self.battle}' AND player_id='{self.a}'")
                self.reject()
                sql(f"UPDATE friend_battle_start_views SET {column}_sha256='{original[column + '_sha256']}' WHERE battle_id='{self.battle}' AND player_id='{self.a}'")
                self.rewrite('friend_battle_start_views', column, self.a, {'schema_version': 1})
                self.reject()
                sql(f"UPDATE friend_battle_start_views SET {column}_json={quoted(original[column + '_json'])},{column}_sha256='{original[column + '_sha256']}' WHERE battle_id='{self.battle}' AND player_id='{self.a}'")
        view = json.loads(original['view_json'])
        view['opponent']['coins'] = 123
        self.rewrite('friend_battle_start_views', 'view', self.a, view)
        self.reject()

    def test_incomplete_extra_views_and_corrupt_source_are_not_repaired(self):
        self.assertIn('ok', self.build())
        sql(f"UPDATE friend_battle_party_snapshots SET snapshot_sha256=REPEAT('0',64) WHERE battle_id='{self.battle}' AND player_id='{self.a}'")
        self.reject()
        raw = next(row for row in self.p.rows() if row['player_id'] == self.a)
        sql(f"UPDATE friend_battle_party_snapshots SET snapshot_sha256='{hashlib.sha256(raw['snapshot_json'].encode()).hexdigest()}' WHERE battle_id='{self.battle}' AND player_id='{self.a}'")
        sql(f"INSERT INTO friend_battle_start_views SELECT battle_id,'{self.c}',context_json,context_sha256,view_json,view_sha256,created_at FROM friend_battle_start_views WHERE battle_id='{self.battle}' AND player_id='{self.a}'")
        self.reject()
        sql(f"DELETE FROM friend_battle_start_views WHERE battle_id='{self.battle}' AND player_id='{self.c}'")
        sql(f"DELETE FROM friend_battle_start_views WHERE battle_id='{self.battle}' AND player_id='{self.b}'")
        self.reject()
        self.assertEqual(len(self.rows()), 1)
        sql(f"DELETE FROM friend_battle_start_views WHERE battle_id='{self.battle}'")
        self.reject()
        self.assertEqual(self.rows(), [])

    def test_authentication_claims_invitation_and_lease_revalidate_on_replay(self):
        self.assertIn('ok', self.build())
        for actor, status in (('', 401), (str(uuid.uuid4()), 401), (self.c, 403)):
            self.reject(status, actor)
        for mutation, restore in (
            (f"UPDATE friend_battle_sessions SET prepare_deadline=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE battle_id='{self.battle}'", f"UPDATE friend_battle_sessions SET prepare_deadline=UTC_TIMESTAMP(6)+INTERVAL 120 SECOND WHERE battle_id='{self.battle}'"),
            (f"UPDATE friend_battle_sessions SET state='CANCELLED' WHERE battle_id='{self.battle}'", f"UPDATE friend_battle_sessions SET state='PREPARING' WHERE battle_id='{self.battle}'"),
            (f"UPDATE friend_battle_invites SET state='REVOKED' WHERE invite_id='{self.invite['invite_id']}'", f"UPDATE friend_battle_invites SET state='PENDING' WHERE invite_id='{self.invite['invite_id']}'"),
            (f"DELETE FROM friend_battle_memberships WHERE player_id='{self.a}'", f"INSERT INTO friend_battle_memberships(player_id,battle_id) VALUES('{self.a}','{self.battle}')"),
        ):
            with self.subTest(mutation=mutation):
                sql(mutation)
                self.reject()
                sql(restore)

    def test_second_insert_failure_rolls_back_both_views(self):
        sql(f"DELETE FROM friend_battle_party_snapshots WHERE battle_id='{self.battle}'")
        self.reject()
        self.assertEqual(self.p.rows(), [])
        self.assertEqual(self.rows(), [])
        self.assertIn('ok', self.p.freeze())
        trigger = 'start_view_fault_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON friend_battle_start_views FOR EACH ROW BEGIN IF NEW.battle_id='{self.battle}' AND EXISTS(SELECT 1 FROM friend_battle_start_views WHERE battle_id=NEW.battle_id) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID second start view failure'; END IF; END")
        self.reject(500)
        self.assertEqual(self.rows(), [])
        sql(f'DROP TRIGGER IF EXISTS {trigger}')
        self.assertIn('ok', self.build())

    def test_public_accept_stays_unavailable_without_native_start_or_events(self):
        self.assertIn('ok', self.build())
        before, rows, sessions = self.p.gameplay(), self.rows(), self.m.sessions()
        self.f.error(self.f.call('response', self.b, token=self.invite['recipient_token'], accept=True), 501, 'FAILED')
        self.assertEqual(self.p.gameplay(), before)
        self.assertEqual(self.rows(), rows)
        self.assertEqual(self.m.sessions(), sessions)
        self.assertEqual(sessions[0]['state'], 'PREPARING')


if __name__ == '__main__':
    unittest.main()

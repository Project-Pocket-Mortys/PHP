"""Internal immutable parties using additive UUID fixtures; never reseed accounts."""
import base64
import hashlib
import json
import unittest
import uuid

import test_friend_battle_membership as membership
from test_http import php, sql


def quoted(value):
    return "'" + str(value).replace('\\', '\\\\').replace("'", "\\'") + "'"


class FriendBattlePartySnapshotTests(unittest.TestCase):
    def setUp(self):
        self.m = membership.FriendBattleMembershipTests(methodName='runTest')
        self.addCleanup(self.m.doCleanups)
        self.m.setUp()
        self.f = self.m.f
        self.a, self.b, self.c, self.d = self.f.players
        self.ids = [str(uuid.uuid4()) for _ in range(3)]
        self.addCleanup(self.cleanup_parties)
        self.f.execute([
            f"DELETE FROM decks WHERE player_id IN ('{self.a}','{self.b}')",
            f"UPDATE users SET active_deck_id=0 WHERE player_id='{self.a}'",
            f"UPDATE users SET active_deck_id=1 WHERE player_id='{self.b}'",
        ])
        for index, morty in enumerate(self.ids):
            owner = self.a if index < 2 else self.b
            self.f.execute([
                "INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,level,xp,hp,hp_stat,attack_stat,defence_stat,speed_stat,variant,is_locked,is_trading_locked,evolution_points,xp_lower,xp_upper) "
                f"VALUES ('{morty}','{owner}','MortyDefault',12,417,{0 if index == 0 else 37},101,23,27,31,{('NULL' if index == 0 else quoted('Shiny'))},'false','false',2,400,500)",
                "INSERT INTO owned_attacks (owned_morty_id,attack_id,position,amount,pp,pp_stat,stat,type,to_self,is_accurate,accuracy,power) "
                f"VALUES ('{morty}','AttackLick',0,7,0,11,'Attack','Normal',0,1,1,19)",
            ])
        for owner, deck, ids in ((self.a, 0, self.ids[:2]), (self.b, 1, self.ids[2:])):
            sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{owner}',{deck},{quoted(json.dumps(ids))})")
        self.invite = self.m.pending()
        result = self.m.reserve(self.invite)
        self.assertIn('ok', result, result)
        self.battle = result['ok']
        sql(f"UPDATE friend_battle_sessions SET prepare_deadline=UTC_TIMESTAMP(6)+INTERVAL 120 SECOND WHERE battle_id='{self.battle}'")
        sql(f"UPDATE friend_battle_invites SET expires_at=UTC_TIMESTAMP(6)+INTERVAL 120 SECOND WHERE invite_id='{self.invite['invite_id']}'")

    def cleanup_parties(self):
        ids = ','.join(map(quoted, self.ids))
        self.f.execute([
            f"DELETE FROM friend_battle_party_snapshots WHERE player_id IN ('{self.f.ids}')",
            f"DELETE FROM owned_attacks WHERE owned_morty_id IN ({ids})",
            f"DELETE FROM owned_morties WHERE owned_morty_id IN ({ids})",
        ])

    def freeze(self, actor=None, battle=None):
        encoded = base64.b64encode(json.dumps([self.a if actor is None else actor, battle or self.battle]).encode()).decode()
        return json.loads(php(
            "require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "require '/var/www/html/lib/friend_battle_party_snapshots.php';"
            "$a=json_decode(base64_decode('" + encoded + "'),true);"
            "try{echo json_encode(['ok'=>friend_battle_snapshot_parties($pdo,$a[0],$a[1])]);}"
            "catch(Throwable $e){echo json_encode(['status'=>$e instanceof FriendError?$e->status:500,"
            "'error'=>$e instanceof FriendError?$e->getMessage():'FAILED']);}"
        ))

    def rows(self):
        return sql(f"SELECT * FROM friend_battle_party_snapshots WHERE battle_id='{self.battle}' ORDER BY player_id")

    def gameplay(self):
        result = self.f.snapshot()
        ids = ','.join(map(quoted, self.ids))
        result['party_attacks'] = sql(f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ({ids}) ORDER BY id")
        return result

    def reject(self, status=409, actor=None, battle=None):
        claims, sessions, rows = self.m.claims(), self.m.sessions(), self.rows()
        self.assertEqual(self.freeze(actor, battle).get('status'), status)
        self.assertEqual(self.rows(), rows)
        self.assertEqual(self.m.claims(), claims)
        self.assertEqual(self.m.sessions(), sessions)

    def test_freezes_exact_rows_order_deck_zero_first_living_and_preserves_gameplay(self):
        before, sessions, invites = self.gameplay(), self.m.sessions(), self.f.rows()
        result = self.freeze()
        self.assertEqual(set(result), {'ok'}, result)
        self.assertEqual(set(result['ok']), {'sender', 'recipient'})
        for role, owner, deck, ids, active in (
            ('sender', self.a, 0, self.ids[:2], self.ids[1]),
            ('recipient', self.b, 1, self.ids[2:], self.ids[2]),
        ):
            snapshot = result['ok'][role]
            expected = []
            for morty in ids:
                row = sql(f"SELECT * FROM owned_morties WHERE owned_morty_id='{morty}'")[0]
                row['owned_attacks'] = sql(f"SELECT * FROM owned_attacks WHERE owned_morty_id='{morty}' ORDER BY position,id")
                expected.append(row)
            self.assertEqual(snapshot, dict(schema_version=1, player_id=owner, deck_id=deck,
                                          active_owned_morty_id=active, owned_morties=expected))
        self.assertIsNone(result['ok']['sender']['owned_morties'][0]['variant'])
        for row in self.rows():
            self.assertEqual(hashlib.sha256(row['snapshot_json'].encode()).hexdigest(), row['snapshot_sha256'])
            stored = json.loads(row['snapshot_json'])
            self.assertEqual(stored, result['ok']['sender' if row['player_id'] == self.a else 'recipient'])
            self.assertNotIn('secret', stored)
            self.assertNotIn('session_id', stored)
            self.assertNotIn('owned_items', stored)
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual(self.gameplay(), before)
        self.assertEqual(self.m.sessions(), sessions)
        self.assertEqual(self.f.rows(), invites)
        self.m.assert_pair(self.battle)

    def test_both_roles_replay_stored_values_after_live_party_changes(self):
        original = self.freeze()
        self.assertIn('ok', original, original)
        rows, sessions = self.rows(), self.m.sessions()
        self.f.execute([
            f"UPDATE owned_morties SET hp=1,level=99,attack_stat=777 WHERE owned_morty_id='{self.ids[1]}'",
            f"UPDATE owned_attacks SET pp=3 WHERE owned_morty_id='{self.ids[1]}'",
            f"UPDATE decks SET owned_morty_ids='[]' WHERE player_id='{self.a}'",
        ])
        for actor in (self.a, self.b):
            self.assertEqual(self.freeze(actor), original)
        self.assertEqual(self.rows(), rows)
        self.assertEqual(self.m.sessions(), sessions)

    def test_authentication_and_roles_are_revalidated(self):
        for actor, status in (('', 401), (str(uuid.uuid4()), 401), (self.c, 403)):
            with self.subTest(actor=actor):
                self.reject(status, actor)
        sql(f"UPDATE users SET session_id='{self.a}' WHERE player_id='{self.c}'")
        self.reject(401)
        self.assertEqual(self.rows(), [])

    def test_deadline_invitation_friendship_and_claims_fail_closed(self):
        mutations = [
            (f"UPDATE friend_battle_sessions SET prepare_deadline=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE battle_id='{self.battle}'",
             f"UPDATE friend_battle_sessions SET prepare_deadline=UTC_TIMESTAMP(6)+INTERVAL 120 SECOND WHERE battle_id='{self.battle}'"),
            (f"UPDATE friend_battle_sessions SET state='CANCELLED' WHERE battle_id='{self.battle}'",
             f"UPDATE friend_battle_sessions SET state='PREPARING' WHERE battle_id='{self.battle}'"),
            (f"UPDATE friend_battle_invites SET state='REVOKED' WHERE invite_id='{self.invite['invite_id']}'",
             f"UPDATE friend_battle_invites SET state='PENDING' WHERE invite_id='{self.invite['invite_id']}'"),
            (f"UPDATE friend_battle_invites SET expires_at=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE invite_id='{self.invite['invite_id']}'",
             f"UPDATE friend_battle_invites SET expires_at=UTC_TIMESTAMP(6)+INTERVAL 120 SECOND WHERE invite_id='{self.invite['invite_id']}'"),
            (f"UPDATE friend_list SET pending='true' WHERE player_id_a='{self.a}' AND player_id_b='{self.b}'",
             f"UPDATE friend_list SET pending='false' WHERE player_id_a='{self.a}' AND player_id_b='{self.b}'"),
            (f"DELETE FROM friend_battle_memberships WHERE player_id='{self.a}'",
             f"INSERT INTO friend_battle_memberships(player_id,battle_id) VALUES('{self.a}','{self.battle}')"),
            (f"INSERT INTO friend_battle_memberships(player_id,battle_id) VALUES('{self.c}','{self.battle}')",
             f"DELETE FROM friend_battle_memberships WHERE player_id='{self.c}'"),
        ]
        for mutation, restore in mutations:
            with self.subTest(mutation=mutation):
                sql(mutation)
                self.reject()
                self.assertEqual(self.rows(), [])
                sql(restore)

    def test_legacy_escaped_json_deck_is_supported(self):
        encoded = json.dumps(self.ids[:2]).replace('"', '\\"')
        sql(f"UPDATE decks SET owned_morty_ids={quoted(encoded)} WHERE player_id='{self.a}'")
        result = self.freeze()
        self.assertIn('ok', result, result)
        self.assertEqual([m['owned_morty_id'] for m in result['ok']['sender']['owned_morties']], self.ids[:2])

    def test_invalid_party_lists_and_ambiguous_decks_reject_both_snapshots(self):
        original = json.dumps(self.ids[:2])
        for value in ('[]', json.dumps([self.ids[0], self.ids[0]]), json.dumps([self.ids[2]]),
                      json.dumps([None]), json.dumps([1]), ','.join(self.ids[:2]),
                      json.dumps([str(uuid.uuid4()) for _ in range(6)])):
            with self.subTest(value=value):
                sql(f"UPDATE decks SET owned_morty_ids={quoted(value)} WHERE player_id='{self.a}'")
                self.reject()
                self.assertEqual(self.rows(), [])
        sql(f"UPDATE decks SET owned_morty_ids={quoted(original)} WHERE player_id='{self.a}'")
        sql(f"UPDATE decks SET deck_id=8 WHERE player_id='{self.a}'")
        self.reject()
        sql(f"UPDATE decks SET deck_id=0 WHERE player_id='{self.a}'")
        sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{self.a}',0,{quoted(original)})")
        self.reject()

    def test_duplicate_global_owned_id_rejects_ownerless_attack_ambiguity(self):
        sql(f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id) VALUES ('{self.ids[1]}','{self.c}','MortyDefault')")
        self.reject()
        self.assertEqual(self.rows(), [])

    def test_invalid_species_variant_and_stats_reject_both_snapshots(self):
        morty = self.ids[2]
        for column, value, restore in (
            ('morty_id', "'UnknownSpeciesForSnapshot'", "'MortyDefault'"), ('variant', "'Unknown'", "'Shiny'"),
            ('level', '0', '12'), ('hp', '-1', '37'), ('hp', '102', '37'),
            ('hp_stat', '0', '101'), ('attack_stat', '-1', '23'), ('defence_stat', '-1', '27'),
            ('speed_stat', '-1', '31'), ('attack_stat', '0', '23'),
        ):
            with self.subTest(column=column, value=value):
                sql(f"UPDATE owned_morties SET {column}={value} WHERE owned_morty_id='{morty}'")
                self.reject()
                self.assertEqual(self.rows(), [])
                sql(f"UPDATE owned_morties SET {column}={restore} WHERE owned_morty_id='{morty}'")

    def test_all_fainted_party_rejects_without_healing(self):
        sql(f"UPDATE owned_morties SET hp=0 WHERE owned_morty_id='{self.ids[1]}'")
        before = self.gameplay()
        self.reject()
        self.assertEqual(self.rows(), [])
        self.assertEqual(self.gameplay(), before)

    def test_attack_slots_and_pp_are_validated_without_refilling(self):
        morty = self.ids[2]
        for column, value, restore in (('position', '-1', '0'), ('position', '4', '0'),
                                       ('attack_id', "''", "'AttackLick'"), ('pp', '-1', '0'),
                                       ('pp', '12', '0'), ('pp_stat', '0', '11')):
            with self.subTest(column=column, value=value):
                sql(f"UPDATE owned_attacks SET {column}={value} WHERE owned_morty_id='{morty}'")
                self.reject()
                self.assertEqual(self.rows(), [])
                sql(f"UPDATE owned_attacks SET {column}={restore} WHERE owned_morty_id='{morty}'")
        sql(f"UPDATE owned_attacks SET owned_morty_id='{self.c}' WHERE owned_morty_id='{morty}'")
        self.reject()
        sql(f"UPDATE owned_attacks SET owned_morty_id='{morty}' WHERE owned_morty_id='{self.c}'")
        sql(f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{morty}','AttackLick',0,1,11)")
        self.reject()

    def test_corrupt_hash_and_missing_snapshot_fail_without_repair(self):
        self.assertIn('ok', self.freeze())
        original = self.rows()
        sql(f"UPDATE friend_battle_party_snapshots SET snapshot_sha256=REPEAT('0',64) WHERE battle_id='{self.battle}' AND player_id='{self.a}'")
        self.reject()
        own = next(row for row in original if row['player_id'] == self.a)
        sql(f"UPDATE friend_battle_party_snapshots SET snapshot_sha256='{own['snapshot_sha256']}' WHERE battle_id='{self.battle}' AND player_id='{self.a}'")
        malformed = '{"schema_version":1}'
        digest = hashlib.sha256(malformed.encode()).hexdigest()
        sql(f"UPDATE friend_battle_party_snapshots SET snapshot_json={quoted(malformed)},snapshot_sha256='{digest}' WHERE battle_id='{self.battle}' AND player_id='{self.a}'")
        self.reject()
        sql(f"UPDATE friend_battle_party_snapshots SET snapshot_json={quoted(own['snapshot_json'])},snapshot_sha256='{own['snapshot_sha256']}' WHERE battle_id='{self.battle}' AND player_id='{self.a}'")
        sql(f"DELETE FROM friend_battle_party_snapshots WHERE battle_id='{self.battle}' AND player_id='{self.b}'")
        self.reject()
        self.assertEqual(len(self.rows()), 1)

    def test_second_snapshot_insert_fault_rolls_back_both_and_preserves_claims(self):
        trigger = 'party_snapshot_fault_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON friend_battle_party_snapshots FOR EACH ROW BEGIN IF NEW.battle_id='{self.battle}' AND EXISTS(SELECT 1 FROM friend_battle_party_snapshots WHERE battle_id=NEW.battle_id) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID second snapshot failure'; END IF; END")
        before = self.gameplay()
        try:
            self.reject(500)
            self.assertEqual(self.rows(), [])
            self.assertEqual(self.gameplay(), before)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')
        self.assertIn('ok', self.freeze())


if __name__ == '__main__':
    unittest.main()

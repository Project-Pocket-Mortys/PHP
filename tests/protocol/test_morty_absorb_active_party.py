"""Point-only absorption must preserve a living active party; UUID fixtures only."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import unittest
import uuid

import test_morty_release as release
from test_http import post, sql


class MortyAbsorbActivePartyTests(unittest.TestCase):
    def setUp(self):
        self.f = release.MortyReleaseTests()
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()

    def request(self, donors=None, recipient=None):
        return post('/session/owned_morties/absorb', {
            'session_id': self.f.player,
            'owned_morty_id': recipient or self.f.storage,
            'absorb_owned_morty_ids': donors if donors is not None else [self.f.target]})

    def party(self, ids):
        sql(f"UPDATE decks SET owned_morty_ids={release.literal(json.dumps(ids))} "
            f"WHERE player_id='{self.f.player}' AND deck_id=7")
        self.f.decks[0]['owned_morty_ids'] = ids

    def reject_unchanged(self, donors=None):
        before = self.f.snapshot()
        response = self.request(donors)
        # Check atomicity independently, including donor attacks and target points.
        with self.subTest(contract='HTTP status and error'):
            self.assertEqual(response, (409, {'error': {'code': 'FAILED'}}))
        with self.subTest(contract='all fixture state unchanged'):
            self.assertEqual(self.f.snapshot(), before)

    def assert_absorbed(self, donors, recipient=None, points=1):
        recipient = recipient or self.f.storage
        before = self.f.snapshot()
        self.assertEqual(self.request(donors, recipient), (200, {
            'removed': donors,
            'modified': {'owned_morty_id': recipient, 'evolution_points': points},
            'decks': self.f.released_decks(donors)}))
        next(row for row in before['owned_morties']
             if row['owned_morty_id'] == recipient)['evolution_points'] = points
        self.f.assert_release_snapshot(before, donors)

    def test_last_living_active_donor_rejects_entire_mixed_batch(self):
        sql(f"UPDATE owned_morties SET hp=0 WHERE player_id='{self.f.player}' "
            f"AND owned_morty_id='{self.f.alive}'")
        self.reject_unchanged([self.f.fainted, self.f.target])

    def test_consuming_entire_active_party_rejects_atomically(self):
        self.reject_unchanged([self.f.target, self.f.alive, self.f.fainted])

    def test_consuming_only_active_member_rejects_even_with_living_storage_target(self):
        self.party([self.f.target])
        self.reject_unchanged()

    def test_large_existing_point_counter_does_not_replace_consumed_party(self):
        # This endpoint still returns modified points, never a created evolution.
        # Its safety check must therefore be independent of any client threshold.
        self.party([self.f.target])
        sql(f"UPDATE owned_morties SET evolution_points=1000000 "
            f"WHERE player_id='{self.f.player}' AND owned_morty_id='{self.f.storage}'")
        self.reject_unchanged()

    def test_active_donor_allowed_when_owned_living_survivor_remains(self):
        self.assert_absorbed([self.f.target])

    def test_inactive_deck_donor_allowed_with_valid_active_party(self):
        self.assert_absorbed([self.f.storage], recipient=self.f.alive)

    def test_locked_living_active_recipient_is_valid_survivor(self):
        self.party([self.f.target, self.f.alive])
        sql(f"UPDATE owned_morties SET is_locked='1' WHERE player_id='{self.f.player}' "
            f"AND owned_morty_id='{self.f.alive}'")
        # Recipient IDs in the request are filtered rather than consumed.
        before = self.f.snapshot()
        response = self.request([self.f.alive, self.f.target, self.f.target], self.f.alive)
        self.assertEqual(response, (200, {
            'removed': [self.f.target],
            'modified': {'owned_morty_id': self.f.alive, 'evolution_points': 1},
            'decks': self.f.released_decks([self.f.target])}))
        next(row for row in before['owned_morties']
             if row['owned_morty_id'] == self.f.alive)['evolution_points'] = 1
        self.f.assert_release_snapshot(before, [self.f.target])

    def test_deck_zero_is_a_valid_active_deck(self):
        sql(f"UPDATE users SET active_deck_id=0 WHERE player_id='{self.f.player}'")
        sql(f"UPDATE decks SET deck_id=0 WHERE player_id='{self.f.player}' AND deck_id=7")
        self.f.decks[0]['deck_id'] = 0
        self.assert_absorbed([self.f.target])

    def test_missing_active_deck_rejects_destructive_request(self):
        sql(f"DELETE FROM decks WHERE player_id='{self.f.player}' AND deck_id=7")
        self.reject_unchanged()

    def test_null_active_identifier_cannot_select_deck_zero_by_coercion(self):
        sql(f"UPDATE users SET active_deck_id=NULL WHERE player_id='{self.f.player}'")
        sql(f"UPDATE decks SET deck_id=0 WHERE player_id='{self.f.player}' AND deck_id=7")
        self.reject_unchanged()

    def test_duplicate_active_deck_rows_are_ambiguous(self):
        sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES "
            f"('{self.f.player}',7,{release.literal(json.dumps([self.f.alive]))})")
        self.reject_unchanged()

    def test_null_deck_identifier_cannot_prove_active_deck_zero(self):
        sql(f"UPDATE users SET active_deck_id=0 WHERE player_id='{self.f.player}'")
        sql(f"UPDATE decks SET deck_id=NULL WHERE player_id='{self.f.player}' AND deck_id=7")
        self.reject_unchanged()

    def test_malformed_active_membership_rejects_atomically(self):
        for raw in ('{}', 'null', '[null]', '[1]', '["unterminated]'):
            with self.subTest(raw=raw):
                sql(f"UPDATE decks SET owned_morty_ids={release.literal(raw)} "
                    f"WHERE player_id='{self.f.player}' AND deck_id=7")
                self.reject_unchanged()

    def test_foreign_living_member_cannot_prove_surviving_party(self):
        self.party([self.f.target, self.f.foreign, self.f.fainted])
        self.reject_unchanged()

    def test_missing_member_cannot_prove_surviving_party(self):
        self.party([self.f.target, str(uuid.uuid4()), self.f.fainted])
        self.reject_unchanged()

    def test_globally_ambiguous_survivor_cannot_prove_living_party(self):
        self.party([self.f.target, self.f.alive, self.f.fainted])
        sql(f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,hp) VALUES "
            f"('{self.f.players[1]}','{self.f.alive}','MortyDefault',42)")
        self.reject_unchanged()

    def invalid_survivor_hp(self, hp):
        # The consumed donor starts alive; this tests loss of the last living
        # member rather than imposing a policy on an already fainted party.
        sql(f"UPDATE owned_morties SET hp={hp} WHERE player_id='{self.f.player}' "
            f"AND owned_morty_id='{self.f.alive}'")
        self.reject_unchanged()

    def test_null_survivor_hp_cannot_prove_living_party(self):
        self.invalid_survivor_hp('NULL')

    def test_negative_survivor_hp_cannot_prove_living_party(self):
        self.invalid_survivor_hp('-1')

    def test_fainted_survivor_cannot_prove_living_party(self):
        self.invalid_survivor_hp('0')

    def test_concurrent_individually_safe_donors_cannot_remove_last_living_party(self):
        before = self.f.snapshot()
        barrier = threading.Barrier(2)

        def absorb(donor):
            barrier.wait(timeout=5)
            return self.request([donor])

        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(absorb, [self.f.target, self.f.alive]))
        successes = [body for status, body in results if status == 200]
        failures = [(status, body) for status, body in results if status != 200]
        self.assertEqual(len(successes), 1, results)
        self.assertEqual(failures, [(409, {'error': {'code': 'FAILED'}})])
        donor = successes[0]['removed']
        self.assertIn(donor, [[self.f.target], [self.f.alive]])
        self.assertEqual(successes[0], {
            'removed': donor,
            'modified': {'owned_morty_id': self.f.storage, 'evolution_points': 1},
            'decks': self.f.released_decks(donor)})
        next(row for row in before['owned_morties']
             if row['owned_morty_id'] == self.f.storage)['evolution_points'] = 1
        self.f.assert_release_snapshot(before, donor)


if __name__ == '__main__':
    unittest.main()

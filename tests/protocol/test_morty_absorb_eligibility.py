"""Native absorption eligibility; mutations stay within cleaned UUID fixtures."""
import unittest

import test_morty_release as release
from test_http import post, sql


class MortyAbsorbEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.f = release.MortyReleaseTests()
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()
        # Preserve the established counter: one point per consumed donor.
        sql(f"UPDATE owned_morties SET evolution_points=7 "
            f"WHERE player_id='{self.f.player}' AND owned_morty_id='{self.f.alive}'")

    def configure(self, morty, variant='Normal', species='MortyDefault'):
        variant_sql = 'NULL' if variant is None else release.literal(variant)
        species_sql = 'NULL' if species is None else release.literal(species)
        sql(f"UPDATE owned_morties SET variant={variant_sql}, "
            f"morty_id={species_sql} WHERE player_id='{self.f.player}' "
            f"AND owned_morty_id='{morty}'")

    def request(self, donors):
        return post('/session/owned_morties/absorb', {
            'session_id': self.f.player, 'owned_morty_id': self.f.alive,
            'absorb_owned_morty_ids': donors})

    def assert_compatible(self, target_variant, donor_variants):
        self.configure(self.f.alive, target_variant)
        # Locking the recipient remains allowed for every native variant.
        sql(f"UPDATE owned_morties SET is_locked='1' "
            f"WHERE player_id='{self.f.player}' AND owned_morty_id='{self.f.alive}'")
        donors = [self.f.target, self.f.storage, self.f.fainted][:len(donor_variants)]
        for donor, variant in zip(donors, donor_variants):
            self.configure(donor, variant)
        before = self.f.snapshot()
        status, body = self.request(donors)
        self.assertEqual(status, 200, body)
        self.assertEqual(body, {
            'removed': donors,
            'modified': {'owned_morty_id': self.f.alive,
                         'evolution_points': 7 + len(donors)},
            'decks': self.f.released_decks(donors)})
        recipient = next(row for row in before['owned_morties']
                         if row['owned_morty_id'] == self.f.alive)
        recipient['evolution_points'] = 7 + len(donors)
        self.f.assert_release_snapshot(before, donors)

    def assert_incompatible_batch(self, target_variant='Normal',
                                  donor_variant='Normal', donor_species='MortyDefault',
                                  target_species='MortyDefault'):
        self.configure(self.f.alive, target_variant, target_species)
        self.configure(self.f.target, donor_variant, donor_species)
        self.configure(self.f.storage, 'Normal')
        before = self.f.snapshot()
        # A valid donor comes first, so rejection must cover the entire batch.
        response = self.request([self.f.storage, self.f.target])
        with self.subTest(contract='HTTP status and native error code'):
            self.assertEqual(response, (409, {'error': {'code': 'ABSORB_INVALID_MORTY'}}))
        with self.subTest(contract='no point, donor, attack, or deck changes'):
            self.assertEqual(self.f.snapshot(), before)

    def test_normal_target_accepts_all_native_donor_variants(self):
        self.assert_compatible('Normal', ['Normal', 'Shiny', 'Pulsing'])

    def test_shiny_target_accepts_normal_and_shiny(self):
        self.assert_compatible('Shiny', ['Normal', 'Shiny'])

    def test_pulsing_target_accepts_normal_and_pulsing(self):
        self.assert_compatible('Pulsing', ['Normal', 'Pulsing'])

    def test_legacy_null_variant_is_normal(self):
        self.assert_compatible(None, [None, 'Shiny', 'Pulsing'])

    def test_cross_species_donor_rejects_entire_batch(self):
        self.assert_incompatible_batch(donor_species='MortyCronenberg')

    def test_shiny_target_rejects_pulsing_donor_atomically(self):
        self.assert_incompatible_batch('Shiny', 'Pulsing')

    def test_pulsing_target_rejects_shiny_donor_atomically(self):
        self.assert_incompatible_batch('Pulsing', 'Shiny')

    def test_unknown_target_variant_rejects_entire_batch(self):
        self.assert_incompatible_batch(target_variant='UnknownVariant')

    def test_unknown_donor_variant_rejects_entire_batch(self):
        self.assert_incompatible_batch(donor_variant='UnknownVariant')

    def test_blank_target_species_rejects_entire_batch(self):
        self.assert_incompatible_batch(target_species='')

    def test_missing_donor_species_rejects_entire_batch(self):
        self.assert_incompatible_batch(donor_species=None)

    def test_species_identifiers_require_exact_case(self):
        self.assert_incompatible_batch(donor_species='mortydefault')

    def test_lowercase_variant_rejects_entire_batch(self):
        self.assert_incompatible_batch(target_variant='shiny')

    def test_empty_variant_rejects_entire_batch(self):
        self.assert_incompatible_batch(donor_variant='')


if __name__ == '__main__':
    unittest.main()

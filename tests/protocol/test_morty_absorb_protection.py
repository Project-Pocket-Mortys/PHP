"""Absorption protection regressions; all mutations use isolated UUID fixtures."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import unittest
import uuid

import test_morty_release as release
from test_http import php, post, sql


class MortyAbsorbProtectionTests(unittest.TestCase):
    def setUp(self):
        self.f = release.MortyReleaseTests()
        self.addCleanup(self.f.doCleanups)
        self.f.setUp()

    def request(self, **overrides):
        body = dict(session_id=self.f.player, owned_morty_id=self.f.alive,
                    absorb_owned_morty_ids=[self.f.target])
        body.update(overrides)
        return post('/session/owned_morties/absorb', body)

    def reject_unchanged(self, **overrides):
        before = self.f.snapshot()
        self.assertEqual(self.request(**overrides), (409, {'error': {'code': 'FAILED'}}))
        self.assertEqual(self.f.snapshot(), before)

    def test_protected_donor_rejects_entire_mixed_batch(self):
        for field, value in [('is_locked', '1'), ('is_trading_locked', 'true'),
                             ('fight_pit_id', str(uuid.uuid4()))]:
            with self.subTest(field=field):
                sql(f"UPDATE owned_morties SET {field}={release.literal(value)} WHERE owned_morty_id='{self.f.target}'")
                self.reject_unchanged(absorb_owned_morty_ids=[self.f.storage, self.f.target])
                sql(f"UPDATE owned_morties SET {field}=NULL WHERE owned_morty_id='{self.f.target}'")

    def test_duplicate_donors_grant_one_point_and_retry_is_read_only(self):
        status, body = self.request(absorb_owned_morty_ids=[self.f.target, self.f.target])
        self.assertEqual(status, 200, body)
        self.assertEqual(body['removed'], [self.f.target])
        self.assertEqual(body['modified'], {'owned_morty_id': self.f.alive, 'evolution_points': 1})
        before = self.f.snapshot()
        self.assertEqual(self.request(), (200, {'error': {'code': 'NO_VALID_MORTYS'}}))
        self.assertEqual(self.f.snapshot(), before)

    def test_ambiguous_donor_or_target_does_not_touch_foreign_rows_or_attacks(self):
        for morty in [self.f.target, self.f.alive]:
            with self.subTest(morty=morty):
                sql(f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id) VALUES ('{self.f.players[1]}','{morty}','MortyDefault')")
                self.reject_unchanged()
                sql(f"DELETE FROM owned_morties WHERE player_id='{self.f.players[1]}' AND owned_morty_id='{morty}'")

    def test_unlocked_donor_locked_recipient_and_foreign_missing_self_filtering(self):
        sql(f"UPDATE owned_morties SET is_locked='1' WHERE owned_morty_id='{self.f.alive}'")
        status, body = self.request(absorb_owned_morty_ids=[self.f.alive, self.f.foreign, str(uuid.uuid4()), self.f.target])
        self.assertEqual(status, 200, body)
        self.assertEqual(body['removed'], [self.f.target])
        self.assertEqual(body['modified']['evolution_points'], 1)
        self.assertEqual(body['decks'], self.f.released_decks([self.f.target]))
        after = self.f.snapshot()
        self.assertTrue(any(r['owned_morty_id'] == self.f.foreign for r in after['owned_morties']))
        self.assertTrue(any(r['owned_morty_id'] == self.f.foreign for r in after['owned_attacks']))

    def test_malformed_decks_and_flags_fail_atomically(self):
        for raw in ['{}', 'null', '[1]', '["unterminated]']:
            with self.subTest(raw=raw):
                sql(f"UPDATE decks SET owned_morty_ids={release.literal(raw)} WHERE player_id='{self.f.player}' AND deck_id=10")
                self.reject_unchanged()
        sql(f"UPDATE decks SET owned_morty_ids='[]' WHERE player_id='{self.f.player}' AND deck_id=10")
        sql(f"UPDATE owned_morties SET is_locked='unknown' WHERE owned_morty_id='{self.f.target}'")
        self.reject_unchanged()

    def test_trade_locked_recipient_and_invalid_points_fail_atomically(self):
        sql(f"UPDATE owned_morties SET is_trading_locked='true' WHERE owned_morty_id='{self.f.alive}'")
        self.reject_unchanged()
        sql(f"UPDATE owned_morties SET is_trading_locked='false', evolution_points=-1 WHERE owned_morty_id='{self.f.alive}'")
        self.reject_unchanged()

    def test_escaped_and_duplicate_logical_decks_use_individual_rows(self):
        escaped = json.dumps([self.f.target, self.f.storage]).replace('"', '\\"')
        sql(f"UPDATE decks SET owned_morty_ids={release.literal(escaped)} WHERE player_id='{self.f.player}' AND deck_id=8")
        sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{self.f.player}',8,{release.literal(json.dumps([self.f.target, self.f.fainted]))})")
        status, body = self.request()
        self.assertEqual(status, 200, body)
        rows = sql(f"SELECT owned_morty_ids FROM decks WHERE player_id='{self.f.player}' AND deck_id=8 ORDER BY id")
        self.assertEqual([json.loads(r['owned_morty_ids']) for r in rows], [[self.f.storage], [self.f.fainted]])

    def test_input_and_auth_errors_preserve_legacy_codes(self):
        for overrides, code in [({'session_id': []}, 'INVALID_REQUEST'),
                                ({'owned_morty_id': []}, 'INVALID_REQUEST'),
                                ({'absorb_owned_morty_ids': [None]}, 'INVALID_REQUEST'),
                                ({'absorb_owned_morty_ids': {'0': self.f.target}}, 'INVALID_REQUEST'),
                                ({'absorb_owned_morty_ids': []}, 'NO_VALID_MORTYS'),
                                ({'absorb_owned_morty_ids': None}, 'NO_VALID_MORTYS'),
                                ({'session_id': str(uuid.uuid4())}, 'NOT_AUTHENTICATED'),
                                ({'owned_morty_id': self.f.foreign}, 'NOT_FOUND')]:
            with self.subTest(overrides=overrides):
                before = self.f.snapshot()
                self.assertEqual(self.request(**overrides), (200, {'error': {'code': code}}))
                self.assertEqual(self.f.snapshot(), before)
        self.assertEqual(post('/session/owned_morties/absorb', {
            'session_id': self.f.player, 'owned_morty_id': self.f.alive}),
            (200, {'error': {'code': 'NO_VALID_MORTYS'}}))

    def test_active_battle_blocks_even_world_user(self):
        sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,player_active_morty,state) VALUES ('{uuid.uuid4()}','{self.f.player}','{self.f.players[1]}','{self.f.alive}','ACTIVE')")
        self.reject_unchanged()

    def test_concurrent_absorb_consumes_once(self):
        barrier = threading.Barrier(2)
        def action(_):
            barrier.wait(timeout=5)
            return self.request()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(action, range(2)))
        self.assertEqual(sum('removed' in body for _, body in results), 1, results)
        self.assertEqual(sql(f"SELECT evolution_points FROM owned_morties WHERE player_id='{self.f.player}' AND owned_morty_id='{self.f.alive}'")[0]['evolution_points'], 1)

    def test_lock_and_absorb_share_user_lock(self):
        barrier = threading.Barrier(2)
        def lock():
            barrier.wait(timeout=5)
            return post('/session/owned_morties/lock', dict(session_id=self.f.player, owned_morty_id=self.f.target, is_locked=True))
        def absorb():
            barrier.wait(timeout=5)
            return self.request()
        with ThreadPoolExecutor(max_workers=2) as pool:
            locked = pool.submit(lock)
            absorbed = pool.submit(absorb)
            l, a = locked.result(), absorbed.result()
        if l[0] == 200:
            self.assertEqual(a, (409, {'error': {'code': 'FAILED'}}))
            self.assertEqual(sql(f"SELECT is_locked FROM owned_morties WHERE owned_morty_id='{self.f.target}'")[0]['is_locked'], '1')
        else:
            self.assertEqual(l[0], 404, l)
            self.assertIn('removed', a[1])

    def test_late_persistence_failure_rolls_back_all_mutations(self):
        before = self.f.snapshot()
        # Inject failure only in this connection, after donor/attack/deck writes;
        # no global triggers or changes to other accounts are involved.
        code = r'''
require '/var/www/html/lib/morty_absorb.php';
class AbsorbFailPDO extends PDO {
    public function prepare(string $query, array $options = []): PDOStatement|false {
        if (str_starts_with($query, 'UPDATE owned_morties SET evolution_points'))
            throw new RuntimeException('injected persistence failure');
        return parent::prepare($query, $options);
    }
}
$db = new AbsorbFailPDO('mysql:host='.getenv('PM_DB_HOST').';dbname='.getenv('PM_DB_NAME'),
    getenv('PM_DB_USER'), getenv('PM_DB_PASS'),
    [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
$db->beginTransaction();
try {
    morty_absorb_apply($db, SESSION, TARGET, [DONOR]);
    throw new LogicException('failure was not injected');
} catch (RuntimeException $error) {
    $db->rollBack();
    echo $error->getMessage();
}
'''
        code = code.replace('SESSION', release.literal(self.f.player)).replace('TARGET', release.literal(self.f.alive)).replace('DONOR', release.literal(self.f.target))
        self.assertEqual(php(code), 'injected persistence failure')
        self.assertEqual(self.f.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

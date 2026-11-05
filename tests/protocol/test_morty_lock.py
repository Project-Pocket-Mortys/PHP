"""Missing collection lock operation; disposable fixtures, no account reseeding."""
import json
import unittest
import uuid
import urllib.request

from test_http import php, post, sql


class MortyLockTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.players = [str(uuid.uuid4()) for _ in range(2)]
        self.morties = [str(uuid.uuid4()) for _ in range(2)]
        self.addCleanup(self.cleanup)
        for player, morty in zip(self.players, self.morties):
            sql(f"INSERT INTO users (secret,player_id,session_id,username,active_deck_id,tags) "
                f"VALUES ('{player}','{player}','{player}','LockFixture',1,'[]')")
            sql(f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,is_locked,is_trading_locked,hp) "
                f"VALUES ('{player}','{morty}','MortyDefault','0','1',42)")
            sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) "
                f"VALUES ('{player}',1,'{json.dumps([morty])}')")

    def cleanup(self):
        for player in self.players:
            for table in ('decks', 'owned_morties', 'users'):
                sql(f"DELETE FROM {table} WHERE player_id='{player}'")

    def request(self, locked, **overrides):
        body = dict(session_id=self.players[0], owned_morty_id=self.morties[0], is_locked=locked)
        body.update(overrides)
        return post('/session/owned_morties/lock', body)

    def rows(self):
        return sql("SELECT * FROM owned_morties WHERE player_id IN ('" +
                   "','".join(self.players) + "') ORDER BY id")

    def test_lock_unlock_retries_and_details_persistence(self):
        before = self.rows()
        for locked in (True, True, False, False):
            status, body = self.request(locked)
            self.assertEqual(status, 200)
            self.assertEqual(body, {'active_deck_id': 1,
                                   'decks': [{'deck_id': 1, 'owned_morty_ids': [self.morties[0]]}]})
            expected = [dict(row) for row in before]
            expected[0]['is_locked'] = '1' if locked else '0'
            self.assertEqual(self.rows(), expected)
            status, details = post('/session/player-details', {'session_id': self.players[0]})
            self.assertEqual(status, 200)
            morty = next(m for m in details['owned_morties'] if m['owned_morty_id'] == self.morties[0])
            self.assertIs(morty['is_locked'], locked)

    def test_invalid_session_and_foreign_or_missing_morty_do_not_mutate(self):
        before = self.rows()
        for overrides in ({'session_id': str(uuid.uuid4())},
                          {'owned_morty_id': self.morties[1]},
                          {'owned_morty_id': str(uuid.uuid4())}):
            status, body = self.request(True, **overrides)
            self.assertIn(status, (400, 401, 404))
            self.assertIn('error', body)
            self.assertEqual(self.rows(), before)

    def test_malformed_lock_values_do_not_unlock(self):
        self.assertEqual(self.request(True)[0], 200)
        before = self.rows()
        for value in ('false', 'true', 0, 1, None, [], {}):
            self.assertEqual(self.request(value)[0], 400)
            self.assertEqual(self.rows(), before)
        status, _ = post('/session/owned_morties/lock', {
            'session_id': self.players[0], 'owned_morty_id': self.morties[0]})
        self.assertEqual(status, 400)
        self.assertEqual(self.rows(), before)

    def test_client_path_without_slash_preserves_post(self):
        body = dict(session_id=self.players[0], owned_morty_id=self.morties[0], is_locked=True)
        req = urllib.request.Request('http://127.0.0.1:8087/session/owned_morties/lock',
                                     json.dumps(body).encode(), {'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(json.load(response)['active_deck_id'], 1)
        self.assertEqual(self.rows()[0]['is_locked'], '1')

    def test_response_preserves_empty_and_legacy_escaped_decks(self):
        player = self.players[0]
        sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{player}',2,'[]')")
        status, body = self.request(True)
        self.assertEqual(status, 200)
        self.assertEqual(body['decks'], [
            {'deck_id': 1, 'owned_morty_ids': [self.morties[0]]},
            {'deck_id': 2, 'owned_morty_ids': []}])
        # Older rows contain backslash-escaped JSON. Match player-details support.
        raw = json.dumps([self.morties[0]]).replace('"', '\\"')
        literal = "'" + raw.replace('\\', '\\\\').replace("'", "\\'") + "'"
        sql(f"UPDATE decks SET owned_morty_ids={literal} WHERE player_id='{player}' AND deck_id=1")
        self.assertEqual(self.request(False)[1], body)


if __name__ == '__main__':
    unittest.main()

"""Collection release contracts; UUID fixtures only, never reseed emulator accounts."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import unittest
import uuid

from test_http import php, post, sql


def literal(value):
    return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"


class MortyReleaseTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.players = [str(uuid.uuid4()) for _ in range(2)]
        self.morties = [str(uuid.uuid4()) for _ in range(5)]
        self.player = self.players[0]
        self.target, self.alive, self.fainted, self.storage, self.foreign = self.morties
        self.addCleanup(self.cleanup)
        for player in self.players:
            sql(f"INSERT INTO users (secret,player_id,session_id,username,state,active_deck_id,tags) "
                f"VALUES ('{player}','{player}','{player}','ReleaseFixture','WORLD',7,'[]')")
            sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{player}','ItemSerum',3)")
        for morty in self.morties:
            player = self.players[1] if morty == self.foreign else self.player
            hp = 0 if morty == self.fainted else 42
            sql(f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,hp,is_locked,is_trading_locked) "
                f"VALUES ('{player}','{morty}','MortyDefault',{hp},'false','false')")
            sql(f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) "
                f"VALUES ('{morty}','AttackLick',0,3,18)")
        self.decks = [
            {'deck_id': 7, 'owned_morty_ids': [self.target, self.alive, self.fainted]},
            {'deck_id': 8, 'owned_morty_ids': [self.storage, self.target, self.alive]},
            {'deck_id': 9, 'owned_morty_ids': [self.target]},
            {'deck_id': 10, 'owned_morty_ids': []}]
        for deck in self.decks:
            sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES "
                f"('{self.player}',{deck['deck_id']},{literal(json.dumps(deck['owned_morty_ids']))})")
        sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES "
            f"('{self.players[1]}',7,{literal(json.dumps([self.foreign]))})")

    def cleanup(self):
        for morty in self.morties:
            sql(f"DELETE FROM owned_attacks WHERE owned_morty_id='{morty}'")
        for player in self.players:
            for table in ('event_queue', 'battles', 'trade_offers', 'trades', 'decks',
                          'owned_items', 'owned_morties', 'users'):
                sql(f"DELETE FROM {table} WHERE player_id='{player}'")

    def request(self, preview=False, **overrides):
        body = dict(session_id=self.player, owned_morty_ids=[self.target])
        body.update(overrides)
        endpoint = 'attempt-release-multiple' if preview else 'release-multiple'
        return post('/session/owned_morties/' + endpoint, body)

    def snapshot(self):
        players = "','".join(self.players)
        morties = "','".join(self.morties)
        queries = {table: f"SELECT * FROM {table} WHERE player_id IN ('{players}') ORDER BY id"
                   for table in ('users', 'owned_morties', 'owned_items', 'decks', 'trades', 'trade_offers', 'event_queue')}
        queries['owned_attacks'] = f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{morties}') ORDER BY id"
        queries['battles'] = f"SELECT * FROM battles WHERE player_id IN ('{players}') ORDER BY battle_id"
        # One connection and one transaction give a consistent fixture snapshot.
        return json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                              "$queries=json_decode(" + literal(json.dumps(queries)) + ",true); "
                              "$pdo->beginTransaction(); $result=[]; "
                              "foreach($queries as $name=>$query) $result[$name]=$pdo->query($query)->fetchAll(); "
                              "$pdo->rollBack(); echo json_encode($result);"))

    def assert_success(self, response, decks):
        status, body = response
        self.assertEqual(status, 200, body)
        self.assertEqual(body, {'active_deck_id': 7, 'decks': decks})
        self.assertIs(type(body['active_deck_id']), int)

    def assert_failed(self, response):
        status, body = response
        self.assertGreaterEqual(status, 400, body)
        self.assertLess(status, 500, body)
        self.assertIn(body['error']['code'], ('FAILED', 'OWNED_MORTY_ID_INVALID'))

    def assert_rejected_without_changes(self, **overrides):
        for preview in (True, False):
            before = self.snapshot()
            self.assert_failed(self.request(preview=preview, **overrides))
            self.assertEqual(self.snapshot(), before)

    def expected_release(self, before, targets):
        before['owned_morties'] = [r for r in before['owned_morties'] if r['owned_morty_id'] not in targets]
        before['owned_attacks'] = [r for r in before['owned_attacks'] if r['owned_morty_id'] not in targets]
        for row in before['decks']:
            if row['player_id'] == self.player:
                row['owned_morty_ids'] = json.dumps(
                    [m for m in json.loads(row['owned_morty_ids']) if m not in targets], separators=(',', ':'))
        return before

    def assert_release_snapshot(self, before, targets):
        expected = self.expected_release(before, targets)
        after = self.snapshot()
        # Compare JSON meaning; database whitespace is not part of the contract.
        for snap in (expected, after):
            for deck in snap['decks']:
                deck['owned_morty_ids'] = json.loads(deck['owned_morty_ids'])
        self.assertEqual(after, expected)

    def released_decks(self, targets):
        return [dict(deck_id=d['deck_id'], owned_morty_ids=[m for m in d['owned_morty_ids'] if m not in targets])
                for d in self.decks]

    def test_preview_read_only_and_direct_confirm_prunes_all_decks(self):
        before = self.snapshot()
        self.assert_success(self.request(preview=True), self.decks)
        self.assertEqual(self.snapshot(), before)
        self.assert_success(self.request(), self.released_decks([self.target]))
        self.assert_release_snapshot(before, [self.target])
        after = self.snapshot()
        status, body = self.request()
        self.assertEqual(status, 404, body)
        self.assert_failed((status, body))
        self.assertEqual(self.snapshot(), after)

    def test_direct_batch_confirm_releases_active_and_storage_members(self):
        targets = [self.storage, self.target]
        before = self.snapshot()
        self.assert_success(self.request(owned_morty_ids=targets), self.released_decks(targets))
        self.assert_release_snapshot(before, targets)

    def test_invalid_or_partly_invalid_batches_are_atomic(self):
        for ids in ([], None, '', self.target, {}, {'0': self.target}, [1], [None], [[]], [''],
                    [self.target, self.target], [self.foreign], [str(uuid.uuid4())],
                    [self.target, self.foreign], [self.target, str(uuid.uuid4())]):
            with self.subTest(ids=ids):
                self.assert_rejected_without_changes(owned_morty_ids=ids)

    def test_locked_trading_locked_and_fight_pit_targets_are_rejected(self):
        for field, value in (('is_locked', '1'), ('is_trading_locked', 'true'), ('fight_pit_id', str(uuid.uuid4()))):
            with self.subTest(field=field):
                sql(f"UPDATE owned_morties SET {field}={literal(value)} WHERE owned_morty_id='{self.target}'")
                self.assert_rejected_without_changes()
                sql(f"UPDATE owned_morties SET {field}=NULL WHERE owned_morty_id='{self.target}'")

    def test_preserves_last_active_party_member_and_last_alive_member(self):
        self.assert_rejected_without_changes(owned_morty_ids=[self.target, self.alive])
        self.assert_rejected_without_changes(owned_morty_ids=[self.target, self.alive, self.fainted])
        sql(f"UPDATE decks SET owned_morty_ids={literal(json.dumps([self.target]))} "
            f"WHERE player_id='{self.player}' AND deck_id=7")
        self.assert_rejected_without_changes()

    def test_requires_world_and_rechecks_after_preview(self):
        self.assert_success(self.request(preview=True), self.decks)
        sql(f"UPDATE owned_morties SET is_locked='1' WHERE owned_morty_id='{self.target}'")
        self.assert_rejected_without_changes()
        sql(f"UPDATE owned_morties SET is_locked='false' WHERE owned_morty_id='{self.target}'")
        sql(f"UPDATE users SET state='BATTLE' WHERE player_id='{self.player}'")
        self.assert_rejected_without_changes()

    def test_pending_trade_or_offer_reference_blocks_unlocked_target(self):
        trade = str(uuid.uuid4())
        sql(f"INSERT INTO trades (trade_id,player_id,morty_trade_id) "
            f"VALUES ('{trade}','{self.player}','{self.target}')")
        self.assert_rejected_without_changes()
        sql(f"DELETE FROM trades WHERE player_id='{self.player}'")
        sql(f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) "
            f"VALUES ('{uuid.uuid4()}','{trade}','{self.player}','{self.target}')")
        self.assert_rejected_without_changes()

    def test_active_battle_reference_blocks_target_even_if_user_is_world(self):
        sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,player_active_morty,state) "
            f"VALUES ('{uuid.uuid4()}','{self.player}','{self.players[1]}','{self.target}','ACTIVE')")
        self.assert_rejected_without_changes()

    def test_preview_then_reassignment_makes_confirm_fail_atomically(self):
        self.assert_success(self.request(preview=True), self.decks)
        sql(f"UPDATE owned_morties SET player_id='{self.players[1]}' WHERE owned_morty_id='{self.target}'")
        self.assert_rejected_without_changes()

    def test_globally_ambiguous_owned_id_cannot_delete_shared_attacks(self):
        sql(f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,hp,is_locked,is_trading_locked) "
            f"VALUES ('{self.players[1]}','{self.target}','MortyDefault',42,'false','false')")
        self.assert_rejected_without_changes()

    def test_malformed_inactive_deck_aborts_instead_of_partially_pruning(self):
        for raw in ('not json', '{}', '[1]', '[null]', '[[]]'):
            with self.subTest(deck=raw):
                sql(f"UPDATE decks SET owned_morty_ids={literal(raw)} "
                    f"WHERE player_id='{self.player}' AND deck_id=8")
                self.assert_rejected_without_changes()

    def test_standard_escaped_json_deck_support(self):
        raw = json.dumps(self.decks[1]['owned_morty_ids']).replace('"', '\\"')
        sql(f"UPDATE decks SET owned_morty_ids={literal(raw)} "
            f"WHERE player_id='{self.player}' AND deck_id=8")
        before = self.snapshot()
        self.assert_success(self.request(preview=True), self.decks)
        self.assertEqual(self.snapshot(), before)
        # Normalize legacy representation only in the expected snapshot.
        next(d for d in before['decks'] if d['player_id'] == self.player and d['deck_id'] == 8)[
            'owned_morty_ids'] = json.dumps(self.decks[1]['owned_morty_ids'])
        self.assert_success(self.request(), self.released_decks([self.target]))
        self.assert_release_snapshot(before, [self.target])

    def test_missing_and_malformed_session_or_missing_batch_is_rejected(self):
        for session in (str(uuid.uuid4()), None, [], {}):
            with self.subTest(session=session):
                self.assert_rejected_without_changes(session_id=session)
        for endpoint in ('attempt-release-multiple', 'release-multiple'):
            before = self.snapshot()
            self.assert_failed(post('/session/owned_morties/' + endpoint, {'session_id': self.player}))
            self.assertEqual(self.snapshot(), before)

    def test_no_active_deck_cannot_release_last_total_owned_morty(self):
        sql(f"DELETE FROM decks WHERE player_id='{self.player}'")
        for morty in (self.alive, self.fainted, self.storage):
            sql(f"DELETE FROM owned_attacks WHERE owned_morty_id='{morty}'")
            sql(f"DELETE FROM owned_morties WHERE player_id='{self.player}' AND owned_morty_id='{morty}'")
        self.assert_rejected_without_changes()

    def test_concurrent_confirm_deletes_only_once(self):
        before = self.snapshot()
        barrier = threading.Barrier(2)
        def release():
            barrier.wait(timeout=5)
            return self.request()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: release(), range(2)))
        self.assertEqual(sum(status == 200 for status, _ in responses), 1, responses)
        for response in responses:
            if response[0] == 200:
                self.assert_success(response, self.released_decks([self.target]))
            else:
                self.assert_failed(response)
        self.assert_release_snapshot(before, [self.target])


if __name__ == '__main__':
    unittest.main()

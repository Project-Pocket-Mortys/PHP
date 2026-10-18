"""Out-of-battle item use with disposable fixtures; never reseed accounts."""
from concurrent.futures import ThreadPoolExecutor
import threading
import unittest
import uuid

from test_http import php, post, sql


class UseItemTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.players = [str(uuid.uuid4()) for _ in range(2)]
        self.morties = [str(uuid.uuid4()) for _ in range(3)]
        self.addCleanup(self.cleanup)
        for player in self.players:
            sql(f"INSERT INTO users (secret,player_id,session_id,username,state,tags) "
                f"VALUES ('{player}','{player}','{player}','UseItemFixture','WORLD','[]')")
            sql(f"INSERT INTO owned_items (player_id,item_id,quantity) "
                f"VALUES ('{player}','ItemSerum',2),('{player}','ItemMortyChip',3)")
        for morty, player in zip(self.morties, [self.players[0], self.players[1], self.players[0]]):
            sql(f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,level,xp,hp,hp_stat,"
                f"attack_stat,defence_stat,speed_stat,variant,is_locked,is_trading_locked,evolution_points,xp_lower,xp_upper) "
                f"VALUES ('{player}','{morty}','MortyDefault',5,125,35,100,12,13,14,'Normal','0','1',0,100,200)")
            sql(f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) "
                f"VALUES ('{morty}','AttackLick',0,3,10),('{morty}','AttackFlail',1,0,10)")

    def cleanup(self):
        for morty in self.morties:
            sql(f"DELETE FROM owned_attacks WHERE owned_morty_id='{morty}'")
        for player in self.players:
            for table in ('battles', 'owned_items', 'owned_morties', 'users'):
                sql(f"DELETE FROM {table} WHERE player_id='{player}'")

    def request(self, **overrides):
        data = dict(session_id=self.players[0], owned_morty_id=self.morties[0], item_id='ItemSerum')
        data.update(overrides)
        return post('/session/use-item', data)

    def snapshot(self):
        players = "','".join(self.players)
        morties = "','".join(self.morties)
        return {
            'morties': sql(f"SELECT * FROM owned_morties WHERE player_id IN ('{players}') ORDER BY id"),
            'items': sql(f"SELECT * FROM owned_items WHERE player_id IN ('{players}') ORDER BY id"),
            'attacks': sql(f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{morties}') ORDER BY id"),
        }

    def assert_failed(self, response):
        status, body = response
        self.assertGreaterEqual(status, 400)
        self.assertLess(status, 500)
        self.assertEqual(body['error']['code'], 'FAILED')

    def assert_result(self, response, hp, quantity, effect):
        status, body = response
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {'owned_morty_id', 'item_id', 'is_success', 'effect_value',
                                     'owned_morties', 'owned_items', 'attacks_to_learn'})
        self.assertEqual(body['owned_morty_id'], self.morties[0])
        self.assertEqual(body['item_id'], 'ItemSerum')
        self.assertIs(body['is_success'], True)
        self.assertEqual(body['effect_value'], effect)
        self.assertIsInstance(body['effect_value'], int)
        self.assertEqual(body['attacks_to_learn'], [])
        self.assertEqual(body['owned_items'], [{'item_id': 'ItemSerum', 'quantity': quantity}])
        self.assertIsInstance(body['owned_items'][0]['quantity'], int)
        self.assertEqual(len(body['owned_morties']), 1)
        _, details = post('/session/player-details', {'session_id': self.players[0]})
        morty = next(m for m in details['owned_morties'] if m['owned_morty_id'] == self.morties[0])
        self.assertEqual(body['owned_morties'], [morty])
        self.assertEqual(morty['hp'], hp)

    def test_heal_consumes_one_and_returns_full_changed_morty(self):
        before = self.snapshot()
        self.assert_result(self.request(), 55, 1, 20)
        after = self.snapshot()
        before['morties'][0]['hp'] = 55
        before['items'][0]['quantity'] = 1
        self.assertEqual(after, before)

    def test_capped_heal_retains_zero_inventory_row_and_retry_is_not_charged(self):
        sql(f"UPDATE owned_morties SET hp=95 WHERE owned_morty_id='{self.morties[0]}'")
        # Leave one extra item so retries test no-effect behavior separately from insufficient stock.
        self.assert_result(self.request(), 100, 1, 5)
        before = self.snapshot()
        self.assert_failed(self.request())
        self.assert_failed(self.request())
        self.assertEqual(self.snapshot(), before)
        sql(f"UPDATE owned_morties SET hp=80 WHERE owned_morty_id='{self.morties[0]}'")
        self.assert_result(self.request(), 100, 0, 20)
        self.assertEqual(sql(f"SELECT quantity FROM owned_items WHERE player_id='{self.players[0]}' "
                             "AND item_id='ItemSerum'"), [{'quantity': 0}])

    def test_fainted_target_is_not_revived_or_charged(self):
        sql(f"UPDATE owned_morties SET hp=0 WHERE owned_morty_id='{self.morties[0]}'")
        before = self.snapshot()
        self.assert_failed(self.request())
        self.assertEqual(self.snapshot(), before)

    def test_supported_healers_use_client_values_and_cap_at_maximum(self):
        healers = [('ItemSerum', 20), ('ItemGreatSerum', 50), ('ItemSensationalSerum', 200),
                   ('ItemPureSerum', None), ('ItemEasterEgg', 30), ('ItemPumpkin', 30),
                   ('ItemSpicyBBQPizza', 200), ('ItemBreakfastMedley', 200)]
        for item, healing in healers:
            with self.subTest(item=item):
                if item != 'ItemSerum':
                    sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.players[0]}','{item}',2)")
                for hp in (100, 495):
                    sql(f"UPDATE owned_morties SET hp={hp}, hp_stat=500 WHERE owned_morty_id='{self.morties[0]}'")
                    before = self.snapshot()
                    status, body = self.request(item_id=item)
                    self.assertEqual(status, 200)
                    effect = 500 - hp if healing is None else min(healing, 500 - hp)
                    self.assertIs(body['is_success'], True)
                    self.assertEqual(body['item_id'], item)
                    self.assertEqual(body['effect_value'], effect)
                    self.assertEqual(body['owned_morties'][0]['hp'], hp + effect)
                    after = self.snapshot()
                    before['morties'][0]['hp'] = hp + effect
                    item_row = next(row for row in before['items']
                                    if row['player_id'] == self.players[0] and row['item_id'] == item)
                    item_row['quantity'] -= 1
                    self.assertEqual(body['owned_items'], [{'item_id': item, 'quantity': item_row['quantity']}])
                    self.assertEqual(after, before)

    def test_invalid_session_foreign_and_missing_morties_do_not_mutate(self):
        before = self.snapshot()
        for override in ({'session_id': str(uuid.uuid4())},
                         {'owned_morty_id': self.morties[1]},
                         {'owned_morty_id': str(uuid.uuid4())}):
            with self.subTest(override=override):
                self.assert_failed(self.request(**override))
                self.assertEqual(self.snapshot(), before)

    def test_invalid_fields_do_not_mutate(self):
        before = self.snapshot()
        valid = dict(session_id=self.players[0], owned_morty_id=self.morties[0], item_id='ItemSerum')
        for key in valid:
            for value in (None, '', [], {}, True, 1):
                with self.subTest(key=key, value=value):
                    self.assert_failed(self.request(**{key: value}))
            missing = dict(valid)
            del missing[key]
            self.assert_failed(post('/session/use-item', missing))
        self.assertEqual(self.snapshot(), before)

    def test_unavailable_unknown_and_unsupported_items_do_not_mutate(self):
        before = self.snapshot()
        for item in ('ItemUnknown', 'ItemMortyChip'):
            self.assert_failed(self.request(item_id=item))
            self.assertEqual(self.snapshot(), before)
        sql(f"UPDATE owned_items SET quantity=0 WHERE player_id='{self.players[0]}' AND item_id='ItemSerum'")
        before = self.snapshot()
        self.assert_failed(self.request())
        self.assertEqual(self.snapshot(), before)
        sql(f"DELETE FROM owned_items WHERE player_id='{self.players[0]}' AND item_id='ItemSerum'")
        before = self.snapshot()
        self.assert_failed(self.request())
        self.assertEqual(self.snapshot(), before)

    def test_non_world_state_rejected(self):
        sql(f"UPDATE users SET state='BATTLE' WHERE player_id='{self.players[0]}'")
        before = self.snapshot()
        self.assert_failed(self.request())
        self.assertEqual(self.snapshot(), before)

    def test_active_battle_rejected_even_with_world_state(self):
        sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,player_active_morty,state) "
            f"VALUES ('{uuid.uuid4()}','{self.players[0]}','{self.players[1]}','{self.morties[0]}','ACTIVE')")
        before = self.snapshot()
        self.assert_failed(self.request())
        self.assertEqual(self.snapshot(), before)

    def test_concurrent_requests_cannot_spend_last_item_twice(self):
        sql(f"UPDATE owned_items SET quantity=1 WHERE player_id='{self.players[0]}' AND item_id='ItemSerum'")
        before = self.snapshot()
        barrier = threading.Barrier(2)

        def use():
            barrier.wait(timeout=5)
            return self.request()

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: use(), range(2)))
        successes = [body for status, body in responses if status == 200 and body.get('is_success') is True]
        self.assertEqual(len(successes), 1)
        self.assertEqual(successes[0]['effect_value'], 20)
        self.assertEqual(successes[0]['owned_items'], [{'item_id': 'ItemSerum', 'quantity': 0}])
        for response in responses:
            if response[0] != 200:
                self.assert_failed(response)
            else:
                self.assertIs(response[1]['is_success'], True)
        before['morties'][0]['hp'] = 55
        before['items'][0]['quantity'] = 0
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

"""Additive crafting contracts; only UUID-owned fixtures are changed or removed."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import unittest
import urllib.request
import uuid

from test_http import php, post, sql


class CraftingTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.player, self.other, self.session, self.other_session = [str(uuid.uuid4()) for _ in range(4)]
        self.scope = f"player_id IN ('{self.player}','{self.other}')"
        self.addCleanup(self.cleanup)
        sql("INSERT INTO users (secret, player_id, session_id, username, state, tags, coins, coupons, permits) VALUES "
            f"('{self.session}','{self.player}','{self.session}','CraftTest','WORLD','[]',1234,12,3),"
            f"('{self.other_session}','{self.other}','{self.other_session}','CraftOther','WORLD','[]',987,8,2)")
        sql("INSERT INTO owned_items (player_id,item_id,quantity) VALUES "
            f"('{self.player}','ItemBattery',2),('{self.player}','ItemFleeb',2),"
            f"('{self.player}','ItemTinCan',7),('{self.other}','ItemBattery',8),"
            f"('{self.other}','ItemFleeb',8),('{self.other}','ItemSerum',4)")

    def cleanup(self):
        for table in ('owned_items', 'event_queue', 'users'):
            sql(f"DELETE FROM {table} WHERE {self.scope}")

    def snapshot(self):
        # One database/container round trip for complete inventory and account rows.
        return json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
                              "echo json_encode(["
                              f"'items'=>$pdo->query(\"SELECT * FROM owned_items WHERE {self.scope} ORDER BY id\")->fetchAll(),"
                              f"'users'=>$pdo->query(\"SELECT * FROM users WHERE {self.scope} ORDER BY id\")->fetchAll()]);"))

    def stock(self, item, quantity):
        sql(f"UPDATE owned_items SET quantity={quantity} WHERE player_id='{self.player}' AND item_id='{item}'")

    def craft(self, **overrides):
        return post('/session/recipe/use', {'session_id': self.session, 'recipe_id': 'RecipeSerum', **overrides})

    def inventory(self):
        rows = self.snapshot()['items']
        own = [r for r in rows if r['player_id'] == self.player]
        self.assertEqual(len(own), len({r['item_id'] for r in own}))
        return {r['item_id']: int(r['quantity']) for r in own}

    def assert_failure(self, response, code=None):
        status, body = response
        self.assertGreaterEqual(status, 400)
        self.assertLess(status, 500 if code != 'FAILED' else 600)
        self.assertIsInstance(body['error']['code'], str)
        if code:
            self.assertEqual(body['error']['code'], code)

    def assert_success(self, response, battery, fleeb, serum=1):
        status, body = response
        self.assertEqual(status, 200)
        self.assertNotIn('error', body)
        self.assertEqual(body['result'], {'type': 3, 'item_id': 'ItemSerum', 'quantity': serum,
                                          'amount': 1, 'amount_received': 1})
        self.assertEqual({item['item_id']: item['quantity'] for item in body['owned_items']},
                         {'ItemBattery': battery, 'ItemFleeb': fleeb, 'ItemSerum': serum})
        self.assertEqual(len(body['owned_items']), 3)

    def test_craft_inserts_reward_and_preserves_other_stock_accounts_and_currency(self):
        before = self.snapshot()
        self.assert_success(self.craft(), 1, 1)
        after = self.snapshot()
        self.assertEqual(after['users'], before['users'])
        self.assertEqual([r for r in after['items'] if r['player_id'] == self.other],
                         [r for r in before['items'] if r['player_id'] == self.other])
        self.assertEqual(self.inventory(), {'ItemBattery': 1, 'ItemFleeb': 1, 'ItemTinCan': 7, 'ItemSerum': 1})

    def test_craft_increments_existing_output_and_reports_depleted_ingredients(self):
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.player}','ItemSerum',3)")
        self.stock('ItemBattery', 1)
        self.stock('ItemFleeb', 1)
        self.assert_success(self.craft(), 0, 0, serum=4)
        items = self.inventory()
        self.assertEqual(items.get('ItemBattery', 0), 0)
        self.assertEqual(items.get('ItemFleeb', 0), 0)
        self.assertEqual(items['ItemSerum'], 4)

    def test_three_ingredient_recipe_consumes_catalog_quantities(self):
        sql("INSERT INTO owned_items (player_id,item_id,quantity) VALUES "
            f"('{self.player}','ItemSuperchargedBattery',2),('{self.player}','ItemCircuitBoard',2)")
        # Native client posts this exact slashless URL; redirects must not turn POST into GET.
        url = 'http://127.0.0.1:8087/session/recipe/use'
        request = urllib.request.Request(url, json.dumps({'session_id': self.session,
            'recipe_id': 'RecipeMortyChip'}).encode(), {'Content-Type': 'application/json'}, method='POST')
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.geturl(), url)
            status, body = response.status, json.load(response)
        self.assertEqual(status, 200)
        self.assertNotIn('error', body)
        self.assertEqual(body['result'], {'type': 3, 'item_id': 'ItemMortyChip', 'quantity': 1,
                                          'amount': 1, 'amount_received': 1})
        expected = {'ItemSuperchargedBattery': 1, 'ItemCircuitBoard': 1,
                    'ItemTinCan': 6, 'ItemMortyChip': 1}
        self.assertEqual({item['item_id']: item['quantity'] for item in body['owned_items']}, expected)
        self.assertEqual(len(body['owned_items']), len(expected))
        self.assertEqual(self.inventory(), {'ItemBattery': 2, 'ItemFleeb': 2, **expected})

    def test_invalid_session_and_input_leave_all_fixture_rows_unchanged(self):
        before = self.snapshot()
        requests = [
            {'session_id': str(uuid.uuid4()), 'recipe_id': 'RecipeSerum'},
            {'recipe_id': 'RecipeSerum'},
            {'session_id': self.session},
            {'session_id': [], 'recipe_id': 'RecipeSerum'},
            {'session_id': self.session, 'recipe_id': []},
            {'session_id': self.session, 'recipe_id': None},
            {'session_id': self.session, 'recipe_id': 1},
        ]
        for request in requests:
            with self.subTest(request=request):
                self.assert_failure(post('/session/recipe/use', request))
                self.assertEqual(self.snapshot(), before)

    def test_unknown_recipe_is_rejected_without_changes(self):
        before = self.snapshot()
        self.assert_failure(self.craft(recipe_id='Recipe' + uuid.uuid4().hex), 'RECIPE_ID_INVALID')
        self.assertEqual(self.snapshot(), before)

    def test_missing_or_insufficient_ingredient_cannot_use_another_owners_stock(self):
        for quantity in (0, None):
            with self.subTest(quantity=quantity):
                if quantity is None:
                    sql(f"DELETE FROM owned_items WHERE player_id='{self.player}' AND item_id='ItemFleeb'")
                else:
                    self.stock('ItemFleeb', quantity)
                before = self.snapshot()
                self.assert_failure(self.craft(), 'RECIPE_ITEM_NOT_OWNED')
                self.assertEqual(self.snapshot(), before)

    def test_output_at_limit_rejects_without_consuming_ingredients(self):
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.player}','ItemSerum',10)")
        before = self.snapshot()
        self.assert_failure(self.craft(), 'RECIPE_ITEM_RESULT_LIMIT')
        self.assertEqual(self.snapshot(), before)

    def test_output_can_reach_limit(self):
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.player}','ItemSerum',9)")
        self.assert_success(self.craft(), 1, 1, serum=10)
        self.assertEqual(self.inventory()['ItemSerum'], 10)

    def test_concurrent_last_ingredients_allow_exactly_one_craft(self):
        self.stock('ItemBattery', 1)
        self.stock('ItemFleeb', 1)
        start = threading.Barrier(2)

        def request(_):
            start.wait(timeout=10)
            return self.craft()

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(request, range(2)))
        successes = [response for response in responses if response[0] == 200]
        failures = [response for response in responses if response[0] != 200]
        self.assertEqual(len(successes), 1)
        self.assertEqual(len(failures), 1)
        self.assert_success(successes[0], 0, 0)
        self.assert_failure(failures[0], 'RECIPE_ITEM_NOT_OWNED')
        items = self.inventory()
        self.assertEqual(items['ItemSerum'], 1)
        self.assertEqual(items.get('ItemBattery', 0), 0)
        self.assertEqual(items.get('ItemFleeb', 0), 0)

    def test_repeat_requests_each_consume_stock_without_idempotency_token(self):
        self.assert_success(self.craft(), 1, 1)
        self.assert_success(self.craft(), 0, 0, serum=2)
        before = self.snapshot()
        self.assert_failure(self.craft(), 'RECIPE_ITEM_NOT_OWNED')
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(self.inventory()['ItemSerum'], 2)

    def test_duplicate_touched_inventory_rows_fail_without_partial_changes(self):
        for item in ('ItemBattery', 'ItemFleeb', 'ItemSerum'):
            with self.subTest(item=item):
                sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES "
                    f"('{self.player}','{item}',1),('{self.player}','{item}',1)")
                before = self.snapshot()
                self.assert_failure(self.craft(), 'FAILED')
                self.assertEqual(self.snapshot(), before)
                sql(f"DELETE FROM owned_items WHERE player_id='{self.player}' AND item_id='{item}'")
                if item != 'ItemSerum':
                    sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.player}','{item}',2)")

    def test_inventory_counts_outside_client_range_fail_without_changes(self):
        for quantity in ('NULL', '-1', '32769'):
            with self.subTest(quantity=quantity):
                sql(f"UPDATE owned_items SET quantity={quantity} WHERE player_id='{self.player}' AND item_id='ItemBattery'")
                before = self.snapshot()
                self.assert_failure(self.craft(), 'FAILED')
                self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

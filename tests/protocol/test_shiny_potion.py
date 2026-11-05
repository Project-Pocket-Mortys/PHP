"""Shiny Potion account timer with disposable UUID fixtures; no account reseeding."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import re
import threading
import unittest
import urllib.request
import uuid

from test_http import ROOT, php, post, sql

ITEM = 'ItemShinyPotion'


class ShinyPotionTests(unittest.TestCase):
    def test_raw_startup_keeps_utc_wall_ticks_while_typed_response_has_zone(self):
        status, body = self.request()
        self.assertEqual(status, 200)
        self.assertTrue(body['end_usage_time'].endswith('Z'))
        _, details = post('/session/player-details', {'session_id':self.player})
        raw = details['play_shiny_potion'][0]['end_usage_time']
        self.assertRegex(raw, r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}$')
        # Raw DateTime.Parse(None) must keep these UTC wall-clock ticks instead
        # of converting a zoned value to the device's local timezone.
        self.assertEqual(datetime.fromisoformat(raw).replace(tzinfo=timezone.utc),
                         datetime.fromisoformat(body['end_usage_time']))
        self.assertEqual(sql(f"SELECT quantity FROM owned_items WHERE player_id='{self.player}' AND item_id='{ITEM}'")[0]['quantity'], 1)

    def test_native_slashless_post_preserves_body_without_redirect(self):
        url = 'http://127.0.0.1:8087/session/use-shiny-potion'
        request = urllib.request.Request(url, json.dumps({'session_id': self.player}).encode(),
                                         {'Content-Type':'application/json'}, method='POST')
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertEqual(response.geturl(), url)
            self.assertIs(json.load(response)['shiny_potion_active'], True)
        self.assertEqual(sql(f"SELECT quantity FROM owned_items WHERE player_id='{self.player}' AND item_id='{ITEM}'")[0]['quantity'], 1)

    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.players = [str(uuid.uuid4()) for _ in range(2)]
        self.player = self.players[0]
        self.addCleanup(self.cleanup)
        for player in self.players:
            sql(f"INSERT INTO users (secret,player_id,session_id,username,state,tags) "
                f"VALUES ('{player}','{player}','{player}','ShinyPotionFixture','WORLD','[]')")
            sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES "
                f"('{player}','{ITEM}',2),('{player}','ItemSerum',7)")

    def cleanup(self):
        for player in self.players:
            for table in ('battles', 'owned_items', 'users'):
                sql(f"DELETE FROM {table} WHERE player_id='{player}'")

    def request(self, **overrides):
        body = {'session_id': self.player}
        body.update(overrides)
        return post('/session/use-shiny-potion', body)

    def snapshot(self):
        ids = "','".join(self.players)
        return {table: sql(f"SELECT * FROM {table} WHERE player_id IN ('{ids}') ORDER BY id")
                for table in ('users', 'owned_items')}

    def details(self, player=None):
        status, body = post('/session/player-details', {'session_id': player or self.player})
        self.assertEqual(status, 200, body)
        return body['play_shiny_potion']

    def assert_failed_unchanged(self, response=None, expected_code='UNKNOWN', **overrides):
        before = self.snapshot()
        status, body = self.request(**overrides) if response is None else response
        self.assertGreaterEqual(status, 400, body)
        self.assertLess(status, 500, body)
        self.assertEqual(body, {'error': {'code': expected_code}})
        self.assertEqual(self.snapshot(), before)

    def assert_success(self, response, quantity=1):
        status, body = response
        self.assertEqual(status, 200, body)
        self.assertEqual(set(body), {'quantity', 'shiny_potion_active', 'end_usage_time', 'shiny_potion_item_id'})
        self.assertIs(type(body['quantity']), int)
        self.assertEqual(body['quantity'], quantity)
        self.assertIs(body['shiny_potion_active'], True)
        self.assertEqual(body['shiny_potion_item_id'], ITEM)
        expiry = datetime.fromisoformat(body['end_usage_time'].replace('Z', '+00:00'))
        self.assertEqual(expiry.utcoffset().total_seconds(), 0)
        self.assertEqual(self.details(), [{'end_usage_time': body['end_usage_time'].removesuffix('Z')}])
        return body

    def test_activation_consumes_one_and_persists_exact_two_hour_db_timer(self):
        before = self.snapshot()
        body = self.assert_success(self.request())
        rows = sql(f"SELECT TIMESTAMPDIFF(SECOND,UTC_TIMESTAMP(6),shiny_potion_expires_at) AS seconds, "
                   f"DATE_FORMAT(shiny_potion_expires_at,'%Y-%m-%dT%H:%i:%s.%fZ') AS expiry "
                   f"FROM users WHERE player_id='{self.player}'")
        self.assertIn(rows[0]['seconds'], range(7195, 7201))
        self.assertEqual(body['end_usage_time'], rows[0]['expiry'])
        after = self.snapshot()
        next(u for u in before['users'] if u['player_id'] == self.player)['shiny_potion_expires_at'] = next(
            u for u in after['users'] if u['player_id'] == self.player)['shiny_potion_expires_at']
        next(u for u in before['users'] if u['player_id'] == self.player)['last_seen'] = next(
            u for u in after['users'] if u['player_id'] == self.player)['last_seen']
        next(i for i in before['owned_items'] if i['player_id'] == self.player and i['item_id'] == ITEM)['quantity'] -= 1
        self.assertEqual(after, before)

    def test_active_retry_does_not_extend_or_charge(self):
        self.assert_success(self.request())
        self.assert_failed_unchanged(expected_code='ALREADY_ACTIVE_SHINY_POTION')

    def test_null_and_expired_startup_are_inactive_and_reads_never_clear_history(self):
        self.assertIsNone(self.details())
        sql(f"UPDATE users SET shiny_potion_expires_at=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE player_id='{self.player}'")
        before = self.snapshot()
        self.assertIsNone(self.details())
        self.assertIsNone(self.details())
        self.assertEqual(self.snapshot(), before)
        self.assert_success(self.request())

    def test_expiry_boundary_uses_database_clock_and_is_account_private(self):
        sql(f"UPDATE users SET shiny_potion_expires_at=UTC_TIMESTAMP(6)+INTERVAL 10 MINUTE WHERE player_id='{self.player}'")
        self.assertEqual(len(self.details()), 1)
        self.assertIsNone(self.details(self.players[1]))
        sql(f"UPDATE users SET shiny_potion_expires_at=UTC_TIMESTAMP(6) WHERE player_id='{self.player}'")
        self.assertIsNone(self.details())

    def test_malformed_requests_and_invalid_sessions_do_not_charge(self):
        for body in ({}, {'session_id': ''}, {'session_id': []}, {'session_id': 12}, [], None,
                     {'session_id': self.player, 'quantity': 99}, {'session_id': self.player, 'item_id': ITEM}):
            before = self.snapshot()
            status, result = post('/session/use-shiny-potion', body)
            self.assertEqual(status, 400, result)
            self.assertEqual(result, {'error': {'code': 'UNKNOWN'}})
            self.assertEqual(self.snapshot(), before)
        self.assert_failed_unchanged(session_id=str(uuid.uuid4()))

    def test_missing_invalid_and_duplicate_stock_do_not_charge(self):
        for quantity in (0, -1, 'NULL'):
            sql(f"UPDATE owned_items SET quantity={quantity} WHERE player_id='{self.player}' AND item_id='{ITEM}'")
            self.assert_failed_unchanged(expected_code='NOT_ENOUGH_SHINY_POTIONS')
        sql(f"UPDATE owned_items SET quantity=1 WHERE player_id='{self.player}' AND item_id='{ITEM}'")
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.player}','{ITEM}',1)")
        self.assert_failed_unchanged(expected_code='NOT_ENOUGH_SHINY_POTIONS')
        sql(f"DELETE FROM owned_items WHERE player_id='{self.player}' AND item_id='{ITEM}'")
        self.assert_failed_unchanged(expected_code='NOT_ENOUGH_SHINY_POTIONS')

    def test_ambiguous_session_and_player_identity_do_not_charge_or_expose_timer(self):
        other = self.players[1]
        sql(f"UPDATE users SET session_id='{self.player}' WHERE player_id='{other}'")
        self.assert_failed_unchanged()
        sql(f"UPDATE users SET session_id='{other}' WHERE player_id='{other}'")
        # Register cleanup before creating the alias so even assertion failures
        # retain ownership of every disposable user row.
        alias_secret = str(uuid.uuid4())
        self.addCleanup(lambda: sql(f"DELETE FROM users WHERE secret='{alias_secret}'"))
        sql(f"INSERT INTO users (secret,player_id,session_id,username,state,tags,shiny_potion_expires_at) "
            f"VALUES ('{alias_secret}','{self.player}','{alias_secret}','ShinyAlias','WORLD','[]',UTC_TIMESTAMP(6)+INTERVAL 1 HOUR)")
        self.assert_failed_unchanged()
        self.assertIsNone(self.details())

    def test_world_state_and_live_battle_guard(self):
        for state in ('BATTLE', 'MAIN_MENU'):
            sql(f"UPDATE users SET state='{state}' WHERE player_id='{self.player}'")
            self.assert_failed_unchanged()
        sql(f"UPDATE users SET state='WORLD' WHERE player_id='{self.player}'")
        battle = str(uuid.uuid4())
        sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,state) VALUES ('{battle}','{self.player}','{self.players[1]}','ACTIVE')")
        self.assert_failed_unchanged()

    def test_concurrent_last_stock_and_expired_reactivation_spend_once(self):
        for expired in (False, True):
            sql(f"UPDATE users SET shiny_potion_expires_at={'UTC_TIMESTAMP(6)-INTERVAL 1 SECOND' if expired else 'NULL'} WHERE player_id='{self.player}'")
            sql(f"UPDATE owned_items SET quantity=1 WHERE player_id='{self.player}' AND item_id='{ITEM}'")
            barrier = threading.Barrier(2)
            def activate(_):
                barrier.wait(timeout=5)
                return self.request()
            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(activate, range(2)))
            self.assertEqual(sorted(r[0] for r in responses), [200, 409], responses)
            self.assertEqual(next(r[1] for r in responses if r[0] == 409),
                             {'error': {'code': 'ALREADY_ACTIVE_SHINY_POTION'}})
            self.assert_success(next(r for r in responses if r[0] == 200), quantity=0)
            self.assertEqual(sql(f"SELECT quantity FROM owned_items WHERE player_id='{self.player}' AND item_id='{ITEM}'"), [{'quantity': 0}])

    def test_stock_update_fault_rolls_back_timer_and_inventory(self):
        trigger = 'shiny_fault_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE UPDATE ON owned_items FOR EACH ROW BEGIN IF NEW.player_id='{self.player}' AND NEW.item_id='{ITEM}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID shiny rollback'; END IF; END")
        before = self.snapshot()
        self.assertEqual(self.request(), (500, {'error': {'code': 'UNKNOWN'}}))
        self.assertEqual(self.snapshot(), before)

    def test_additive_migration_preserves_original_users_and_reapplies(self):
        table = 'shiny_schema_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TABLE IF EXISTS {table}'))
        original = (ROOT / 'pocket_mortys.sql').read_text(encoding='utf-8')
        definition = re.search(r'CREATE TABLE `users` \(.*?\) ENGINE=.*?;', original, re.S).group(0)
        sql(definition.replace('`users`', f'`{table}`', 1))
        sql(f"INSERT INTO {table} (id,secret,player_id,session_id,username,state,tags) VALUES (1,'{self.player}','{self.player}','{self.player}','ShinyMigration','WORLD','[]')")
        before = sql(f'SELECT * FROM {table}')
        migration = (ROOT / 'tools/research/server/migrations/005-shiny-potion-expiry.sql').read_text(encoding='utf-8')
        for _ in range(2):
            sql(re.sub(r'\busers\b', table, migration))
            after = sql(f'SELECT * FROM {table}')
            self.assertIsNone(after[0].pop('shiny_potion_expires_at'))
            self.assertEqual(after, before)


if __name__ == '__main__':
    unittest.main()

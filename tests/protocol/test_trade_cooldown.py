"""Cooldown projection with additive UUID fixtures; never reseed native accounts."""
import base64
from datetime import datetime, timezone
import json
import unittest
import urllib.error
import urllib.request
import uuid

from test_http import php, post


class TradeCooldownTests(unittest.TestCase):
    def execute(self, queries, fetch=False):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                "$queries=json_decode(base64_decode('" + encoded + "'),true); $pdo->beginTransaction(); ")
        if fetch:
            return json.loads(php(code + "$out=[]; foreach($queries as $k=>$q) $out[$k]=$pdo->query($q)->fetchAll(); $pdo->commit(); echo json_encode($out);"))
        php(code + "foreach($queries as $q) $pdo->exec($q); $pdo->commit();")

    def setUp(self):
        self.a, self.b = [str(uuid.uuid4()) for _ in range(2)]
        self.party, self.spare = [str(uuid.uuid4()) for _ in range(2)]
        self.players = "','".join((self.a, self.b))
        self.morties = "','".join((self.party, self.spare))
        self.addCleanup(self.cleanup)
        queries = []
        for player in (self.a, self.b):
            queries.append(
                f"INSERT INTO users (secret,player_id,session_id,username,state,active_deck_id,tags,coins,coupons,permits) "
                f"VALUES ('{player}','{player}','{player}','TradeCooldownFixture','WORLD',0,'[]',21,9,3)")
        for morty in (self.party, self.spare):
            queries.extend([
                f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,level,xp,hp,hp_stat,attack_stat,defence_stat,speed_stat,variant,is_locked,is_trading_locked,fight_pit_id,evolution_points,xp_lower,xp_upper) "
                f"VALUES ('{self.a}','{morty}','MortyDefault',5,125,20,20,11,10,10,'Normal','false','false','null',0,125,216)",
                f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{morty}','AttackOutburst',0,12,12)",
            ])
        queries.extend([
            f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{self.a}',0,'[\"{self.party}\"]')",
            f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.a}','ItemSerum',2)",
        ])
        self.execute(queries)

    def cleanup(self):
        self.execute([
            f"DELETE FROM completed_trades WHERE request_player_id IN ('{self.players}') OR offer_player_id IN ('{self.players}')",
            f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.morties}')",
            *[f"DELETE FROM {table} WHERE player_id IN ('{self.players}')" for table in
              ('event_queue', 'trade_offers', 'trades', 'decks', 'owned_items', 'owned_morties', 'users')],
        ])

    def snapshot(self):
        queries = {table: f"SELECT * FROM {table} WHERE player_id IN ('{self.players}') ORDER BY id"
                   for table in ('users', 'owned_items', 'owned_morties', 'decks', 'trades', 'trade_offers', 'event_queue')}
        queries['attacks'] = f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.morties}') ORDER BY id"
        queries['completed'] = (f"SELECT * FROM completed_trades WHERE request_player_id IN ('{self.players}') "
                                f"OR offer_player_id IN ('{self.players}') ORDER BY id")
        return self.execute(queries, fetch=True)

    def cooldown(self, spoof_player=None):
        before = self.snapshot()
        payload = {'session_id': self.a, 'use_friends': False}
        if spoof_player is not None:
            payload['player_id'] = spoof_player
        status, body = post('/trading/get-trades', payload)
        self.assertEqual(status, 200, body)
        self.assertEqual(self.snapshot(), before, 'GetTrades must remain read-only')
        return body['player_cooldown_data']

    def cancel(self, trade_id):
        request = urllib.request.Request(
            'http://127.0.0.1:8087/trading/cancel-trade/',
            json.dumps({'trade_id': trade_id}).encode(),
            {'Content-Type': 'application/json', 'Cookie': 'session_id=' + self.a}, method='POST')
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def test_null_expiry_roundtrips_without_writes(self):
        self.assertEqual(self.cooldown(), {'expiry': None, 'trades': 0})

    def test_future_expiry_uses_authenticated_account_without_writes(self):
        expiry = '2097-03-04T05:06:07.123Z'
        other_expiry = '2098-08-09T10:11:12.456Z'
        self.execute([
            f"UPDATE users SET expiry_trade='{expiry}' WHERE player_id='{self.a}'",
            f"UPDATE users SET expiry_trade='{other_expiry}' WHERE player_id='{self.b}'",
        ])
        self.assertEqual(self.cooldown(spoof_player=self.b), {'expiry': expiry, 'trades': 1})

    def test_free_creation_and_owner_cancellation_preserve_cooldown_and_resources(self):
        before = self.snapshot()
        status, body = post('/trading/request-morty', {
            'session_id': self.a, 'owned_morty_id': self.spare,
            'requested_morty_id': 'any', 'request_variant': 'Normal', 'is_free_trade': True,
        })
        self.assertEqual(status, 200, body)
        self.assertEqual(body['error'], 'None')
        trade_id = body['trade']['trade_id']
        created = self.snapshot()
        owner = next(row for row in created['users'] if row['player_id'] == self.a)
        expiry = owner['expiry_trade']
        self.assertIsInstance(expiry, str)
        self.assertGreater(datetime.fromisoformat(expiry.replace('Z', '+00:00')), datetime.now(timezone.utc))
        self.assertEqual(len(created['trades']), 1)
        for table in ('owned_items', 'owned_morties', 'decks', 'attacks', 'trade_offers', 'completed', 'event_queue'):
            self.assertEqual(created[table], before[table], table)
        expected_users = json.loads(json.dumps(before['users']))
        for expected, actual in zip(expected_users, created['users']):
            if expected['player_id'] == self.a:
                expected['expiry_trade'] = expiry
                expected['last_seen'] = actual['last_seen']
        self.assertEqual(created['users'], expected_users, 'Free creation must not charge coupons or change profile/resources')
        # Continue through cancellation even while the creation projection is red.
        with self.subTest(stage='created'):
            self.assertEqual(self.cooldown(), {'expiry': expiry, 'trades': 1})
        self.assertEqual(self.cancel(trade_id), (200, {'error': 'None'}))
        cancelled = self.snapshot()
        expected = dict(created)
        expected['trades'] = []
        self.assertEqual(cancelled, expected, 'Cancellation must only remove the listing, preserving cooldown/resources/party/attacks')
        with self.subTest(stage='cancelled'):
            self.assertEqual(self.cooldown(), {'expiry': expiry, 'trades': 1})

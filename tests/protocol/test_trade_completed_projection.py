"""Native completed-trade spelling with additive UUID fixtures; no global seed."""
import base64
import json
import unittest
import uuid

from test_http import php, post


class TradeCompletedProjectionTests(unittest.TestCase):
    def execute(self, queries, fetch=False):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                "$queries=json_decode(base64_decode('" + encoded + "'),true); ")
        if fetch:
            return json.loads(php(code + "$pdo->exec('START TRANSACTION READ ONLY'); $out=[]; "
                                  "foreach($queries as $k=>$q) $out[$k]=$pdo->query($q)->fetchAll(); "
                                  "$pdo->rollBack(); echo json_encode($out);"))
        php(code + "$pdo->beginTransaction(); foreach($queries as $q) $pdo->exec($q); $pdo->commit();")

    def setUp(self):
        self.requester, self.offerer, self.unrelated = [str(uuid.uuid4()) for _ in range(3)]
        self.requested, self.offered = [str(uuid.uuid4()) for _ in range(2)]
        self.completions = [str(uuid.uuid4()) for _ in range(2)]
        self.parents = [str(uuid.uuid4()) for _ in range(2)]
        self.offers = [str(uuid.uuid4()) for _ in range(2)]
        self.players = "','".join((self.requester, self.offerer, self.unrelated))
        self.morties = "','".join((self.requested, self.offered))
        self.addCleanup(self.cleanup)
        queries = []
        for player in (self.requester, self.offerer, self.unrelated):
            queries.append(
                "INSERT INTO users (secret,player_id,session_id,username,state,active_deck_id,tags,coins,coupons,permits) "
                f"VALUES ('{player}','{player}','{player}','TComp{player[:8]}','WORLD',0,'[]',21,9,3)")
        for player, morty in ((self.requester, self.requested), (self.offerer, self.offered)):
            queries.extend([
                "INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,level,xp,hp,hp_stat,attack_stat,defence_stat,speed_stat,variant,is_locked,is_trading_locked,fight_pit_id,evolution_points,xp_lower,xp_upper) "
                f"VALUES ('{player}','{morty}','MortyDefault',5,125,20,20,11,10,10,'Normal','false','false','null',0,125,216)",
                f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{morty}','AttackOutburst',0,12,12)",
                f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{player}',0,'[\"{morty}\"]')",
                f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{player}','ItemSerum',2)",
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
        queries['owned_attacks'] = f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.morties}') ORDER BY id"
        queries['completed_trades'] = (
            f"SELECT * FROM completed_trades WHERE request_player_id IN ('{self.players}') "
            f"OR offer_player_id IN ('{self.players}') ORDER BY id")
        queries['friend_list'] = (
            f"SELECT * FROM friend_list WHERE player_id_a IN ('{self.players}') "
            f"OR player_id_b IN ('{self.players}') ORDER BY id")
        return self.execute(queries, fetch=True)

    def add_completed(self):
        queries, expected = [], []
        for index, free in enumerate((False, True)):
            fulfilled = f'2026-01-0{index + 1} 12:34:56'
            queries.append(
                "INSERT INTO completed_trades (completed_trade_id,request_player_id,offer_player_id,morty_request_id,morty_offer_id,trade_request_id,trade_offer_id,is_free_trade,fulfilled_at) "
                f"VALUES ('{self.completions[index]}','{self.requester}','{self.offerer}','{self.requested}',"
                f"'{self.offered}','{self.parents[index]}','{self.offers[index]}',{int(free)},'{fulfilled}')")
            expected.append({'completed_trade_id': self.completions[index],
                             'request_player_id': self.requester, 'offer_player_id': self.offerer,
                             'morty_request_id': self.requested, 'morty_offer_id': self.offered,
                             'trade_request_id': self.parents[index], 'trade_offer_id': self.offers[index],
                             'is_free_trade': free, '_fulfilled': f'2026-01-0{index + 1}T12:34:56.000Z'})
        self.execute(queries)
        return list(reversed(expected))

    def listing(self, player):
        before = self.snapshot()
        status, body = post('/trading/get-trades', {'session_id': player, 'use_friends': False})
        self.assertEqual(status, 200, body)
        self.assertEqual(self.snapshot(), before, 'GetTrades must preserve all scoped raw gameplay rows')
        self.assertIn('competed_trades', body, 'Native JsonFx field must exist even when the array is empty')
        self.assertIn('completed_trades', body, 'Retain the existing completed-trade response field')
        self.assertIsInstance(body['competed_trades'], list)
        self.assertIsInstance(body['completed_trades'], list)
        self.assertEqual(body['competed_trades'], body['completed_trades'])
        return body

    def test_empty_completed_arrays_are_present_for_native_and_existing_callers(self):
        for player in (self.requester, self.offerer, self.unrelated):
            with self.subTest(player=player):
                body = self.listing(player)
                self.assertEqual(body['competed_trades'], [])
                self.assertEqual(body['completed_trades'], [])

    def test_both_participants_receive_exact_alias_values_and_boolean_types(self):
        expected = self.add_completed()
        for player in (self.requester, self.offerer):
            with self.subTest(player=player):
                body = self.listing(player)
                for name in ('competed_trades', 'completed_trades'):
                    self.assertEqual(body[name], expected)
                    self.assertEqual([type(row['is_free_trade']) for row in body[name]], [bool, bool])
                    self.assertEqual([row['is_free_trade'] for row in body[name]], [True, False])

    def test_unrelated_caller_receives_empty_aliases_despite_other_completed_rows(self):
        self.add_completed()
        body = self.listing(self.unrelated)
        self.assertEqual(body['competed_trades'], [])
        self.assertEqual(body['completed_trades'], [])

    def test_repeated_completed_reads_preserve_database_and_projection(self):
        expected = self.add_completed()
        before = self.snapshot()
        for _ in range(3):
            for player in (self.requester, self.offerer):
                self.assertEqual(self.listing(player)['competed_trades'], expected)
        self.assertEqual(self.snapshot(), before, 'Repeated projection cannot consume or rewrite completion records')


if __name__ == '__main__':
    unittest.main()

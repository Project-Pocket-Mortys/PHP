"""Native offer display metadata with additive UUID fixtures; never reseed.

The consumers documented in docs/protocol/native-trade-offer-contract.md use
request_user_name for display and both enrichment Morty IDs for species lookup.
"""
import base64
import json
import unittest
import urllib.request
import uuid

from test_http import php, post


class TradeOfferMetadataTests(unittest.TestCase):
    def execute(self, queries, fetch=False):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                "$queries=json_decode(base64_decode('" + encoded + "'),true); $pdo->beginTransaction(); ")
        if fetch:
            return json.loads(php(code + "$out=[]; foreach($queries as $k=>$q) $out[$k]=$pdo->query($q)->fetchAll(); $pdo->rollBack(); echo json_encode($out);"))
        php(code + "foreach($queries as $q) $pdo->exec($q); $pdo->commit();")

    def setUp(self):
        self.offer_player, self.request_player = [str(uuid.uuid4()) for _ in range(2)]
        self.players = "','".join((self.offer_player, self.request_player))
        self.offered, self.requested, self.offer_party, self.request_party = [str(uuid.uuid4()) for _ in range(4)]
        self.morties = "','".join((self.offered, self.requested, self.offer_party, self.request_party))
        self.trade = str(uuid.uuid4())
        self.offer_name = 'OfferMetadata_' + uuid.uuid4().hex
        self.request_name = 'RequestMetadata_' + uuid.uuid4().hex
        self.addCleanup(self.cleanup)
        queries = []
        for player, name, spare, party in (
            (self.offer_player, self.offer_name, self.offered, self.offer_party),
            (self.request_player, self.request_name, self.requested, self.request_party),
        ):
            queries.extend([
                f"INSERT INTO users (secret,player_id,session_id,username,state,active_deck_id,tags,level,coupons) VALUES ('{player}','{player}','{player}','{name}','WORLD',0,'[]',5,9)",
                f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{player}',0,'[\"{party}\"]')",
            ])
            for instance in (spare, party):
                species = 'MortyScruffy' if instance == self.offered else 'MortyDefault'
                queries.extend([
                    f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,level,xp,hp,hp_stat,attack_stat,defence_stat,speed_stat,variant,is_locked,is_trading_locked,fight_pit_id,evolution_points,xp_lower,xp_upper) VALUES ('{player}','{instance}','{species}',5,125,20,20,11,10,10,'Normal','false','false','null',0,125,216)",
                    f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{instance}','AttackOutburst',0,12,12)",
                ])
        queries.append(f"INSERT INTO trades (trade_id,player_id,morty_trade_id,requested_morty_id,request_variant,is_free_trade) VALUES ('{self.trade}','{self.request_player}','{self.requested}','any','Normal',1)")
        self.execute(queries)
        self.assertEqual(post('/session/friend/request', {'session_id': self.offer_player,
                                                        'player_id': self.request_player})[0], 200)
        self.assertEqual(post('/session/friend/response', {'session_id': self.request_player,
                                                         'player_id': self.offer_player, 'approve': True}), (200, 1))

    def cleanup(self):
        self.execute([
            f"DELETE FROM completed_trades WHERE request_player_id IN ('{self.players}') OR offer_player_id IN ('{self.players}')",
            f"DELETE FROM trade_offers WHERE player_id IN ('{self.players}') OR trade_id='{self.trade}'",
            f"DELETE FROM trades WHERE player_id IN ('{self.players}')",
            f"DELETE FROM friend_list WHERE player_id_a IN ('{self.players}') OR player_id_b IN ('{self.players}')",
            f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.morties}')",
            *[f"DELETE FROM {table} WHERE player_id IN ('{self.players}')" for table in
              ('event_queue', 'owned_items', 'decks', 'owned_morties', 'users')],
        ])

    def snapshot(self):
        queries = {table: f"SELECT * FROM {table} WHERE player_id IN ('{self.players}') ORDER BY id"
                   for table in ('users', 'owned_morties', 'owned_items', 'decks', 'trades', 'trade_offers', 'event_queue')}
        queries.update(
            owned_attacks=f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.morties}') ORDER BY id",
            friend_list=f"SELECT * FROM friend_list WHERE player_id_a IN ('{self.players}') OR player_id_b IN ('{self.players}') ORDER BY id",
            completed_trades=f"SELECT * FROM completed_trades WHERE request_player_id IN ('{self.players}') OR offer_player_id IN ('{self.players}') ORDER BY id",
        )
        return self.execute(queries, fetch=True)

    def create_offer(self):
        # The four fields emitted by the native OfferMorty request.
        status, body = post('/trading/offer-morty', {
            'session_id': self.offer_player, 'player_id': self.offer_player,
            'offered_morty_id': self.offered, 'trade_request_id': self.trade,
        })
        self.assertEqual(status, 200, body)
        self.assertEqual(body['error'], 'None')
        return body['offer']

    def assert_offer_identity(self, offer, offer_id):
        self.assertEqual({key: offer[key] for key in ('trade_offer_id', 'trade_id', 'player_id', 'morty_offer_id')},
                         {'trade_offer_id': offer_id, 'trade_id': self.trade,
                          'player_id': self.offer_player, 'morty_offer_id': self.offered})

    def assert_display_metadata(self, offer):
        self.assertEqual(offer['request_user_name'], self.request_name)
        self.assertEqual(offer['offering_morty_id'], 'MortyScruffy')
        self.assertEqual(offer['request_morty_id'], 'MortyDefault')
        self.assertNotEqual(offer['request_user_name'], self.request_player)
        self.assertNotIn(offer['request_morty_id'], ('any', self.requested))
        self.assertNotEqual(offer['offering_morty_id'], self.offered)

    def test_native_offer_creation_uses_request_owner_name_and_both_owned_species(self):
        before = self.snapshot()
        offer = self.create_offer()
        self.assert_offer_identity(offer, offer['trade_offer_id'])
        self.assert_display_metadata(offer)
        after = self.snapshot()
        added = [row for row in after['trade_offers'] if row['trade_offer_id'] == offer['trade_offer_id']]
        self.assertEqual(len(added), 1)
        self.assert_offer_identity(added[0], offer['trade_offer_id'])
        after['trade_offers'].remove(added[0])
        self.assertEqual(after, before, 'Offer creation must only insert its own offer row')

    def test_get_trades_retains_offer_display_metadata_for_both_friends_without_writes(self):
        created = self.create_offer()
        before = self.snapshot()
        reloaded = []
        for actor in (self.offer_player, self.request_player):
            for _ in range(2):
                status, body = post('/trading/get-trades', {'session_id': actor, 'use_friends': True})
                self.assertEqual(status, 200, body)
                self.assertEqual(len(body['trade_offers']), 1, 'One durable offer must project exactly once')
                offer = body['trade_offers'][0]
                self.assert_offer_identity(offer, created['trade_offer_id'])
                self.assert_display_metadata(offer)
                reloaded.append(offer)
                self.assertEqual(self.snapshot(), before, 'GetTrades must not change persisted rows')
        self.assertTrue(all(offer == reloaded[0] for offer in reloaded))

    def test_duplicate_request_player_identity_omits_name_without_multiplying_offers(self):
        duplicate_session = str(uuid.uuid4())
        duplicate_name = 'AmbiguousMetadata_' + uuid.uuid4().hex
        self.execute([
            f"INSERT INTO users (secret,player_id,session_id,username,state,tags) VALUES ('{duplicate_session}','{self.request_player}','{duplicate_session}','{duplicate_name}','WORLD','[]')",
        ])
        created = self.create_offer()
        self.assert_offer_identity(created, created['trade_offer_id'])
        self.assertNotIn('request_user_name', created)
        self.assertEqual(created['offering_morty_id'], 'MortyScruffy')
        self.assertEqual(created['request_morty_id'], 'MortyDefault')
        before = self.snapshot()
        for actor in (self.offer_player, self.request_player):
            with self.subTest(actor=actor):
                status, body = post('/trading/get-trades', {'session_id': actor, 'use_friends': True})
                self.assertEqual(status, 200, body)
                self.assertEqual(len(body['trade_offers']), 1)
                offer = body['trade_offers'][0]
                self.assert_offer_identity(offer, created['trade_offer_id'])
                self.assertNotIn('request_user_name', offer)
                self.assertEqual(offer['offering_morty_id'], 'MortyScruffy')
                self.assertEqual(offer['request_morty_id'], 'MortyDefault')
                self.assertEqual(self.snapshot(), before, 'Ambiguous metadata projection must remain read-only')

    def test_orphan_offer_omits_metadata_and_owner_cookie_cancels_only_offer(self):
        offer_id, absent_parent = [str(uuid.uuid4()) for _ in range(2)]
        self.execute([
            f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{offer_id}','{absent_parent}','{self.offer_player}','{self.offered}')",
        ])
        before = self.snapshot()
        status, body = post('/trading/get-trades', {'session_id': self.offer_player, 'use_friends': True})
        self.assertEqual(status, 200, body)
        self.assertEqual(len(body['trade_offers']), 1)
        offer = body['trade_offers'][0]
        self.assertEqual({key: offer[key] for key in ('trade_offer_id', 'trade_id', 'player_id', 'morty_offer_id')},
                         {'trade_offer_id': offer_id, 'trade_id': absent_parent,
                          'player_id': self.offer_player, 'morty_offer_id': self.offered})
        for key in ('request_user_name', 'offering_morty_id', 'request_morty_id'):
            self.assertNotIn(key, offer)
        self.assertEqual(self.snapshot(), before, 'Orphan list projection must remain read-only')
        request = urllib.request.Request(
            'http://127.0.0.1:8087/trading/cancel-trade-offer/',
            json.dumps({'trade_offer_id': offer_id}).encode(),
            {'Content-Type': 'application/json', 'Cookie': 'session_id=' + self.offer_player},
            method='POST',
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            self.assertEqual((response.status, json.load(response)), (200, {'error': 'None'}))
        expected = dict(before)
        expected['trade_offers'] = [row for row in before['trade_offers'] if row['trade_offer_id'] != offer_id]
        self.assertEqual(self.snapshot(), expected, 'Orphan cancellation must only delete its offer')


if __name__ == '__main__':
    unittest.main()

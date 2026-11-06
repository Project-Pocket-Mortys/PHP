"""Durable trade references protect collections without changing stored flags.

All setup and cleanup is additive and scoped to UUID fixtures; no global seed.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import unittest
import urllib.error
import urllib.request
import uuid

from test_http import php, post, sql


def literal(value):
    if value is None:
        return 'NULL'
    return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"


class TradeReferenceTests(unittest.TestCase):
    def execute(self, queries, fetch=False):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                "$queries=json_decode(base64_decode('" + encoded + "'),true); $pdo->beginTransaction(); ")
        if fetch:
            return json.loads(php(code + "$out=[]; foreach($queries as $k=>$q) $out[$k]=$pdo->query($q)->fetchAll(); $pdo->rollBack(); echo json_encode($out);"))
        php(code + "foreach($queries as $q) $pdo->exec($q); $pdo->commit();")

    def setUp(self):
        self.a, self.b = [str(uuid.uuid4()) for _ in range(2)]
        self.target, self.donor, self.living, self.foreign = [str(uuid.uuid4()) for _ in range(4)]
        self.players = "','".join((self.a, self.b))
        self.morties = "','".join((self.target, self.donor, self.living, self.foreign))
        self.addCleanup(self.cleanup)
        queries = []
        for player in (self.a, self.b):
            queries.append(f"INSERT INTO users (secret,player_id,session_id,username,state,active_deck_id,tags,coupons) VALUES ('{player}','{player}','{player}','TradeReferenceFixture','WORLD',7,'[]',9)")
        for morty in (self.target, self.donor, self.living, self.foreign):
            owner = self.b if morty == self.foreign else self.a
            queries.extend([
                f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,hp,hp_stat,is_locked,is_trading_locked,evolution_points) VALUES ('{owner}','{morty}','MortyDefault',42,100,'false','false',0)",
                f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{morty}','AttackLick',0,3,18)",
            ])
        for player, party in ((self.a, [self.target, self.donor, self.living]), (self.b, [self.foreign])):
            queries.append(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{player}',7,{literal(json.dumps(party))})")
        self.execute(queries)

    def cleanup(self):
        self.execute([
            f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.morties}')",
            *[f"DELETE FROM {table} WHERE player_id IN ('{self.players}')" for table in
              ('event_queue', 'battles', 'trade_offers', 'trades', 'decks', 'owned_items', 'owned_morties', 'users')],
        ])

    def snapshot(self):
        queries = {table: f"SELECT * FROM {table} WHERE player_id IN ('{self.players}') ORDER BY id"
                   for table in ('users', 'owned_morties', 'owned_items', 'decks', 'trades', 'trade_offers', 'event_queue')}
        queries['attacks'] = f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.morties}') ORDER BY id"
        return self.execute(queries, fetch=True)

    def reference(self, morty, offer=False, owner=None, upper=False):
        ref = str(uuid.uuid4())
        owner = owner or self.a
        morty = morty.upper() if upper else morty
        if offer:
            # A deliberately absent parent models historical orphan offers.
            query = f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{ref}','{uuid.uuid4()}','{owner}','{morty}')"
        else:
            query = f"INSERT INTO trades (trade_id,player_id,morty_trade_id,is_free_trade) VALUES ('{ref}','{owner}','{morty}',1)"
        sql(query)
        return ref

    def cancel(self, ref, offer=False, owner=None):
        endpoint = 'cancel-trade-offer' if offer else 'cancel-trade'
        key = 'trade_offer_id' if offer else 'trade_id'
        request = urllib.request.Request('http://127.0.0.1:8087/trading/' + endpoint + '/',
                                         json.dumps({key: ref}).encode(),
                                         {'Content-Type': 'application/json', 'Cookie': 'session_id=' + (owner or self.a)}, method='POST')
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def details(self):
        status, body = post('/session/player-details', {'session_id': self.a})
        self.assertEqual(status, 200, body)
        return {row['owned_morty_id']: row for row in body['owned_morties']}

    def assert_lock(self, morty, expected):
        before = self.snapshot()
        self.assertIs(self.details()[morty]['is_trading_locked'], expected)
        self.assertEqual(self.snapshot(), before, 'Refreshing details must not rewrite legacy flags or gameplay rows')

    def assert_raw_false(self, morty):
        self.assertEqual(sql(f"SELECT is_trading_locked FROM owned_morties WHERE owned_morty_id='{morty}'"),
                         [{'is_trading_locked': 'false'}])

    def prepare_listing_donor(self):
        # Keep an unchanged living active party and list a separate spare.
        sql(f"UPDATE decks SET owned_morty_ids='{json.dumps([self.target, self.living])}' WHERE player_id='{self.a}' AND deck_id=7")

    def absorb(self, ids=None):
        return post('/session/owned_morties/absorb', {'session_id': self.a, 'owned_morty_id': self.target,
                                                    'absorb_owned_morty_ids': ids if ids is not None else [self.donor]})

    def reject_absorb(self, ids=None):
        before = self.snapshot()
        self.assertEqual(self.absorb(ids), (409, {'error': {'code': 'FAILED'}}))
        self.assertEqual(self.snapshot(), before, 'Reference rejection must precede every gameplay write')

    def test_details_combines_global_request_and_orphan_offer_references_without_writes(self):
        self.reference(self.target, owner=self.b)
        self.reference(self.donor, offer=True, owner=self.b)
        self.assert_lock(self.target, True)
        self.assert_lock(self.donor, True)
        self.assert_lock(self.living, False)

    def test_multiple_references_keep_lock_until_last_owner_cancellation(self):
        request = self.reference(self.donor)
        offer = self.reference(self.donor, offer=True)
        self.assert_lock(self.donor, True)
        self.assertEqual(self.cancel(request), (200, {'error': 'None'}))
        self.assert_lock(self.donor, True)
        self.assertEqual(self.cancel(offer, offer=True), (200, {'error': 'None'}))
        self.assert_lock(self.donor, False)

    def test_legacy_true_survives_cancellation_and_false_variants_stay_booleans(self):
        for raw, expected in ((None, False), ('', False), ('0', False), ('false', False), ('1', True), ('true', True)):
            with self.subTest(raw=raw):
                sql(f"UPDATE owned_morties SET is_trading_locked={literal(raw)} WHERE owned_morty_id='{self.donor}'")
                self.assert_lock(self.donor, expected)
        ref = self.reference(self.donor)
        self.assertEqual(self.cancel(ref), (200, {'error': 'None'}))
        self.assert_lock(self.donor, True)
        self.assertEqual(sql(f"SELECT is_trading_locked FROM owned_morties WHERE owned_morty_id='{self.donor}'"), [{'is_trading_locked': 'true'}])

    def test_orphan_offer_protects_until_exact_owner_withdraws(self):
        offer = self.reference(self.donor, offer=True)
        before = self.snapshot()
        self.assertEqual(self.cancel(offer, offer=True, owner=self.b), (403, {'error': {'code': 'FAILED'}}))
        self.assertEqual(self.snapshot(), before)
        self.assert_lock(self.donor, True)
        self.reject_absorb()
        self.assertEqual(self.cancel(offer, offer=True), (200, {'error': 'None'}))
        self.assert_lock(self.donor, False)
        self.assertEqual(self.absorb()[1]['removed'], [self.donor])

    def test_target_and_donor_references_reject_atomically_including_foreign_declared_rows(self):
        for morty in (self.target, self.donor):
            for offer in (False, True):
                with self.subTest(morty=morty, offer=offer):
                    ref = self.reference(morty, offer=offer, owner=self.b)
                    self.reject_absorb([self.living, self.donor])
                    table, key = ('trade_offers', 'trade_offer_id') if offer else ('trades', 'trade_id')
                    sql(f"DELETE FROM {table} WHERE {key}='{ref}'")

    def test_referenced_foreign_and_missing_inputs_are_ignored(self):
        self.reference(self.foreign, owner=self.b)
        missing = str(uuid.uuid4())
        self.reference(missing, offer=True, owner=self.b)
        before = sql(f"SELECT * FROM owned_morties WHERE owned_morty_id='{self.foreign}'")
        status, body = self.absorb([self.foreign, missing, self.target, self.donor])
        self.assertEqual(status, 200, body)
        self.assertEqual(body['removed'], [self.donor])
        self.assertEqual(sql(f"SELECT * FROM owned_morties WHERE owned_morty_id='{self.foreign}'"), before)

    def test_reference_matching_uses_database_case_insensitive_identity(self):
        for offer in (False, True):
            with self.subTest(offer=offer):
                ref = self.reference(self.donor, offer=offer, upper=True)
                self.assert_lock(self.donor, True)
                self.reject_absorb()
                self.assertEqual(self.cancel(ref, offer=offer), (200, {'error': 'None'}))
        self.assert_lock(self.donor, False)
        self.assertEqual(self.absorb()[1]['removed'], [self.donor])

    def test_native_paid_request_refresh_cancel_preserves_cost_and_raw_flags(self):
        self.prepare_listing_donor()
        status, body = post('/trading/request-morty', {'session_id': self.a, 'owned_morty_id': self.donor,
                                                     'requested_morty_id': 'any', 'is_free_trade': False})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['coupons'], 8)
        self.assert_raw_false(self.donor)
        self.assert_lock(self.donor, True)
        self.reject_absorb()
        before = self.snapshot()
        ref = body['trade']['trade_id']
        self.assertEqual(self.cancel(ref), (200, {'error': 'None'}))
        after = self.snapshot()
        before['trades'] = [row for row in before['trades'] if row['trade_id'] != ref]
        self.assertEqual(after, before, 'Cancellation must not refund coupons or change raw flags')
        self.assert_lock(self.donor, False)

    def test_native_offer_refresh_and_cancel_preserve_raw_flags(self):
        self.prepare_listing_donor()
        parent = self.reference(self.foreign, owner=self.b)
        status, body = post('/trading/offer-morty', {'session_id': self.a, 'player_id': self.a,
                                                  'offered_morty_id': self.donor, 'trade_request_id': parent})
        self.assertEqual(status, 200, body)
        ref = body['offer']['trade_offer_id']
        self.assert_raw_false(self.donor)
        self.assert_lock(self.donor, True)
        self.reject_absorb()
        self.assertEqual(self.cancel(ref, offer=True), (200, {'error': 'None'}))
        self.assert_lock(self.donor, False)
        self.assertEqual(self.absorb()[1]['removed'], [self.donor])

    def test_native_free_request_keeps_cooldown_after_cancellation(self):
        self.prepare_listing_donor()
        status, body = post('/trading/request-morty', {'session_id': self.a, 'owned_morty_id': self.donor, 'is_free_trade': True})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['coupons'], 9)
        self.assert_raw_false(self.donor)
        before = sql(f"SELECT coupons,expiry_trade FROM users WHERE player_id='{self.a}'")
        self.assertTrue(before[0]['expiry_trade'])
        self.assertEqual(self.cancel(body['trade']['trade_id']), (200, {'error': 'None'}))
        self.assertEqual(sql(f"SELECT coupons,expiry_trade FROM users WHERE player_id='{self.a}'"), before)
        self.assert_lock(self.donor, False)

    def test_concurrent_request_creation_and_absorb_serialize(self):
        self.prepare_listing_donor()
        barrier = threading.Barrier(2)
        def create():
            barrier.wait(timeout=5)
            return post('/trading/request-morty', {'session_id': self.a, 'owned_morty_id': self.donor, 'is_free_trade': True})
        def absorb():
            barrier.wait(timeout=5)
            return self.absorb()
        with ThreadPoolExecutor(max_workers=2) as pool:
            created, absorbed = pool.submit(create), pool.submit(absorb)
            c, a = created.result(timeout=15), absorbed.result(timeout=15)
        if c[0] == 200:
            self.assertEqual(a, (409, {'error': {'code': 'FAILED'}}))
            self.assert_lock(self.donor, True)
        else:
            self.assertEqual(c, (403, {'error': {'code': 'TRADE_REQUEST_MORTY_DOES_NOT_BELONG_TO_PLAYER'}}))
            self.assertEqual(a[1]['removed'], [self.donor])
            self.assertEqual(sql(f"SELECT id FROM trades WHERE morty_trade_id='{self.donor}'"), [])

    def test_concurrent_offer_creation_and_absorb_serialize(self):
        self.prepare_listing_donor()
        parent = self.reference(self.foreign, owner=self.b)
        before = self.snapshot()
        barrier = threading.Barrier(2)

        def create():
            barrier.wait(timeout=5)
            return post('/trading/offer-morty', {'session_id': self.a, 'player_id': self.a,
                                              'offered_morty_id': self.donor, 'trade_request_id': parent})

        def absorb():
            barrier.wait(timeout=5)
            return self.absorb()

        with ThreadPoolExecutor(max_workers=2) as pool:
            created, absorbed = pool.submit(create), pool.submit(absorb)
            c, a = created.result(timeout=15), absorbed.result(timeout=15)
        after = self.snapshot()
        if c[0] == 200:
            self.assertEqual(a, (409, {'error': {'code': 'FAILED'}}))
            self.assertEqual(c[1]['error'], 'None')
            added = [row for row in after['trade_offers']
                     if row['trade_offer_id'] == c[1]['offer']['trade_offer_id']]
            self.assertEqual(len(added), 1)
            self.assertEqual((added[0]['trade_id'], added[0]['player_id'], added[0]['morty_offer_id']),
                             (parent, self.a, self.donor))
            # A rejected absorption changes nothing, including attacks/decks/points.
            after['trade_offers'].remove(added[0])
            self.assertEqual(after, before)
        else:
            self.assertEqual(c, (404, {'error': {'code': 'TRADE_NO_SUCH_MORTY'}}))
            self.assertEqual(a[0], 200, a)
            self.assertEqual(a[1]['removed'], [self.donor])
            self.assertEqual(after['trade_offers'], before['trade_offers'])
            self.assertEqual(after['trades'], before['trades'])
            self.assertFalse(any(row['owned_morty_id'] == self.donor for row in after['owned_morties']))
            self.assertFalse(any(row['owned_morty_id'] == self.donor for row in after['attacks']))
            recipient = next(row for row in after['owned_morties'] if row['owned_morty_id'] == self.target)
            self.assertEqual(recipient['evolution_points'], 1)
            self.assertEqual(after['users'], before['users'])


if __name__ == '__main__':
    unittest.main()

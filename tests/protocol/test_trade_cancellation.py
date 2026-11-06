"""Cancellation contracts with additive UUID fixtures; never reseed accounts."""
import base64
from concurrent.futures import ThreadPoolExecutor
import http.cookiejar
import json
import unittest
import urllib.error
import urllib.request
import uuid

from test_http import php, post, sql


class TradeCancellationTests(unittest.TestCase):
    def execute(self, queries, fetch=False):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                "$queries=json_decode(base64_decode('" + encoded + "'),true); ")
        if fetch:
            code += "$out=[]; foreach($queries as $key=>$q) $out[$key]=$pdo->query($q)->fetchAll(); echo json_encode($out);"
            return json.loads(php(code))
        php(code + "$pdo->beginTransaction(); foreach($queries as $q) $pdo->exec($q); $pdo->commit();")

    def setUp(self):
        self.players = [str(uuid.uuid4()) for _ in range(3)]
        self.a, self.b, self.c = self.players
        self.ids = "','".join(self.players)
        self.trade, self.other_trade = [str(uuid.uuid4()) for _ in range(2)]
        self.offer, self.sibling, self.other_offer = [str(uuid.uuid4()) for _ in range(3)]
        self.addCleanup(self.cleanup)
        queries = []
        for player in self.players:
            queries.extend([
                f"INSERT INTO users (secret,player_id,session_id,username,state,tags,level,wins,losses) VALUES ('{player}','{player}','{player}','TradeCancelFixture','WORLD','[]',7,2,1)",
                f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{player}','ItemSerum',3)",
                f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat,is_locked,is_trading_locked) VALUES ('{player}','{player}','Morty',42,100,'1','1')",
                f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{player}','AttackLick',0,3,5)",
                f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{player}',1,'[\"{player}\"]')",
            ])
        queries.extend([
            f"INSERT INTO trades (trade_id,player_id,morty_trade_id,is_free_trade) VALUES ('{self.trade}','{self.a}','{self.a}',1),('{self.other_trade}','{self.c}','{self.c}',0)",
            f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{self.offer}','{self.trade}','{self.b}','{self.b}'),('{self.sibling}','{self.trade}','{self.c}','{self.c}'),('{self.other_offer}','{self.other_trade}','{self.b}','{self.b}')",
        ])
        self.execute(queries)

    def cleanup(self):
        self.execute([
            f"DELETE FROM completed_trades WHERE trade_request_id IN ('{self.trade}','{self.other_trade}')",
            f"DELETE FROM trade_offers WHERE trade_id IN ('{self.trade}','{self.other_trade}')",
            f"DELETE FROM trades WHERE trade_id IN ('{self.trade}','{self.other_trade}')",
            f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.ids}')",
            *[f"DELETE FROM {table} WHERE player_id IN ('{self.ids}')" for table in ('owned_items', 'owned_morties', 'decks', 'users')],
        ])

    def snapshot(self):
        queries = {table: f"SELECT * FROM {table} WHERE player_id IN ('{self.ids}') ORDER BY id"
                   for table in ('users', 'owned_items', 'owned_morties', 'decks', 'event_queue')}
        queries.update(
            attacks=f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.ids}') ORDER BY id",
            trades=f"SELECT * FROM trades WHERE trade_id IN ('{self.trade}','{self.other_trade}') ORDER BY id",
            offers=f"SELECT * FROM trade_offers WHERE trade_id IN ('{self.trade}','{self.other_trade}') ORDER BY id",
            completed=f"SELECT * FROM completed_trades WHERE trade_request_id IN ('{self.trade}','{self.other_trade}') ORDER BY id")
        return self.execute(queries, fetch=True)

    def call(self, offer=False, actor=None, body=None, headers=None, slash=True):
        data = body if body is not None else ({'trade_offer_id': self.offer} if offer else {'trade_id': self.trade})
        request_headers = {'Content-Type': 'application/json'}
        if actor is not None:
            request_headers['Cookie'] = 'session_id=' + actor
        request_headers.update(headers or {})
        path = '/trading/cancel-trade-offer/' if offer else '/trading/cancel-trade/'
        if not slash:
            path = path.rstrip('/')
        request = urllib.request.Request('http://127.0.0.1:8087' + path,
                                         json.dumps(data).encode(), request_headers, method='POST')
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_unauthenticated_parent_cancellation_preserves_all_rows(self):
        before = self.snapshot()
        status, body = self.call()
        after = self.snapshot()
        self.assertEqual(after, before, f'Unauthenticated cancellation returned {(status, body)!r} and changed trade rows')
        self.assertEqual((status, body), (401, {'error': {'code': 'FAILED'}}))

    def assert_rejected(self, offer=False, actor=None, body=None, headers=None, status=400, code='FAILED'):
        before = self.snapshot()
        result = self.call(offer, actor, body, headers)
        self.assertEqual(result, (status, {'error': {'code': code}}))
        self.assertTrue(self.snapshot() == before, 'Rejected cancellation changed persisted rows')
        return result

    def assert_only_deleted(self, before, trade=None, offers=()):
        expected = dict(before)
        expected['trades'] = [row for row in before['trades'] if row['trade_id'] != trade]
        expected['offers'] = [row for row in before['offers'] if row['trade_offer_id'] not in offers]
        self.assertTrue(self.snapshot() == expected, 'Cancellation changed rows beyond the selected trade/offer')

    def test_parent_owner_removes_only_parent_and_children(self):
        before = self.snapshot()
        status, body = self.call(actor=self.a)
        self.assertEqual((status, body), (200, {'error': 'None'}))
        self.assert_only_deleted(before, trade=self.trade, offers=(self.offer, self.sibling))

    def test_offer_owner_removes_only_selected_offer(self):
        before = self.snapshot()
        status, body = self.call(offer=True, actor=self.b)
        self.assertEqual((status, body), (200, {'error': 'None'}))
        self.assert_only_deleted(before, offers=(self.offer,))

    def test_missing_invalid_and_foreign_sessions_cannot_cancel(self):
        for offer in (False, True):
            owner = self.b if offer else self.a
            for actor in (None, str(uuid.uuid4()), *[p for p in self.players if p != owner]):
                with self.subTest(offer=offer, actor=actor):
                    self.assert_rejected(offer=offer, actor=actor,
                                         status=401 if actor is None or actor not in self.players else 403)

    def test_body_identity_is_not_authentication(self):
        for offer in (False, True):
            body = {'trade_offer_id': self.offer} if offer else {'trade_id': self.trade}
            body.update(session_id=self.b if offer else self.a,
                        player_id=self.b if offer else self.a)
            self.assert_rejected(offer=offer, body=body, status=401)
            self.assert_rejected(offer=offer, actor=self.b if offer else self.a, body=body)

    def test_malformed_and_missing_identifiers_preserve_all_rows(self):
        for offer in (False, True):
            key = 'trade_offer_id' if offer else 'trade_id'
            actor = self.b if offer else self.a
            for value in (None, '', [], {}, True, 1, '   ', 'x' * 65):
                with self.subTest(offer=offer, value=value):
                    self.assert_rejected(offer=offer, actor=actor, body={key: value})
            self.assert_rejected(offer=offer, actor=actor, body={})
            for body in ([], 'trade', True, 1):
                self.assert_rejected(offer=offer, actor=actor, body=body)
            self.assert_rejected(offer=offer, actor=actor, body={key: str(uuid.uuid4())},
                                 status=404, code='TRADE_NO_SUCH_OFFER' if offer else 'FAILED')

    def test_ambiguous_session_and_actor_rows_fail_closed(self):
        for duplicate in ('session', 'player'):
            duplicate_player = str(uuid.uuid4()) if duplicate == 'session' else self.a
            duplicate_session = self.a if duplicate == 'session' else str(uuid.uuid4())
            sql(f"INSERT INTO users (secret,player_id,session_id) VALUES ('{duplicate_session}','{duplicate_player}','{duplicate_session}')")
            try:
                self.assert_rejected(actor=self.a, status=409)
            finally:
                sql(f"DELETE FROM users WHERE secret='{duplicate_session}' AND player_id='{duplicate_player}' AND session_id='{duplicate_session}' AND username IS NULL")

    def test_ambiguous_trade_and_offer_ids_fail_closed(self):
        sql(f"INSERT INTO trades (trade_id,player_id,morty_trade_id) VALUES ('{self.trade}','{self.c}','{self.c}')")
        self.assert_rejected(actor=self.a, status=409)
        sql(f"DELETE FROM trades WHERE trade_id='{self.trade}' AND player_id='{self.c}'")
        sql(f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{self.offer}','{self.other_trade}','{self.b}','{self.b}')")
        self.assert_rejected(offer=True, actor=self.b, status=409)

    def test_parent_delete_fault_rolls_back_child_deletions(self):
        trigger = 'trade_cancel_fault_' + uuid.uuid4().hex
        sql(f"CREATE TRIGGER {trigger} BEFORE DELETE ON trades FOR EACH ROW BEGIN IF OLD.trade_id='{self.trade}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID trade cancellation failure'; END IF; END")
        try:
            self.assert_rejected(actor=self.a, status=500)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')

    def test_offer_delete_fault_preserves_all_rows(self):
        trigger = 'offer_cancel_fault_' + uuid.uuid4().hex
        sql(f"CREATE TRIGGER {trigger} BEFORE DELETE ON trade_offers FOR EACH ROW BEGIN IF OLD.trade_offer_id='{self.offer}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID offer cancellation failure'; END IF; END")
        try:
            self.assert_rejected(offer=True, actor=self.b, status=500)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')

    def test_cancellation_replay_is_an_error_without_mutation(self):
        for offer, actor in ((True, self.b), (False, self.a)):
            with self.subTest(offer=offer):
                self.assertEqual(self.call(offer=offer, actor=actor), (200, {'error': 'None'}))
                self.assert_rejected(offer=offer, actor=actor, status=404,
                                     code='TRADE_NO_SUCH_OFFER' if offer else 'FAILED')

    def test_cookie_and_bearer_must_agree_and_malformed_bearer_fails_closed(self):
        for offer, owner, foreign in ((True, self.b, self.a), (False, self.a, self.b)):
            for authorization in ('Basic ' + owner, 'Bearer', 'Bearer ' + foreign):
                self.assert_rejected(offer=offer, actor=owner,
                                     headers={'Authorization': authorization}, status=401)
            self.assertEqual(self.call(offer=offer, actor=owner,
                                      headers={'Authorization': 'Bearer ' + owner}),
                             (200, {'error': 'None'}))

    def test_bearer_owner_can_cancel_without_cookie(self):
        before = self.snapshot()
        self.assertEqual(self.call(offer=True, headers={'Authorization': 'Bearer ' + self.b}),
                         (200, {'error': 'None'}))
        self.assert_only_deleted(before, offers=(self.offer,))

    def test_native_paths_without_slash_preserve_post_and_cookie(self):
        before = self.snapshot()
        self.assertEqual(self.call(offer=True, actor=self.b, slash=False),
                         (200, {'error': 'None'}))
        self.assert_only_deleted(before, offers=(self.offer,))
        self.assertEqual(self.call(actor=self.a, slash=False),
                         (200, {'error': 'None'}))
        self.assert_only_deleted(before, trade=self.trade, offers=(self.offer, self.sibling))

    def test_login_cookie_jar_authenticates_native_one_id_request(self):
        jar = http.cookiejar.CookieJar()
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
        request = urllib.request.Request('http://127.0.0.1:8087/user/login/',
                                         json.dumps({'secret': self.a, 'consent_identifier': 'synthetic'}).encode(),
                                         {'Content-Type': 'application/json'}, method='POST')
        with opener.open(request, timeout=10) as response:
            self.assertEqual(response.status, 200)
            self.assertIn('session_url', json.load(response))
        cookies = [cookie for cookie in jar if cookie.name == 'session_id']
        self.assertEqual(len(cookies), 1)
        cookie = cookies[0]
        self.assertFalse(cookie.domain_specified)
        self.assertEqual(cookie.path, '/trading/')
        self.assertTrue(cookie.discard)
        self.assertIsNone(cookie.expires)
        self.assertFalse(cookie.secure)  # Dedicated stack uses an HTTP public origin.
        self.assertTrue(cookie.has_nonstandard_attr('HttpOnly'))
        self.assertEqual(cookie.get_nonstandard_attr('SameSite'), 'Lax')
        self.assertTrue(cookie.value != self.a, 'Login must rotate the existing session')
        current = sql(f"SELECT session_id FROM users WHERE player_id='{self.a}'")
        self.assertTrue(cookie.value == current[0]['session_id'], 'Cookie must contain the newly persisted session')
        self.assert_rejected(actor=self.a, status=401)
        before = self.snapshot()
        request = urllib.request.Request('http://127.0.0.1:8087/trading/cancel-trade/',
                                         json.dumps({'trade_id': self.trade}).encode(),
                                         {'Content-Type': 'application/json'}, method='POST')
        with opener.open(request, timeout=10) as response:
            self.assertEqual((response.status, json.load(response)), (200, {'error': 'None'}))
        self.assert_only_deleted(before, trade=self.trade, offers=(self.offer, self.sibling))

    def test_concurrent_parent_and_offer_cancellation_preserves_unrelated_rows(self):
        before = self.snapshot()
        with ThreadPoolExecutor(max_workers=2) as pool:
            parent = pool.submit(self.call, actor=self.a)
            offer = pool.submit(self.call, offer=True, actor=self.b)
            results = [parent.result(timeout=15), offer.result(timeout=15)]
        self.assertEqual(results[0][0], 200, results)
        self.assertIn(results[1][0], (200, 404), results)
        self.assert_only_deleted(before, trade=self.trade, offers=(self.offer, self.sibling))

    def create_offer(self):
        return post('/trading/offer-morty', {'session_id': self.b, 'player_id': self.b,
                                          'offered_morty_id': self.b, 'trade_request_id': self.trade})

    def test_offer_creation_preserves_legacy_success_and_exact_parent(self):
        before = self.snapshot()
        status, body = self.create_offer()
        self.assertEqual(status, 200)
        self.assertEqual(set(body), {'error', 'offer'})
        self.assertEqual(body['error'], 'None')
        offer = body['offer']
        self.assertEqual(set(offer), {'trade_offer_id', 'trade_id', 'player_id', 'morty_offer_id',
                                    '_created', 'request_user_name', 'offering_morty_id', 'request_morty_id'})
        self.assertRegex(offer['trade_offer_id'], r'^[0-9a-f]{32}$')
        self.assertRegex(offer['_created'], r'^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{3}Z$')
        self.assertEqual({k: v for k, v in offer.items() if k not in ('trade_offer_id', '_created')},
                         {'trade_id': self.trade, 'player_id': self.b, 'morty_offer_id': self.b,
                          'request_user_name': self.a, 'offering_morty_id': 'Morty', 'request_morty_id': self.a})
        after = self.snapshot()
        added = [row for row in after['offers'] if row['trade_offer_id'] == offer['trade_offer_id']]
        self.assertEqual(len(added), 1)
        self.assertEqual({k: added[0][k] for k in ('trade_offer_id', 'trade_id', 'player_id', 'morty_offer_id')},
                         {k: offer[k] for k in ('trade_offer_id', 'trade_id', 'player_id', 'morty_offer_id')})
        after['offers'] = [row for row in after['offers'] if row['trade_offer_id'] != offer['trade_offer_id']]
        self.assertTrue(after == before, 'Offer creation must preserve its parent and gameplay rows')

    def test_concurrent_offer_creation_and_parent_cancellation_leave_no_orphans(self):
        before = self.snapshot()
        with ThreadPoolExecutor(max_workers=2) as pool:
            creator = pool.submit(self.create_offer)
            cancellation = pool.submit(self.call, actor=self.a)
            created, cancelled = creator.result(timeout=15), cancellation.result(timeout=15)
        self.assertEqual(cancelled, (200, {'error': 'None'}))
        if created[0] == 200:
            self.assertEqual(created[1]['error'], 'None')
            self.assertEqual(sql(f"SELECT id FROM trade_offers WHERE trade_offer_id='{created[1]['offer']['trade_offer_id']}'"), [])
        else:
            self.assertEqual(created, (404, {'error': 'TRADE_NOT_FOUND'}))
        self.assert_only_deleted(before, trade=self.trade, offers=(self.offer, self.sibling))
        self.assertEqual(self.create_offer(), (404, {'error': 'TRADE_NOT_FOUND'}))
        self.assert_only_deleted(before, trade=self.trade, offers=(self.offer, self.sibling))

    def test_get_cannot_cancel_either_listing(self):
        before = self.snapshot()
        for path in ('/trading/cancel-trade/', '/trading/cancel-trade-offer/'):
            request = urllib.request.Request('http://127.0.0.1:8087' + path,
                                             headers={'Cookie': 'session_id=' + self.a})
            with self.assertRaises(urllib.error.HTTPError) as rejected:
                urllib.request.urlopen(request, timeout=10)
            with rejected.exception as response:
                self.assertEqual((response.status, json.load(response)), (405, {'error': {'code': 'FAILED'}}))
        self.assertTrue(self.snapshot() == before, 'GET requests must leave both listings intact')


if __name__ == '__main__':
    unittest.main()

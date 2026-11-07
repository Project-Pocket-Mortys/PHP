"""Offer response authorization with additive UUID fixtures; never reseed accounts."""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import time
import unittest
import urllib.error
import urllib.request
import uuid

from test_http import COMPOSE, ROOT, php, sql


class TradeResponseAuthorizationTests(unittest.TestCase):
    def execute(self, queries, fetch=False):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                "$queries=json_decode(base64_decode('" + encoded + "'),true); ")
        if fetch:
            code += "$out=[]; foreach($queries as $key=>$q) $out[$key]=$pdo->query($q)->fetchAll(); echo json_encode($out);"
            return json.loads(php(code))
        php(code + "$pdo->beginTransaction(); foreach($queries as $q) $pdo->exec($q); $pdo->commit();")

    def setUp(self):
        self.players = [str(uuid.uuid4()) for _ in range(4)]
        self.a, self.b, self.c, self.d = self.players
        self.ids = "','".join(self.players)
        self.parties = {player: str(uuid.uuid4()) for player in self.players}
        self.trade, self.other_trade = [str(uuid.uuid4()) for _ in range(2)]
        self.offer, self.sibling, self.other_offer = [str(uuid.uuid4()) for _ in range(3)]
        self.addCleanup(self.cleanup)
        queries = []
        for player in self.players:
            queries.extend([
                f"INSERT INTO users (secret,player_id,session_id,username,state,active_deck_id,tags,level,wins,losses) VALUES ('{player}','{player}','{player}','TradeResponseFixture','WORLD',1,'[]',7,2,1)",
                f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{player}','ItemSerum',3)",
                f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat,is_locked,is_trading_locked) VALUES ('{player}','{player}','Morty',42,100,'1','1')",
                f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{player}','AttackLick',0,3,5)",
                f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat) VALUES ('{self.parties[player]}','{player}','Morty',100,100)",
                f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{player}',1,'[\"{self.parties[player]}\"]')",
            ])
        queries.extend([
            f"INSERT INTO trades (trade_id,player_id,morty_trade_id,is_free_trade) VALUES ('{self.trade}','{self.a}','{self.a}',1),('{self.other_trade}','{self.c}','{self.c}',0)",
            f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{self.offer}','{self.trade}','{self.b}','{self.b}'),('{self.sibling}','{self.trade}','{self.d}','{self.d}'),('{self.other_offer}','{self.other_trade}','{self.d}','{self.d}')",
        ])
        self.execute(queries)

    def cleanup(self):
        self.execute([
            f"DELETE FROM completed_trades WHERE trade_request_id IN ('{self.trade}','{self.other_trade}') OR trade_offer_id IN ('{self.offer}','{self.sibling}','{self.other_offer}')",
            f"DELETE FROM trade_offers WHERE trade_id IN ('{self.trade}','{self.other_trade}') OR trade_offer_id IN ('{self.offer}','{self.sibling}','{self.other_offer}')",
            f"DELETE FROM trades WHERE trade_id IN ('{self.trade}','{self.other_trade}')",
            f"DELETE FROM friend_battle_memberships WHERE player_id IN ('{self.ids}')",
            f"DELETE FROM event_queue WHERE player_id IN ('{self.ids}') OR only_show_to_player_id IN ('{self.ids}')",
            f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.ids}')",
            *[f"DELETE FROM {table} WHERE player_id IN ('{self.ids}')" for table in ('trade_refresh_notifications', 'owned_items', 'owned_morties', 'decks', 'users')],
        ])

    def snapshot(self):
        queries = {table: f"SELECT * FROM {table} WHERE player_id IN ('{self.ids}') ORDER BY id"
                   for table in ('users', 'owned_items', 'owned_morties', 'decks', 'event_queue')}
        queries.update(
            attacks=f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.ids}') ORDER BY id",
            trades=f"SELECT * FROM trades WHERE trade_id IN ('{self.trade}','{self.other_trade}') ORDER BY id",
            offers=f"SELECT * FROM trade_offers WHERE trade_id IN ('{self.trade}','{self.other_trade}') OR trade_offer_id IN ('{self.offer}','{self.sibling}','{self.other_offer}') ORDER BY id",
            completed=f"SELECT * FROM completed_trades WHERE trade_request_id IN ('{self.trade}','{self.other_trade}') OR trade_offer_id IN ('{self.offer}','{self.sibling}','{self.other_offer}') ORDER BY id",
            claims=f"SELECT * FROM friend_battle_memberships WHERE player_id IN ('{self.ids}') ORDER BY player_id")
        return self.execute(queries, fetch=True)

    def body(self, accepted=True, **changes):
        body = dict(trade_request_id=self.trade, trade_offer_id=self.offer,
                    request_accepted=accepted)
        body.update(changes)
        return body

    def call(self, actor=None, body=None, headers=None, accepted=True):
        request_headers = {'Content-Type': 'application/json'}
        if actor is not None:
            request_headers['Cookie'] = 'session_id=' + actor
        request_headers.update(headers or {})
        request = urllib.request.Request('http://127.0.0.1:8087/trading/offer-response/',
                                         json.dumps(self.body(accepted) if body is None else body).encode(),
                                         request_headers, method='POST')
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def assert_rejected(self, status, code='FAILED', **request):
        before = self.snapshot()
        result = self.call(**request)
        self.assertEqual(self.snapshot(), before, f'Rejected response {result!r} changed persisted rows')
        self.assertEqual(result, (status, {'error': {'code': code}}))

    def test_missing_and_invalid_authentication_cannot_accept_or_reject(self):
        for accepted in (True, False):
            for actor in (None, str(uuid.uuid4()), ''):
                with self.subTest(accepted=accepted, actor=actor):
                    self.assert_rejected(401, actor=actor, accepted=accepted)

    def test_only_request_owner_can_accept_or_reject(self):
        for accepted in (True, False):
            for actor in (self.b, self.c, self.d):
                with self.subTest(accepted=accepted, actor=actor):
                    self.assert_rejected(403, actor=actor, accepted=accepted)

    def test_body_identity_cannot_replace_transport_authentication(self):
        for key in ('session_id', 'player_id'):
            self.assert_rejected(401, body=self.body(**{key: self.a}))
            self.assert_rejected(403, actor=self.b, body=self.body(**{key: self.a}))

    def test_conflicting_and_malformed_bearer_fails_closed(self):
        for authorization in ('Basic ' + self.a, 'Bearer', 'Bearer ' + self.b,
                              'Bearer ' + self.a + ', ' + self.b):
            with self.subTest(authorization=authorization):
                self.assert_rejected(401, actor=self.a, headers={'Authorization': authorization})

    def test_body_identity_does_not_override_authenticated_requester_on_decline(self):
        before = self.snapshot()
        self.assertEqual(self.call(actor=self.a,
                                   body=self.body(False, session_id=self.b, player_id=self.b)),
                         (200, [None, None]))
        before['offers'] = [r for r in before['offers'] if r['trade_offer_id'] != self.offer]
        self.assertEqual(self.snapshot(), before)

    def test_rejection_with_matching_cookie_and_bearer_preserves_other_rows(self):
        before = self.snapshot()
        self.assertEqual(self.call(actor=self.a, accepted=False,
                                   headers={'Authorization': 'Bearer ' + self.a}), (200, [None, None]))
        before['offers'] = [r for r in before['offers'] if r['trade_offer_id'] != self.offer]
        self.assertEqual(self.snapshot(), before)
        self.assert_rejected(404, 'TRADE_NO_OFFER_EXISTS', actor=self.a, accepted=False)

    def test_mismatched_parent_and_child_are_noops_for_both_actions(self):
        for accepted in (True, False):
            with self.subTest(accepted=accepted):
                self.assert_rejected(409, actor=self.a,
                                     body=self.body(accepted, trade_offer_id=self.other_offer))

    def test_request_accepted_requires_an_explicit_json_boolean(self):
        for value in (None, 0, 1, '', 'false', 'true', [], {}, [False]):
            with self.subTest(value=value):
                self.assert_rejected(400, actor=self.a, body=self.body(value))
        body = self.body()
        del body['request_accepted']
        self.assert_rejected(400, actor=self.a, body=body)

    def test_identifiers_and_body_require_valid_native_shapes(self):
        for key in ('trade_request_id', 'trade_offer_id'):
            for value in (None, '', '   ', [], {}, True, 1, 'x' * 65):
                with self.subTest(key=key, value=value):
                    self.assert_rejected(400, actor=self.a, body=self.body(**{key: value}))
            body = self.body()
            del body[key]
            self.assert_rejected(400, actor=self.a, body=body)
        for body in ([], 'trade', True, 1):
            self.assert_rejected(400, actor=self.a, body=body)

    def test_unknown_identifiers_use_native_errors(self):
        self.assert_rejected(404, 'TRADE_NO_TRADE_EXISTS', actor=self.a,
                             body=self.body(trade_request_id=str(uuid.uuid4())))
        self.assert_rejected(404, 'TRADE_NO_OFFER_EXISTS', actor=self.a,
                             body=self.body(trade_offer_id=str(uuid.uuid4())))

    def test_session_and_player_case_aliases_do_not_authorize(self):
        self.assert_rejected(409, actor=self.a.upper())
        sql(f"UPDATE users SET player_id='{self.a.upper()}' WHERE secret='{self.a}'")
        self.assert_rejected(409, actor=self.a)

    def test_ambiguous_session_or_actor_rows_fail_closed(self):
        for duplicate in ('session', 'player'):
            secret = str(uuid.uuid4())
            player = self.c if duplicate == 'session' else self.a.upper()
            session = self.a.upper() if duplicate == 'session' else secret
            sql(f"INSERT INTO users (secret,player_id,session_id) VALUES ('{secret}','{player}','{session}')")
            try:
                self.assert_rejected(409, actor=self.a)
            finally:
                sql(f"DELETE FROM users WHERE secret='{secret}'")

    def test_trade_and_offer_case_alias_requests_fail_closed(self):
        for key, value in (('trade_request_id', self.trade), ('trade_offer_id', self.offer)):
            with self.subTest(key=key):
                self.assert_rejected(409, actor=self.a, body=self.body(**{key: value.upper()}))

    def test_ambiguous_parent_child_and_morty_logical_rows_fail_closed(self):
        queries = [
            (f"INSERT INTO trades (trade_id,player_id,morty_trade_id) VALUES ('{self.trade.upper()}','{self.c}','{self.c}')",
             f"DELETE FROM trades WHERE trade_id='{self.trade}' AND player_id='{self.c}'"),
            (f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{self.offer.upper()}','{self.other_trade}','{self.d}','{self.d}')",
             f"DELETE FROM trade_offers WHERE trade_offer_id='{self.offer}' AND trade_id='{self.other_trade}'"),
            (f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id) VALUES ('{self.a.upper()}','{self.c}','Morty')",
             f"DELETE FROM owned_morties WHERE owned_morty_id='{self.a}' AND player_id='{self.c}'"),
        ]
        for insert, delete in queries:
            sql(insert)
            try:
                for accepted in (True, False):
                    self.assert_rejected(409, actor=self.a, accepted=accepted)
            finally:
                sql(delete)

    def test_reserved_declared_and_actual_owners_block_both_actions(self):
        self.execute([
            f"UPDATE owned_morties SET player_id='{self.c}' WHERE owned_morty_id='{self.a}'",
            f"UPDATE owned_morties SET player_id='{self.d}' WHERE owned_morty_id='{self.b}'",
        ])
        claim = str(uuid.uuid4())
        for player in self.players:
            sql(f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{player}','{claim}')")
            try:
                for accepted in (True, False):
                    self.assert_rejected(409, actor=self.a, accepted=accepted)
            finally:
                sql(f"DELETE FROM friend_battle_memberships WHERE player_id='{player}' AND battle_id='{claim}'")

    def test_authenticated_accept_swaps_exact_owners_completes_and_cleans_children_once(self):
        before = self.snapshot()
        self.assertEqual(self.call(headers={'Authorization': 'Bearer ' + self.a}), (200, [None, None]))
        after = self.snapshot()
        completed = after['completed']
        self.assertEqual(len(completed), 1)
        row = completed[0]
        self.assertRegex(row['completed_trade_id'], r'^[0-9a-f]{32}$')
        self.assertTrue(row['fulfilled_at'])
        self.assertEqual({key: row[key] for key in ('request_player_id', 'offer_player_id',
                         'morty_request_id', 'morty_offer_id', 'trade_request_id', 'trade_offer_id', 'is_free_trade')},
                         dict(request_player_id=self.a, offer_player_id=self.b,
                              morty_request_id=self.a, morty_offer_id=self.b,
                              trade_request_id=self.trade, trade_offer_id=self.offer,
                              is_free_trade=before['trades'][0]['is_free_trade']))
        expected = dict(before)
        expected['completed'] = completed
        expected['trades'] = [r for r in before['trades'] if r['trade_id'] != self.trade]
        expected['offers'] = [r for r in before['offers'] if r['trade_id'] != self.trade]
        expected['owned_morties'] = [dict(r, player_id=self.b if r['owned_morty_id'] == self.a else self.a)
                                    if r['owned_morty_id'] in (self.a, self.b) else r
                                    for r in before['owned_morties']]
        self.assertEqual(after, expected)
        self.assert_rejected(404, 'TRADE_NO_TRADE_EXISTS', actor=self.a)

    def test_duplicate_accept_completes_and_transfers_once(self):
        before = self.snapshot()
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(self.call, actor=self.a) for _ in range(2)]
            results = [request.result(timeout=15) for request in pending]
        self.assertEqual(sum(result == (200, [None, None]) for result in results), 1, results)
        loser = next(result for result in results if result != (200, [None, None]))
        self.assertIn(loser, ((404, {'error': {'code': 'TRADE_NO_TRADE_EXISTS'}}),
                              (409, {'error': {'code': 'FAILED'}})), results)
        after = self.snapshot()
        self.assertEqual(len(after['completed']), 1)
        self.assertEqual([r for r in after['trades'] if r['trade_id'] == self.trade], [])
        self.assertEqual([r for r in after['offers'] if r['trade_id'] == self.trade], [])
        expected = dict(before)
        expected['completed'] = after['completed']
        expected['trades'] = [r for r in before['trades'] if r['trade_id'] != self.trade]
        expected['offers'] = [r for r in before['offers'] if r['trade_id'] != self.trade]
        expected['owned_morties'] = [dict(r, player_id=self.b if r['owned_morty_id'] == self.a else self.a)
                                    if r['owned_morty_id'] in (self.a, self.b) else r
                                    for r in before['owned_morties']]
        self.assertEqual(after, expected)
        self.assert_rejected(404, 'TRADE_NO_TRADE_EXISTS', actor=self.a)

    def test_completion_insert_fault_rolls_back_every_change(self):
        trigger = 'trade_response_fault_' + uuid.uuid4().hex
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON completed_trades FOR EACH ROW BEGIN IF NEW.trade_request_id='{self.trade}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID response completion failure'; END IF; END")
        try:
            self.assert_rejected(500, actor=self.a)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')

    def test_sibling_parent_case_alias_blocks_acceptance_without_mutation(self):
        sql(f"UPDATE trade_offers SET trade_id='{self.trade.upper()}' WHERE trade_offer_id='{self.sibling}'")
        self.assert_rejected(409, actor=self.a)

    def test_stale_actual_owner_on_either_side_blocks_acceptance(self):
        for morty, owner in ((self.a, self.a), (self.b, self.b)):
            with self.subTest(morty=morty):
                sql(f"UPDATE owned_morties SET player_id='{self.c}' WHERE owned_morty_id='{morty}'")
                try:
                    self.assert_rejected(409, actor=self.a)
                finally:
                    sql(f"UPDATE owned_morties SET player_id='{owner}' WHERE owned_morty_id='{morty}'")

    def test_parent_delete_fault_rolls_back_transfer_completion_and_child_deletions(self):
        trigger = 'trade_response_delete_fault_' + uuid.uuid4().hex
        sql(f"CREATE TRIGGER {trigger} BEFORE DELETE ON trades FOR EACH ROW BEGIN IF OLD.trade_id='{self.trade}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID response late deletion failure'; END IF; END")
        try:
            self.assert_rejected(500, actor=self.a)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')

    def test_session_rotated_while_waiting_cannot_authorize_transfer(self):
        session = str(uuid.uuid4())
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
                "$pdo->beginTransaction();"
                f"$pdo->query(\"SELECT id FROM users WHERE player_id='{self.a}' FOR UPDATE\")->fetchAll();"
                "echo \"locked\\n\"; flush(); fgets(STDIN);"
                f"$pdo->exec(\"UPDATE users SET session_id='{session}' WHERE player_id='{self.a}'\");"
                "$pdo->commit(); echo \"committed\\n\";")
        blocker = subprocess.Popen(COMPOSE + ['exec', '-T', 'web', 'php', '-r', code],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, text=True, cwd=ROOT)
        before = self.snapshot()
        try:
            self.assertEqual(blocker.stdout.readline().strip(), 'locked')
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(self.call, actor=self.a)
                try:
                    time.sleep(0.5)
                    self.assertFalse(pending.done(), 'Response did not wait for the requesting user lock')
                finally:
                    blocker.stdin.write('release\n')
                    blocker.stdin.flush()
                self.assertEqual(pending.result(timeout=15), (401, {'error': {'code': 'FAILED'}}))
            self.assertEqual(blocker.wait(timeout=10), 0, blocker.stderr.read())
            # Ignore only the deliberate credential rotation and its timestamp.
            after = self.snapshot()
            before['users'] = [dict(r, session_id=session,
                                    last_seen=next(a['last_seen'] for a in after['users'] if a['id'] == r['id']))
                               if r['player_id'] == self.a else r for r in before['users']]
            self.assertEqual(after, before)
        finally:
            if blocker.poll() is None:
                blocker.kill()
                blocker.wait(timeout=10)
            for stream in (blocker.stdin, blocker.stdout, blocker.stderr):
                stream.close()


if __name__ == '__main__':
    unittest.main()

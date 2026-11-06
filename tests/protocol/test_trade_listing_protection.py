"""Native listing eligibility with additive UUID fixtures; never reseed accounts.

Request and offer creation share the native active-deck and lock exclusions.
Only test_http's transport/SQL helpers are reused; no other TestCase is invoked.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import subprocess
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid

from test_http import COMPOSE, ROOT, php, post, sql


class TradeListingProtectionTests(unittest.TestCase):
    def execute(self, queries, fetch=False):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
                "$queries=json_decode(base64_decode('" + encoded + "'),true);$pdo->beginTransaction();")
        if fetch:
            return json.loads(php(code + "$out=[];foreach($queries as $k=>$q)$out[$k]=$pdo->query($q)->fetchAll();$pdo->rollBack();echo json_encode($out);"))
        php(code + "foreach($queries as $q)$pdo->exec($q);$pdo->commit();")

    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.a, self.b, self.c = [str(uuid.uuid4()) for _ in range(3)]
        self.players = "','".join((self.a, self.b, self.c))
        self.spare, self.party, self.requested, self.other_party = [str(uuid.uuid4()) for _ in range(4)]
        self.morties = "','".join((self.spare, self.party, self.requested, self.other_party))
        self.trade, self.reference, self.offer_id, self.battle = [str(uuid.uuid4()) for _ in range(4)]
        self.addCleanup(self.cleanup)
        queries = []
        for player in (self.a, self.b, self.c):
            queries.extend([
                f"INSERT INTO users (secret,player_id,session_id,username,state,active_deck_id,tags,coupons,coins,permits) VALUES ('{player}','{player}','{player}','ListingFixture','WORLD',7,'[]',9,21,3)",
                f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{player}','ItemSerum',2)",
            ])
        for player, morty in ((self.a, self.spare), (self.a, self.party),
                              (self.b, self.requested), (self.b, self.other_party)):
            queries.extend([
                f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,level,xp,hp,hp_stat,attack_stat,defence_stat,speed_stat,variant,is_locked,is_trading_locked,fight_pit_id,evolution_points,xp_lower,xp_upper) VALUES ('{player}','{morty}','MortyDefault',5,125,20,20,11,10,10,'Normal','false','false','null',0,125,216)",
                f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{morty}','AttackOutburst',0,12,12)",
            ])
        queries.extend([
            f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{self.a}',7,'[\"{self.party}\"]'),('{self.a}',8,'[\"{self.spare}\"]'),('{self.b}',7,'[\"{self.other_party}\"]')",
            f"INSERT INTO friend_list (player_id_a,player_id_b,pending,direction,created,modified) VALUES ('{self.a}','{self.b}','false','true',NOW(),NOW())",
            f"INSERT INTO trades (trade_id,player_id,morty_trade_id,requested_morty_id,request_variant,is_free_trade) VALUES ('{self.trade}','{self.b}','{self.requested}','any','Normal',1)",
        ])
        self.execute(queries)

    def cleanup(self):
        self.execute([
            f"DELETE FROM completed_trades WHERE request_player_id IN ('{self.players}') OR offer_player_id IN ('{self.players}')",
            f"DELETE FROM trade_offers WHERE player_id IN ('{self.players}') OR morty_offer_id IN ('{self.morties}')",
            f"DELETE FROM trades WHERE player_id IN ('{self.players}') OR morty_trade_id IN ('{self.morties}')",
            f"DELETE FROM friend_list WHERE player_id_a IN ('{self.players}') OR player_id_b IN ('{self.players}')",
            f"DELETE FROM friend_battle_memberships WHERE player_id IN ('{self.players}')",
            f"DELETE FROM battles WHERE player_id IN ('{self.players}') OR opponent_id IN ('{self.players}')",
            f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.morties}')",
            *[f"DELETE FROM {table} WHERE player_id IN ('{self.players}')" for table in
              ('event_queue', 'owned_items', 'decks', 'owned_morties', 'users')],
        ])

    def snapshot(self):
        queries = {table: f"SELECT * FROM {table} WHERE player_id IN ('{self.players}') ORDER BY id"
                   for table in ('users', 'owned_morties', 'owned_items', 'decks', 'trades', 'trade_offers', 'event_queue')}
        queries.update(
            attacks=f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.morties}') ORDER BY id",
            friends=f"SELECT * FROM friend_list WHERE player_id_a IN ('{self.players}') OR player_id_b IN ('{self.players}') ORDER BY id",
            completed=f"SELECT * FROM completed_trades WHERE request_player_id IN ('{self.players}') OR offer_player_id IN ('{self.players}') ORDER BY id",
            claims=f"SELECT * FROM friend_battle_memberships WHERE player_id IN ('{self.players}') ORDER BY player_id",
            battles=f"SELECT * FROM battles WHERE player_id IN ('{self.players}') OR opponent_id IN ('{self.players}') ORDER BY battle_id",
        )
        return self.execute(queries, fetch=True)

    def body(self, offer=False, **overrides):
        body = dict(session_id=self.a, player_id=self.a)
        body.update(dict(offered_morty_id=self.spare, trade_request_id=self.trade) if offer else
                    dict(owned_morty_id=self.spare, requested_morty_id='any', request_variant='Normal', is_free_trade=True))
        body.update(overrides)
        return body

    def call(self, offer=False, **overrides):
        return post('/trading/' + ('offer-morty' if offer else 'request-morty'), self.body(offer, **overrides))

    def blocked(self, offer=False, code=None, status=409, **overrides):
        before = self.snapshot()
        response = self.call(offer, **overrides)
        self.assertEqual(response, (status, {'error': {'code': code or ('FAILED' if offer else 'TRADE_MORTY_LOCKED')}}))
        self.assertEqual(self.snapshot(), before, 'Rejected creation must be a complete no-op')

    def test_active_party_is_blocked_for_requests_and_offers(self):
        self.blocked(owned_morty_id=self.party)
        self.blocked(True, offered_morty_id=self.party)

    def test_manual_and_trading_lock_legacy_flags_block_both(self):
        for field in ('is_locked', 'is_trading_locked'):
            for flag in ('true', '1'):
                with self.subTest(field=field, flag=flag):
                    sql(f"UPDATE owned_morties SET {field}='{flag}' WHERE owned_morty_id='{self.spare}'")
                    self.blocked()
                    self.blocked(True)
            sql(f"UPDATE owned_morties SET {field}='false' WHERE owned_morty_id='{self.spare}'")

    def test_durable_requests_and_orphan_offers_block_both_even_with_stale_owner(self):
        for table in ('trades', 'trade_offers'):
            for owner in (self.a, self.c):
                with self.subTest(table=table, owner=owner):
                    if table == 'trades':
                        query = f"INSERT INTO trades (trade_id,player_id,morty_trade_id,requested_morty_id,request_variant) VALUES ('{self.reference}','{owner}','{self.spare}','any','Normal')"
                    else:
                        # Deliberately orphaned: eligibility must not join away this reference.
                        query = f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{self.offer_id}','{self.reference}','{owner}','{self.spare}')"
                    sql(query)
                    self.blocked()
                    self.blocked(True)
                    sql(f"DELETE FROM {table} WHERE player_id='{owner}' AND " + (f"trade_id='{self.reference}'" if table == 'trades' else f"trade_offer_id='{self.offer_id}'"))

    def test_foreign_owned_morty_uses_native_ownership_errors(self):
        self.blocked(code='TRADE_REQUEST_MORTY_DOES_NOT_BELONG_TO_PLAYER', status=403, owned_morty_id=self.requested)
        self.blocked(True, code='TRADE_OFFER_MORTY_DOES_NOT_BELONG_TO_OFFERING_PLAYER', status=403, offered_morty_id=self.requested)

    def test_missing_parent_and_missing_offered_morty_use_native_errors(self):
        self.blocked(True, code='TRADE_NO_TRADE_EXISTS', status=404, trade_request_id=str(uuid.uuid4()))
        self.blocked(True, code='TRADE_NO_SUCH_MORTY', status=404, offered_morty_id=str(uuid.uuid4()))

    def test_specific_species_and_variant_must_both_match(self):
        for species, variant in (('MortyScruffy', 'Normal'), ('MortyDefault', 'Shiny')):
            with self.subTest(species=species, variant=variant):
                sql(f"UPDATE trades SET requested_morty_id='{species}',request_variant='{variant}' WHERE trade_id='{self.trade}'")
                self.blocked(True, code='TRADE_MORTY_NOT_MATCH_CRITERIA')

    def test_ambiguous_global_owned_instance_fails_without_writes(self):
        sql(f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id) VALUES ('{self.c}','{self.spare}','MortyDefault')")
        self.blocked(code='FAILED')
        self.blocked(True)

    def test_duplicate_authenticated_player_is_rejected(self):
        other_session = str(uuid.uuid4())
        sql(f"INSERT INTO users (secret,player_id,session_id) VALUES ('{other_session}','{self.a}','{other_session}')")
        self.blocked(code='FAILED')
        self.blocked(True)

    def test_duplicate_session_is_rejected(self):
        sql(f"UPDATE users SET session_id='{self.a}' WHERE player_id='{self.c}'")
        self.blocked(code='FAILED')
        self.blocked(True)

    def test_spoofed_player_and_case_aliases_are_rejected(self):
        for offer in (False, True):
            for fields, status in (({'player_id': self.b}, 403), ({'player_id': self.a.upper()}, 403),
                                   ({'session_id': self.a.upper()}, 409), ({'session_id': str(uuid.uuid4())}, 401)):
                with self.subTest(offer=offer, fields=fields):
                    self.blocked(offer, code='FAILED', status=status, **fields)

    def test_morty_and_parent_case_aliases_do_not_resolve(self):
        self.blocked(code='FAILED', owned_morty_id=self.spare.upper())
        self.blocked(True, offered_morty_id=self.spare.upper())
        self.blocked(True, trade_request_id=self.trade.upper())

    def test_duplicate_parent_trade_identifier_is_rejected(self):
        sql(f"INSERT INTO trades (trade_id,player_id,morty_trade_id,requested_morty_id,request_variant) VALUES ('{self.trade}','{self.c}','{self.party}','any','Normal')")
        self.blocked(True)

    def test_missing_ambiguous_and_malformed_active_decks_fail_closed(self):
        sql(f"DELETE FROM decks WHERE player_id='{self.a}' AND deck_id=7")
        self.blocked(code='FAILED')
        self.blocked(True)
        sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{self.a}',7,'[]'),('{self.a}',7,'[]')")
        self.blocked(code='FAILED')
        self.blocked(True)
        sql(f"DELETE FROM decks WHERE player_id='{self.a}' AND deck_id=7")
        sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{self.a}',7,'[]')")
        for malformed in ('{}', '[7]', '[null]', '[\"' + self.party + '\",{}]'):
            with self.subTest(deck=malformed):
                sql(f"UPDATE decks SET owned_morty_ids='{malformed}' WHERE player_id='{self.a}' AND deck_id=7")
                self.blocked(code='FAILED')
                self.blocked(True)

    def test_invalid_typed_fields_are_clean_native_errors_and_noops(self):
        for offer in (False, True):
            body = self.body(offer)
            for field in body:
                for invalid in (None, [], {}, 7):
                    with self.subTest(offer=offer, field=field, value=invalid):
                        before = self.snapshot()
                        status, response = self.call(offer, **{field: invalid})
                        self.assertIn(status, (400, 401))
                        self.assertEqual(response, {'error': {'code': 'FAILED'}})
                        self.assertEqual(self.snapshot(), before)

    def test_non_object_json_bodies_are_rejected_without_writes(self):
        for endpoint in ('request-morty', 'offer-morty'):
            for body in (None, [], 'invalid', 1, True):
                with self.subTest(endpoint=endpoint, body=body):
                    before = self.snapshot()
                    self.assertEqual(post('/trading/' + endpoint, body), (400, {'error': {'code': 'FAILED'}}))
                    self.assertEqual(self.snapshot(), before)

    def test_get_with_valid_creation_body_cannot_write(self):
        for offer in (False, True):
            with self.subTest(offer=offer):
                before = self.snapshot()
                request = urllib.request.Request(
                    'http://127.0.0.1:8087/trading/' + ('offer-morty' if offer else 'request-morty') + '/',
                    json.dumps(self.body(offer)).encode(), {'Content-Type': 'application/json'}, method='GET')
                try:
                    response = urllib.request.urlopen(request, timeout=10)
                except urllib.error.HTTPError as error:
                    response = error
                with response:
                    self.assertEqual((response.status, json.load(response)), (405, {'error': {'code': 'FAILED'}}))
                self.assertEqual(self.snapshot(), before)

    def test_offer_requires_each_native_body_field(self):
        for field in self.body(True):
            with self.subTest(field=field):
                body = self.body(True)
                del body[field]
                before = self.snapshot()
                status, response = post('/trading/offer-morty', body)
                self.assertIn(status, (400, 401))
                self.assertEqual(response, {'error': {'code': 'FAILED'}})
                self.assertEqual(self.snapshot(), before)

    def test_shared_battle_claims_block_both_listings(self):
        sql(f"INSERT INTO friend_battle_memberships (player_id,battle_id) VALUES ('{self.a}','{self.battle}')")
        self.blocked(code='FAILED')
        self.blocked(True)

    def assert_success_writes(self, offer=False, free=True, payload=None):
        before = self.snapshot()
        status, body = (post('/trading/request-morty', payload) if payload is not None else
                        self.call(offer, **({} if offer else {'is_free_trade': free})))
        self.assertEqual(status, 200, body)
        self.assertEqual(body['error'], 'None')
        after = self.snapshot()
        table, key = ('trade_offers', 'offer') if offer else ('trades', 'trade')
        record = body[key]
        identity = 'trade_offer_id' if offer else 'trade_id'
        added = [row for row in after[table] if row[identity] == record[identity]]
        self.assertEqual(len(added), 1)
        self.assertEqual(record['player_id'], self.a)
        self.assertEqual(record['morty_offer_id' if offer else 'morty_trade_id'], self.spare)
        after[table].remove(added[0])
        if offer:
            self.assertEqual(record['trade_id'], self.trade)
            self.assertEqual(record['offering_morty_id'], 'MortyDefault')
            self.assertEqual(record['request_morty_id'], 'MortyDefault')
            self.assertEqual(record['request_user_name'], 'ListingFixture')
        else:
            self.assertEqual(record['morty_request'], 'any')
            self.assertEqual(record['request_variant'], 'Normal')
            self.assertIs(record['is_free_trade'], free)
            self.assertEqual(body['coupons'], 9 if free else 8)
            expected_actor = next(row for row in before['users'] if row['player_id'] == self.a)
            actual_actor = next(row for row in after['users'] if row['player_id'] == self.a)
            if free:
                expiry = actual_actor['expiry_trade']
                self.assertGreater(datetime.fromisoformat(expiry.replace('Z', '+00:00')), datetime.now(timezone.utc))
                expected_actor['expiry_trade'] = expiry
            else:
                expected_actor['coupons'] = int(expected_actor['coupons']) - 1
            # Both request updates invoke the schema's automatic timestamp.
            expected_actor['last_seen'] = actual_actor['last_seen']
        self.assertEqual(after, before, 'Creation must only insert its listing and apply the existing request cost/cooldown')
        return body

    def test_inactive_deck_spare_can_create_free_request_with_existing_wire_and_cooldown(self):
        self.assert_success_writes()

    def test_inactive_deck_spare_can_create_paid_request_with_existing_coupon_cost(self):
        self.assert_success_writes(free=False)

    def test_inactive_deck_spare_can_create_offer_without_resource_writes(self):
        self.assert_success_writes(True)

    def test_any_species_bypasses_variant_restriction(self):
        sql(f"UPDATE trades SET request_variant='Shiny' WHERE trade_id='{self.trade}'")
        self.assert_success_writes(True)

    def test_specific_species_variant_matrix_requires_exact_equality(self):
        for requested in ('Normal', 'Shiny', 'Pulsing'):
            sql(f"UPDATE trades SET requested_morty_id='MortyDefault',request_variant='{requested}' WHERE trade_id='{self.trade}'")
            for offered in ('Normal', 'Shiny', 'Pulsing'):
                with self.subTest(requested=requested, offered=offered):
                    sql(f"UPDATE owned_morties SET variant='{offered}' WHERE owned_morty_id='{self.spare}'")
                    if offered == requested:
                        body = self.assert_success_writes(True)
                        sql(f"DELETE FROM trade_offers WHERE trade_offer_id='{body['offer']['trade_offer_id']}'")
                    else:
                        self.blocked(True, code='TRADE_MORTY_NOT_MATCH_CRITERIA')

    def test_numeric_false_legacy_lock_flags_remain_eligible(self):
        sql(f"UPDATE owned_morties SET is_locked='0',is_trading_locked='0' WHERE owned_morty_id='{self.spare}'")
        self.assert_success_writes(True)

    def test_legacy_request_omissions_keep_defaults_and_authenticated_owner(self):
        self.assert_success_writes(free=False, payload={'session_id': self.a, 'owned_morty_id': self.spare})

    def test_concurrent_request_and_offer_can_reserve_spare_only_once(self):
        barrier = threading.Barrier(2)
        def create(offer):
            barrier.wait(timeout=10)
            return self.call(offer)
        before = self.snapshot()
        with ThreadPoolExecutor(max_workers=2) as pool:
            pending = [pool.submit(create, offer) for offer in (False, True)]
            results = [future.result(timeout=20) for future in pending]
        self.assertEqual(sum(status == 200 for status, _ in results), 1, results)
        for offer, (status, body) in zip((False, True), results):
            if status != 200:
                self.assertEqual((status, body), (409, {'error': {'code': 'FAILED' if offer else 'TRADE_MORTY_LOCKED'}}))
        after = self.snapshot()
        requests = [r for r in after['trades'] if r['morty_trade_id'] == self.spare]
        offers = [r for r in after['trade_offers'] if r['morty_offer_id'] == self.spare]
        self.assertEqual(len(requests) + len(offers), 1)
        expected_actor = next(row for row in before['users'] if row['player_id'] == self.a)
        actual_actor = next(row for row in after['users'] if row['player_id'] == self.a)
        if requests:
            self.assertGreater(datetime.fromisoformat(actual_actor['expiry_trade'].replace('Z', '+00:00')), datetime.now(timezone.utc))
            expected_actor['expiry_trade'] = actual_actor['expiry_trade']
            expected_actor['last_seen'] = actual_actor['last_seen']
        self.assertEqual(after['users'], before['users'])
        for table in ('owned_morties', 'owned_items', 'decks', 'attacks', 'friends', 'completed', 'claims', 'battles', 'event_queue'):
            self.assertEqual(after[table], before[table], table)

    def waiting_creation(self, offer, mutation, code):
        """Commit a writer while creation waits on its actor's primary-key lock."""
        before = self.snapshot()
        actor_id = next(row['id'] for row in before['users'] if row['player_id'] == self.a)
        encoded = base64.b64encode(mutation.encode()).decode()
        program = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
                   "$pdo->beginTransaction();"
                   f"$pdo->query('SELECT id FROM users WHERE id={int(actor_id)} FOR UPDATE')->fetchAll();"
                   "echo \"locked\\n\";flush();fgets(STDIN);"
                   f"$pdo->exec(base64_decode('{encoded}'));$pdo->commit();echo \"committed\\n\";")
        blocker = subprocess.Popen(COMPOSE + ['exec', '-T', 'web', 'php', '-r', program],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, cwd=ROOT)
        try:
            self.assertEqual(blocker.stdout.readline().strip(), 'locked')
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(self.call, offer)
                try:
                    time.sleep(0.3)
                    self.assertFalse(pending.done(), 'Creation must wait for the actor lock')
                finally:
                    blocker.stdin.write('release\n')
                    blocker.stdin.flush()
                self.assertEqual(pending.result(timeout=15), (403 if 'DOES_NOT_BELONG' in code else 409,
                                                            {'error': {'code': code}}))
            self.assertEqual(blocker.wait(timeout=10), 0, blocker.stderr.read())
            return before, self.snapshot()
        finally:
            if blocker.poll() is None:
                blocker.kill()
                blocker.wait(timeout=10)
            for stream in (blocker.stdin, blocker.stdout, blocker.stderr):
                stream.close()

    def test_waiting_creations_observe_committed_ownership_change(self):
        for offer in (False, True):
            with self.subTest(offer=offer):
                code = ('TRADE_OFFER_MORTY_DOES_NOT_BELONG_TO_OFFERING_PLAYER' if offer else
                        'TRADE_REQUEST_MORTY_DOES_NOT_BELONG_TO_PLAYER')
                before, after = self.waiting_creation(offer,
                    f"UPDATE owned_morties SET player_id='{self.c}' WHERE owned_morty_id='{self.spare}'", code)
                next(row for row in before['owned_morties'] if row['owned_morty_id'] == self.spare)['player_id'] = self.c
                self.assertEqual(after, before, 'The blocked creator must add no writes to the competing ownership change')
                sql(f"UPDATE owned_morties SET player_id='{self.a}' WHERE owned_morty_id='{self.spare}'")

    def test_waiting_creations_observe_committed_active_deck_change(self):
        for offer in (False, True):
            with self.subTest(offer=offer):
                deck = json.dumps([self.party, self.spare], separators=(',', ':'))
                before, after = self.waiting_creation(offer,
                    f"UPDATE decks SET owned_morty_ids='{deck}' WHERE player_id='{self.a}' AND deck_id=7",
                    'FAILED' if offer else 'TRADE_MORTY_LOCKED')
                next(row for row in before['decks'] if row['player_id'] == self.a and int(row['deck_id']) == 7)['owned_morty_ids'] = deck
                self.assertEqual(after, before, 'The blocked creator must add no writes to the competing deck change')
                sql(f"UPDATE decks SET owned_morty_ids='[\"{self.party}\"]' WHERE player_id='{self.a}' AND deck_id=7")


if __name__ == '__main__':
    unittest.main()

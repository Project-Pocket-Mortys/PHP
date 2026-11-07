"""Party/trade transitions use additive UUID fixtures and native transport.

Only transport/SQL helpers are shared; no other TestCase or global seed runs.
"""
import base64
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import time
import unittest
import urllib.error
import urllib.request
import uuid

from test_http import php, post, sql


def literal(value):
    return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"


class TradePartyTransitionTests(unittest.TestCase):
    def execute(self, queries, fetch=False):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
                "$queries=json_decode(base64_decode('" + encoded + "'),true);$pdo->beginTransaction();")
        if fetch:
            return json.loads(php(code + "$out=[];foreach($queries as $k=>$q)$out[$k]=$pdo->query($q)->fetchAll();$pdo->rollBack();echo json_encode($out);"))
        php(code + "foreach($queries as $q)$pdo->exec($q);$pdo->commit();")

    def setUp(self):
        self.players = [str(uuid.uuid4()) for _ in range(3)]
        self.a, self.b, self.c = self.players
        self.sessions = {player: str(uuid.uuid4()) for player in self.players}
        self.party = {player: str(uuid.uuid4()) for player in self.players}
        self.spare = {player: str(uuid.uuid4()) for player in self.players}
        self.ids = "','".join(self.players)
        self.morties = "','".join([*self.party.values(), *self.spare.values()])
        self.trade, self.offer, self.sibling, self.other_trade, self.reference = [str(uuid.uuid4()) for _ in range(5)]
        self.addCleanup(self.cleanup)
        queries = []
        for player in self.players:
            queries.extend([
                f"INSERT INTO users (secret,player_id,session_id,username,state,active_deck_id,decks_owned,tags,level,wins,losses,coupons,coins,permits) VALUES ('{player}','{player}','{self.sessions[player]}','PartyTransitionFixture','WORLD',1,4,'[]',7,2,1,9,21,3)",
                f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{player}','ItemSerum',3)",
            ])
            for morty in (self.party[player], self.spare[player]):
                queries.extend([
                    f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,level,xp,hp,hp_stat,attack_stat,defence_stat,speed_stat,variant,is_locked,is_trading_locked,fight_pit_id) VALUES ('{player}','{morty}','MortyDefault',5,125,20,20,11,10,10,'Normal','false','false','null')",
                    f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{morty}','AttackOutburst',0,12,12)",
                ])
            queries.append(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{player}',1,'[\"{self.party[player]}\"]'),('{player}',2,'[\"{self.spare[player]}\"]')")
        self.execute(queries)

    def cleanup(self):
        self.execute([
            f"DELETE FROM completed_trades WHERE request_player_id IN ('{self.ids}') OR offer_player_id IN ('{self.ids}')",
            f"DELETE FROM trade_offers WHERE player_id IN ('{self.ids}') OR morty_offer_id IN ('{self.morties}')",
            f"DELETE FROM trades WHERE player_id IN ('{self.ids}') OR morty_trade_id IN ('{self.morties}')",
            f"DELETE FROM friend_battle_memberships WHERE player_id IN ('{self.ids}')",
            f"DELETE FROM event_queue WHERE player_id IN ('{self.ids}') OR only_show_to_player_id IN ('{self.ids}')",
            f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.morties}')",
            *[f"DELETE FROM {table} WHERE player_id IN ('{self.ids}')" for table in
              ('owned_items', 'decks', 'owned_morties', 'users')],
        ])

    def snapshot(self):
        queries = {table: f"SELECT * FROM {table} WHERE player_id IN ('{self.ids}') ORDER BY id"
                   for table in ('users', 'owned_items', 'owned_morties', 'decks', 'trades', 'trade_offers', 'event_queue')}
        queries.update(
            attacks=f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.morties}') ORDER BY id",
            completed=f"SELECT * FROM completed_trades WHERE request_player_id IN ('{self.ids}') OR offer_player_id IN ('{self.ids}') ORDER BY id",
            claims=f"SELECT * FROM friend_battle_memberships WHERE player_id IN ('{self.ids}') ORDER BY player_id")
        return self.execute(queries, fetch=True)

    def native(self, route, body, actor=None):
        request = urllib.request.Request('http://127.0.0.1:8087/trading/' + route + '/',
            json.dumps(body).encode(), {'Content-Type': 'application/json',
            'Cookie': 'session_id=' + self.sessions[actor or self.a]}, method='POST')
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def deck(self, route, player=None, deck_id=2, ids=None):
        player = player or self.a
        body = dict(session_id=self.sessions[player], deck_id=deck_id)
        if route == 'edit':
            body['owned_morty_ids'] = ids if ids is not None else [self.spare[player]]
        return post('/session/deck/' + route, body)

    def block_deck(self, route, **request):
        before = self.snapshot()
        self.assertEqual(self.deck(route, **request), (409, {'success': False, 'error': {'code': 'FAILED'}}))
        self.assertEqual(self.snapshot(), before, 'Rejected activation changed gameplay or reservation rows')

    def reserve(self, offer=False, owner=None, upper=False):
        morty = self.spare[self.a]
        morty = morty.upper() if upper else morty
        owner = owner or self.a
        if offer:
            # Deliberately orphaned; a missing parent must not hide a reservation.
            query = f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{self.reference}','{self.reference}','{owner}','{morty}')"
        else:
            query = f"INSERT INTO trades (trade_id,player_id,morty_trade_id,is_free_trade) VALUES ('{self.reference}','{owner}','{morty}',1)"
        sql(query)

    def legacy_listing(self):
        self.execute([
            f"INSERT INTO trades (trade_id,player_id,morty_trade_id,is_free_trade) VALUES ('{self.trade}','{self.a}','{self.spare[self.a]}',1),('{self.other_trade}','{self.c}','{self.spare[self.c]}',0)",
            f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{self.offer}','{self.trade}','{self.b}','{self.spare[self.b]}'),('{self.sibling}','{self.trade}','{self.c}','{self.spare[self.c]}')",
        ])

    def respond(self, accepted=True):
        return self.native('offer-response', dict(trade_request_id=self.trade,
                           trade_offer_id=self.offer, request_accepted=accepted))

    def block_accept(self):
        before = self.snapshot()
        self.assertEqual(self.respond(), (409, {'error': {'code': 'FAILED'}}))
        self.assertEqual(self.snapshot(), before, 'Rejected acceptance changed rows')

    def set_party(self, player, raw):
        sql(f"UPDATE decks SET owned_morty_ids={literal(raw)} WHERE player_id='{player}' AND deck_id=1")

    def assert_deck_success(self, route, **request):
        status, body = self.deck(route, **request)
        self.assertEqual(status, 200, body)
        self.assertEqual(body['player_id'], self.a)
        self.assertEqual(body['active_deck_id'], request.get('deck_id', 2))
        self.assertEqual(body['decks_owned'], 4)
        self.assertEqual({row['deck_id']: row['owned_morty_ids'] for row in body['decks']}[2],
                         [self.spare[self.a]])
        self.assertEqual(body['tags'], [])

    def test_nonempty_edit_activates_and_cannot_insert_reserved_morty(self):
        self.reserve()
        # Even editing a previously absent inactive slot activates it.
        self.block_deck('edit', deck_id=3)
        self.block_deck('edit', deck_id=1, ids=[self.party[self.a], self.spare[self.a]])

    def test_set_active_cannot_activate_existing_reserved_deck(self):
        self.reserve()
        self.block_deck('set-active')

    def test_global_orphan_stale_owner_and_collated_references_block_activation(self):
        for offer in (False, True):
            for owner in (self.a, self.c):
                for upper in (False, True):
                    with self.subTest(offer=offer, owner=owner, upper=upper):
                        self.reserve(offer, owner, upper)
                        self.block_deck('edit')
                        self.block_deck('set-active')
                        sql(f"DELETE FROM {'trade_offers' if offer else 'trades'} WHERE player_id='{owner}'")

    def test_stored_trading_lock_blocks_both_activation_paths(self):
        for flag in ('true', '1'):
            with self.subTest(flag=flag):
                sql(f"UPDATE owned_morties SET is_trading_locked='{flag}' WHERE owned_morty_id='{self.spare[self.a]}'")
                self.block_deck('edit')
                self.block_deck('set-active')

    def test_manual_favorite_lock_allows_ordinary_party_changes(self):
        sql(f"UPDATE owned_morties SET is_locked='true' WHERE player_id='{self.a}'")
        self.assert_deck_success('edit')
        sql(f"UPDATE users SET active_deck_id=1 WHERE player_id='{self.a}'")
        self.assert_deck_success('set-active')

    def test_unlocked_unreserved_decks_keep_success_response_fields(self):
        self.assert_deck_success('edit')
        sql(f"UPDATE users SET active_deck_id=1 WHERE player_id='{self.a}'")
        self.assert_deck_success('set-active')

    def test_escaped_stored_deck_survives_activation_and_other_deck_edit_response(self):
        escaped = json.dumps([self.spare[self.a]]).replace('"', '\\"')
        sql(f"UPDATE decks SET owned_morty_ids={literal(escaped)} WHERE player_id='{self.a}' AND deck_id=2")
        for route in ('set-active', 'edit'):
            with self.subTest(route=route):
                sql(f"UPDATE users SET active_deck_id=1 WHERE player_id='{self.a}'")
                before = self.snapshot()
                deck_id = 2 if route == 'set-active' else 1
                self.assert_deck_success(route, deck_id=deck_id, ids=[self.party[self.a]])
                after = self.snapshot()
                expected = dict(before)
                expected['users'] = [dict(row, active_deck_id=deck_id,
                                         last_seen=next(actual['last_seen'] for actual in after['users']
                                                        if actual['player_id'] == self.a))
                                     if row['player_id'] == self.a else row for row in before['users']]
                self.assertEqual(after, expected,
                                 'Successful response rewrote escaped deck storage or unrelated gameplay state')

    def test_unrelated_inactive_reservation_does_not_ban_party_changes(self):
        self.reserve()
        # Keeping the living active party is safe while another deck is reserved.
        self.assertEqual(self.deck('set-active', deck_id=1)[0], 200)
        self.assertEqual(self.deck('edit', deck_id=1, ids=[self.party[self.a]])[0], 200)
        before = self.snapshot()
        self.assertEqual(self.deck('edit', ids=[])[0], 200)
        expected = dict(before)
        expected['decks'] = [row for row in before['decks'] if not
                             (row['player_id'] == self.a and int(row['deck_id']) == 2)]
        self.assertEqual(self.snapshot(), expected)

    def test_malformed_target_deck_fails_closed(self):
        values = ('bad-json', '{}', '"morty"', '[1]',
                  json.dumps([self.spare[self.a], self.spare[self.a]]))
        for raw in values:
            with self.subTest(raw=raw):
                sql(f"UPDATE decks SET owned_morty_ids={literal(raw)} WHERE player_id='{self.a}' AND deck_id=2")
                self.block_deck('set-active')

    def test_ambiguous_target_deck_fails_for_both_writers(self):
        sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{self.a}',2,'[\"{self.spare[self.a]}\"]')")
        self.block_deck('edit')
        self.block_deck('set-active')

    def test_ambiguous_current_ownership_fails_for_both_writers(self):
        sql(f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id) VALUES ('{self.c}','{self.spare[self.a].upper()}','MortyDefault')")
        self.block_deck('edit')
        self.block_deck('set-active')

    def test_stale_target_deck_ownership_fails_closed(self):
        sql(f"UPDATE owned_morties SET player_id='{self.c}' WHERE owned_morty_id='{self.spare[self.a]}'")
        self.block_deck('set-active')

    def test_acceptance_checks_each_outgoing_morty_against_current_active_party(self):
        self.legacy_listing()
        for player in (self.a, self.b):
            with self.subTest(player=player):
                self.set_party(player, json.dumps([self.party[player], self.spare[player]]))
                self.block_accept()
                self.set_party(player, json.dumps([self.party[player]]))

    def test_acceptance_fails_closed_for_each_malformed_current_party(self):
        self.legacy_listing()
        for player in (self.a, self.b):
            for raw in ('bad-json', '{}', '"morty"', '[1]'):
                with self.subTest(player=player, raw=raw):
                    self.set_party(player, raw)
                    self.block_accept()
            self.set_party(player, json.dumps([self.party[player]]))

    def test_acceptance_fails_closed_for_missing_current_deck_on_either_side(self):
        self.legacy_listing()
        for player in (self.a, self.b):
            with self.subTest(player=player):
                sql(f"UPDATE users SET active_deck_id=3 WHERE player_id='{player}'")
                self.block_accept()
                sql(f"UPDATE users SET active_deck_id=1 WHERE player_id='{player}'")

    def test_acceptance_fails_closed_for_duplicate_current_deck_on_either_side(self):
        self.legacy_listing()
        for player in (self.a, self.b):
            with self.subTest(player=player):
                sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{player}',1,'[\"{self.party[player]}\"]')")
                self.block_accept()
                sql(f"DELETE FROM decks WHERE player_id='{player}' AND deck_id=1 ORDER BY id DESC LIMIT 1")

    def test_unsafe_legacy_offer_can_still_be_rejected(self):
        self.legacy_listing()
        for player in (self.a, self.b):
            self.set_party(player, json.dumps([self.spare[player]]))
        before = self.snapshot()
        self.assertEqual(self.respond(False), (200, [None, None]))
        expected = dict(before)
        expected['trade_offers'] = [row for row in before['trade_offers'] if row['trade_offer_id'] != self.offer]
        self.assertEqual(self.snapshot(), expected)

    def test_unsafe_legacy_offer_can_still_be_cancelled_by_offerer(self):
        self.legacy_listing()
        self.set_party(self.b, json.dumps([self.spare[self.b]]))
        before = self.snapshot()
        self.assertEqual(self.native('cancel-trade-offer', {'trade_offer_id': self.offer}, self.b),
                         (200, {'error': 'None'}))
        expected = dict(before)
        expected['trade_offers'] = [row for row in before['trade_offers'] if row['trade_offer_id'] != self.offer]
        self.assertEqual(self.snapshot(), expected)

    def test_unsafe_legacy_request_can_still_be_cancelled_by_requester(self):
        self.legacy_listing()
        self.set_party(self.a, json.dumps([self.spare[self.a]]))
        before = self.snapshot()
        self.assertEqual(self.native('cancel-trade', {'trade_id': self.trade}), (200, {'error': 'None'}))
        expected = dict(before)
        expected['trades'] = [row for row in before['trades'] if row['trade_id'] != self.trade]
        expected['trade_offers'] = [row for row in before['trade_offers'] if row['trade_id'] != self.trade]
        self.assertEqual(self.snapshot(), expected)

    def test_valid_spares_accept_swap_complete_and_clean_only_selected_listing(self):
        self.legacy_listing()
        before = self.snapshot()
        # Cookie contains the requester's distinct session, never its player ID.
        self.assertEqual(self.respond(), (200, [None, None]))
        after = self.snapshot()
        self.assertEqual(len(after['completed']), 1)
        completion = after['completed'][0]
        self.assertEqual({key: completion[key] for key in ('request_player_id', 'offer_player_id',
                         'morty_request_id', 'morty_offer_id', 'trade_request_id', 'trade_offer_id')},
                         dict(request_player_id=self.a, offer_player_id=self.b,
                              morty_request_id=self.spare[self.a], morty_offer_id=self.spare[self.b],
                              trade_request_id=self.trade, trade_offer_id=self.offer))
        self.assertTrue(completion['fulfilled_at'])
        expected = dict(before)
        expected['completed'] = after['completed']
        expected['trades'] = [row for row in before['trades'] if row['trade_id'] != self.trade]
        expected['trade_offers'] = [row for row in before['trade_offers'] if row['trade_id'] != self.trade]
        owners = {self.spare[self.a]: self.b, self.spare[self.b]: self.a}
        expected['owned_morties'] = [dict(row, player_id=owners[row['owned_morty_id']])
                                    if row['owned_morty_id'] in owners else row for row in before['owned_morties']]
        self.assertEqual(after, expected, 'Transfer touched parties, resources, statistics, attacks, or unrelated rows')

    def test_active_party_case_alias_cannot_bypass_acceptance_guard(self):
        self.legacy_listing()
        for player in (self.a, self.b):
            with self.subTest(player=player):
                self.set_party(player, json.dumps([self.spare[player].upper()]))
                self.block_accept()
                self.set_party(player, json.dumps([self.party[player]]))

    def race_listing(self, route):
        barrier = threading.Barrier(2)

        def activate():
            barrier.wait(timeout=10)
            return self.deck(route)

        def create():
            barrier.wait(timeout=10)
            return post('/trading/request-morty', dict(session_id=self.sessions[self.a],
                        player_id=self.a, owned_morty_id=self.spare[self.a],
                        requested_morty_id='any', request_variant='Normal', is_free_trade=True))

        before = self.snapshot()
        with ThreadPoolExecutor(max_workers=2) as pool:
            activation = pool.submit(activate)
            creation = pool.submit(create)
            activated, created = activation.result(timeout=20), creation.result(timeout=20)
        self.assertEqual(sum(result[0] == 200 for result in (activated, created)), 1,
                         (activated, created))
        if activated[0] != 200:
            self.assertEqual(activated, (409, {'success': False, 'error': {'code': 'FAILED'}}))
        if created[0] != 200:
            self.assertEqual(created, (409, {'error': {'code': 'TRADE_MORTY_LOCKED'}}))
        after = self.snapshot()
        requests = [row for row in after['trades'] if row['morty_trade_id'] == self.spare[self.a]]
        active = next(row['active_deck_id'] for row in after['users'] if row['player_id'] == self.a)
        self.assertEqual(len(requests), int(created[0] == 200))
        self.assertEqual(int(active), 1 if requests else 2)
        for table in ('owned_items', 'owned_morties', 'attacks', 'completed', 'claims', 'event_queue', 'trade_offers'):
            self.assertEqual(after[table], before[table], table)
        self.assertEqual([row for row in after['users'] if row['player_id'] != self.a],
                         [row for row in before['users'] if row['player_id'] != self.a])

    def test_racing_nonempty_edit_and_listing_creation_only_one_can_win(self):
        self.race_listing('edit')

    def test_racing_set_active_and_listing_creation_only_one_can_win(self):
        self.race_listing('set-active')

    def test_racing_acceptance_and_offerer_activation_cannot_commit_unsafe_party(self):
        self.legacy_listing()
        barrier = threading.Barrier(2)

        def activate():
            barrier.wait(timeout=10)
            return self.deck('set-active', player=self.b)

        def accept():
            barrier.wait(timeout=10)
            return self.respond()

        before = self.snapshot()
        with ThreadPoolExecutor(max_workers=2) as pool:
            activation = pool.submit(activate)
            acceptance = pool.submit(accept)
            self.assertEqual(activation.result(timeout=20),
                             (409, {'success': False, 'error': {'code': 'FAILED'}}))
            self.assertEqual(acceptance.result(timeout=20), (200, [None, None]))
        after = self.snapshot()
        for table in ('users', 'decks', 'owned_items', 'attacks', 'claims', 'event_queue'):
            self.assertEqual(after[table], before[table], table)
        owners = {row['owned_morty_id']: row['player_id'] for row in after['owned_morties']}
        self.assertEqual(owners[self.spare[self.a]], self.b)
        self.assertEqual(owners[self.spare[self.b]], self.a)
        self.assertEqual(len(after['completed']), 1)
        self.assertFalse(any(row['trade_id'] == self.trade for row in after['trades']))
        self.assertFalse(any(row['trade_id'] == self.trade for row in after['trade_offers']))

    def waiting_writer(self, player, action, queries):
        """Commit fixture-only mutations after proving the HTTP writer waits.

        A fixture item acts as a release signal. The blocker uses READ COMMITTED
        only for that signal; the actual endpoint retains its normal isolation.
        The advisory lock identifies readiness without relying on a timed sleep.
        """
        marker = 'party_transition_' + uuid.uuid4().hex
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        program = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
                   "$pdo->exec('SET SESSION TRANSACTION ISOLATION LEVEL READ COMMITTED');"
                   "$pdo->beginTransaction();"
                   f"$pdo->query(\"SELECT id FROM users WHERE player_id='{player}' FOR UPDATE\")->fetchAll();"
                   f"$pdo->query(\"SELECT GET_LOCK('{marker}',0)\")->fetchColumn();"
                   "$deadline=microtime(true)+15;"
                   f"while((int)$pdo->query(\"SELECT quantity FROM owned_items WHERE player_id='{self.c}' AND item_id='ItemSerum'\")->fetchColumn()!==4){{"
                   "if(microtime(true)>$deadline)throw new RuntimeException('Fixture release timed out');usleep(10000);}"
                   f"foreach(json_decode(base64_decode('{encoded}'),true) as $q)$pdo->exec($q);"
                   "$pdo->commit();")
        with ThreadPoolExecutor(max_workers=2) as pool:
            blocker = pool.submit(php, program)
            try:
                deadline = time.monotonic() + 10
                while time.monotonic() < deadline:
                    self.assertFalse(blocker.done(), 'Fixture blocker exited before obtaining its user lock')
                    if sql(f"SELECT IS_USED_LOCK('{marker}') AS holder")[0]['holder'] is not None:
                        break
                    time.sleep(0.02)
                else:
                    self.fail('Fixture blocker did not obtain the affected user lock')
                pending = pool.submit(action)
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    self.assertFalse(pending.done(), 'Writer returned while the affected user lock was held')
                    waiting = sql("SELECT ID FROM information_schema.PROCESSLIST WHERE ID<>CONNECTION_ID() "
                                  "AND INFO LIKE '%FOR UPDATE%' AND INFO LIKE '%users%'")
                    if waiting:
                        break
                    time.sleep(0.02)
                else:
                    self.fail('Writer did not wait on an affected user row')
            finally:
                sql(f"UPDATE owned_items SET quantity=4 WHERE player_id='{self.c}' AND item_id='ItemSerum'")
            try:
                result = pending.result(timeout=15)
                blocker.result(timeout=15)
                return result
            finally:
                sql(f"UPDATE owned_items SET quantity=3 WHERE player_id='{self.c}' AND item_id='ItemSerum'")

    def test_waiting_deck_writers_observe_newly_committed_global_trade_reference(self):
        for route in ('edit', 'set-active'):
            with self.subTest(route=route):
                before = self.snapshot()
                result = self.waiting_writer(self.a, lambda: self.deck(route), [
                    f"INSERT INTO trades (trade_id,player_id,morty_trade_id,is_free_trade) VALUES ('{self.reference}','{self.c}','{self.spare[self.a]}',1)"])
                self.assertEqual(result, (409, {'success': False, 'error': {'code': 'FAILED'}}))
                after = self.snapshot()
                self.assertEqual(len(after['trades']), 1)
                self.assertEqual(after['trades'][0]['trade_id'], self.reference)
                expected = dict(before, trades=after['trades'])
                self.assertEqual(after, expected, 'Waiting activation added writes beyond the competing reservation')
                sql(f"DELETE FROM trades WHERE trade_id='{self.reference}'")

    def test_waiting_acceptance_observes_new_active_deck_on_either_side(self):
        self.legacy_listing()
        for player in (self.a, self.b):
            with self.subTest(player=player):
                before = self.snapshot()
                result = self.waiting_writer(player, self.respond, [
                    f"UPDATE users SET active_deck_id=2 WHERE player_id='{player}'"])
                self.assertEqual(result, (409, {'error': {'code': 'FAILED'}}))
                after = self.snapshot()
                expected = dict(before)
                expected['users'] = [dict(row, active_deck_id=2,
                                         last_seen=next(actual['last_seen'] for actual in after['users']
                                                        if actual['player_id'] == player))
                                     if row['player_id'] == player else row for row in before['users']]
                self.assertEqual(after, expected,
                                 'Waiting acceptance added writes beyond the competing active-deck change')
                sql(f"UPDATE users SET active_deck_id=1 WHERE player_id='{player}'")


if __name__ == '__main__':
    unittest.main()

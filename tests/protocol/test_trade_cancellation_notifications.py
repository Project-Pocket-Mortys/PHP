"""Cancellation invalidations with additive UUID fixtures; no account reseeding.

Run this module explicitly against the dedicated research stack after migration
015. Only test_http's transport helpers are imported; its TestCase is not run.
"""
import base64
import json
import unittest
import urllib.error
import urllib.request
import uuid

from test_http import php, sql


SUBMIT = 'trade:offer-submit'
REJECTED = 'trade:offer-rejected'
BOOT = "require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"


class TradeCancellationNotificationTests(unittest.TestCase):
    def execute(self, queries, fetch=False):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        code = BOOT + "$qs=json_decode(base64_decode('" + encoded + "'),true);"
        if fetch:
            return json.loads(php(code + "$out=[];foreach($qs as $k=>$q)$out[$k]=$pdo->query($q)->fetchAll();echo json_encode($out);"))
        php(code + "$pdo->beginTransaction();foreach($qs as $q)$pdo->exec($q);$pdo->commit();")

    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.players = [str(uuid.uuid4()) for _ in range(4)]
        self.a, self.b, self.c, self.d = self.players
        self.ids = "','".join(self.players)
        self.notification_ids = "','".join(self.players + [self.a.upper(), self.a + ' '])
        self.trade, self.other_trade = [str(uuid.uuid4()) for _ in range(2)]
        self.offer, self.sibling, self.other_offer = [str(uuid.uuid4()) for _ in range(3)]
        self.addCleanup(self.cleanup)
        queries = []
        for player in self.players:
            queries.extend([
                f"INSERT INTO users (secret,player_id,session_id,username,state,tags,coupons,level,wins,losses) VALUES ('{player}','{player}','{player}','CancelNotifyFixture','WORLD','[]',13,7,2,1)",
                f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{player}','ItemSerum',3)",
                f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat,is_locked,is_trading_locked) VALUES ('{player}','{player}','Morty',42,100,'1','1')",
                f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{player}','AttackLick',0,3,5)",
                f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{player}',1,'[\"{player}\"]')",
            ])
        queries.extend([
            f"INSERT INTO trades (trade_id,player_id,morty_trade_id,is_free_trade) VALUES ('{self.trade}','{self.a}','{self.a}',1),('{self.other_trade}','{self.d}','{self.d}',0)",
            f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{self.offer}','{self.trade}','{self.b}','{self.b}'),('{self.sibling}','{self.trade}','{self.c}','{self.c}'),('{self.other_offer}','{self.other_trade}','{self.b}','{self.b}')",
        ])
        self.execute(queries)

    def cleanup(self):
        self.execute([
            f"DELETE FROM trade_refresh_notifications WHERE player_id IN ('{self.notification_ids}')",
            f"DELETE FROM completed_trades WHERE trade_request_id IN ('{self.trade}','{self.other_trade}')",
            f"DELETE FROM trade_offers WHERE trade_id IN ('{self.trade}','{self.other_trade}') OR player_id IN ('{self.ids}')",
            f"DELETE FROM trades WHERE trade_id IN ('{self.trade}','{self.other_trade}') OR player_id IN ('{self.ids}')",
            f"DELETE FROM event_queue WHERE player_id IN ('{self.ids}') OR only_show_to_player_id IN ('{self.ids}')",
            f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.ids}')",
            *[f"DELETE FROM {table} WHERE player_id IN ('{self.ids}')" for table in
              ('owned_items', 'owned_morties', 'decks', 'users')],
        ])

    def notifications(self):
        return sql(f"SELECT player_id,CAST(revision AS CHAR) AS revision,event_name FROM trade_refresh_notifications WHERE player_id IN ('{self.notification_ids}') ORDER BY BINARY player_id")

    def assert_notifications(self, expected):
        self.assertEqual({row['player_id']: (row['event_name'], row['revision'])
                          for row in self.notifications()},
                         {p: (event, str(revision)) for p, (event, revision) in expected.items()})

    def seed_notifications(self):
        self.execute([f"INSERT INTO trade_refresh_notifications (player_id,revision,event_name) VALUES ('{p}',7,'{SUBMIT}')"
                      for p in self.players])

    def snapshot(self):
        queries = {table: f"SELECT * FROM {table} WHERE player_id IN ('{self.ids}') ORDER BY id"
                   for table in ('users', 'owned_items', 'owned_morties', 'decks', 'event_queue')}
        queries.update(
            attacks=f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.ids}') ORDER BY id",
            trades=f"SELECT * FROM trades WHERE trade_id IN ('{self.trade}','{self.other_trade}') ORDER BY id",
            offers=f"SELECT * FROM trade_offers WHERE trade_id IN ('{self.trade}','{self.other_trade}') ORDER BY id",
            completed=f"SELECT * FROM completed_trades WHERE trade_request_id IN ('{self.trade}','{self.other_trade}') ORDER BY id",
            notifications=f"SELECT * FROM trade_refresh_notifications WHERE player_id IN ('{self.notification_ids}') ORDER BY BINARY player_id")
        return self.execute(queries, fetch=True)

    def call(self, offer=False, actor=None, body=None, headers=None):
        body = body if body is not None else {'trade_offer_id' if offer else 'trade_id': self.offer if offer else self.trade}
        request_headers = {'Content-Type': 'application/json'}
        if actor is not None:
            request_headers['Cookie'] = 'session_id=' + actor
        request_headers.update(headers or {})
        path = '/trading/cancel-trade-offer/' if offer else '/trading/cancel-trade/'
        request = urllib.request.Request('http://127.0.0.1:8087' + path,
                                         json.dumps(body).encode(), request_headers, method='POST')
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    def assert_only_deleted(self, before, trade=None, offers=()):
        after = self.snapshot()
        expected = dict(before)
        expected['trades'] = [r for r in before['trades'] if r['trade_id'] != trade]
        expected['offers'] = [r for r in before['offers'] if r['trade_offer_id'] not in offers]
        # Notification assertions independently check exact targets and revisions.
        expected.pop('notifications')
        after.pop('notifications')
        self.assertEqual(after, expected)

    def test_parent_cancel_notifies_only_removed_offer_owners(self):
        before = self.snapshot()
        self.assertEqual(self.call(actor=self.a), (200, {'error': 'None'}))
        self.assert_notifications({self.b: (REJECTED, 1), self.c: (REJECTED, 1)})
        self.assert_only_deleted(before, trade=self.trade, offers=(self.offer, self.sibling))
        self.assertEqual(self.call(actor=self.a), (404, {'error': {'code': 'FAILED'}}))
        self.assert_notifications({self.b: (REJECTED, 1), self.c: (REJECTED, 1)})

    def test_child_cancel_notifies_only_current_parent_owner(self):
        # Notification must use the current parent owner, even if ownership was
        # changed after the child listing was created.
        self.execute([f"UPDATE trades SET player_id='{self.d}' WHERE trade_id='{self.trade}'"])
        before = self.snapshot()
        self.assertEqual(self.call(offer=True, actor=self.b), (200, {'error': 'None'}))
        self.assert_notifications({self.d: (SUBMIT, 1)})
        self.assert_only_deleted(before, offers=(self.offer,))
        self.assertEqual(self.call(offer=True, actor=self.b),
                         (404, {'error': {'code': 'TRADE_NO_SUCH_OFFER'}}))
        self.assert_notifications({self.d: (SUBMIT, 1)})

    def test_parent_deduplicates_siblings_excludes_actor_and_advances_exact_revisions(self):
        duplicate, own = [str(uuid.uuid4()) for _ in range(2)]
        self.execute([f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{duplicate}','{self.trade}','{self.b}','{self.b}'),('{own}','{self.trade}','{self.a}','{self.a}')"])
        self.seed_notifications()
        before = self.snapshot()
        self.assertEqual(self.call(actor=self.a), (200, {'error': 'None'}))
        self.assert_notifications({self.a: (SUBMIT, 7), self.b: (REJECTED, 8),
                                   self.c: (REJECTED, 8), self.d: (SUBMIT, 7)})
        self.assert_only_deleted(before, trade=self.trade, offers=(self.offer, self.sibling, duplicate, own))

    def test_child_advances_parent_revision_once_and_preserves_every_other_target(self):
        self.seed_notifications()
        before = self.snapshot()
        self.assertEqual(self.call(offer=True, actor=self.b), (200, {'error': 'None'}))
        self.assert_notifications({self.a: (SUBMIT, 8), self.b: (SUBMIT, 7),
                                   self.c: (SUBMIT, 7), self.d: (SUBMIT, 7)})
        self.assert_only_deleted(before, offers=(self.offer,))

    def test_self_owned_child_and_orphan_cancel_without_notifications(self):
        self.execute([f"UPDATE trade_offers SET player_id='{self.a}' WHERE trade_offer_id='{self.offer}'"])
        before = self.snapshot()
        self.assertEqual(self.call(offer=True, actor=self.a), (200, {'error': 'None'}))
        self.assert_notifications({})
        self.assert_only_deleted(before, offers=(self.offer,))
        self.execute([f"DELETE FROM trades WHERE trade_id='{self.trade}'"])
        before = self.snapshot()
        self.assertEqual(self.call(offer=True, actor=self.c, body={'trade_offer_id': self.sibling}),
                         (200, {'error': 'None'}))
        self.assert_notifications({})
        self.assert_only_deleted(before, offers=(self.sibling,))

    def test_parent_without_children_has_no_notification(self):
        self.execute([f"DELETE FROM trade_offers WHERE trade_id='{self.trade}'"])
        before = self.snapshot()
        self.assertEqual(self.call(actor=self.a), (200, {'error': 'None'}))
        self.assert_notifications({})
        self.assert_only_deleted(before, trade=self.trade)

    def assert_rejected(self, status, **kwargs):
        before = self.snapshot()
        self.assertEqual(self.call(**kwargs)[0], status)
        self.assertEqual(self.snapshot(), before)

    def test_authentication_and_foreign_owner_failures_do_not_publish(self):
        self.seed_notifications()
        for offer, owner in ((False, self.a), (True, self.b)):
            with self.subTest(offer=offer):
                self.assert_rejected(401, offer=offer)
                self.assert_rejected(401, offer=offer, actor=str(uuid.uuid4()))
                self.assert_rejected(403, offer=offer, actor=self.d)
                self.assert_rejected(401, offer=offer, actor=owner,
                                     headers={'Authorization': 'Bearer ' + self.d})

    def test_malformed_and_collation_alias_identifiers_do_not_publish(self):
        self.seed_notifications()
        for offer, owner, identifier in ((False, self.a, self.trade), (True, self.b, self.offer)):
            key = 'trade_offer_id' if offer else 'trade_id'
            for bad in (None, [], {}, '', ' ', True, 17, 'x' * 65):
                with self.subTest(offer=offer, value=bad):
                    self.assert_rejected(400, offer=offer, actor=owner, body={key: bad})
            for alias in (identifier.upper(), identifier + ' '):
                self.assert_rejected(409, offer=offer, actor=owner, body={key: alias})
            self.assert_rejected(400, offer=offer, actor=owner,
                                 body={key: identifier, 'player_id': owner})

    def test_ambiguous_parent_and_child_rows_do_not_publish(self):
        self.seed_notifications()
        self.execute([f"INSERT INTO trades (trade_id,player_id,morty_trade_id) VALUES ('{self.trade.upper()}','{self.d}','{self.d}')"])
        self.assert_rejected(409, actor=self.a)
        self.assert_rejected(409, offer=True, actor=self.b)
        self.execute([f"DELETE FROM trades WHERE trade_id='{self.trade}' AND player_id='{self.d}'",
                      f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{self.offer.upper()}','{self.other_trade}','{self.b}','{self.b}')"])
        self.assert_rejected(409, offer=True, actor=self.b)

    def test_parent_rejects_child_parent_identifier_collation_alias(self):
        self.seed_notifications()
        for alias in (self.trade.upper(), self.trade + ' '):
            self.execute([f"UPDATE trade_offers SET trade_id='{alias}' WHERE trade_offer_id='{self.sibling}'"])
            self.assert_rejected(409, actor=self.a)
        self.execute([f"UPDATE trade_offers SET trade_id='{self.trade}' WHERE trade_offer_id='{self.sibling}'"])

    def test_parent_recipient_aliases_are_distinct_and_actor_exclusion_is_exact(self):
        self.execute([
            f"UPDATE trade_offers SET player_id='{self.a.upper()}' WHERE trade_offer_id='{self.offer}'",
            f"UPDATE trade_offers SET player_id='{self.a} ' WHERE trade_offer_id='{self.sibling}'",
        ])
        before = self.snapshot()
        self.assertEqual(self.call(actor=self.a), (200, {'error': 'None'}))
        self.assert_notifications({self.a.upper(): (REJECTED, 1), self.a + ' ': (REJECTED, 1)})
        self.assert_only_deleted(before, trade=self.trade, offers=(self.offer, self.sibling))

    def test_legacy_empty_offer_owner_is_removed_without_invalid_recipient(self):
        self.execute([f"UPDATE trade_offers SET player_id='' WHERE trade_offer_id='{self.offer}'"])
        before = self.snapshot()
        self.assertEqual(self.call(actor=self.a), (200, {'error': 'None'}))
        self.assert_notifications({self.c: (REJECTED, 1)})
        self.assert_only_deleted(before, trade=self.trade, offers=(self.offer, self.sibling))

    def test_legacy_blank_parent_owner_does_not_block_child_withdrawal(self):
        self.execute([f"UPDATE trades SET player_id=' ' WHERE trade_id='{self.trade}'"])
        before = self.snapshot()
        self.assertEqual(self.call(offer=True, actor=self.b), (200, {'error': 'None'}))
        self.assert_notifications({})
        self.assert_only_deleted(before, offers=(self.offer,))

    def test_second_recipient_publisher_failure_rolls_back_deletions_and_all_notifications(self):
        self.seed_notifications()
        before = self.snapshot()
        failed = max(self.b, self.c)
        trigger = 'cancel_notify_fault_' + uuid.uuid4().hex
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON trade_refresh_notifications FOR EACH ROW BEGIN IF NEW.player_id='{failed}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID cancellation notification failure'; END IF; END")
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        try:
            self.assertEqual(self.call(actor=self.a), (500, {'error': {'code': 'FAILED'}}))
            self.assertEqual(self.snapshot(), before)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')

    def test_child_publisher_failure_rolls_back_selected_offer_deletion(self):
        self.seed_notifications()
        before = self.snapshot()
        trigger = 'child_cancel_notify_fault_' + uuid.uuid4().hex
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON trade_refresh_notifications FOR EACH ROW BEGIN IF NEW.player_id='{self.a}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID child notification failure'; END IF; END")
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        try:
            self.assertEqual(self.call(offer=True, actor=self.b), (500, {'error': {'code': 'FAILED'}}))
            self.assertEqual(self.snapshot(), before)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')


if __name__ == '__main__':
    unittest.main()

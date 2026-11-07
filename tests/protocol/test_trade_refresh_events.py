"""Trade cache invalidation with isolated UUID fixtures; never reseed accounts.

Run this module explicitly after migration 015; importing test_http reuses only
transport helpers and does not run its destructive seed-based TestCase.
"""
import base64
import json
import subprocess
import unittest
import urllib.error
import urllib.request
import uuid

from test_http import COMPOSE, ROOT, php, post, sql


SUBMIT = 'trade:offer-submit'
REJECTED = 'trade:offer-rejected'
ACCEPTED = 'trade:offer-accepted'
BOOT = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
        "require_once '/var/www/html/lib/trade_refresh.php';")


class TradeRefreshEventsTests(unittest.TestCase):
    def execute(self, queries):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        php(BOOT + "$qs=json_decode(base64_decode('" + encoded + "'),true);"
            "$pdo->beginTransaction();foreach($qs as $q)$pdo->exec($q);$pdo->commit();")

    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.players = [str(uuid.uuid4()) for _ in range(4)]
        self.a, self.b, self.c, self.d = self.players
        self.ids = "','".join(self.players)
        self.parties = {p: str(uuid.uuid4()) for p in self.players}
        self.trade = str(uuid.uuid4())
        self.offer, self.sibling, self.duplicate = [str(uuid.uuid4()) for _ in range(3)]
        self.addCleanup(self.cleanup)
        queries = []
        for player in self.players:
            queries.extend([
                f"INSERT INTO users (secret,player_id,session_id,username,state,active_deck_id,tags,coupons) VALUES ('{player}','{player}','{player}','RefreshFixture','WORLD',1,'[]',9)",
                f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat,variant,is_locked,is_trading_locked) VALUES ('{player}','{player}','MortyDefault',42,100,'Normal','false','false'),('{self.parties[player]}','{player}','MortyDefault',100,100,'Normal','false','false')",
                f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{player}',1,'[\"{self.parties[player]}\"]')",
            ])
        queries.append(f"INSERT INTO trades (trade_id,player_id,morty_trade_id,requested_morty_id,request_variant,is_free_trade) VALUES ('{self.trade}','{self.a}','{self.a}','any','Normal',1)")
        self.execute(queries)

    def cleanup(self):
        self.execute([
            f"DELETE FROM trade_refresh_notifications WHERE player_id IN ('{self.ids}')",
            f"DELETE FROM trade_refresh_notifications WHERE player_id IN ('{self.a.upper()}','{self.a} ')",
            f"DELETE FROM completed_trades WHERE trade_request_id='{self.trade}' OR request_player_id IN ('{self.ids}') OR offer_player_id IN ('{self.ids}')",
            f"DELETE FROM trade_offers WHERE trade_id='{self.trade}' OR player_id IN ('{self.ids}')",
            f"DELETE FROM trades WHERE player_id IN ('{self.ids}')",
            f"DELETE FROM event_queue WHERE player_id IN ('{self.ids}') OR only_show_to_player_id IN ('{self.ids}')",
            *[f"DELETE FROM {table} WHERE player_id IN ('{self.ids}')" for table in
              ('friend_battle_memberships', 'owned_morties', 'decks', 'users')],
        ])

    def rows(self):
        return sql(f"SELECT player_id,CAST(revision AS CHAR) AS revision,event_name FROM trade_refresh_notifications WHERE player_id IN ('{self.ids}') ORDER BY BINARY player_id")

    def assert_notifications(self, expected):
        actual = {row['player_id']: (row['event_name'], row['revision']) for row in self.rows()}
        self.assertEqual(actual, {player: (event, str(revision))
                                  for player, (event, revision) in expected.items()})

    def publish(self, recipients, event=SUBMIT, rollback=False):
        encoded = base64.b64encode(json.dumps(recipients).encode()).decode()
        php(BOOT + "$pdo->beginTransaction();trade_refresh_publish($pdo,"
            "json_decode(base64_decode('" + encoded + "'),true),'" + event + "');"
            + ('$pdo->rollBack();' if rollback else '$pdo->commit();'))

    def poll(self, player, session=None, seen=None):
        values = base64.b64encode(json.dumps([player, session or player, seen]).encode()).decode()
        return json.loads(php(BOOT + "$v=json_decode(base64_decode('" + values + "'),true);"
            "try {echo json_encode(['ok'=>trade_refresh_poll($pdo,$v[0],$v[1],$v[2])],JSON_THROW_ON_ERROR);}"
            "catch(Throwable $e){echo json_encode(['error'=>get_class($e),'status'=>$e->status??null]);}"))

    def add_offers(self, duplicate_winner=False):
        values = [f"('{self.offer}','{self.trade}','{self.b}','{self.b}')",
                  f"('{self.sibling}','{self.trade}','{self.c}','{self.c}')"]
        if duplicate_winner:
            values.append(f"('{self.duplicate}','{self.trade}','{self.b}','{self.b}')")
        self.execute(['INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ' + ','.join(values)])

    def respond(self, accepted, actor=None):
        request = urllib.request.Request('http://127.0.0.1:8087/trading/offer-response/',
            json.dumps(dict(trade_request_id=self.trade, trade_offer_id=self.offer,
                            request_accepted=accepted)).encode(),
            {'Content-Type': 'application/json', 'Cookie': 'session_id=' + (actor or self.a)}, method='POST')
        try:
            response = urllib.request.urlopen(request, timeout=10)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            return response.status, json.loads(response.read())

    def test_offer_http_notifies_only_request_owner(self):
        status, body = post('/trading/offer-morty', dict(session_id=self.b, player_id=self.b,
            offered_morty_id=self.b, trade_request_id=self.trade))
        self.assertEqual(status, 200)
        self.assertEqual(body['error'], 'None')
        self.assert_notifications({self.a: (SUBMIT, 1)})
        status, _ = post('/trading/offer-morty', dict(session_id=self.b, player_id=self.b,
            offered_morty_id=self.b, trade_request_id=self.trade))
        self.assertEqual(status, 409)
        self.assert_notifications({self.a: (SUBMIT, 1)})

    def test_decline_http_notifies_only_offer_owner_and_retry_is_noop(self):
        self.add_offers()
        self.assertEqual(self.respond(False), (200, [None, None]))
        self.assert_notifications({self.b: (REJECTED, 1)})
        self.assertEqual(len(sql(f"SELECT id FROM trade_offers WHERE trade_id='{self.trade}'")), 1)
        self.assertEqual(self.respond(False)[0], 404)
        self.assert_notifications({self.b: (REJECTED, 1)})

    def test_accept_http_deduplicates_siblings_and_winner_takes_precedence(self):
        self.add_offers(duplicate_winner=True)
        self.assertEqual(self.respond(True), (200, [None, None]))
        self.assert_notifications({self.b: (ACCEPTED, 1), self.c: (REJECTED, 1)})
        self.assertEqual(sql(f"SELECT id FROM trades WHERE trade_id='{self.trade}'"), [])
        self.assertEqual(sql(f"SELECT id FROM trade_offers WHERE trade_id='{self.trade}'"), [])
        self.assertEqual(self.respond(True)[0], 404)
        self.assert_notifications({self.b: (ACCEPTED, 1), self.c: (REJECTED, 1)})

    def test_self_offer_and_response_do_not_notify_actor(self):
        self.execute([f"UPDATE trades SET morty_trade_id='{self.parties[self.a]}' WHERE trade_id='{self.trade}'",
                      f"UPDATE decks SET owned_morty_ids='[]' WHERE player_id='{self.a}'"])
        status, _ = post('/trading/offer-morty', dict(session_id=self.a, player_id=self.a,
            offered_morty_id=self.a, trade_request_id=self.trade))
        self.assertEqual(status, 200)
        self.assert_notifications({})
        offer = sql(f"SELECT trade_offer_id FROM trade_offers WHERE trade_id='{self.trade}'")[0]['trade_offer_id']
        self.offer = offer
        self.assertEqual(self.respond(False), (200, [None, None]))
        self.assert_notifications({})

    def test_unauthorized_response_does_not_publish(self):
        self.add_offers()
        for accepted in (False, True):
            self.assertEqual(self.respond(accepted, actor=self.d)[0], 403)
        self.assert_notifications({})

    def test_publish_transaction_dedup_rollback_and_invalid_events(self):
        self.publish([self.b, self.a, self.b])
        self.assert_notifications({self.a: (SUBMIT, 1), self.b: (SUBMIT, 1)})
        self.publish([self.a], REJECTED, rollback=True)
        self.assert_notifications({self.a: (SUBMIT, 1), self.b: (SUBMIT, 1)})
        result = php(BOOT + "$pdo->beginTransaction();try {trade_refresh_publish($pdo,['" + self.a + "'],'room:user-added');echo 'accepted';}"
                     "catch(Throwable $e){echo 'rejected';}$pdo->rollBack();")
        self.assertEqual(result, 'rejected')
        result = php(BOOT + "try {trade_refresh_publish($pdo,['" + self.a + "'],'" + SUBMIT + "');echo 'accepted';}catch(Throwable $e){echo 'rejected';}")
        self.assertEqual(result, 'rejected')
        self.assert_notifications({self.a: (SUBMIT, 1), self.b: (SUBMIT, 1)})

    def test_poll_coalesces_replays_and_never_mutates(self):
        self.publish([self.a])
        self.publish([self.a], REJECTED)
        before = self.rows()
        expected = {'ok': {'revision': '2', 'event': REJECTED, 'payload': {}}}
        self.assertEqual(self.poll(self.a), expected)
        self.assertEqual(self.poll(self.a, seen='1'), expected)
        self.assertEqual(self.poll(self.a, seen='2'), {'ok': None})
        self.assertEqual(self.poll(self.a), expected)
        self.assertEqual(self.rows(), before)

    def test_recipient_storage_isolates_case_and_trailing_space_aliases(self):
        self.publish([self.a.upper(), self.a + ' '], REJECTED)
        self.assertEqual(self.poll(self.a), {'ok': None})
        self.publish([self.a], SUBMIT)
        self.assertEqual(self.poll(self.a), {
            'ok': {'revision': '1', 'event': SUBMIT, 'payload': {}}})
        rows = sql(f"SELECT HEX(player_id) AS recipient,CAST(revision AS CHAR) AS revision,event_name FROM trade_refresh_notifications WHERE player_id IN ('{self.a}','{self.a.upper()}','{self.a} ')")
        self.assertEqual({row['recipient']: (row['revision'], row['event_name']) for row in rows}, {
            self.a.encode().hex().upper(): ('1', SUBMIT),
            self.a.upper().encode().hex().upper(): ('1', REJECTED),
            (self.a + ' ').encode().hex().upper(): ('1', REJECTED),
        })

    def test_large_revision_stays_a_string_and_overflow_rolls_back_whole_publish(self):
        self.publish([self.a, self.b])
        earlier, overflowed = sorted([self.a, self.b])
        above_signed_max = '9223372036854775808'
        self.execute([f"UPDATE trade_refresh_notifications SET revision={above_signed_max} WHERE player_id='{overflowed}'"])
        self.assertEqual(self.poll(overflowed)['ok']['revision'], above_signed_max)
        self.assertEqual(self.poll(overflowed, seen=above_signed_max), {'ok': None})
        self.execute([f"UPDATE trade_refresh_notifications SET revision=18446744073709551615 WHERE player_id='{overflowed}'"])
        before = self.rows()
        result = php(BOOT + "$pdo->beginTransaction();try {trade_refresh_publish($pdo,['"
                     + earlier + "','" + overflowed + "'],'" + REJECTED
                     + "');$pdo->commit();echo 'accepted';}catch(Throwable $e){"
                     "if($pdo->inTransaction())$pdo->rollBack();echo 'rejected';}")
        self.assertEqual(result, 'rejected')
        self.assertEqual(self.rows(), before)

    def test_poll_is_private_across_rooms_no_room_and_exact_sessions(self):
        self.execute([f"UPDATE users SET room_id='{uuid.uuid4()}' WHERE player_id='{self.b}'",
                      f"UPDATE users SET room_id=NULL WHERE player_id='{self.a}'"])
        self.publish([self.a])
        self.assertEqual(self.poll(self.a)['ok']['event'], SUBMIT)
        self.assertEqual(self.poll(self.b), {'ok': None})
        self.assertEqual(self.poll(self.a, session=self.b).get('status'), 401)
        self.assertEqual(self.poll(self.a.upper(), session=self.a).get('status'), 401)
        self.assertEqual(self.poll(self.a + ' ', session=self.a).get('status'), 401)
        self.assertEqual(self.poll(self.a, session=self.a.upper()).get('status'), 401)
        replacement = str(uuid.uuid4())
        self.execute([f"UPDATE users SET session_id='{replacement}' WHERE player_id='{self.a}'"])
        self.assertEqual(self.poll(self.a).get('status'), 401)
        self.assertEqual(self.poll(self.a, session=replacement)['ok']['event'], SUBMIT)

    def snapshot(self):
        return {
            'morties': sql(f"SELECT * FROM owned_morties WHERE player_id IN ('{self.ids}') ORDER BY id"),
            'trades': sql(f"SELECT * FROM trades WHERE trade_id='{self.trade}' ORDER BY id"),
            'offers': sql(f"SELECT * FROM trade_offers WHERE trade_id='{self.trade}' ORDER BY id"),
            'completed': sql(f"SELECT * FROM completed_trades WHERE trade_request_id='{self.trade}' ORDER BY id"),
            'notifications': self.rows(),
        }

    def test_publisher_failure_rolls_back_acceptance_and_all_notifications(self):
        self.add_offers()
        before = self.snapshot()
        trigger = 'trade_refresh_fault_' + uuid.uuid4().hex
        # Fail the second recipient so rollback also removes an earlier publish.
        failed_recipient = max(self.b, self.c)
        # Trigger DDL is global; the condition affects only this fixture's IDs.
        # Always remove it, even when an HTTP assertion fails.
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON trade_refresh_notifications FOR EACH ROW BEGIN IF NEW.player_id='{failed_recipient}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID refresh fixture failure'; END IF; END")
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        try:
            self.assertEqual(self.respond(True)[0], 500)
            self.assertEqual(self.snapshot(), before)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')

    def test_publisher_failure_rolls_back_offer_creation(self):
        before = self.snapshot()
        trigger = 'trade_refresh_submit_fault_' + uuid.uuid4().hex
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON trade_refresh_notifications FOR EACH ROW BEGIN IF NEW.player_id='{self.a}' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='UUID refresh fixture failure'; END IF; END")
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        try:
            status, _ = post('/trading/offer-morty', dict(session_id=self.b, player_id=self.b,
                offered_morty_id=self.b, trade_request_id=self.trade))
            self.assertEqual(status, 500)
            self.assertEqual(self.snapshot(), before)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')

    def test_publish_rejects_invalid_recipients_before_writing_any(self):
        for invalid in ('', ' ', 7, None, 'x' * 256):
            encoded = base64.b64encode(json.dumps([self.a, invalid]).encode()).decode()
            result = php(BOOT + "$pdo->beginTransaction();try {trade_refresh_publish($pdo,json_decode(base64_decode('"
                + encoded + "'),true),'" + SUBMIT + "');echo 'accepted';}catch(Throwable $e){echo 'rejected';}"
                "$pdo->commit();")
            self.assertEqual(result, 'rejected')
            self.assert_notifications({})

    def test_live_sse_waits_for_new_membership_then_survives_leave_and_reconnect(self):
        # Backend transport test: SQL simulates the native post-startup join.
        # It does not prove native callback ordering or device behavior.
        room = str(uuid.uuid4())
        self.execute([f"UPDATE users SET room_id='{room}' WHERE player_id='{self.a}'"])
        status, _ = post('/trading/offer-morty', dict(session_id=self.b, player_id=self.b,
            offered_morty_id=self.b, trade_request_id=self.trade))
        self.assertEqual(status, 200)
        token = base64.urlsafe_b64encode(json.dumps({'session_id': self.a}).encode()).decode().rstrip('=')
        url = 'http://127.0.0.1:8087/sse/?since=0&token=e30.' + token + '.synthetic'

        def next_event(stream):
            event, data, ids = None, [], []
            for _ in range(200):
                raw = stream.readline()
                if not raw:
                    self.fail('SSE closed before the expected event')
                line = raw.decode().rstrip('\r\n')
                if line.startswith('event: '):
                    event = line[7:]
                elif line.startswith('data: '):
                    data.append(line[6:])
                elif line.startswith('id:'):
                    ids.append(line)
                elif not line and event is not None:
                    return event, json.loads('\n'.join(data)), ids
            self.fail('SSE did not complete an event')

        def marker(stream, label):
            # An ordinary targeted event proves a queue poll completed while
            # the trade replay remained gated, without timing-based absence.
            self.execute([f"INSERT INTO event_queue (room_id,event_name,player_id,only_show_to_player_id,emote) VALUES ('{room}','emote:room','{self.a}','{self.a}','{label}')"])
            self.assertEqual(next_event(stream),
                             ('emote:room', {'player_id': self.a, 'emote': label}, []))

        with urllib.request.urlopen(url, timeout=8) as stream:
            self.assertEqual(next_event(stream)[0], 'session:start')
            marker(stream, 'before-startup-join')
            self.execute([f"UPDATE users SET room_id='{room}' WHERE player_id='{self.a}'"])
            marker(stream, 'same-old-membership')
            self.execute([f"UPDATE users SET room_membership_generation=room_membership_generation+1 WHERE player_id='{self.a}'"])
            self.assertEqual(next_event(stream), (SUBMIT, {}, []))
            self.execute([f"UPDATE users SET room_id=NULL,room_membership_generation=room_membership_generation+1 WHERE player_id='{self.a}'"])
            self.publish([self.a], REJECTED)
            self.assertEqual(next_event(stream), (REJECTED, {}, []))
        boundary = sql(f"SELECT COALESCE(MAX(id),0) AS boundary FROM event_queue WHERE room_id='{room}'")[0]['boundary']
        reconnect_url = url.replace('since=0', 'since=' + str(boundary))
        with urllib.request.urlopen(reconnect_url, timeout=8) as stream:
            self.assertEqual(next_event(stream)[0], 'session:start')
            # Reconnecting resets readiness. Merely restoring a room does not
            # satisfy the new connection's membership-generation barrier.
            self.execute([f"UPDATE users SET room_id='{room}' WHERE player_id='{self.a}'"])
            marker(stream, 'reconnect-still-gated')
            self.execute([f"UPDATE users SET room_membership_generation=room_membership_generation+1 WHERE player_id='{self.a}'"])
            self.assertEqual(next_event(stream), (REJECTED, {}, []))

    def test_concurrent_publishers_serialize_revisions_and_hide_uncommitted_changes(self):
        self.publish([self.a])
        first_code = (BOOT + "$pdo->beginTransaction();trade_refresh_publish($pdo,['"
                      + self.a + "'],'" + REJECTED + "');echo \"ready\\n\";flush();"
                      "fgets(STDIN);$pdo->commit();")
        first = subprocess.Popen(COMPOSE + ['exec', '-T', 'web', 'php', '-r', first_code],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=ROOT)
        self.addCleanup(lambda: first.kill() if first.poll() is None else None)
        second = None
        try:
            self.assertEqual(first.stdout.readline().strip(), 'ready')
            self.assertEqual(self.poll(self.a)['ok']['revision'], '1')
            second_code = (BOOT + "$pdo->beginTransaction();echo \"attempting\\n\";flush();"
                           "trade_refresh_publish($pdo,['" + self.a + "'],'" + ACCEPTED
                           + "');$pdo->commit();")
            second = subprocess.Popen(COMPOSE + ['exec', '-T', 'web', 'php', '-r', second_code],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=ROOT)
            self.addCleanup(lambda: second.kill() if second.poll() is None else None)
            self.assertEqual(second.stdout.readline().strip(), 'attempting')
            with self.assertRaises(subprocess.TimeoutExpired):
                second.communicate(timeout=0.3)
            self.assertEqual(self.poll(self.a)['ok']['revision'], '1')
            _, errors = first.communicate(input='commit\n', timeout=10)
            self.assertEqual(first.returncode, 0, errors)
            _, errors = second.communicate(timeout=10)
            self.assertEqual(second.returncode, 0, errors)
            self.assert_notifications({self.a: (ACCEPTED, 3)})
        finally:
            if first.poll() is None:
                first.communicate(input='release\n', timeout=10)
            if second is not None and second.poll() is None:
                second.communicate(timeout=10)


if __name__ == '__main__':
    unittest.main()

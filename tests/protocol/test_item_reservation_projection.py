"""Item response reservation projection using additive UUID fixtures only."""
import base64
import json
import unittest
import urllib.error
import urllib.request
import uuid

from test_http import php, post, sql


class ItemReservationProjectionTests(unittest.TestCase):
    def execute(self, queries):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "$pdo->beginTransaction();foreach(json_decode(base64_decode('" + encoded +
            "'),true) as $q)$pdo->exec($q);$pdo->commit();")

    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.a, self.b, self.morty, self.foreign, self.trade, self.offer = [str(uuid.uuid4()) for _ in range(6)]
        self.addCleanup(self.cleanup)
        queries = []
        for player, morty in ((self.a, self.morty), (self.b, self.foreign)):
            queries.extend([
                f"INSERT INTO users (secret,player_id,session_id,username,state,tags) VALUES ('{player}','{player}','{player}','ItemReservationFixture','WORLD','[]')",
                f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{player}','ItemSerum',2)",
                f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,level,xp,hp,hp_stat,attack_stat,defence_stat,speed_stat,variant,is_locked,is_trading_locked,evolution_points,xp_lower,xp_upper) VALUES ('{player}','{morty}','MortyDefault',5,125,42,100,12,13,14,'Normal','true','false',0,100,200)",
                f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{morty}','AttackOutburst',0,3,12)",
            ])
        self.execute(queries)

    def cleanup(self):
        self.execute([
            f"DELETE FROM trade_offers WHERE trade_offer_id='{self.offer}' OR morty_offer_id IN ('{self.morty}','{self.foreign}')",
            f"DELETE FROM trades WHERE trade_id='{self.trade}' OR morty_trade_id IN ('{self.morty}','{self.foreign}')",
            f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.morty}','{self.foreign}')",
            *[f"DELETE FROM {table} WHERE player_id IN ('{self.a}','{self.b}')" for table in
              ('trade_refresh_notifications', 'event_queue', 'owned_items', 'owned_morties', 'users')],
        ])

    def reference(self, offer=False, stale=False, uppercase=False):
        owner = self.b if stale else self.a
        morty = self.morty.upper() if uppercase else self.morty
        if offer:
            sql(f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{self.offer}','{self.trade}','{owner}','{morty}')")
        else:
            sql(f"INSERT INTO trades (trade_id,player_id,morty_trade_id,requested_morty_id,request_variant) VALUES ('{self.trade}','{owner}','{morty}','any','Normal')")

    def request(self, **overrides):
        body = dict(session_id=self.a, owned_morty_id=self.morty, item_id='ItemSerum')
        body.update(overrides)
        return post('/session/use-item', body)

    def snapshot(self):
        queries = {
            **{table: f"SELECT * FROM {table} WHERE player_id IN ('{self.a}','{self.b}') ORDER BY id"
               for table in ('owned_morties', 'owned_items', 'trades', 'trade_offers')},
            'attacks': f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.morty}','{self.foreign}') ORDER BY id",
        }
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        return json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
                              "$out=[];foreach(json_decode(base64_decode('" + encoded +
                              "'),true) as $key=>$query)$out[$key]=$pdo->query($query)->fetchAll();echo json_encode($out);"))

    def assert_success(self, expected=True, item='ItemSerum', hp=62, effect=20, flags=None, restore_ap=False):
        before = self.snapshot()
        status, body = self.request(item_id=item)
        self.assertEqual(status, 200)
        self.assertIs(body['is_success'], True)
        result = body['owned_morties'][0]
        self.assertIs(result['is_trading_locked'], expected)
        self.assertIs(result['is_locked'], True)
        self.assertEqual(result['hp'], hp)
        self.assertEqual(body['effect_value'], effect)
        self.assertEqual(body['owned_items'], [{'item_id': item, 'quantity': 1}])
        status, details = post('/session/player-details', {'session_id': self.a})
        self.assertEqual(status, 200)
        known = next(m for m in details['owned_morties'] if m['owned_morty_id'] == self.morty)
        self.assertEqual(result, known)
        after = self.snapshot()
        own = next(m for m in before['owned_morties'] if m['owned_morty_id'] == self.morty)
        own['hp'] = hp
        for key, value in (flags or {}).items():
            own[key] = value
        if restore_ap:
            for attack in before['attacks']:
                if attack['owned_morty_id'] == self.morty:
                    attack['pp'] = attack['pp_stat'] = 12
        stock = next(i for i in before['owned_items'] if i['player_id'] == self.a and i['item_id'] == item)
        stock['quantity'] = 1
        self.assertEqual(after, before)
        return body

    def test_request_reservation_survives_item_response(self):
        self.reference()
        self.assert_success()

    def test_orphan_offer_reservation_survives_item_response(self):
        self.reference(offer=True)
        self.assert_success()

    def reset_effect(self, item='ItemSerum', hp=42):
        self.execute([
            f"UPDATE owned_morties SET hp={hp},is_poisoned=1,is_paralysed=1 WHERE owned_morty_id='{self.morty}'",
            f"UPDATE owned_attacks SET pp=3,pp_stat=12 WHERE owned_morty_id='{self.morty}'",
            f"DELETE FROM owned_items WHERE player_id='{self.a}' AND item_id='{item}'",
            f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.a}','{item}',2)",
        ])

    def test_global_stale_owner_and_case_collated_references(self):
        for offer in (False, True):
            with self.subTest(offer=offer):
                self.reference(offer=offer, stale=True, uppercase=True)
                self.reset_effect()
                self.assert_success()
                self.execute([f"DELETE FROM trade_offers WHERE trade_offer_id='{self.offer}'",
                              f"DELETE FROM trades WHERE trade_id='{self.trade}'"])

    def test_unreferenced_legacy_flags_remain_boolean_and_stored(self):
        for flag, expected in (('true', True), ('1', True), ('on', True), ('yes', True), ('y', True), ('Y', True),
                               ('false', False), ('0', False), ('off', False), ('', False)):
            with self.subTest(flag=flag):
                sql(f"UPDATE owned_morties SET is_trading_locked='{flag}' WHERE owned_morty_id='{self.morty}'")
                self.reset_effect()
                self.assert_success(expected=expected)

    def cancel(self, offer):
        path = '/trading/cancel-trade-offer/' if offer else '/trading/cancel-trade/'
        data = {'trade_offer_id': self.offer} if offer else {'trade_id': self.trade}
        req = urllib.request.Request('http://127.0.0.1:8087' + path, json.dumps(data).encode(),
                                     {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + self.a})
        with urllib.request.urlopen(req, timeout=10) as response:
            self.assertEqual(response.status, 200)

    def test_cancellation_retains_reservation_until_last_reference_is_removed(self):
        self.reference()
        self.reference(offer=True)
        self.assert_success()
        self.cancel(offer=True)
        self.reset_effect()
        self.assert_success()
        self.cancel(offer=False)
        self.reset_effect()
        self.assert_success(expected=False)

    def test_thirteen_supported_effects_preserve_reservation_and_exact_mutations(self):
        self.reference()
        cases = [('ItemSerum', 42, 62, 20), ('ItemGreatSerum', 42, 92, 50),
                 ('ItemSensationalSerum', 42, 100, 58), ('ItemPureSerum', 42, 100, 58),
                 ('ItemEasterEgg', 42, 72, 30), ('ItemPumpkin', 42, 72, 30),
                 ('ItemSpicyBBQPizza', 42, 100, 58), ('ItemBreakfastMedley', 42, 100, 58),
                 ('ItemPureHalzinger', 0, 100, 100), ('ItemPurePlutonicRock', 42, 42, 100),
                 ('ItemPoisonCure', 42, 42, 0), ('ItemParalysisCure', 42, 42, 0),
                 ('ItemFullRecover', 42, 100, 0)]
        for item, start_hp, end_hp, effect in cases:
            with self.subTest(item=item):
                self.reset_effect(item, start_hp)
                flags = {}
                if item in ('ItemPoisonCure', 'ItemFullRecover'):
                    flags['is_poisoned'] = 0
                if item in ('ItemParalysisCure', 'ItemFullRecover'):
                    flags['is_paralysed'] = 0
                self.assert_success(item=item, hp=end_hp, effect=effect, flags=flags,
                                    restore_ap=item == 'ItemPurePlutonicRock')

    def assert_rejected_unchanged(self, **overrides):
        before = self.snapshot()
        status, body = self.request(**overrides)
        self.assertGreaterEqual(status, 400)
        self.assertLess(status, 500)
        self.assertEqual(body, {'error': {'code': 'FAILED'}})
        self.assertEqual(self.snapshot(), before)

    def test_invalid_session_foreign_target_and_no_effect_do_not_leak_or_mutate(self):
        self.reference()
        self.assert_rejected_unchanged(session_id=str(uuid.uuid4()))
        self.assert_rejected_unchanged(owned_morty_id=self.foreign)
        self.assert_rejected_unchanged(session_id=self.b)
        sql(f"UPDATE owned_morties SET hp=100 WHERE owned_morty_id='{self.morty}'")
        self.assert_rejected_unchanged()
        sql(f"UPDATE owned_morties SET hp=0 WHERE owned_morty_id='{self.morty}'")
        self.assert_rejected_unchanged()

    def test_missing_exhausted_and_ambiguous_stock_roll_back(self):
        self.reference(offer=True)
        sql(f"UPDATE owned_items SET quantity=0 WHERE player_id='{self.a}'")
        self.assert_rejected_unchanged()
        sql(f"DELETE FROM owned_items WHERE player_id='{self.a}'")
        self.assert_rejected_unchanged()
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.a}','ItemSerum',2),('{self.a}','ItemSerum',2)")
        self.assert_rejected_unchanged()

    def test_serializer_rejects_mismatched_physical_id_owner_and_instance(self):
        self.reference()
        before = self.snapshot()
        code = ("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
                "require '/var/www/html/lib/healing_items.php';"
                f"$m=$pdo->query(\"SELECT * FROM owned_morties WHERE owned_morty_id='{self.morty}'\")->fetch();"
                f"$other=$pdo->query(\"SELECT * FROM owned_morties WHERE owned_morty_id='{self.foreign}'\")->fetch();"
                "$out=[];foreach(['id','player_id','owned_morty_id'] as $key){"
                "$bad=$m;$bad[$key]=$other[$key];try{$out[]=item_updated_morty($pdo,$bad);}"
                "catch(LogicException $e){$out[]='rejected';}}echo json_encode($out);")
        self.assertEqual(json.loads(php(code)), ['rejected'] * 3)
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

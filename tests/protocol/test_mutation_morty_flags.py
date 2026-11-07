"""Heal/learn response flags with isolated additive UUID fixtures; never reseed."""
import base64
import json
import unittest
import uuid

from test_http import php, post, sql


class MutationMortyFlagsTests(unittest.TestCase):
    def execute(self, queries):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
            "$pdo->beginTransaction();foreach(json_decode(base64_decode('" + encoded +
            "'),true) as $q)$pdo->exec($q);$pdo->commit();")

    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.a, self.b, self.morty, self.bench, self.foreign, self.trade, self.offer = [
            str(uuid.uuid4()) for _ in range(7)]
        self.addCleanup(self.cleanup)
        queries = []
        for player in (self.a, self.b):
            queries.append(f"INSERT INTO users (secret,player_id,session_id,username,state,active_deck_id,tags,coins,coupons,permits) VALUES ('{player}','{player}','{player}','MutationFlagsFixture','WORLD',1,'[]',123,4,5)")
        for player, morty in ((self.a, self.morty), (self.a, self.bench), (self.b, self.foreign)):
            queries.extend([
                f"INSERT INTO owned_morties (player_id,owned_morty_id,morty_id,level,xp,hp,hp_stat,attack_stat,defence_stat,speed_stat,variant,is_locked,is_trading_locked,is_poisoned,is_paralysed,evolution_points,xp_lower,xp_upper) VALUES ('{player}','{morty}','MortyDefault',5,125,42,100,12,13,14,'Normal','false','false',1,0,7,100,200)",
                f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{morty}','AttackOutburst',0,3,12)",
            ])
        queries.append(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{self.a}',1,'{json.dumps([self.morty])}'),('{self.a}',2,'{json.dumps([self.bench])}')")
        self.execute(queries)

    def cleanup(self):
        self.execute([
            f"DELETE FROM trade_offers WHERE trade_offer_id='{self.offer}'",
            f"DELETE FROM trades WHERE trade_id='{self.trade}'",
            f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.morty}','{self.bench}','{self.foreign}')",
            *[f"DELETE FROM {table} WHERE player_id IN ('{self.a}','{self.b}')" for table in
              ('trade_refresh_notifications', 'event_queue', 'decks', 'owned_morties', 'users')],
        ])

    def snapshot(self):
        queries = {table: f"SELECT * FROM {table} WHERE player_id IN ('{self.a}','{self.b}') ORDER BY id"
                   for table in ('users', 'decks', 'owned_morties', 'trades', 'trade_offers')}
        queries['attacks'] = f"SELECT owned_morty_id,attack_id,position,pp,pp_stat FROM owned_attacks WHERE owned_morty_id IN ('{self.morty}','{self.bench}','{self.foreign}') ORDER BY owned_morty_id,position"
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        return json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php';"
                              "$out=[];foreach(json_decode(base64_decode('" + encoded +
                              "'),true) as $k=>$q)$out[$k]=$pdo->query($q)->fetchAll();echo json_encode($out);"))

    def reference(self, offer=False, stale=False, uppercase=False):
        owner = self.b if stale else self.a
        morty = self.morty.upper() if uppercase else self.morty
        if offer:
            sql(f"INSERT INTO trade_offers (trade_offer_id,trade_id,player_id,morty_offer_id) VALUES ('{self.offer}','{self.trade}','{owner}','{morty}')")
        else:
            sql(f"INSERT INTO trades (trade_id,player_id,morty_trade_id,requested_morty_id,request_variant) VALUES ('{self.trade}','{owner}','{morty}','any','Normal')")

    def assert_mutation(self, endpoint, locked=False, trading=False,
                        poisoned=True, paralysed=False):
        before = self.snapshot()
        request = {'session_id': self.a}
        if endpoint == 'learn':
            request['owned_morties'] = [{'owned_morty_id': self.morty,
                                         'attack_ids': ['AttackOutburst', 'AttackSlam']},
                                        {'owned_morty_id': self.foreign,
                                         'attack_ids': ['AttackSlam']}]
        status, body = post('/session/heal' if endpoint == 'heal' else
                            '/session/owned_morties/learn-attacks', request)
        self.assertEqual(status, 200, body)
        self.assertEqual(len(body['owned_morties']), 1)
        result = body['owned_morties'][0]
        # Assert mutation boundaries before checking the repaired projection.
        after = self.snapshot()
        if endpoint == 'heal':
            next(m for m in before['owned_morties'] if m['owned_morty_id'] == self.morty)['hp'] = 100
            for attack in before['attacks']:
                if attack['owned_morty_id'] == self.morty:
                    attack['pp'] = attack['pp_stat']
        else:
            before['attacks'] = [a for a in before['attacks'] if a['owned_morty_id'] != self.morty]
            before['attacks'].extend({'owned_morty_id': self.morty, 'attack_id': attack,
                                      'position': pos, 'pp': 8, 'pp_stat': 8}
                                     for pos, attack in enumerate(('AttackOutburst', 'AttackSlam')))
            before['attacks'].sort(key=lambda a: (a['owned_morty_id'], a['position']))
        self.assertEqual(after, before)
        self.assertIs(result['is_locked'], locked)
        self.assertIs(result['is_trading_locked'], trading)
        self.assertIs(result['is_poisoned'], poisoned)
        self.assertIs(result['is_paralysed'], paralysed)
        self.assertIsNone(result['fight_pit_id'])
        self.assertEqual(result['hp'], 100 if endpoint == 'heal' else 42)
        for key, value in {'level': 5, 'xp': 125, 'hp_stat': 100, 'attack_stat': 12,
                           'defence_stat': 13, 'speed_stat': 14, 'evolution_points': 7,
                           'xp_lower': 100, 'xp_upper': 200}.items():
            self.assertEqual(result[key], value)
        expected_attacks = [{key: value for key, value in attack.items() if key != 'owned_morty_id'}
                            for attack in before['attacks'] if attack['owned_morty_id'] == self.morty]
        if endpoint == 'learn':
            expected_attacks = [{'attack_id': attack, 'position': pos, 'pp': 8, 'pp_stat': 8}
                                for pos, attack in enumerate(('AttackOutburst', 'AttackSlam'))]
            self.assertEqual((body['coins'], body['coupons'], body['permits']), (123, 4, 5))
        self.assertEqual(result['owned_attacks'], expected_attacks)
        status, details = post('/session/player-details', {'session_id': self.a})
        self.assertEqual(status, 200)
        known = next(m for m in details['owned_morties'] if m['owned_morty_id'] == self.morty)
        self.assertEqual(result, known)

    def test_learn_false_strings_are_json_false(self):
        self.assert_mutation('learn')

    def test_heal_false_strings_are_json_false(self):
        self.assert_mutation('heal')

    def test_heal_projects_legacy_active_party_trade_reference(self):
        # Deliberately model a durable legacy reference to an active party member.
        self.reference()
        self.assert_mutation('heal', trading=True)

    def test_legacy_flags_are_booleans_without_rewriting_storage(self):
        for endpoint in ('learn', 'heal'):
            for raw, expected in (('true', True), ('1', True), ('yes', True), ('y', True), ('on', True),
                                  ('false', False), ('0', False), ('off', False), ('', False)):
                with self.subTest(endpoint=endpoint, raw=raw):
                    sql(f"UPDATE owned_morties SET hp=42,is_locked='{raw}',is_trading_locked='{raw}',is_poisoned={int(expected)},is_paralysed={int(not expected)} WHERE owned_morty_id='{self.morty}'")
                    self.assert_mutation(endpoint, locked=expected, trading=expected,
                                         poisoned=expected, paralysed=not expected)

    def test_global_trade_references_override_stored_zero(self):
        for endpoint in ('learn', 'heal'):
            for offer, stale, uppercase in ((False, False, False), (True, False, False),
                                            (False, True, True), (True, True, True)):
                with self.subTest(endpoint=endpoint, offer=offer, stale=stale, uppercase=uppercase):
                    sql(f"UPDATE owned_morties SET hp=42,is_trading_locked='0' WHERE owned_morty_id='{self.morty}'")
                    self.reference(offer=offer, stale=stale, uppercase=uppercase)
                    try:
                        self.assert_mutation(endpoint, trading=True)
                    finally:
                        self.execute([f"DELETE FROM trade_offers WHERE trade_offer_id='{self.offer}'",
                                      f"DELETE FROM trades WHERE trade_id='{self.trade}'"])


if __name__ == '__main__':
    unittest.main()

"""WORLD status cures with disposable UUID fixtures; no account reseeding."""
from concurrent.futures import ThreadPoolExecutor
import subprocess
import threading
import unittest
import uuid

from test_http import COMPOSE, ROOT, php, post, sql
import test_use_item


class StatusCureMigrationTests(unittest.TestCase):
    def test_migration_preserves_records_defaults_and_is_repeatable_on_copy(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_DB_NAME');"), 'db:pocket_mortys')
        database = 'status_migration_' + uuid.uuid4().hex

        def mysql(statement):
            return subprocess.check_output(COMPOSE + ['exec', '-T', 'db', 'sh', '-c',
                'exec mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --batch --skip-column-names'],
                input=statement, text=True, cwd=ROOT)

        mysql(f'CREATE DATABASE {database};')
        try:
            mysql(f'USE {database};\n' + (ROOT/'pocket_mortys.sql').read_text())
            mysql(f"USE {database}; INSERT INTO owned_morties (owned_morty_id,hp,hp_stat) "
                  "VALUES ('existing',37,100);")
            before = mysql(f'USE {database}; SELECT id,owned_morty_id,hp,hp_stat FROM owned_morties;')
            migration = (ROOT/'tools/research/server/migrations/003-morty-ailments.sql').read_text()
            mysql(f'USE {database};\n' + migration + '\n' + migration)
            self.assertEqual(mysql(f'USE {database}; SELECT id,owned_morty_id,hp,hp_stat FROM owned_morties;'), before)
            self.assertEqual(mysql(f'USE {database}; SELECT is_poisoned,is_paralysed FROM owned_morties;').strip(), '0\t0')
            mysql(f"USE {database}; UPDATE owned_morties SET is_poisoned=1,is_paralysed=1;\n" + migration)
            self.assertEqual(mysql(f'USE {database}; SELECT is_poisoned,is_paralysed FROM owned_morties;').strip(), '1\t1')
            mysql(f"USE {database}; INSERT INTO owned_morties (owned_morty_id) VALUES ('new');")
            self.assertEqual(mysql(f"USE {database}; SELECT is_poisoned,is_paralysed FROM owned_morties "
                                   "WHERE owned_morty_id='new';").strip(), '0\t0')
            self.assertEqual(mysql(f"USE {database}; SELECT COUNT(*) FROM information_schema.COLUMNS "
                                   f"WHERE TABLE_SCHEMA='{database}' AND TABLE_NAME='owned_morties' "
                                   "AND COLUMN_NAME IN ('is_poisoned','is_paralysed') AND IS_NULLABLE='NO';").strip(), '2')
        finally:
            mysql(f'DROP DATABASE {database};')


class StatusCureTests(unittest.TestCase):
    def setUp(self):
        # Compose the established fixture helper without inheriting its test cases.
        self.fixture = test_use_item.UseItemTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.players, self.morties = self.fixture.players, self.fixture.morties
        self.addCleanup(lambda: sql(f"DELETE FROM decks WHERE player_id='{self.players[0]}'"))
        sql(f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) "
            f"VALUES ('{self.players[0]}',1,'[\"{self.morties[0]}\",\"{self.morties[2]}\"]')")
        for item in ('ItemPoisonCure', 'ItemParalysisCure'):
            sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.players[0]}','{item}',2)")

    def request(self, **overrides):
        return self.fixture.request(item_id=overrides.pop('item_id', 'ItemPoisonCure'), **overrides)

    def snapshot(self):
        result = self.fixture.snapshot()
        players = "','".join(self.players)
        result['decks'] = sql(f"SELECT * FROM decks WHERE player_id IN ('{players}') ORDER BY id")
        result['events'] = sql(f"SELECT * FROM event_queue WHERE player_id IN ('{players}') ORDER BY id")
        return result

    def status(self, poisoned=1, paralysed=1, hp=35):
        sql(f"UPDATE owned_morties SET is_poisoned={poisoned},is_paralysed={paralysed},hp={hp} "
            f"WHERE owned_morty_id='{self.morties[0]}'")

    def assert_rejected_unchanged(self, code=409, **overrides):
        before = self.snapshot()
        status, body = self.request(**overrides)
        self.assertEqual((status, body), (code, {'error': {'code': 'FAILED'}}))
        self.assertEqual(self.snapshot(), before)

    def test_each_cure_clears_only_its_flag_at_damaged_and_full_hp(self):
        for item, flag in (('ItemPoisonCure', 'is_poisoned'), ('ItemParalysisCure', 'is_paralysed')):
            for hp in (35, 100):
                with self.subTest(item=item, hp=hp):
                    self.status(hp=hp)
                    before = self.snapshot()
                    status, body = self.request(item_id=item)
                    self.assertEqual(status, 200)
                    self.assertEqual(set(body), {'owned_morty_id', 'item_id', 'is_success', 'effect_value',
                                                'owned_morties', 'owned_items', 'attacks_to_learn'})
                    self.assertIs(body['is_success'], True)
                    self.assertEqual(body['owned_morty_id'], self.morties[0])
                    self.assertEqual(body['item_id'], item)
                    self.assertEqual(body['effect_value'], 0)
                    self.assertIs(type(body['effect_value']), int)
                    self.assertEqual(body['attacks_to_learn'], [])
                    changed = body['owned_morties'][0]
                    self.assertIs(changed[flag], False)
                    other = 'is_paralysed' if flag == 'is_poisoned' else 'is_poisoned'
                    self.assertIs(changed[other], True)
                    self.assertEqual(changed['hp'], hp)
                    before['morties'][0][flag] = 0
                    inventory = next(row for row in before['items'] if row['item_id'] == item)
                    inventory['quantity'] -= 1
                    self.assertEqual(body['owned_items'], [{'item_id': item, 'quantity': inventory['quantity']}])
                    self.assertEqual(self.snapshot(), before)
                    _, details = post('/session/player-details', {'session_id': self.players[0]})
                    self.assertEqual(body['owned_morties'], [next(m for m in details['owned_morties']
                                                               if m['owned_morty_id'] == self.morties[0])])

    def test_no_affliction_wrong_cure_and_fainted_never_spend(self):
        for poisoned, paralysed, hp, item in ((0, 0, 35, 'ItemPoisonCure'),
                                            (0, 1, 35, 'ItemPoisonCure'),
                                            (1, 0, 35, 'ItemParalysisCure'),
                                            (1, 1, 0, 'ItemPoisonCure'),
                                            (1, 1, 0, 'ItemParalysisCure')):
            self.status(poisoned, paralysed, hp)
            self.assert_rejected_unchanged(item_id=item)

    def test_retry_after_one_effect_does_not_spend_remaining_stock(self):
        self.status()
        self.assertEqual(self.request()[0], 200)
        self.assert_rejected_unchanged()

    def test_existing_hp_and_ap_items_preserve_and_return_status_flags(self):
        self.status()
        for item in ('ItemSerum', 'ItemPurePlutonicRock', 'ItemPureHalzinger'):
            with self.subTest(item=item):
                if item != 'ItemSerum':
                    sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.players[0]}','{item}',1)")
                if item == 'ItemPureHalzinger':
                    self.status(hp=0)
                status, body = self.request(item_id=item)
                self.assertEqual(status, 200)
                self.assertIs(body['owned_morties'][0]['is_poisoned'], True)
                self.assertIs(body['owned_morties'][0]['is_paralysed'], True)
                self.assertEqual(sql(f"SELECT is_poisoned,is_paralysed FROM owned_morties "
                                     f"WHERE owned_morty_id='{self.morties[0]}'"),
                                 [{'is_poisoned': 1, 'is_paralysed': 1}])

    def test_stock_auth_ownership_and_world_guards(self):
        self.status()
        self.assert_rejected_unchanged(401, session_id=str(uuid.uuid4()))
        self.assert_rejected_unchanged(404, owned_morty_id=self.morties[1])
        self.assert_rejected_unchanged(404, owned_morty_id=str(uuid.uuid4()))
        sql(f"UPDATE owned_items SET quantity=0 WHERE player_id='{self.players[0]}' AND item_id='ItemPoisonCure'")
        self.assert_rejected_unchanged()
        sql(f"DELETE FROM owned_items WHERE player_id='{self.players[0]}' AND item_id='ItemPoisonCure'")
        self.assert_rejected_unchanged()
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.players[0]}','ItemPoisonCure',2)")
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.players[0]}','ItemPoisonCure',2)")
        self.assert_rejected_unchanged()
        sql(f"UPDATE users SET state='BATTLE' WHERE player_id='{self.players[0]}'")
        self.assert_rejected_unchanged()
        sql(f"UPDATE users SET state='WORLD' WHERE player_id='{self.players[0]}'")
        sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,player_active_morty,state) "
            f"VALUES ('{uuid.uuid4()}','{self.players[0]}','{self.players[1]}','{self.morties[0]}','ACTIVE')")
        self.assert_rejected_unchanged()

    def test_ambiguous_owned_target_is_not_charged(self):
        self.status()
        sql(f"INSERT INTO owned_morties (player_id,owned_morty_id,hp,hp_stat,is_poisoned) "
            f"VALUES ('{self.players[0]}','{self.morties[0]}',35,100,1)")
        self.assert_rejected_unchanged(404)

    def test_foreign_duplicate_owned_id_rejects_cures_and_ap_without_leaking_attacks(self):
        self.status()
        sql(f"INSERT INTO owned_morties (player_id,owned_morty_id,hp,hp_stat,is_poisoned,is_paralysed) "
            f"VALUES ('{self.players[1]}','{self.morties[0]}',70,100,1,1)")
        sql(f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) "
            f"VALUES ('{self.morties[0]}','AttackLick',3,1,10)")
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) "
            f"VALUES ('{self.players[0]}','ItemPurePlutonicRock',1)")
        for item in ('ItemPoisonCure', 'ItemParalysisCure', 'ItemPurePlutonicRock', 'ItemSerum'):
            with self.subTest(item=item):
                self.assert_rejected_unchanged(item_id=item)

    def test_concurrent_last_item_has_one_effect(self):
        self.status()
        sql(f"UPDATE owned_items SET quantity=1 WHERE player_id='{self.players[0]}' AND item_id='ItemPoisonCure'")
        before = self.snapshot()
        barrier = threading.Barrier(2)

        def use(_):
            barrier.wait(timeout=5)
            return self.request()

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(use, range(2)))
        self.assertEqual(sorted(status for status, _ in responses), [200, 409])
        before['morties'][0]['is_poisoned'] = 0
        next(row for row in before['items'] if row['item_id'] == 'ItemPoisonCure')['quantity'] = 0
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

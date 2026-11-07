"""UUID-isolated battle-only Mr. Meeseeks regressions; never reseed accounts."""
from concurrent.futures import ThreadPoolExecutor
import json
import threading
import unittest
import uuid

import test_battle_lifecycle
from test_http import php, post, sql


ITEM = 'ItemMrMeeseek'


class BattleMeeseeksTests(unittest.TestCase):
    def setUp(self):
        self.f = test_battle_lifecycle.BattleLifecycleTests(methodName='runTest')
        self.f.setUp()
        self.addCleanup(lambda: self.assertTrue(self.f.doCleanups()))
        self.bench, self.storage = str(uuid.uuid4()), str(uuid.uuid4())
        self.addCleanup(lambda: sql(f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.bench}','{self.storage}')"))
        self.f.execute([
            f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat) VALUES ('{self.bench}','{self.f.player}','Morty',100,100),('{self.storage}','{self.f.player}','Morty',100,100)",
            f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{self.bench}','AttackLick',0,5,5),('{self.storage}','AttackLick',0,5,5)",
            f"UPDATE decks SET owned_morty_ids='[\"{self.f.morty}\",\"{self.bench}\"]' WHERE player_id='{self.f.player}'",
        ])

    def stock(self, quantity=2):
        quantity = 'NULL' if quantity is None else str(quantity)
        self.f.execute([
            f"DELETE FROM owned_items WHERE player_id='{self.f.player}' AND item_id='{ITEM}'",
            f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.f.player}','{ITEM}',{quantity})",
        ])

    def snapshot(self):
        result = self.f.snapshot()
        result['bench_attacks'] = sql(f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.bench}','{self.storage}') ORDER BY id")
        return result

    def item(self, **changes):
        request = dict(move_id=ITEM, owned_morty_id=self.f.morty)
        request.update(changes)
        return self.f.move('ITEM', **request)

    def rejected(self, action=None, status=409):
        before = self.snapshot()
        response = (action or self.item)()
        self.assertEqual(response[0], status, response)
        self.assertIs(response[1]['success'], False)
        self.assertEqual(self.snapshot(), before)

    def assert_win(self, before, actor=None, previous_turns=0, quantity=1):
        actor = actor or self.f.morty
        after = self.snapshot()
        battle = next(b for b in after['battles'] if b['battle_id'] == self.f.battle)
        old_battle = next(b for b in before['battles'] if b['battle_id'] == self.f.battle)
        self.assertGreaterEqual(battle['updated_at'], old_battle['updated_at'])
        expected = dict(old_battle, state='COMPLETED', winner=self.f.player,
                        opponent_hp=0, move_deadline=None, updated_at=battle['updated_at'])
        self.assertEqual(battle, expected)
        self.assertEqual(battle['player_active_morty'], actor)
        events = [e for e in after['events'] if e['event_name'] == 'battle:turn-result']
        self.assertEqual(len(events), previous_turns + 1)
        event = events[-1]
        self.assertEqual((event['room_id'], event['player_id'], event['only_show_to_player_id']),
                         (self.f.room, self.f.player, self.f.player))
        result = json.loads(event['battle_turn_result'])
        self.assertEqual((result['battle_id'], result['outcome']), (self.f.battle, 'WIN'))
        self.assertEqual(result['turn_datas'], [{
            'type': 'ITEM', 'owned_morty_id': actor, 'item_id': ITEM,
            'success': True, 'effect_value': old_battle['opponent_hp'],
            'attacker_player_id': self.f.player, 'defender_player_id': battle['opponent_id'],
            'attacker_morty_datas': [],
            'defender_morty_datas': [{'owned_morty_id': self.f.wild, 'hp': 0}],
        }])
        self.assertIs(result['turn_datas'][0]['success'], True)
        self.assertIs(type(result['turn_datas'][0]['effect_value']), int)
        player_data = result['player_datas']['player']
        self.assertEqual(player_data['owned_items'], [{'item_id': ITEM, 'quantity': quantity}])
        self.assertEqual(player_data['xp_datas'], [])
        self.assertEqual(player_data['rewards'], [])
        self.assertEqual(player_data['attacks_to_learn'], [])
        self.assertEqual(player_data['move_log']['count'], {'ITEM': 1})
        self.assertEqual(player_data['move_log']['last_move_type'], 'ITEM')
        for key in ('morties', 'attacks', 'bench_attacks', 'decks', 'rooms'):
            self.assertEqual(after[key], before[key], key)
        expected_items = [dict(i) for i in before['items']]
        next(i for i in expected_items if i['player_id'] == self.f.player and i['item_id'] == ITEM)['quantity'] -= 1
        self.assertEqual(after['items'], expected_items)
        expected_users = [dict(u) for u in before['users']]
        expected_owner = next(u for u in expected_users if u['player_id'] == self.f.player)
        owner = next(u for u in after['users'] if u['player_id'] == self.f.player)
        self.assertGreaterEqual(owner['last_seen'], expected_owner['last_seen'])
        expected_owner.update(state='WORLD', last_seen=owner['last_seen'])
        self.assertEqual(after['users'], expected_users)
        retained = [e for e in before['events'] if e['event_name'] != 'room:wild-morty-added']
        self.assertEqual([e for e in after['events'] if e['id'] in {old['id'] for old in retained}], retained)
        added = [e for e in after['events'] if e['id'] not in {old['id'] for old in before['events']}]
        self.assertEqual([e['event_name'] for e in added],
                         ['room:wild-morty-removed', 'room:user-state-changed', 'battle:turn-result'])
        self.assertEqual(added[0]['wild_morty_id'], self.f.wild)
        self.f.assert_world(after, spawn=False)
        return after

    def test_native_active_actor_wins_consumes_one_and_rejects_replay(self):
        self.stock()
        self.f.begin()
        sql(f"UPDATE battles SET opponent_hp=137 WHERE battle_id='{self.f.battle}'")
        before = self.snapshot()
        self.assertEqual(self.item(), (200, {'success': True}))
        self.assert_win(before)
        self.rejected()

    def test_after_switch_requires_current_active_actor(self):
        self.stock()
        self.f.begin()
        self.assertEqual(self.f.move('SWITCH', move_id=self.bench), (200, {'success': True}))
        self.rejected(status=403)
        before = self.snapshot()
        self.assertEqual(self.item(owned_morty_id=self.bench), (200, {'success': True}))
        self.assert_win(before, actor=self.bench, previous_turns=1)

    def test_last_box_reports_absolute_zero_and_cannot_be_replayed(self):
        self.stock(1)
        self.f.begin()
        before = self.snapshot()
        self.assertEqual(self.item(), (200, {'success': True}))
        self.assert_win(before, quantity=0)
        self.rejected()

    def test_bench_foreign_storage_and_changed_deck_cannot_act(self):
        self.stock()
        self.f.begin()
        for actor in (self.bench, self.storage, self.f.other_morty):
            with self.subTest(actor=actor):
                self.rejected(lambda: self.item(owned_morty_id=actor), 403)
        sql(f"UPDATE decks SET owned_morty_ids='[\"{self.storage}\"]' WHERE player_id='{self.f.player}'")
        self.rejected(lambda: self.item(owned_morty_id=self.storage), 403)

    def test_invalid_session_owner_battle_and_identifiers_do_not_write(self):
        self.stock()
        self.f.begin()
        for changes, status in [
                ({'session_id': str(uuid.uuid4())}, 401),
                ({'session_id': self.f.other_session}, 403),
                ({'battle_id': str(uuid.uuid4())}, 404),
                ({'session_id': ''}, 400), ({'owned_morty_id': None}, 400),
                ({'owned_morty_id': []}, 400), ({'move_id': None}, 400)]:
            with self.subTest(changes=changes):
                self.rejected(lambda: self.item(**changes), status)

    def test_missing_depleted_invalid_and_duplicate_stock_are_atomic(self):
        self.f.begin()
        self.rejected()
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.f.other_player}','{ITEM}',2)")
        self.rejected()
        for quantity in (0, -1, None):
            with self.subTest(quantity=quantity):
                self.stock(quantity)
                self.rejected()
        self.stock()
        sql(f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{self.f.player}','{ITEM}',2)")
        self.rejected()

    def test_fainted_actor_and_stale_hp_cache_are_atomic(self):
        self.stock()
        self.f.begin()
        sql(f"UPDATE owned_morties SET hp=90 WHERE owned_morty_id='{self.f.morty}'")
        self.rejected()
        self.f.execute([
            f"UPDATE owned_morties SET hp=0 WHERE owned_morty_id='{self.f.morty}'",
            f"UPDATE battles SET player_hp=0 WHERE battle_id='{self.f.battle}'",
        ])
        self.rejected()

    def test_missing_foreign_and_ambiguous_active_ownership_are_atomic(self):
        self.stock()
        self.f.begin()
        sql(f"UPDATE owned_morties SET player_id='{self.f.other_player}' WHERE owned_morty_id='{self.f.morty}'")
        self.rejected(status=403)
        sql(f"UPDATE owned_morties SET player_id='{self.f.player}' WHERE owned_morty_id='{self.f.morty}'")
        sql(f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat) VALUES ('{self.f.morty}','{self.f.other_player}','Morty',100,100)")
        self.rejected()
        sql(f"DELETE FROM owned_morties WHERE owned_morty_id='{self.f.morty}'")
        self.rejected()

    def test_invalid_enemy_hp_is_rejected_without_a_charge(self):
        self.stock()
        self.f.begin()
        # The signed INT schema admits NULL/negative corruption, but no overflow.
        for hp in ('NULL', '0', '-1'):
            with self.subTest(hp=hp):
                sql(f"UPDATE battles SET opponent_hp={hp} WHERE battle_id='{self.f.battle}'")
                self.rejected()

    def test_changed_room_wrong_state_and_wrong_origin_do_not_write(self):
        self.stock()
        self.f.begin()
        mutations = [
            (f"UPDATE users SET room_id='{self.f.other_room}' WHERE player_id='{self.f.player}'",
             f"UPDATE users SET room_id='{self.f.room}' WHERE player_id='{self.f.player}'"),
            (f"UPDATE users SET state='WORLD' WHERE player_id='{self.f.player}'",
             f"UPDATE users SET state='BATTLE' WHERE player_id='{self.f.player}'"),
            (f"UPDATE event_queue SET room_id='{self.f.other_room}' WHERE player_id='{self.f.player}' AND event_name='battle:start'",
             f"UPDATE event_queue SET room_id='{self.f.room}' WHERE player_id='{self.f.player}' AND event_name='battle:start'"),
            (f"UPDATE event_queue SET battle_start=JSON_SET(battle_start,'$.battle_type','PvP') WHERE player_id='{self.f.player}' AND event_name='battle:start'",
             f"UPDATE event_queue SET battle_start=JSON_SET(battle_start,'$.battle_type','PvWM') WHERE player_id='{self.f.player}' AND event_name='battle:start'"),
        ]
        for mutate, restore in mutations:
            with self.subTest(mutate=mutate):
                sql(mutate)
                self.rejected()
                sql(restore)

    def test_missing_initial_roster_and_ambiguous_private_origin_are_atomic(self):
        self.stock()
        self.f.begin()
        sql(f"INSERT INTO event_queue (room_id,event_name,player_id,only_show_to_player_id,battle_start) SELECT room_id,event_name,player_id,only_show_to_player_id,battle_start FROM event_queue WHERE room_id='{self.f.room}' AND event_name='battle:start'")
        self.rejected()
        sql(f"DELETE FROM event_queue WHERE id=(SELECT id FROM (SELECT MAX(id) id FROM event_queue WHERE room_id='{self.f.room}' AND event_name='battle:start') latest)")
        sql(f"UPDATE event_queue SET battle_start=JSON_REMOVE(battle_start,'$.player.owned_morties') WHERE room_id='{self.f.room}' AND event_name='battle:start'")
        self.rejected()

    def test_ambiguous_spawn_and_second_active_claim_are_atomic(self):
        self.stock()
        self.f.begin()
        sql(f"INSERT INTO event_queue (room_id,event_name,wild_morty_id,morty_id,state,placement,variant) VALUES ('{self.f.room}','room:wild-morty-added','{self.f.wild}','Morty','BATTLE','0,0','Normal')")
        self.rejected()
        sql(f"DELETE FROM event_queue WHERE id=(SELECT id FROM (SELECT MAX(id) id FROM event_queue WHERE room_id='{self.f.room}' AND event_name='room:wild-morty-added') latest)")
        duplicate = str(uuid.uuid4())
        sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,opponent_active_morty,state) VALUES ('{duplicate}','{self.f.other_player}','{self.f.player}','{self.f.wild}','ACTIVE')")
        self.rejected()

    def test_missing_wrong_state_and_foreign_private_spawn_are_atomic(self):
        self.stock()
        self.f.begin()
        predicate = f"room_id='{self.f.room}' AND event_name='room:wild-morty-added' AND wild_morty_id='{self.f.wild}'"
        sql(f"UPDATE event_queue SET state='WORLD' WHERE {predicate}")
        self.rejected()
        sql(f"UPDATE event_queue SET state='BATTLE',only_show_to_player_id='{self.f.other_player}' WHERE {predicate}")
        self.rejected(status=403)
        sql(f"DELETE FROM event_queue WHERE {predicate}")
        self.rejected()

    def test_expired_timer_abandons_without_item_or_damage(self):
        self.stock()
        self.f.begin()
        self.assertEqual(post('/session/battle/ready', dict(session_id=self.f.session, battle_id=self.f.battle)),
                         (200, {'success': True}))
        sql(f"UPDATE battles SET move_deadline=UTC_TIMESTAMP(6)-INTERVAL 1 SECOND WHERE battle_id='{self.f.battle}'")
        before = self.snapshot()
        self.assertEqual(self.item()[0], 409)
        after = self.snapshot()
        for key in ('morties', 'attacks', 'bench_attacks', 'items', 'decks', 'rooms'):
            self.assertEqual(after[key], before[key], key)
        self.assertGreaterEqual(after['battles'][0]['updated_at'], before['battles'][0]['updated_at'])
        self.assertEqual(after['battles'], [dict(before['battles'][0], state='CANCELLED', move_deadline=None,
                         updated_at=after['battles'][0]['updated_at'])])
        result = self.f.turn(after)
        self.assertEqual((result['outcome'], result['turn_datas']), ('ABANDONED', []))
        self.f.assert_world(after)
        self.rejected()

    def test_private_result_failure_rolls_back_charge_win_and_public_events(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.stock()
        self.f.begin()
        trigger = 'research_meeseeks_' + uuid.uuid4().hex
        self.addCleanup(lambda: sql(f'DROP TRIGGER IF EXISTS {trigger}'))
        sql(f"CREATE TRIGGER {trigger} BEFORE INSERT ON event_queue FOR EACH ROW "
            f"BEGIN IF NEW.player_id = '{self.f.player}' AND NEW.event_name = 'battle:turn-result' THEN "
            "SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Research Meeseeks fault'; END IF; END")
        try:
            self.rejected(status=500)
        finally:
            sql(f'DROP TRIGGER IF EXISTS {trigger}')

    def test_concurrent_requests_commit_one_terminal_and_one_charge(self):
        self.stock()
        self.f.begin()
        before = self.snapshot()
        barrier = threading.Barrier(2)
        def request():
            barrier.wait()
            return self.item()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: request(), range(2)))
        self.assertEqual(sorted(response[0] for response in responses), [200, 409])
        self.assert_win(before)

    def test_world_route_is_unsupported_without_mutation(self):
        self.stock()
        before = self.snapshot()
        response = post('/session/use-item', dict(session_id=self.f.session,
                        owned_morty_id=self.f.morty, item_id=ITEM))
        self.assertEqual(response, (400, {'error': {'code': 'FAILED'}}))
        self.assertEqual(self.snapshot(), before)


if __name__ == '__main__':
    unittest.main()

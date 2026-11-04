"""Additive UUID battle lifecycle regressions; never reseed shared accounts."""
from concurrent.futures import ThreadPoolExecutor
import base64
import json
import unittest
import uuid
import urllib.request

from test_http import php, post, sql


class BattleLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.room, self.other_room, self.player, self.other_player, self.session, self.other_session, self.morty, self.other_morty, self.wild = [str(uuid.uuid4()) for _ in range(9)]
        self.battle = None
        self.addCleanup(self.cleanup)
        queries = [f"INSERT INTO room_ids (room_id, world_id, zone_id) VALUES ('{self.room}','battle-test','[1,1]'), ('{self.other_room}','battle-test','[1,1]')"]
        for player, session, morty in ((self.player, self.session, self.morty), (self.other_player, self.other_session, self.other_morty)):
            queries.extend([
                f"INSERT INTO users (secret,player_id,session_id,username,room_id,active_deck_id,state,tags) VALUES ('{session}','{player}','{session}','Lifecycle','{self.room}',1,'WORLD','[]')",
                f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat) VALUES ('{morty}','{player}','Morty',100,100)",
                f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{morty}','AttackLick',0,5,5)",
                f"INSERT INTO decks (player_id,deck_id,owned_morty_ids) VALUES ('{player}',1,'[\"{morty}\"]')",
                f"INSERT INTO owned_items (player_id,item_id,quantity) VALUES ('{player}','ItemMortyChip',10)",
            ])
        queries.append(f"INSERT INTO event_queue (room_id,event_name,wild_morty_id,morty_id,state,placement,variant) VALUES ('{self.room}','room:wild-morty-added','{self.wild}','Morty','WORLD','0,0','Normal')")
        self.execute(queries)

    def execute(self, queries):
        encoded = base64.b64encode(json.dumps(queries).encode()).decode()
        php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; $pdo->beginTransaction(); foreach(json_decode(base64_decode('" + encoded + "'),true) as $query) $pdo->exec($query); $pdo->commit();")

    def cleanup(self):
        # Every predicate is restricted to this fixture's fresh UUIDs.
        self.execute([
            f"DELETE FROM event_queue WHERE room_id IN ('{self.room}','{self.other_room}')",
            f"DELETE FROM battles WHERE player_id IN ('{self.player}','{self.other_player}')",
            f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.morty}','{self.other_morty}')",
            *[f"DELETE FROM {table} WHERE player_id IN ('{self.player}','{self.other_player}')" for table in ('owned_items','owned_morties','decks','users')],
            f"DELETE FROM room_ids WHERE room_id IN ('{self.room}','{self.other_room}')",
        ])

    def start(self, **changes):
        request = dict(session_id=self.session, wild_morty_id=self.wild)
        request.update(changes)
        return post('/session/battle-wild-morty', request)

    def begin(self):
        self.assertEqual(self.start(), (200, {'success': True}))
        rows = sql(f"SELECT * FROM battles WHERE player_id='{self.player}'")
        self.assertEqual(len(rows), 1)
        self.battle = rows[0]['battle_id']
        return rows[0]

    def move(self, kind='ATTACK', **changes):
        request = dict(session_id=self.session, battle_id=self.battle, type=kind, owned_morty_id=self.morty, move_id='AttackLick')
        request.update(changes)
        return post('/session/battle/move', request)

    def snapshot(self):
        queries = {
            'users': f"SELECT * FROM users WHERE player_id IN ('{self.player}','{self.other_player}') ORDER BY player_id",
            'morties': f"SELECT * FROM owned_morties WHERE player_id IN ('{self.player}','{self.other_player}') ORDER BY owned_morty_id",
            'attacks': f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ('{self.morty}','{self.other_morty}') ORDER BY id",
            'items': f"SELECT * FROM owned_items WHERE player_id IN ('{self.player}','{self.other_player}') ORDER BY id",
            'decks': f"SELECT * FROM decks WHERE player_id IN ('{self.player}','{self.other_player}') ORDER BY id",
            'rooms': f"SELECT * FROM room_ids WHERE room_id IN ('{self.room}','{self.other_room}') ORDER BY room_id",
            'battles': f"SELECT * FROM battles WHERE player_id IN ('{self.player}','{self.other_player}') ORDER BY battle_id",
            'events': f"SELECT * FROM event_queue WHERE room_id IN ('{self.room}','{self.other_room}') ORDER BY id",
        }
        encoded = json.dumps(queries).replace('\\', '\\\\').replace("'", "\\'")
        return json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; $queries=json_decode('" + encoded + "',true); $pdo->beginTransaction(); $out=[]; foreach($queries as $key=>$query) $out[$key]=$pdo->query($query)->fetchAll(); $pdo->commit(); echo json_encode($out);"))

    def turn(self, snapshot):
        events = [e for e in snapshot['events'] if e['event_name'] == 'battle:turn-result']
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]['player_id'], self.player)
        self.assertEqual(events[0]['room_id'], self.room)
        result = json.loads(events[0]['battle_turn_result'])
        self.assertEqual(result['battle_id'], self.battle)
        return result

    def test_run_persists_terminal_state_and_rejects_replay(self):
        self.begin()
        self.assertEqual(self.move('RUN'), (200, {'success': True}))
        after = self.snapshot()
        battle = after['battles'][0]
        self.assertEqual(battle['state'], 'CANCELLED')
        self.assertIsNone(battle['winner'])
        self.assertEqual(self.turn(after)['outcome'], 'RUN')
        self.assert_world(after)
        self.assertEqual(self.move('RUN')[0], 409)
        self.assertEqual(self.snapshot(), after)

    def test_android_run_allows_null_move_id_but_attack_requires_strings(self):
        self.begin()
        self.assert_rejected_unchanged(lambda: self.move(move_id=None), 400)
        self.assert_rejected_unchanged(lambda: self.move(owned_morty_id=None), 400)
        self.assertEqual(self.move('RUN', move_id=None), (200, {'success': True}))
        after = self.snapshot()
        self.assertEqual(after['battles'][0]['state'], 'CANCELLED')
        self.assertEqual(self.turn(after)['outcome'], 'RUN')
        self.assert_world(after)

    def assert_rejected_unchanged(self, action, status):
        before = self.snapshot()
        response = action()
        self.assertEqual(response[0], status, response)
        self.assertFalse(response[1]['success'])
        self.assertEqual(self.snapshot(), before)
        return response[1]

    def assert_world(self, snapshot, spawn=True):
        player = next(u for u in snapshot['users'] if u['player_id'] == self.player)
        self.assertEqual(player['state'], 'WORLD')
        wild = [e for e in snapshot['events'] if e['event_name'] == 'room:wild-morty-added']
        self.assertEqual(len(wild), int(spawn))
        if spawn:
            self.assertEqual(wild[0]['state'], 'WORLD')
        changes = [e for e in snapshot['events'] if e['event_name'] == 'room:user-state-changed']
        self.assertEqual(changes[-1]['state'], 'WORLD')

    def test_start_claims_spawn_and_player_with_private_snapshot(self):
        battle = self.begin()
        after = self.snapshot()
        self.assertEqual(battle['player_active_morty'], self.morty)
        self.assertEqual(battle['opponent_active_morty'], self.wild)
        self.assertEqual(battle['opponent_hp'], 1)
        self.assertEqual(next(u for u in after['users'] if u['player_id'] == self.player)['state'], 'BATTLE')
        self.assertEqual(next(e for e in after['events'] if e['event_name'] == 'room:wild-morty-added')['state'], 'BATTLE')
        event = next(e for e in after['events'] if e['event_name'] == 'battle:start')
        self.assertEqual((event['player_id'], event['only_show_to_player_id']), (self.player, self.player))
        payload = json.loads(event['battle_start'])
        self.assertEqual(payload['battle_id'], self.battle)
        self.assertEqual(payload['player']['active_owned_morty'], self.morty)
        self.assertEqual(payload['opponent']['active_owned_morty'], self.wild)
        self.assert_rejected_unchanged(self.start, 409)
        self.assert_rejected_unchanged(lambda: self.start(session_id=self.other_session), 409)
        other_wild = str(uuid.uuid4())
        sql(f"INSERT INTO event_queue (room_id,event_name,wild_morty_id,morty_id,state,placement,variant) VALUES ('{self.room}','room:wild-morty-added','{other_wild}','Morty','WORLD','1,1','Normal')")
        self.assert_rejected_unchanged(lambda: self.start(wild_morty_id=other_wild), 409)

    def test_continue_persists_exact_action_hp_and_pp(self):
        self.begin()
        sql(f"UPDATE battles SET opponent_hp=100 WHERE battle_id='{self.battle}'")
        before = self.snapshot()
        self.assertEqual(self.move(), (200, {'success': True}))
        after = self.snapshot()
        battle = after['battles'][0]
        turn = self.turn(after)
        self.assertEqual(turn['outcome'], 'CONTINUE')
        self.assertEqual(battle['state'], 'ACTIVE')
        self.assertEqual(battle['opponent_hp'], 80)
        self.assertIn(battle['player_hp'], (97, 98, 99))
        player_action, ai_action = turn['turn_datas']
        self.assertEqual(player_action['effect_datas'][0]['defender_morty_datas'], [{'owned_morty_id': self.wild, 'hp': 80}])
        self.assertEqual(player_action['attacker_morty_datas'][0]['owned_attacks'], [{'attack_id': 'AttackLick', 'pp': 4}])
        self.assertEqual(ai_action['effect_datas'][0]['defender_morty_datas'], [{'owned_morty_id': self.morty, 'hp': battle['player_hp']}])
        self.assertEqual(next(m for m in after['morties'] if m['owned_morty_id'] == self.morty)['hp'], battle['player_hp'])
        self.assertEqual(next(a for a in after['attacks'] if a['owned_morty_id'] == self.morty)['pp'], 4)
        self.assertEqual(next(e for e in before['events'] if e['event_name'] == 'battle:start'), next(e for e in after['events'] if e['event_name'] == 'battle:start'))

    def test_win_removes_spawn_without_ai_or_fabricated_rewards(self):
        self.begin()
        before = self.snapshot()
        self.assertEqual(self.move(), (200, {'success': True}))
        after = self.snapshot()
        battle = after['battles'][0]
        self.assertEqual((battle['state'], battle['winner'], battle['player_hp'], battle['opponent_hp']), ('COMPLETED', self.player, 100, 0))
        turn = self.turn(after)
        self.assertEqual(turn['outcome'], 'WIN')
        self.assertEqual(len(turn['turn_datas']), 1)
        self.assertEqual(turn['player_datas']['player']['xp_datas'], [])
        self.assertEqual(turn['player_datas']['player']['rewards'], [])
        self.assertEqual(after['items'], before['items'])
        for old in before['morties']:
            new = next(m for m in after['morties'] if m['owned_morty_id'] == old['owned_morty_id'])
            for key in ('hp', 'xp', 'level', 'hp_stat'):
                self.assertEqual(new[key], old[key])
        removed = [e for e in after['events'] if e['event_name'] == 'room:wild-morty-removed']
        self.assertEqual([e['wild_morty_id'] for e in removed], [self.wild])
        self.assert_world(after, spawn=False)
        self.assert_rejected_unchanged(self.move, 409)

    def test_lose_persists_fainted_morty_and_releases_spawn(self):
        sql(f"UPDATE owned_morties SET hp=1 WHERE owned_morty_id='{self.morty}'")
        self.begin()
        sql(f"UPDATE battles SET opponent_hp=100 WHERE battle_id='{self.battle}'")
        self.assertEqual(self.move(), (200, {'success': True}))
        after = self.snapshot()
        battle = after['battles'][0]
        self.assertEqual((battle['state'], battle['winner'], battle['player_hp']), ('COMPLETED', battle['opponent_id'], 0))
        self.assertEqual(next(m for m in after['morties'] if m['owned_morty_id'] == self.morty)['hp'], 0)
        self.assertEqual(next(a for a in after['attacks'] if a['owned_morty_id'] == self.morty)['pp'], 4)
        self.assertEqual(self.turn(after)['outcome'], 'LOSE')
        self.assert_world(after)

    def test_item_capture_is_explicitly_unsupported_and_changes_nothing(self):
        self.begin()
        body = self.assert_rejected_unchanged(lambda: self.move('ITEM', move_id='ItemMortyChip'), 501)
        self.assertEqual(body['error']['code'], 'ITEM_UNUSABLE')

    def test_unsupported_move_types_do_not_change_anything(self):
        self.begin()
        for kind in ('WAIT', 'INVALID'):
            with self.subTest(kind=kind):
                self.assert_rejected_unchanged(lambda: self.move(kind), 400)

    def test_invalid_foreign_and_exhausted_attacks_do_not_change_anything(self):
        self.begin()
        for changes, status in (({'owned_morty_id': self.other_morty}, 403), ({'move_id': 'AttackMissing'}, 400), ({'move_id': ''}, 400)):
            with self.subTest(changes=changes):
                self.assert_rejected_unchanged(lambda: self.move(**changes), status)
        sql(f"UPDATE owned_attacks SET pp=0 WHERE owned_morty_id='{self.morty}'")
        self.assert_rejected_unchanged(self.move, 409)

    def test_authentication_and_battle_owner_guards_do_not_write(self):
        self.begin()
        self.assert_rejected_unchanged(lambda: self.move(session_id=''), 400)
        self.assert_rejected_unchanged(lambda: self.move(session_id=str(uuid.uuid4())), 401)
        self.assert_rejected_unchanged(lambda: self.move(session_id=self.other_session), 403)
        self.assert_rejected_unchanged(lambda: self.move(battle_id=str(uuid.uuid4())), 404)

    def test_changed_room_rejects_move_without_other_room_events(self):
        self.begin()
        sql(f"UPDATE users SET room_id='{self.other_room}' WHERE player_id='{self.player}'")
        self.assert_rejected_unchanged(lambda: self.move('RUN'), 409)

    def test_ambiguous_legacy_spawn_claim_cannot_release_another_active_battle(self):
        self.begin()
        duplicate = str(uuid.uuid4())
        sql(f"INSERT INTO battles (battle_id,player_id,opponent_id,opponent_active_morty,state) VALUES ('{duplicate}','{self.other_player}','{self.player}','{self.wild}','ACTIVE')")
        self.assert_rejected_unchanged(lambda: self.move('RUN'), 409)
        self.assert_rejected_unchanged(self.move, 409)

    def test_missing_room_or_wrong_user_state_rejects_move(self):
        self.begin()
        sql(f"UPDATE users SET room_id=NULL WHERE player_id='{self.player}'")
        self.assert_rejected_unchanged(lambda: self.move('RUN'), 409)
        sql(f"UPDATE users SET room_id='{self.room}',state='WORLD' WHERE player_id='{self.player}'")
        self.assert_rejected_unchanged(self.move, 409)

    def test_concurrent_terminal_run_has_one_result(self):
        self.begin()
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _: self.move('RUN'), range(2)))
        self.assertEqual(sorted(r[0] for r in responses), [200, 409])
        after = self.snapshot()
        self.assertEqual(after['battles'][0]['state'], 'CANCELLED')
        self.assertEqual(self.turn(after)['outcome'], 'RUN')
        self.assert_world(after)

    def test_start_honors_deck_zero_and_ignores_foreign_deck(self):
        sql(f"UPDATE users SET active_deck_id=0 WHERE player_id='{self.player}'")
        sql(f"UPDATE decks SET deck_id=0 WHERE player_id='{self.player}'")
        sql(f"UPDATE decks SET deck_id=0 WHERE player_id='{self.other_player}'")
        self.assertEqual(self.begin()['player_active_morty'], self.morty)

    def test_start_rejects_foreign_or_fainted_selected_morty(self):
        sql(f"UPDATE decks SET owned_morty_ids='[\"{self.other_morty}\"]' WHERE player_id='{self.player}'")
        self.assert_rejected_unchanged(self.start, 409)
        sql(f"UPDATE decks SET owned_morty_ids='[\"{self.morty}\"]' WHERE player_id='{self.player}'")
        sql(f"UPDATE owned_morties SET hp=0 WHERE owned_morty_id='{self.morty}'")
        self.assert_rejected_unchanged(self.start, 409)

    def test_concurrent_start_claims_one_wild_once(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda session: self.start(session_id=session), (self.session, self.other_session)))
        self.assertEqual(sorted(r[0] for r in responses), [200, 409])
        after = self.snapshot()
        self.assertEqual(len(after['battles']), 1)
        starts = [e for e in after['events'] if e['event_name'] == 'battle:start']
        self.assertEqual(len(starts), 1)
        self.assertEqual(starts[0]['player_id'], after['battles'][0]['player_id'])
        self.assertEqual(next(e for e in after['events'] if e['event_name'] == 'room:wild-morty-added')['state'], 'BATTLE')

    def test_stale_active_morty_ownership_rejects_attack(self):
        self.begin()
        sql(f"UPDATE battles SET player_active_morty='{self.other_morty}' WHERE battle_id='{self.battle}'")
        self.assert_rejected_unchanged(lambda: self.move(owned_morty_id=self.other_morty), 403)

    def test_legacy_run_with_world_snapshot_does_not_overwrite_owned_hp_or_pp(self):
        self.begin()
        self.execute([
            f"UPDATE users SET state='WORLD' WHERE player_id='{self.player}'",
            f"UPDATE event_queue SET state='WORLD' WHERE room_id='{self.room}' AND event_name='room:wild-morty-added'",
            f"UPDATE battles SET player_hp=7 WHERE battle_id='{self.battle}'",
        ])
        before = self.snapshot()
        self.assertEqual(self.move('RUN'), (200, {'success': True}))
        after = self.snapshot()
        self.assertEqual(after['morties'], before['morties'])
        self.assertEqual(after['attacks'], before['attacks'])
        self.assertEqual((after['battles'][0]['state'], after['battles'][0]['player_hp']), ('CANCELLED', 7))
        self.assertEqual(self.turn(after)['outcome'], 'RUN')
        self.assert_world(after)

    def test_new_start_reconciles_legacy_active_row_with_private_terminal_result(self):
        self.begin()
        self.assertEqual(self.move('RUN'), (200, {'success': True}))
        sql(f"UPDATE battles SET state='ACTIVE' WHERE battle_id='{self.battle}'")
        before = self.snapshot()
        self.assertEqual(self.start(), (200, {'success': True}))
        after = self.snapshot()
        self.assertEqual(len(after['battles']), 2)
        old = next(b for b in after['battles'] if b['battle_id'] == self.battle)
        self.assertEqual(old['state'], 'CANCELLED')
        self.assertIsNone(old['winner'])
        self.assertEqual(len([b for b in after['battles'] if b['state'] == 'ACTIVE']), 1)
        self.assertEqual(after['morties'], before['morties'])
        self.assertEqual(after['attacks'], before['attacks'])
        self.assertEqual(after['items'], before['items'])
        self.assertEqual(self.turn(after)['outcome'], 'RUN')

    def legacy_terminal(self):
        self.begin()
        self.assertEqual(self.move('RUN'), (200, {'success': True}))
        sql(f"UPDATE battles SET state='ACTIVE' WHERE battle_id='{self.battle}'")

    def test_reconciliation_rejects_conflicting_terminal_outcomes_without_writes(self):
        self.legacy_terminal()
        sql(f"INSERT INTO event_queue (room_id,event_name,player_id,battle_turn_result) SELECT room_id,event_name,player_id,JSON_SET(battle_turn_result,'$.outcome','WIN') FROM event_queue WHERE room_id='{self.room}' AND event_name='battle:turn-result'")
        self.assert_rejected_unchanged(self.start, 409)

    def test_reconciliation_rejects_untrusted_recipients_and_start_snapshot_without_writes(self):
        self.legacy_terminal()
        result = f"room_id='{self.room}' AND event_name='battle:turn-result'"
        start = f"room_id='{self.room}' AND event_name='battle:start'"
        cases = [
            ("missing result recipient", f"UPDATE event_queue SET player_id=NULL WHERE {result}", f"UPDATE event_queue SET player_id='{self.player}' WHERE {result}"),
            ("foreign result recipient", f"UPDATE event_queue SET player_id='{self.other_player}' WHERE {result}", f"UPDATE event_queue SET player_id='{self.player}' WHERE {result}"),
            ("conflicting explicit result recipient", f"UPDATE event_queue SET only_show_to_player_id='{self.other_player}' WHERE {result}", f"UPDATE event_queue SET only_show_to_player_id=NULL WHERE {result}"),
            ("missing private start recipient", f"UPDATE event_queue SET only_show_to_player_id=NULL WHERE {start}", f"UPDATE event_queue SET only_show_to_player_id='{self.player}' WHERE {start}"),
            ("foreign private start recipient", f"UPDATE event_queue SET only_show_to_player_id='{self.other_player}' WHERE {start}", f"UPDATE event_queue SET only_show_to_player_id='{self.player}' WHERE {start}"),
            ("mismatched active Morty snapshot", f"UPDATE event_queue SET battle_start=JSON_SET(battle_start,'$.player.active_owned_morty','{self.other_morty}') WHERE {start}", f"UPDATE event_queue SET battle_start=JSON_SET(battle_start,'$.player.active_owned_morty','{self.morty}') WHERE {start}"),
        ]
        for label, mutate, restore in cases:
            with self.subTest(case=label):
                sql(mutate)
                self.assert_rejected_unchanged(self.start, 409)
                sql(restore)

    def test_reconciliation_accepts_duplicate_private_legacy_results_with_null_explicit_recipient(self):
        self.legacy_terminal()
        self.execute([
            f"UPDATE event_queue SET only_show_to_player_id=NULL WHERE room_id='{self.room}' AND event_name='battle:turn-result'",
            f"INSERT INTO event_queue (room_id,event_name,player_id,battle_turn_result,only_show_to_player_id) SELECT room_id,event_name,player_id,battle_turn_result,NULL FROM event_queue WHERE room_id='{self.room}' AND event_name='battle:turn-result'",
        ])
        before = self.snapshot()
        self.assertEqual(self.start(), (200, {'success': True}))
        after = self.snapshot()
        self.assertEqual(next(b for b in after['battles'] if b['battle_id'] == self.battle)['state'], 'CANCELLED')
        self.assertEqual(len([b for b in after['battles'] if b['state'] == 'ACTIVE']), 1)
        for key in ('morties', 'attacks', 'items'):
            self.assertEqual(after[key], before[key])
        self.assertEqual([e for e in after['events'] if e['event_name'] == 'battle:turn-result'], [e for e in before['events'] if e['event_name'] == 'battle:turn-result'])

    def test_sse_owner_gets_private_turn_peer_only_public_wild_removal(self):
        self.begin()
        self.assertEqual(self.move(), (200, {'success': True}))
        sentinel = str(uuid.uuid4())
        sql(f"INSERT INTO event_queue (room_id,event_name,player_id) VALUES ('{self.room}','room:user-removed','{sentinel}')")
        for session, is_owner in ((self.session, True), (self.other_session, False)):
            with self.subTest(owner=is_owner):
                token = base64.urlsafe_b64encode(json.dumps({'session_id': session}).encode()).decode().rstrip('=')
                events = []
                with urllib.request.urlopen(f'http://127.0.0.1:8087/sse/?since=0&token=e30.{token}.synthetic', timeout=5) as stream:
                    event_name = None
                    for _ in range(150):
                        line = stream.readline().decode().strip()
                        if line.startswith('event: '):
                            event_name = line[7:]
                        elif line.startswith('data: '):
                            payload = json.loads(line[6:])
                            events.append((event_name, payload))
                            if event_name == 'room:user-removed' and payload.get('player_id') == sentinel:
                                break
                    else:
                        self.fail('SSE did not reach public sentinel')
                turns = [payload for name, payload in events if name == 'battle:turn-result']
                self.assertEqual(len(turns), int(is_owner))
                if is_owner:
                    self.assertEqual((turns[0]['battle_id'], turns[0]['outcome']), (self.battle, 'WIN'))
                self.assertEqual(len([name for name, _ in events if name == 'battle:start']), int(is_owner))
                self.assertEqual([payload for name, payload in events if name == 'room:wild-morty-removed'], [{'wild_morty_id': self.wild}])


if __name__ == '__main__':
    unittest.main()

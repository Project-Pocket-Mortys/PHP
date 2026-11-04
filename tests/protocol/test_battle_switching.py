"""UUID-scoped party switching regressions; compose the lifecycle fixture."""
from concurrent.futures import ThreadPoolExecutor
import json
import unittest
import uuid

import test_battle_lifecycle as lifecycle
from test_http import post, sql


class BattleSwitchingTests(unittest.TestCase):
    def setUp(self):
        self.fx = lifecycle.BattleLifecycleTests()
        self.fx.setUp()
        self.addCleanup(self.fx.doCleanups)
        self.second, self.third = str(uuid.uuid4()), str(uuid.uuid4())
        self.party = [self.fx.morty, self.second, self.third]
        self.addCleanup(self.cleanup_attacks)
        queries = []
        for morty in self.party[1:]:
            queries += [
                f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat,is_poisoned,is_paralysed) VALUES ('{morty}','{self.fx.player}','Morty',100,100,1,1)",
                f"INSERT INTO owned_attacks (owned_morty_id,attack_id,position,pp,pp_stat) VALUES ('{morty}','AttackLick',0,5,5)",
            ]
        self.fx.execute(queries)
        self.deck(self.party)

    def cleanup_attacks(self):
        self.fx.execute([f"DELETE FROM owned_attacks WHERE owned_morty_id IN ('{self.second}','{self.third}')"])

    def deck(self, party):
        sql(f"UPDATE decks SET owned_morty_ids='{json.dumps(party)}' WHERE player_id='{self.fx.player}'")

    def begin(self):
        battle = self.fx.begin()
        sql(f"UPDATE battles SET opponent_hp=100 WHERE battle_id='{self.fx.battle}'")
        return battle

    def snapshot(self):
        result = self.fx.snapshot()
        ids = ','.join("'" + m + "'" for m in self.party)
        result['attacks'] = sql(f"SELECT * FROM owned_attacks WHERE owned_morty_id IN ({ids},'{self.fx.other_morty}') ORDER BY id")
        return result

    def switch(self, target=None, **changes):
        return self.fx.move('SWITCH', owned_morty_id=changes.pop('owned_morty_id', self.fx.morty), move_id=self.second if target is None else target, **changes)

    def turns(self, snapshot):
        events = [e for e in snapshot['events'] if e['event_name'] == 'battle:turn-result']
        for event in events:
            self.assertEqual(event['player_id'], self.fx.player)
            self.assertEqual(event['room_id'], self.fx.room)
            self.assertIn(event['only_show_to_player_id'], (None, '', self.fx.player))
        return [json.loads(e['battle_turn_result']) for e in events]

    def rejected(self, action, status):
        before = self.snapshot()
        response = action()
        self.assertEqual(response[0], status, response)
        self.assertFalse(response[1]['success'])
        self.assertEqual(self.snapshot(), before)

    def test_voluntary_switch_persists_incoming_hp_and_preserves_resources(self):
        self.begin()
        before = self.snapshot()
        start = next(e for e in before['events'] if e['event_name'] == 'battle:start')
        self.assertEqual((start['player_id'], start['only_show_to_player_id']), (self.fx.player, self.fx.player))
        roster = json.loads(start['battle_start'])['player']['owned_morties']
        self.assertEqual([m['owned_morty_id'] for m in roster], self.party)
        self.assertTrue(all(m['hp'] == 100 and m['hp_stat'] == 100 for m in roster))
        self.assertEqual(self.switch(), (200, {'success': True}))
        after = self.snapshot()
        battle = after['battles'][0]
        self.assertEqual(battle['player_active_morty'], self.second)
        self.assertIn(battle['player_hp'], (97, 98, 99))
        self.assertEqual(battle['opponent_hp'], 100)
        for old in before['morties']:
            expected = dict(old)
            if old['owned_morty_id'] == self.second:
                expected['hp'] = battle['player_hp']
            self.assertEqual(next(m for m in after['morties'] if m['id'] == old['id']), expected)
        self.assertEqual(after['attacks'], before['attacks'])
        self.assertEqual(after['items'], before['items'])
        turn, = self.turns(after)
        self.assertEqual(turn['outcome'], 'CONTINUE')
        self.assertEqual([d['type'] for d in turn['turn_datas']], ['SWITCH', 'ATTACK'])
        self.assertEqual(turn['turn_datas'][0]['owned_morty_id'], self.second)
        self.assertEqual(turn['turn_datas'][0]['defender_player_id'], battle['opponent_id'])
        self.assertEqual(turn['turn_datas'][1]['effect_datas'][0]['defender_morty_datas'], [{'owned_morty_id': self.second, 'hp': battle['player_hp']}])
        self.rejected(self.switch, 409)
        self.assertEqual(self.fx.move(owned_morty_id=self.second), (200, {'success': True}))
        attacked = self.snapshot()
        self.assertEqual(attacked['battles'][0]['opponent_hp'], 80)
        self.assertEqual(next(a for a in attacked['attacks'] if a['owned_morty_id'] == self.second)['pp'], 4)
        self.assertEqual(next(a for a in attacked['attacks'] if a['owned_morty_id'] == self.fx.morty)['pp'], 5)
        self.assertEqual(self.fx.move('RUN', owned_morty_id=self.second, move_id=None), (200, {'success': True}))
        self.assertEqual(self.snapshot()['battles'][0]['state'], 'CANCELLED')

    def test_forced_replacement_is_required_and_does_not_retaliate(self):
        sql(f"UPDATE owned_morties SET hp=1 WHERE owned_morty_id='{self.fx.morty}'")
        self.begin()
        self.assertEqual(self.fx.move(), (200, {'success': True}))
        fainted = self.snapshot()
        battle = fainted['battles'][0]
        self.assertEqual((battle['state'], battle['player_hp'], battle['opponent_hp']), ('ACTIVE', 0, 80))
        self.assertEqual(next(u for u in fainted['users'] if u['player_id'] == self.fx.player)['state'], 'BATTLE')
        self.assertEqual(self.turns(fainted)[-1]['outcome'], 'FORCE_SWITCH')
        self.rejected(self.fx.move, 409)
        self.assertEqual(post('/session/battle/ready', {'session_id': self.fx.session, 'battle_id': self.fx.battle}), (200, {'success': True}))
        self.rejected(self.fx.move, 409)
        before = self.snapshot()
        self.assertEqual(self.switch(), (200, {'success': True}))
        after = self.snapshot()
        self.assertEqual(after['morties'], before['morties'])
        self.assertEqual(after['attacks'], before['attacks'])
        self.assertEqual(after['items'], before['items'])
        self.assertEqual((after['battles'][0]['player_active_morty'], after['battles'][0]['player_hp']), (self.second, 100))
        turn = self.turns(after)[-1]
        self.assertEqual(turn['outcome'], 'CONTINUE')
        self.assertEqual([d['type'] for d in turn['turn_datas']], ['SWITCH'])
        self.assertEqual(turn['turn_datas'][0]['owned_morty_id'], self.second)
        self.assertEqual(self.fx.move(owned_morty_id=self.second), (200, {'success': True}))
        self.assertEqual(self.snapshot()['battles'][0]['opponent_hp'], 60)

    def test_legacy_csv_party_trims_spaces_and_preserves_deck_order(self):
        sql(f"UPDATE decks SET owned_morty_ids='{' , '.join(self.party)}' WHERE player_id='{self.fx.player}'")
        self.fx.begin()
        start = next(e for e in self.snapshot()['events'] if e['event_name'] == 'battle:start')
        self.assertEqual([m['owned_morty_id'] for m in json.loads(start['battle_start'])['player']['owned_morties']], self.party)
        self.assertEqual(self.fx.move('RUN', move_id=None), (200, {'success': True}))

    def test_voluntary_replacement_faints_and_requires_another_switch(self):
        sql(f"UPDATE owned_morties SET hp=1 WHERE owned_morty_id='{self.second}'")
        self.begin()
        self.assertEqual(self.switch(), (200, {'success': True}))
        after = self.snapshot()
        self.assertEqual((after['battles'][0]['state'], after['battles'][0]['player_hp']), ('ACTIVE', 0))
        self.assertEqual(self.turns(after)[-1]['outcome'], 'FORCE_SWITCH')
        self.rejected(lambda: self.fx.move(owned_morty_id=self.second), 409)
        self.assertEqual(self.switch(self.fx.morty, owned_morty_id=self.second), (200, {'success': True}))
        self.assertEqual(self.snapshot()['battles'][0]['player_hp'], 100)

    def test_loss_requires_every_initial_participant_to_faint(self):
        self.fx.execute([f"UPDATE owned_morties SET hp=0 WHERE owned_morty_id IN ('{self.second}','{self.third}')", f"UPDATE owned_morties SET hp=1 WHERE owned_morty_id='{self.fx.morty}'"])
        self.begin()
        self.assertEqual(self.fx.move(), (200, {'success': True}))
        after = self.snapshot()
        self.assertEqual(after['battles'][0]['state'], 'COMPLETED')
        self.assertEqual(self.turns(after)[-1]['outcome'], 'LOSE')
        self.fx.assert_world(after)

    def test_target_guards_preserve_database_and_events(self):
        self.begin()
        self.rejected(lambda: self.switch(self.fx.morty), 409)
        self.rejected(lambda: self.switch(self.fx.other_morty), 403)
        self.rejected(lambda: self.switch(str(uuid.uuid4())), 403)
        sql(f"UPDATE owned_morties SET hp=0 WHERE owned_morty_id='{self.second}'")
        self.rejected(self.switch, 409)
        sql(f"UPDATE owned_morties SET hp=100,player_id='{self.fx.other_player}' WHERE owned_morty_id='{self.second}'")
        self.rejected(self.switch, 403)
        sql(f"UPDATE owned_morties SET player_id='{self.fx.player}' WHERE owned_morty_id='{self.second}'")
        self.fx.execute([f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat) VALUES ('{self.second}','{self.fx.other_player}','Morty',100,100)"])
        self.rejected(self.switch, 409)

    def test_switch_rejects_malformed_or_missing_identifiers(self):
        self.begin()
        for field in ('owned_morty_id', 'move_id'):
            for value in (None, '', 1, [], {}):
                with self.subTest(field=field, value=value):
                    request = dict(session_id=self.fx.session, battle_id=self.fx.battle, type='SWITCH', owned_morty_id=self.fx.morty, move_id=self.second)
                    request[field] = value
                    self.rejected(lambda: post('/session/battle/move', request), 400)
            request = dict(session_id=self.fx.session, battle_id=self.fx.battle, type='SWITCH', owned_morty_id=self.fx.morty, move_id=self.second)
            del request[field]
            self.rejected(lambda: post('/session/battle/move', request), 400)

    def test_initial_roster_authority_survives_mutable_deck(self):
        self.deck([self.fx.morty, self.second])
        self.begin()
        # The third Morty was storage at start, then added to the live deck.
        self.rejected(lambda: self.switch(self.third), 403)
        self.deck([self.fx.morty, self.third])
        self.rejected(lambda: self.switch(self.third), 403)
        # Removing the original second participant does not remove its authority.
        self.assertEqual(self.switch(), (200, {'success': True}))
        self.assertEqual(self.fx.move('RUN', owned_morty_id=self.second, move_id=None), (200, {'success': True}))

    def test_start_rejects_invalid_full_roster_without_writes(self):
        for label, party in (
            ('duplicate', [self.fx.morty, self.second, self.second]),
            ('missing', [self.fx.morty, str(uuid.uuid4())]),
            ('foreign', [self.fx.morty, self.fx.other_morty]),
        ):
            with self.subTest(case=label):
                self.deck(party)
                self.rejected(self.fx.start, 409)
        self.deck(self.party)
        for hp in (-1, 101):
            with self.subTest(hp=hp):
                sql(f"UPDATE owned_morties SET hp={hp} WHERE owned_morty_id='{self.third}'")
                self.rejected(self.fx.start, 409)
        sql(f"UPDATE owned_morties SET hp=100 WHERE owned_morty_id='{self.third}'")
        self.fx.execute([f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat) VALUES ('{self.third}','{self.fx.other_player}','Morty',100,100)"])
        self.rejected(self.fx.start, 409)

    def assert_broken_bench_blocks_combat_but_allows_run(self):
        self.rejected(self.fx.move, 409)
        self.rejected(self.switch, 409)
        self.assertEqual(self.fx.move('RUN', move_id=None), (200, {'success': True}))
        self.assertEqual(self.snapshot()['battles'][0]['state'], 'CANCELLED')

    def test_missing_nonselected_participant_blocks_combat_but_allows_run(self):
        self.begin()
        sql(f"DELETE FROM owned_morties WHERE owned_morty_id='{self.third}' AND player_id='{self.fx.player}'")
        self.assert_broken_bench_blocks_combat_but_allows_run()

    def test_ambiguous_nonselected_participant_blocks_combat_but_allows_run(self):
        self.begin()
        self.fx.execute([f"INSERT INTO owned_morties (owned_morty_id,player_id,morty_id,hp,hp_stat) VALUES ('{self.third}','{self.fx.other_player}','Morty',100,100)"])
        self.assert_broken_bench_blocks_combat_but_allows_run()

    def test_reassigned_nonselected_participant_blocks_combat_but_allows_run(self):
        self.begin()
        sql(f"UPDATE owned_morties SET player_id='{self.fx.other_player}' WHERE owned_morty_id='{self.third}'")
        self.assert_broken_bench_blocks_combat_but_allows_run()

    def test_invalid_hp_nonselected_participant_blocks_combat_but_allows_run(self):
        self.begin()
        sql(f"UPDATE owned_morties SET hp=-1 WHERE owned_morty_id='{self.third}'")
        self.assert_broken_bench_blocks_combat_but_allows_run()

    def test_legacy_snapshot_without_roster_allows_run_and_blocks_switch(self):
        self.begin()
        sql(f"UPDATE event_queue SET battle_start=JSON_REMOVE(battle_start,'$.player.owned_morties') WHERE room_id='{self.fx.room}' AND event_name='battle:start'")
        self.rejected(self.switch, 409)
        self.assertEqual(self.fx.move('RUN', move_id=None), (200, {'success': True}))

    def test_legacy_snapshot_without_roster_keeps_same_active_attack(self):
        self.begin()
        sql(f"UPDATE event_queue SET battle_start=JSON_REMOVE(battle_start,'$.player.owned_morties') WHERE room_id='{self.fx.room}' AND event_name='battle:start'")
        self.assertEqual(self.fx.move(), (200, {'success': True}))
        after = self.snapshot()
        self.assertEqual(after['battles'][0]['opponent_hp'], 80)
        self.assertIn(after['battles'][0]['player_hp'], (97, 98, 99))
        self.assertEqual(next(a for a in after['attacks'] if a['owned_morty_id'] == self.fx.morty)['pp'], 4)

    def test_malformed_private_roster_blocks_run_without_writes(self):
        self.begin()
        start = next(e for e in self.snapshot()['events'] if e['event_name'] == 'battle:start')
        payload = json.loads(start['battle_start'])
        for roster in (None, [], {}, [{'owned_morty_id': self.second}],
                       [{'owned_morty_id': self.fx.morty}] * 2,
                       [{'owned_morty_id': 17}]):
            with self.subTest(roster=roster):
                payload['player']['owned_morties'] = roster
                encoded = json.dumps(payload).replace("'", "''")
                sql(f"UPDATE event_queue SET battle_start='{encoded}' WHERE id={int(start['id'])}")
                self.rejected(lambda: self.fx.move('RUN', move_id=None), 409)

    def test_legacy_caught_terminal_marker_reconciles_without_replaying_rewards(self):
        self.begin()
        self.assertEqual(self.fx.move('RUN', move_id=None), (200, {'success': True}))
        self.fx.execute([
            f"UPDATE event_queue SET battle_start=JSON_REMOVE(battle_start,'$.player.owned_morties') WHERE room_id='{self.fx.room}' AND event_name='battle:start'",
            f"UPDATE event_queue SET battle_turn_result=JSON_SET(battle_turn_result,'$.outcome','CAUGHT') WHERE room_id='{self.fx.room}' AND event_name='battle:turn-result'",
            f"UPDATE battles SET state='ACTIVE' WHERE battle_id='{self.fx.battle}'",
        ])
        before = self.snapshot()
        self.assertEqual(self.fx.start(), (200, {'success': True}))
        after = self.snapshot()
        old = next(b for b in after['battles'] if b['battle_id'] == self.fx.battle)
        self.assertEqual((old['state'], old['winner']), ('COMPLETED', self.fx.player))
        self.assertEqual(len([b for b in after['battles'] if b['state'] == 'ACTIVE']), 1)
        for key in ('morties', 'attacks', 'items'):
            self.assertEqual(after[key], before[key])
        self.assertEqual(self.turns(after), self.turns(before))

    def test_terminal_reconciliation_after_legitimate_switch(self):
        self.begin()
        self.assertEqual(self.switch(), (200, {'success': True}))
        self.assertEqual(self.fx.move('RUN', owned_morty_id=self.second, move_id=None), (200, {'success': True}))
        sql(f"UPDATE battles SET state='ACTIVE' WHERE battle_id='{self.fx.battle}'")
        before = self.snapshot()
        self.assertEqual(self.fx.start(), (200, {'success': True}))
        after = self.snapshot()
        old = next(b for b in after['battles'] if b['battle_id'] == self.fx.battle)
        self.assertEqual(old['state'], 'CANCELLED')
        self.assertEqual(len([b for b in after['battles'] if b['state'] == 'ACTIVE']), 1)
        for key in ('morties', 'attacks', 'items'):
            self.assertEqual(after[key], before[key])

    def test_concurrent_same_target_switch_only_executes_once(self):
        self.begin()
        with ThreadPoolExecutor(max_workers=2) as workers:
            responses = list(workers.map(lambda _: self.switch(), range(2)))
        self.assertEqual(sorted(r[0] for r in responses), [200, 409])
        after = self.snapshot()
        self.assertEqual(len(self.turns(after)), 1)
        self.assertIn(after['battles'][0]['player_hp'], (97, 98, 99))
        self.assertTrue(all(a['pp'] == 5 for a in after['attacks']))

    def test_run_and_switch_race_remains_atomic(self):
        self.begin()
        with ThreadPoolExecutor(max_workers=2) as workers:
            switch_future = workers.submit(self.switch)
            run_future = workers.submit(lambda: self.fx.move('RUN', move_id=None))
            switch_response, run_response = switch_future.result(), run_future.result()
        after = self.snapshot()
        turns = self.turns(after)
        self.assertEqual(run_response, (200, {'success': True}))
        self.assertEqual(after['battles'][0]['state'], 'CANCELLED')
        self.assertTrue(all(a['pp'] == 5 for a in after['attacks']))
        if switch_response[0] == 409:
            self.assertEqual([t['outcome'] for t in turns], ['RUN'])
            self.assertTrue(all(m['hp'] == 100 for m in after['morties']))
        else:
            self.assertEqual(switch_response, (200, {'success': True}))
            self.assertEqual([t['outcome'] for t in turns], ['CONTINUE', 'RUN'])
            self.assertIn(after['battles'][0]['player_hp'], (97, 98, 99))
            self.assertEqual(after['battles'][0]['player_active_morty'], self.second)


if __name__ == '__main__':
    unittest.main()

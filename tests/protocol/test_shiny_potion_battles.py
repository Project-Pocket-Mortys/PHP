"""Private wild variants follow the actor's persisted potion and existing spawn flag."""
import json
import unittest

import test_battle_lifecycle as lifecycle
from test_http import sql


class ShinyPotionBattleTests(unittest.TestCase):
    def setUp(self):
        self.f = lifecycle.BattleLifecycleTests(methodName='runTest')
        self.f.setUp()
        self.addCleanup(lambda: self.assertTrue(self.f.doCleanups()))

    def configure(self, expiry, flag=1, variant='Normal'):
        sql(f"UPDATE users SET shiny_potion_expires_at={expiry} WHERE player_id='{self.f.player}'")
        sql(f"UPDATE event_queue SET variant='{variant}',shiny_if_potion={flag} WHERE room_id='{self.f.room}' AND wild_morty_id='{self.f.wild}'")

    def start_variant(self):
        self.assertEqual(self.f.start(), (200, {'success': True}))
        active = sql(f"SELECT battle_id FROM battles WHERE player_id='{self.f.player}' AND state='ACTIVE'")
        self.assertEqual(len(active), 1)
        self.f.battle = active[0]['battle_id']
        rows = sql(f"SELECT * FROM event_queue WHERE room_id='{self.f.room}' AND event_name='battle:start' ORDER BY id DESC")
        rows = [r for r in rows if json.loads(r['battle_start'])['battle_id'] == self.f.battle]
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['player_id'], rows[0]['only_show_to_player_id']), (self.f.player, self.f.player))
        payload = json.loads(rows[0]['battle_start'])
        opponent = payload['opponent']
        self.assertEqual(opponent['active_owned_morty'], self.f.wild)
        self.assertEqual(opponent['owned_morties'][0]['owned_morty_id'], self.f.wild)
        return opponent['owned_morties'][0]['variant']

    def test_active_flagged_normal_is_shiny_privately_without_spawn_or_owned_changes(self):
        self.configure('UTC_TIMESTAMP(6)+INTERVAL 1 HOUR')
        before = self.f.snapshot()
        self.assertEqual(self.start_variant(), 'Shiny')
        after = self.f.snapshot()
        for key in ('morties','attacks','items','decks'):
            self.assertEqual(after[key], before[key])
        spawn = next(e for e in after['events'] if e['event_name'] == 'room:wild-morty-added')
        self.assertEqual((spawn['variant'], int(spawn['shiny_if_potion'])), ('Normal', 1))
        self.assertEqual(self.f.move('RUN')[0], 200)
        spawn = sql(f"SELECT variant,state FROM event_queue WHERE room_id='{self.f.room}' AND event_name='room:wild-morty-added'")[0]
        self.assertEqual(spawn, {'variant':'Normal','state':'WORLD'})

    def test_missing_expired_and_exactly_due_potions_keep_normal(self):
        for expiry in ('NULL','UTC_TIMESTAMP(6)-INTERVAL 1 SECOND','UTC_TIMESTAMP(6)'):
            with self.subTest(expiry=expiry):
                self.configure(expiry)
                self.assertEqual(self.start_variant(), 'Normal')
                self.assertEqual(self.f.move('RUN')[0], 200)

    def test_active_potion_does_not_change_unflagged_or_existing_variants(self):
        for flag, variant in ((0,'Normal'),(1,'Shiny'),(1,'Pulsing')):
            with self.subTest(flag=flag,variant=variant):
                self.configure('UTC_TIMESTAMP(6)+INTERVAL 1 HOUR',flag,variant)
                self.assertEqual(self.start_variant(), variant)
                self.assertEqual(self.f.move('RUN')[0], 200)

    def test_other_players_potion_does_not_change_requesters_variant(self):
        self.configure('NULL')
        sql(f"UPDATE users SET shiny_potion_expires_at=UTC_TIMESTAMP(6)+INTERVAL 1 HOUR WHERE player_id='{self.f.other_player}'")
        self.assertEqual(self.start_variant(), 'Normal')


if __name__ == '__main__':
    unittest.main()

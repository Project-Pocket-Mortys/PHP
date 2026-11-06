"""World mutations must preserve active battles, including legacy WORLD users."""
import unittest

import test_battle_lifecycle as lifecycle
from test_http import post, sql


class BattleWorldGuardTests(unittest.TestCase):
    def setUp(self):
        # Compose the UUID fixture without inheriting its lifecycle test methods.
        self.fixture = lifecycle.BattleLifecycleTests()
        self.addCleanup(self.fixture.doCleanups)
        self.fixture.setUp()
        f = self.fixture
        f.execute([
            f"UPDATE owned_morties SET player_id='{f.player}' WHERE owned_morty_id='{f.other_morty}'",
            f"UPDATE room_ids SET world_id='{f.other_room}' WHERE room_id='{f.other_room}'",
        ])

    def actions(self):
        f = self.fixture
        return [
            ('heal', '/session/heal', {}),
            ('absorb', '/session/owned_morties/absorb', {
                'owned_morty_id': f.other_morty, 'absorb_owned_morty_ids': [f.morty]}),
            ('join', '/session/join-room', {'world_id': f.other_room}),
            ('leave', '/session/leave-room', {}),
        ]

    def test_active_battle_blocks_world_mutations_without_changes(self):
        f = self.fixture
        f.begin()
        for state in ('BATTLE', 'WORLD'):
            sql(f"UPDATE users SET state='{state}' WHERE player_id='{f.player}'")
            for name, path, body in self.actions():
                with self.subTest(state=state, action=name):
                    before = f.snapshot()
                    response = post(path, dict(session_id=f.session, **body))
                    self.assertEqual(response[0], 409, response)
                    self.assertEqual(f.snapshot(), before)
        self.assertEqual(f.move('RUN'), (200, {'success': True}))
        f.assert_world(f.snapshot())

    def test_completed_battle_allows_existing_world_actions(self):
        f = self.fixture
        f.begin()
        self.assertEqual(f.move(), (200, {'success': True}))
        self.assertEqual(f.snapshot()['battles'][0]['state'], 'COMPLETED')
        sql(f"UPDATE owned_morties SET hp=50 WHERE owned_morty_id='{f.morty}'")
        sql(f"UPDATE owned_attacks SET pp=1 WHERE owned_morty_id='{f.morty}'")
        status, body = post('/session/heal', {'session_id': f.session})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['owned_morties'][0]['hp'], 100)
        self.assertEqual(body['owned_morties'][0]['owned_attacks'][0]['pp'], 5)
        status, body = post('/session/owned_morties/absorb', {
            'session_id': f.session, 'owned_morty_id': f.morty,
            'absorb_owned_morty_ids': [f.other_morty]})
        self.assertEqual(status, 200, body)
        self.assertEqual(body['removed'], [f.other_morty])
        status, body = post('/session/join-room', {'session_id': f.session, 'world_id': f.other_room})
        self.assertEqual(status, 200, body)
        self.assertEqual(sql(f"SELECT room_id FROM users WHERE player_id='{f.player}'")[0]['room_id'], f.other_room)
        self.assertEqual(post('/session/leave-room', {'session_id': f.session}), (200, {'success': True}))
        self.assertIsNone(sql(f"SELECT room_id FROM users WHERE player_id='{f.player}'")[0]['room_id'])

    def test_proven_legacy_terminal_does_not_disable_world_healing(self):
        f = self.fixture
        f.begin()
        self.assertEqual(f.move('RUN'), (200, {'success': True}))
        sql(f"UPDATE battles SET state='ACTIVE' WHERE battle_id='{f.battle}'")
        before = f.snapshot()
        status, body = post('/session/heal', {'session_id': f.session})
        self.assertEqual(status, 200, body)
        after = f.snapshot()
        self.assertEqual(after['battles'][0]['state'], 'CANCELLED')
        self.assertEqual(after['events'], before['events'])
        self.assertEqual(after['morties'], before['morties'])
        self.assertEqual(after['attacks'], before['attacks'])
        self.assertEqual(after['items'], before['items'])


if __name__ == '__main__':
    unittest.main()

"""Ailment persistence through fresh DTO reads, using disposable UUID fixtures."""
import base64
import json
import unittest
import urllib.request
import uuid

import test_battle_lifecycle
from test_http import php, post, sql


class MortyAilmentSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        # Composition avoids running the fixture class's lifecycle tests again.
        self.fixture = test_battle_lifecycle.BattleLifecycleTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.world = str(uuid.uuid4())
        sql(f"UPDATE room_ids SET world_id='{self.world}' WHERE room_id='{self.fixture.room}'")
        self.accounts = ((self.fixture.player, self.fixture.session, self.fixture.morty),
                         (self.fixture.other_player, self.fixture.other_session, self.fixture.other_morty))

    def flags(self):
        return sql("SELECT owned_morty_id,is_poisoned,is_paralysed FROM owned_morties "
                   f"WHERE player_id IN ('{self.fixture.player}','{self.fixture.other_player}') "
                   "ORDER BY owned_morty_id")

    def set_mixed_flags(self):
        sql(f"UPDATE owned_morties SET is_poisoned=1,is_paralysed=0 "
            f"WHERE owned_morty_id='{self.fixture.morty}'")
        sql(f"UPDATE owned_morties SET is_poisoned=0,is_paralysed=1 "
            f"WHERE owned_morty_id='{self.fixture.other_morty}'")

    def assert_morty_flags(self, morties, morty_id, expected):
        matching = [row for row in morties if row['owned_morty_id'] == morty_id]
        self.assertEqual(len(matching), 1, morties)
        row = matching[0]
        for key, value in zip(('is_poisoned', 'is_paralysed'), expected):
            self.assertIs(type(row[key]), bool, row)
            self.assertIs(row[key], value, row)

    def test_legacy_insert_defaults_are_false_in_fresh_player_details(self):
        before = self.flags()
        self.assertEqual([(int(r['is_poisoned']), int(r['is_paralysed'])) for r in before],
                         [(0, 0), (0, 0)])
        for _, session, morty in self.accounts:
            status, body = post('/session/player-details', {'session_id': session})
            self.assertEqual(status, 200, body)
            self.assert_morty_flags(body['owned_morties'], morty, (False, False))
        self.assertEqual(self.flags(), before)

    def test_fresh_player_join_and_room_details_preserve_own_and_peer_flags(self):
        self.set_mixed_flags()
        before = self.flags()
        for _, session, morty in self.accounts:
            status, body = post('/session/player-details', {'session_id': session})
            self.assertEqual(status, 200, body)
            expected = (True, False) if morty == self.fixture.morty else (False, True)
            self.assert_morty_flags(body['owned_morties'], morty, expected)
            for route in ('join-room', 'room-details'):
                status, body = post('/session/' + route,
                                    {'session_id': session, 'world_id': self.world})
                self.assertEqual(status, 200, body)
                users = {row['player_id']: row for row in body['users']}
                for player, _, owned in self.accounts:
                    expected = (True, False) if owned == self.fixture.morty else (False, True)
                    self.assert_morty_flags(users[player]['owned_morties'], owned, expected)
        self.assertEqual(self.flags(), before)

    def test_sse_user_added_rebuilds_each_subject_flags_for_both_subscribers(self):
        self.set_mixed_flags()
        before = self.flags()
        # The event carries the subject ID, while the DTO is loaded on delivery.
        for player, _, _ in self.accounts:
            sql("INSERT INTO event_queue (room_id,event_name,player_id,state) "
                f"VALUES ('{self.fixture.room}','room:user-added','{player}','WORLD')")
        marker = str(uuid.uuid4())
        sql("INSERT INTO event_queue (room_id,event_name,player_id) "
            f"VALUES ('{self.fixture.room}','room:user-removed','{marker}')")
        for _, session, _ in self.accounts:
            token = base64.urlsafe_b64encode(json.dumps({'session_id': session}).encode()).decode().rstrip('=')
            url = f'http://127.0.0.1:8087/sse/?token=e30.{token}.synthetic&since=0'
            users = {}
            ended = False
            with urllib.request.urlopen(url, timeout=5) as stream:
                event = None
                for _ in range(250):
                    line = stream.readline().decode().strip()
                    if line.startswith('event: '):
                        event = line[7:]
                    elif line.startswith('data: '):
                        body = json.loads(line[6:])
                        if event == 'room:user-added':
                            users[body['player_id']] = body
                        if event == 'room:user-removed' and body.get('player_id') == marker:
                            ended = True
                            break
            self.assertTrue(ended, 'Missing UUID terminal marker')
            self.assertEqual(set(users), {row[0] for row in self.accounts})
            for player, _, morty in self.accounts:
                expected = (True, False) if morty == self.fixture.morty else (False, True)
                self.assert_morty_flags(users[player]['owned_morties'], morty, expected)
        self.assertEqual(self.flags(), before)

    def test_private_battle_start_preserves_player_ailments(self):
        self.set_mixed_flags()
        before = self.flags()
        self.fixture.begin()
        rows = sql("SELECT player_id,only_show_to_player_id,battle_start FROM event_queue "
                   f"WHERE room_id='{self.fixture.room}' AND event_name='battle:start'")
        self.assertEqual(len(rows), 1)
        self.assertEqual((rows[0]['player_id'], rows[0]['only_show_to_player_id']),
                         (self.fixture.player, self.fixture.player))
        body = json.loads(rows[0]['battle_start'])
        self.assert_morty_flags(body['player']['owned_morties'], self.fixture.morty, (True, False))
        self.assertEqual(self.flags(), before)

    def test_existing_heal_and_learn_attacks_return_and_preserve_ailments(self):
        self.set_mixed_flags()
        before = self.flags()
        for _, session, morty in self.accounts:
            expected = (True, False) if morty == self.fixture.morty else (False, True)
            sql(f"UPDATE owned_morties SET hp=37 WHERE owned_morty_id='{morty}'")
            status, body = post('/session/heal', {'session_id': session})
            self.assertEqual(status, 200, body)
            self.assert_morty_flags(body['owned_morties'], morty, expected)
            self.assertEqual(next(r for r in body['owned_morties'] if r['owned_morty_id'] == morty)['hp'], 100)
            status, body = post('/session/owned_morties/learn-attacks', {
                'session_id': session, 'owned_morties': [
                    {'owned_morty_id': morty, 'attack_ids': ['AttackLick']}],
            })
            self.assertEqual(status, 200, body)
            self.assert_morty_flags(body['owned_morties'], morty, expected)
            status, fresh = post('/session/player-details', {'session_id': session})
            self.assertEqual(status, 200, fresh)
            self.assert_morty_flags(fresh['owned_morties'], morty, expected)
        self.assertEqual(self.flags(), before)

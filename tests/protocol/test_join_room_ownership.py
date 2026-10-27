"""Join snapshots with stale deck references; additive UUID fixtures only."""
import json
import unittest
import uuid

from test_http import php, post, sql


class JoinRoomOwnershipTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.room, self.world = str(uuid.uuid4()), str(uuid.uuid4())
        self.players = [str(uuid.uuid4()) for _ in range(2)]
        self.morties = [str(uuid.uuid4()) for _ in range(2)]
        self.addCleanup(self.cleanup)
        sql(f"INSERT INTO room_ids (room_id, world_id, zone_id) "
            f"VALUES ('{self.room}', '{self.world}', '[1,1]')")
        for player, morty in zip(self.players, self.morties):
            sql(f"INSERT INTO users (secret, player_id, session_id, username, room_id, state, tags, active_deck_id, last_seen) "
                f"VALUES ('{player}', '{player}', '{player}', 'JoinOwnerTest', '{self.room}', 'WORLD', '[]', 1, NOW())")
            sql(f"INSERT INTO owned_morties (owned_morty_id, player_id, morty_id, hp, hp_stat) "
                f"VALUES ('{morty}', '{player}', 'Morty', 100, 100)")
            # Simulate stale data after an ownership change: both active decks
            # reference both Morties, but each player owns only one.
            sql(f"INSERT INTO decks (player_id, deck_id, owned_morty_ids) "
                f"VALUES ('{player}', 1, '{json.dumps(self.morties)}')")

    def cleanup(self):
        sql(f"DELETE FROM event_queue WHERE room_id='{self.room}'")
        for player in self.players:
            for table in ('decks', 'owned_morties', 'users'):
                sql(f"DELETE FROM {table} WHERE player_id='{player}'")
        sql(f"DELETE FROM room_ids WHERE room_id='{self.room}'")

    def test_join_snapshot_only_contains_each_players_owned_morties(self):
        status, body = post('/session/join-room', {
            'session_id': self.players[0], 'world_id': self.world})
        self.assertEqual(status, 200)
        self.assertEqual(body['room_id'], self.room)
        users = {user['player_id']: user for user in body['users']}
        self.assertEqual(set(users), set(self.players))
        for player, morty in zip(self.players, self.morties):
            with self.subTest(player=player):
                self.assertEqual([row['owned_morty_id'] for row in users[player]['owned_morties']], [morty])
                self.assertEqual(users[player]['owned_morties'][0]['hp'], 100)
                self.assertIsNone(users[player]['owned_morties'][0]['fight_pit_id'])


if __name__ == '__main__':
    unittest.main()

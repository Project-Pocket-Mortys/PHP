"""Additive emulator configuration; does not reseed or delete client accounts."""
import subprocess
import unittest
from test_http import COMPOSE, ROOT, post, sql


class ClientFixtureTests(unittest.TestCase):
    def test_fixture_is_repeatable_and_deck_configuration_is_json(self):
        players = sql('SELECT player_id, session_id FROM users ORDER BY player_id')
        for _ in range(2):
            subprocess.run(COMPOSE + ['exec', '-T', 'web', 'php',
                           '/var/www/html/tools/research/server/seed-client.php'],
                           check=True, stdout=subprocess.DEVNULL, cwd=ROOT)
        self.assertEqual(sql('SELECT player_id, session_id FROM users ORDER BY player_id'), players)
        self.assertEqual(len(sql("SELECT id FROM room_ids WHERE room_id='00000000-0000-4000-8000-000000000001'")), 1)
        status, body = post('/decks/slots/config', {})
        self.assertEqual(status, 200)
        config = body['config_data']
        row = sql('SELECT config_id, starting_deck_slots, max_deck_slots, cost_additional_slot FROM deck_config LIMIT 1')[0]
        self.assertEqual(config, row)
        self.assertIsInstance(config['starting_deck_slots'], int)

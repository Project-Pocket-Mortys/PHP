"""Synthetic account bootstrap checks against the isolated Compose environment."""
import base64
import json
import subprocess
import unittest
from test_http import COMPOSE, ROOT, post, sql


class AccountBootstrapTests(unittest.TestCase):
    def setUp(self):
        subprocess.run(COMPOSE + ['exec', '-T', 'web', 'php', '/var/www/html/tests/protocol/seed.php'],
                       check=True, stdout=subprocess.DEVNULL, cwd=ROOT)

    def test_registered_account_can_login_to_local_session(self):
        status, registered = post('/user/register', {'username': 'ResearchAccount',
                                                     'player_avatar_ids': ['CharacterRick']})
        self.assertEqual(status, 200)
        status, logged_in = post('/user/login', {'secret': registered['secret'],
                                               'consent_identifier': 'synthetic'})
        self.assertEqual(status, 200)
        self.assertTrue(logged_in['session_url'].startswith('http://localhost:8087/sse/?token='))
        token = logged_in['session_url'].split('token=', 1)[1]
        encoded = token.split('.')[1]
        payload = json.loads(base64.urlsafe_b64decode(encoded + '=' * (-len(encoded) % 4)))
        self.assertEqual(payload['player_id'], registered['player_id'])
        self.assertEqual(payload['ping_url'], 'http://localhost:8087/session/ping-dynamic')
        self.assertEqual(sql("SELECT session_id FROM users WHERE username='ResearchAccount'")[0]['session_id'],
                         payload['session_id'])
        raw = subprocess.check_output(COMPOSE + ['exec', '-T', 'web', 'cat',
                                                 '/tmp/pocket-research-http.jsonl'], text=True, cwd=ROOT)
        records = [json.loads(line) for line in raw.splitlines()]
        captured = [row for row in records if row['path'] == '/user/login/'][-1]
        self.assertEqual(captured['request']['secret'], '[REDACTED]')
        self.assertEqual(captured['response']['session_url'], '[REDACTED]')
        self.assertNotIn(registered['secret'], raw)

    def test_invalid_secret_does_not_change_sessions(self):
        before = sql('SELECT player_id, session_id FROM users ORDER BY player_id')
        status, body = post('/user/login', {'secret': 'invalid', 'consent_identifier': 'synthetic'})
        self.assertEqual((status, body), (400, {'error': {'code': 'SECRET_INVALID'}}))
        self.assertEqual(sql('SELECT player_id, session_id FROM users ORDER BY player_id'), before)

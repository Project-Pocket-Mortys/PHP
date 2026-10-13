"""Integration tests against the dedicated Compose stack; reseeds synthetic data."""
import json
import base64
import hashlib
from urllib.parse import urlsplit
from pathlib import Path
import subprocess
import unittest
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ['docker', 'compose', '-f', str(ROOT / 'compose.research.yaml')]

def php(code):
    return subprocess.check_output(COMPOSE + ['exec', '-T', 'web', 'php', '-r', code], text=True, cwd=ROOT)

def sql(query):
    # Pass as a PHP string literal, not through a shell.
    literal = "'" + query.replace('\\', '\\\\').replace("'", "\\'") + "'"
    return json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; echo json_encode($pdo->query(" + literal + ")->fetchAll());"))

def post(path, data):
    req = urllib.request.Request('http://127.0.0.1:8087' + path + '/',
        json.dumps(data).encode(), {'Content-Type': 'application/json'}, method='POST')
    try:
        response = urllib.request.urlopen(req, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())

class BattleContractTests(unittest.TestCase):
    def setUp(self):
        subprocess.run(COMPOSE + ['exec', '-T', 'web', 'php', '/var/www/html/tests/protocol/seed.php'],
            check=True, stdout=subprocess.DEVNULL, cwd=ROOT)

    def test_ready_uses_battle_id(self):
        fixture = json.loads((Path(__file__).parent/'fixtures/battle-ready.json').read_text())
        status, body = post(fixture['request']['path'], fixture['request']['body'])
        self.assertEqual((status, body), (fixture['response']['status'], fixture['response']['body']))
        rows = sql('SELECT battle_move_timer_started FROM event_queue')
        self.assertEqual(json.loads(rows[0]['battle_move_timer_started']), fixture['event']['payload'])

    def test_ready_missing_id_no_event(self):
        status, _ = post('/session/battle/ready', {'session_id': 'test-session-a'})
        self.assertEqual(status, 400)
        self.assertEqual(sql('SELECT id FROM event_queue'), [])

    def test_other_player_cannot_ready_or_move(self):
        for path in ('ready', 'move'):
            status, _ = post('/session/battle/' + path, {'session_id': 'test-session-b',
                'battle_id': 'test-battle', 'type': 'ATTACK', 'owned_morty_id': 'test-morty-b', 'move_id': 'AttackLick'})
            self.assertEqual(status, 403)
        self.assertEqual(sql('SELECT id FROM event_queue'), [])
        self.assertEqual(sql('SELECT opponent_hp FROM battles')[0]['opponent_hp'], 100)

    def test_completed_battle_rejected(self):
        sql("UPDATE battles SET state='COMPLETED'")
        for path in ('ready', 'move'):
            status, _ = post('/session/battle/' + path, {'session_id': 'test-session-a',
                'battle_id': 'test-battle', 'type': 'ATTACK', 'owned_morty_id': 'test-morty-a', 'move_id': 'AttackLick'})
            self.assertEqual(status, 409)
        self.assertEqual(sql('SELECT id FROM event_queue'), [])

    def test_invalid_session(self):
        status, _ = post('/session/battle/ready', {'session_id': 'invalid', 'battle_id': 'test-battle'})
        self.assertEqual(status, 401)

    def test_missing_battle(self):
        status, _ = post('/session/battle/ready', {'session_id': 'test-session-a', 'battle_id': 'missing'})
        self.assertEqual(status, 404)
        self.assertEqual(sql('SELECT id FROM event_queue'), [])

    def test_attack_rejects_another_players_morty(self):
        status, _ = post('/session/battle/move', {'session_id': 'test-session-a', 'battle_id': 'test-battle',
            'type': 'ATTACK', 'owned_morty_id': 'test-morty-b', 'move_id': 'AttackLick'})
        self.assertEqual(status, 403)
        self.assertEqual(sql('SELECT id FROM event_queue'), [])

    def test_array_identifiers_are_clean_json_errors(self):
        for path in ('ready', 'move'):
            status, body = post('/session/battle/' + path, {'session_id': [], 'battle_id': [], 'type': []})
            self.assertEqual(status, 400)
            self.assertFalse(body['success'])

    def test_ready_event_targets_requesting_player(self):
        post('/session/battle/ready', {'session_id': 'test-session-a', 'battle_id': 'test-battle'})
        rows = sql('SELECT player_id, event_name FROM event_queue')
        self.assertEqual(rows, [{'player_id': 'test-player-a', 'event_name': 'battle:move-timer-started'}])

    def test_active_deck_selection_and_ownership(self):
        sql("INSERT INTO decks (player_id, deck_id, owned_morty_ids) VALUES ('test-player-a', 2, '[\"test-morty-b\"]'), ('test-player-a', 1, '[\"test-morty-a\",\"test-morty-b\"]')")
        result = json.loads(php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; require '/var/www/html/lib/active_deck.php'; echo json_encode(get_active_deck_morties($pdo, 'test-player-a'));"))
        self.assertEqual([m['owned_morty_id'] for m in result], ['test-morty-a'])

    def test_sse_private_timer_not_sent_to_other_account(self):
        post('/session/battle/ready', {'session_id': 'test-session-a', 'battle_id': 'test-battle'})
        php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; require '/var/www/html/lib/events.php'; publish_event($pdo, 'test-room', 'room:user-state-changed', ['player_id'=>'test-player-a','state'=>'WORLD']);")
        for account in ('a', 'b'):
            payload = base64.urlsafe_b64encode(json.dumps({'session_id':'test-session-'+account}).encode()).decode().rstrip('=')
            with urllib.request.urlopen('http://127.0.0.1:8087/sse/?since=0&token=e30.'+payload+'.synthetic', timeout=5) as stream:
                events = []
                for _ in range(30):
                    line = stream.readline().decode().strip()
                    if line.startswith('event: '):
                        events.append(line[7:])
                        if events[-1] == 'room:user-state-changed':
                            break
                self.assertIn('session:start', events)
                self.assertIn('room:user-state-changed', events)
                self.assertEqual('battle:move-timer-started' in events, account == 'a')

    def test_capture_returns_exactly_one_json_document(self):
        # Both random outcomes must produce one parseable HTTP document.
        for _ in range(20):
            status, body = post('/session/battle/move', {'session_id': 'test-session-a',
                'battle_id': 'test-battle', 'type': 'ITEM', 'move_id': 'ItemMortyChip'})
            self.assertEqual((status, body), (200, {'success': True}))

class AssetServingTests(unittest.TestCase):
    def test_manifest_asset_path_serves_existing_bundle(self):
        manifest = json.loads((ROOT/'Aliases/rat/Android/manifest.json').read_text())
        # Fetch the locally rewritten manifest; upstream URLs may carry a GitHub prefix.
        with urllib.request.urlopen('http://127.0.0.1:8087/Aliases/rat/Android/manifest.json', timeout=10) as response:
            manifest = json.load(response)
        path = urlsplit(manifest['appdata']['url']).path
        with urllib.request.urlopen('http://127.0.0.1:8087'+path, timeout=10) as response:
            received = response.read()
        existing = next((ROOT/'AssetBundles').glob('*/Android/appdata.assetbundle')).read_bytes()
        self.assertEqual(hashlib.sha256(received).digest(), hashlib.sha256(existing).digest())

if __name__ == '__main__':
    unittest.main()

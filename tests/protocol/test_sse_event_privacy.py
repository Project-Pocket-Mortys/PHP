"""Recipient isolation using additive UUID fixtures; never reseed shared data."""
import base64
import json
import unittest
import urllib.request
import uuid

from test_http import php, post, sql


class EventPrivacyTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.room, self.world = str(uuid.uuid4()), str(uuid.uuid4())
        self.a, self.b = str(uuid.uuid4()), str(uuid.uuid4())
        self.addCleanup(self.cleanup)
        sql(f"INSERT INTO room_ids (room_id, world_id, zone_id) VALUES ('{self.room}', '{self.world}', '[1,1]')")
        for player in (self.a, self.b):
            sql(f"INSERT INTO users (secret, player_id, session_id, username, room_id, state, tags) "
                f"VALUES ('{player}', '{player}', '{player}', 'PrivacyTest', '{self.room}', 'WORLD', '[]')")

    def cleanup(self):
        sql(f"DELETE FROM users WHERE player_id IN ('{self.a}', '{self.b}')")
        sql(f"DELETE FROM event_queue WHERE room_id='{self.room}'")
        sql(f"DELETE FROM room_ids WHERE room_id='{self.room}'")

    def insert(self, event, payload=None, subject=None, recipient=None, **fields):
        columns = {'battle:start': 'battle_start', 'battle:turn-result': 'battle_turn_result',
                   'battle:move-timer-started': 'battle_move_timer_started'}
        if payload is not None:
            fields[columns[event]] = json.dumps(payload)
        fields.update(room_id=self.room, event_name=event, player_id=subject,
                      only_show_to_player_id=recipient)
        def literal(value):
            return 'NULL' if value is None else "'" + str(value).replace('\\', '\\\\').replace("'", "\\'") + "'"
        sql('INSERT INTO event_queue (' + ','.join(fields) + ') VALUES (' +
            ','.join(literal(v) for v in fields.values()) + ')')

    def read(self, player, fresh=False):
        token = base64.urlsafe_b64encode(json.dumps({'session_id': player}).encode()).decode().rstrip('=')
        url = f'http://127.0.0.1:8087/sse/?token=e30.{token}.synthetic'
        if not fresh:
            url += '&since=0'
        events = []
        with urllib.request.urlopen(url, timeout=5) as stream:
            event = None
            for _ in range(250):
                line = stream.readline().decode().strip()
                if line.startswith('event: '):
                    event = line[7:]
                elif line.startswith('data: '):
                    body = json.loads(line[6:])
                    events.append((event, body))
                    if body.get('player_id') == 'privacy-end' or body.get('bot_id') == 'privacy-end':
                        return events
        self.fail('Missing terminal marker')

    def test_private_recipient_precedence_and_public_subject(self):
        for event in ('battle:start', 'battle:turn-result', 'battle:move-timer-started'):
            for label, subject, recipient in (
                    ('explicit', None, self.a), ('legacy', self.a, None),
                    ('empty', self.a, ''), ('conflict', self.b, self.a),
                    ('missing', None, None)):
                self.insert(event, {'battle_id': event + ':' + label,
                                   'player': {'player_id': self.a},
                                   'opponent': {'player_id': self.b},
                                   'attacker_player_id': self.a,
                                   'turn_datas': [{'attacker_player_id': self.a,
                                                   'defender_player_id': self.b}]}, subject, recipient)
        self.insert('room:user-state-changed', subject=self.b, state='WORLD')
        self.insert('emote:room', subject=self.b, recipient=self.a, emote='private-emote')
        self.insert('room:user-removed', subject='privacy-end')
        for player in (self.a, self.b):
            events = self.read(player)
            battles = [body['battle_id'] for event, body in events if event.startswith('battle:')]
            expected = [event + ':' + label
                        for event in ('battle:start', 'battle:turn-result', 'battle:move-timer-started')
                        for label in ('explicit', 'legacy', 'empty', 'conflict')] if player == self.a else []
            self.assertEqual(battles, expected)
            self.assertIn(('room:user-state-changed', {'player_id': self.b, 'state': 'WORLD'}), events)
            self.assertEqual(any(event == 'emote:room' for event, _ in events), player == self.a)
            self.assertEqual(events[-1], ('room:user-removed', {'player_id': 'privacy-end'}))

    def snapshot_rows(self):
        for label, recipient in (('public', None), ('empty', ''), ('a', self.a), ('b', self.b)):
            self.insert('room:pickup-added', recipient=recipient, pickup_id=label,
                        placement='1,2', pick_up_contents='[]')
            self.insert('room:wild-morty-added', recipient=recipient, wild_morty_id=label,
                        morty_id='MortyDefault', placement='1,2', state='WORLD', division=1)
            self.insert('room:bot-added', recipient=recipient, bot_id=label,
                        username='PrivacyBot', placement='1,2', state='WORLD', owned_morties='[]')
        self.insert('room:bot-added', bot_id='privacy-end', placement='1,2', owned_morties='[]')

    def test_fresh_sse_snapshot_respects_recipients(self):
        self.snapshot_rows()
        for player, label in ((self.a, 'a'), (self.b, 'b')):
            events = self.read(player, fresh=True)
            for event, key in (('room:pickup-added', 'pickup_id'),
                               ('room:wild-morty-added', 'wild_morty_id'), ('room:bot-added', 'bot_id')):
                expected = {'public', 'empty', label}
                if key == 'bot_id':
                    expected.add('privacy-end')
                self.assertEqual({body[key] for name, body in events if name == event}, expected)

    def test_http_snapshots_respect_recipients(self):
        self.snapshot_rows()
        for route in ('join-room', 'room-details'):
            for player, label in ((self.a, 'a'), (self.b, 'b')):
                status, body = post('/session/' + route, {'session_id': player, 'world_id': self.world})
                self.assertEqual(status, 200)
                for collection, key in (('pickups', 'pickup_id'), ('wild_morties', 'wild_morty_id'), ('bots', 'bot_id')):
                    expected = {'public', 'empty', label}
                    if key == 'bot_id':
                        expected.add('privacy-end')
                    self.assertEqual({row[key] for row in body[collection]}, expected)

    def test_publish_records_recipients_for_all_private_types(self):
        for event in ('battle:start', 'battle:turn-result', 'battle:move-timer-started'):
            php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; "
                "require '/var/www/html/lib/events.php'; "
                f"publish_event($pdo, '{self.room}', '{event}', ['battle_id'=>'fixture'], '{self.a}');")
        rows = sql(f"SELECT only_show_to_player_id FROM event_queue WHERE room_id='{self.room}'")
        self.assertEqual([row['only_show_to_player_id'] for row in rows], [self.a] * 3)

    def test_cursor_advances_past_a_batch_of_hidden_events(self):
        # The stream reads at most 200 rows per poll. The marker requires a second poll.
        values = ','.join(f"('{self.room}', 'battle:move-timer-started', '{self.a}', '{{}}')"
                          for _ in range(205))
        sql('INSERT INTO event_queue (room_id, event_name, only_show_to_player_id, '
            'battle_move_timer_started) VALUES ' + values)
        self.insert('room:user-removed', subject='privacy-end')
        self.assertEqual([event for event, _ in self.read(self.b)],
                         ['session:start', 'room:user-removed'])

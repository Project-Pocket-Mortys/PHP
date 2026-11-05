"""Deterministic same-room rejoin on real SSE code, using disposable fixtures.

Only a dedicated CLI handler is paused. HTTP join/leave still use Apache; no
production hooks, Apache signals, global locks, or emulator account changes.
This exercises SSE control flow and SQL, not HTTP stream transport.
"""
import base64
import json
import queue
import subprocess
import threading
import time
import unittest
import uuid

from test_http import COMPOSE, ROOT, php, post, sql


class SameRoomRejoinTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.player, self.session, self.room, self.world, self.nonce = (
            str(uuid.uuid4()) for _ in range(5))
        self.process = self.identity = self.reader = None
        self.events = queue.Queue()
        self.addCleanup(self.cleanup)
        sql(f"INSERT INTO room_ids (room_id, world_id, zone_id) "
            f"VALUES ('{self.room}', '{self.world}', '[1,1]')")
        sql(f"INSERT INTO users (secret, player_id, session_id, username, room_id, state, tags) "
            f"VALUES ('{self.player}', '{self.player}', '{self.session}', "
            f"'RejoinTest', '{self.room}', 'WORLD', '[]')")

    def launch_stream(self):
        payload = base64.urlsafe_b64encode(json.dumps({'session_id': self.session}).encode()).decode().rstrip('=')
        # Credentials go through stdin, never command arguments or diagnostic logs.
        wrapper = """<?php
$fields = preg_split('/\\s+/', substr(file_get_contents('/proc/self/stat'),
    strrpos(file_get_contents('/proc/self/stat'), ')') + 2));
echo json_encode(['pid' => getmypid(), 'start' => $fields[19]]) . "\\n";
flush();
$_GET = ['since' => '0', 'token' => 'TOKEN'];
require '/var/www/html/sse/index.php';
""".replace('TOKEN', f'e30.{payload}.synthetic')
        self.process = subprocess.Popen(
            COMPOSE + ['exec', '-T', '-e', f'PM_SSE_TEST_PROCESS={self.nonce}', 'web', 'php'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=ROOT)
        self.process.stdin.write(wrapper)
        self.process.stdin.close()
        self.reader = threading.Thread(target=self.read_stream, daemon=True)
        self.reader.start()
        kind, self.identity = self.events.get(timeout=10)
        self.assertEqual(kind, 'identity')
        self.assertGreater(self.identity['pid'], 1)
        self.assertEqual(self.next_label(), 'session:start')

    def read_stream(self):
        try:
            first = self.process.stdout.readline()
            self.events.put(('identity', json.loads(first)))
            event = None
            for line in self.process.stdout:
                if line.startswith('event: '):
                    event = line[7:].strip()
                elif line.startswith('data: '):
                    body = json.loads(line[6:])
                    if event == 'session:start':
                        label = event
                    elif body.get('player_id') == self.player:
                        label = {'room:user-added': 'self-arrival',
                                 'room:user-removed': 'self-departure'}.get(event, event)
                    else:
                        label = body.get('player_id', event)
                    self.events.put(('event', label))
            self.events.put(('eof', None))
        except Exception as error:
            self.events.put(('reader-error', type(error).__name__))

    def control(self, signal=0):
        # Revalidate process identity before every signal, including cleanup, so
        # a recycled PID cannot target another CLI request or an Apache worker.
        code = """
$pid = PID;
$base = '/proc/' . $pid;
if ($pid <= 1 || !is_dir($base)) { echo 'gone'; exit; }
$stat = file_get_contents($base . '/stat');
$fields = preg_split('/\\s+/', substr($stat, strrpos($stat, ')') + 2));
$env = explode("\\0", file_get_contents($base . '/environ'));
$cmd = explode("\\0", file_get_contents($base . '/cmdline'));
if ($fields[19] !== 'START' || !in_array('PM_SSE_TEST_PROCESS=NONCE', $env, true)
    || $cmd[0] !== 'php' || count(array_filter($cmd, 'strlen')) !== 1) {
    throw new RuntimeException('Dedicated SSE process identity mismatch');
}
if (SIGNAL !== 0 && !posix_kill($pid, SIGNAL)) {
    throw new RuntimeException('Dedicated SSE process signal failed');
}
echo $fields[0];
"""
        code = (code.replace('PID', str(self.identity['pid']))
                .replace('START', self.identity['start']).replace('NONCE', self.nonce)
                .replace('SIGNAL', str(signal)))
        return php(code).strip()

    def next_label(self):
        kind, label = self.events.get(timeout=5)
        self.assertEqual(kind, 'event', 'Dedicated SSE reader ended unexpectedly')
        return label

    def marker(self, label):
        sql(f"INSERT INTO event_queue (room_id, event_name, player_id) "
            f"VALUES ('{self.room}', 'room:user-removed', '{label}')")
        return int(sql(f"SELECT MAX(id) AS id FROM event_queue WHERE room_id='{self.room}'")[0]['id'])

    def wait_for(self, predicate, message):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.03)
        self.fail(message)

    def cleanup(self):
        try:
            if self.identity:
                self.control(18)  # SIGCONT, Linux research container only.
        finally:
            try:
                sql(f"DELETE FROM users WHERE player_id='{self.player}'")
            finally:
                try:
                    if self.process:
                        try:
                            self.process.wait(timeout=6)
                        except subprocess.TimeoutExpired:
                            if self.identity:
                                self.control(15)
                            self.process.wait(timeout=5)
                        if self.reader:
                            self.reader.join(timeout=2)
                        self.process.stdout.close()
                        self.process.stderr.close()
                finally:
                    sql(f"DELETE FROM event_queue WHERE room_id='{self.room}'")
                    sql(f"DELETE FROM room_ids WHERE room_id='{self.room}'")

    def test_same_room_rejoin_adopts_new_baseline_between_stream_polls(self):
        # Exercise unsigned BIGINT generations beyond PHP's signed integer range.
        generation = 9223372036854775808
        sql(f"UPDATE users SET room_membership_generation={generation} WHERE player_id='{self.player}'")
        self.launch_stream()
        initial = self.marker('initial')
        self.assertEqual(self.next_label(), 'initial')
        self.wait_for(lambda: int(sql(f"SELECT last_event_id FROM users "
                                     f"WHERE player_id='{self.player}'")[0]['last_event_id']) == initial,
                      'Initial SSE cursor did not settle')
        self.control(19)  # SIGSTOP; never an Apache or emulator process.
        self.wait_for(lambda: self.control() == 'T', 'Dedicated SSE process did not stop')

        self.assertEqual(post('/session/leave-room', {'session_id': self.session}),
                         (200, {'success': True}))
        historical = self.marker('while-away')
        status, body = post('/session/join-room', {'session_id': self.session, 'world_id': self.world})
        self.assertEqual(status, 200)
        self.assertTrue(body.get('room_id') == self.room, 'Join selected a different fixture room')
        baseline = int(sql(f"SELECT last_event_id FROM users WHERE player_id='{self.player}'")[0]['last_event_id'])
        self.assertGreaterEqual(baseline, historical)
        self.assertEqual(self.generation(), generation + 2)
        self.assertEqual(self.control(), 'T', 'SSE resumed before HTTP transition completed')
        live = self.marker('live')
        self.control(18)

        labels = []
        for _ in range(10):
            labels.append(self.next_label())
            if labels[-1] == 'live':
                break
        self.assertEqual(labels, ['self-arrival', 'live'],
                         'Same-room rejoin replayed events below the installed join baseline')
        self.wait_for(lambda: int(sql(f"SELECT last_event_id FROM users "
                                     f"WHERE player_id='{self.player}'")[0]['last_event_id']) == live,
                      'Post-join SSE cursor did not settle')

    def generation(self):
        return int(sql(f"SELECT room_membership_generation FROM users "
                       f"WHERE player_id='{self.player}'")[0]['room_membership_generation'])

    def test_leave_retry_preserves_generation_and_every_join_advances_it(self):
        self.assertEqual(self.generation(), 0)
        for expected in (1, 1):
            self.assertEqual(post('/session/leave-room', {'session_id': self.session}),
                             (200, {'success': True}))
            self.assertEqual(self.generation(), expected)
        for expected in (2, 3):
            status, _ = post('/session/join-room', {'session_id': self.session, 'world_id': self.world})
            self.assertEqual(status, 200)
            self.assertEqual(self.generation(), expected)


if __name__ == '__main__':
    unittest.main()

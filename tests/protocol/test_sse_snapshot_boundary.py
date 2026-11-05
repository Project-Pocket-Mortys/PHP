"""Pause only a synthetic CLI stream during its first pickup snapshot flush.

Production SSE code and SQL execute unchanged. This tests publication across the
fresh snapshot boundary, not Apache transport buffering or Android processing.
"""
import base64
from collections import Counter
import json
import subprocess
import threading
import unittest

import test_sse_rejoin_generation as rejoin
from test_http import COMPOSE, ROOT, sql


class SnapshotBoundaryTests(unittest.TestCase):
    def setUp(self):
        # Compose the existing harness instead of inheriting its test methods.
        self.harness = rejoin.SameRoomRejoinTests()
        self.addCleanup(lambda: self.assertTrue(self.harness.doCleanups(),
                                                'Dedicated stream fixture cleanup failed'))
        self.harness.setUp()

    def launch_fresh_stream(self):
        h = self.harness
        payload = base64.urlsafe_b64encode(json.dumps({'session_id': h.session}).encode()).decode().rstrip('=')
        wrapper = """<?php
$stat = file_get_contents('/proc/self/stat');
$fields = preg_split('/\\s+/', substr($stat, strrpos($stat, ')') + 2));
echo json_encode(['pid' => getmypid(), 'start' => $fields[19]]) . "\\n";
flush();
// A test wrapper output callback, not a hook in the production handler.
$paused = false;
ob_start(function ($chunk) use (&$paused) {
    if (!$paused && str_contains($chunk, '"pickup_id":"seed-pickup"')) {
        $paused = true;
        if (!posix_kill(getmypid(), 19)) throw new RuntimeException('Test self-stop failed');
    }
    return $chunk;
});
$_GET = ['token' => 'TOKEN'];
require '/var/www/html/sse/index.php';
""".replace('TOKEN', f'e30.{payload}.synthetic')
        h.process = subprocess.Popen(
            COMPOSE + ['exec', '-T', '-e', f'PM_SSE_TEST_PROCESS={h.nonce}', 'web', 'php'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, cwd=ROOT)
        h.process.stdin.write(wrapper)
        h.process.stdin.close()
        h.reader = threading.Thread(target=self.read_stream, daemon=True)
        h.reader.start()
        kind, identity = h.events.get(timeout=10)
        self.assertEqual(kind, 'identity')
        h.identity = identity
        self.assertGreater(identity['pid'], 1)
        self.assertEqual(h.next_label(), 'session:start')
        # The callback stops its own process. Existing harness control verifies
        # PID/start time/exact CLI command/environment nonce before every signal.
        h.wait_for(lambda: h.control() == 'T', 'Snapshot callback did not stop its dedicated process')

    def read_stream(self):
        h = self.harness
        try:
            h.events.put(('identity', json.loads(h.process.stdout.readline())))
            event = None
            for line in h.process.stdout:
                if line.startswith('event: '):
                    event = line[7:].strip()
                elif line.startswith('data: '):
                    body = json.loads(line[6:])
                    label = next((body[key] for key in
                                  ('pickup_id', 'wild_morty_id', 'bot_id', 'player_id')
                                  if key in body), event) if event != 'session:start' else event
                    h.events.put(('event', label))
            h.events.put(('eof', None))
        except Exception as error:
            h.events.put(('reader-error', type(error).__name__))

    def entity(self, kind, label):
        fields = {
            'pickup': ("pickup_id, pick_up_contents", f"'{label}', '[]'"),
            'wild-morty': ("wild_morty_id, morty_id, division, variant, shiny_if_potion",
                           f"'{label}', 'MortyDefault', 1, 'Normal', 0"),
            'bot': ("bot_id, username, player_avatar_id, owned_morties",
                    f"'{label}', 'SyntheticBot', 'RickDefault', '[]'"),
        }
        columns, values = fields[kind]
        sql(f"INSERT INTO event_queue (room_id, event_name, placement, state, {columns}) "
            f"VALUES ('{self.harness.room}', 'room:{kind}-added', '1,1', 'WORLD', {values})")

    def test_mid_snapshot_publications_are_delivered_once(self):
        h = self.harness
        self.entity('pickup', 'seed-pickup')
        self.launch_fresh_stream()
        self.entity('pickup', 'late-pickup')
        self.entity('wild-morty', 'late-wild')
        self.entity('bot', 'late-bot')
        marker = h.marker('mid-snapshot-marker')
        self.assertEqual(h.control(), 'T', 'Stream resumed before fixture publication completed')
        h.control(18)
        # Both old and repaired handlers eventually commit at least this ID.
        # A subsequent fence makes skipped marker/entity failures bounded and
        # exposes duplicates from unbounded later snapshot SELECTs as well.
        h.wait_for(lambda: int(sql(f"SELECT last_event_id FROM users WHERE "
                                 f"player_id='{h.player}'")[0]['last_event_id']) >= marker,
                   'Snapshot initialization cursor did not settle')
        h.marker('after-initialization-fence')
        labels = []
        for _ in range(15):
            labels.append(h.next_label())
            if labels[-1] == 'after-initialization-fence':
                break
        self.assertEqual(Counter(labels), Counter([
            'seed-pickup', 'late-pickup', 'late-wild', 'late-bot',
            'mid-snapshot-marker', 'after-initialization-fence',
        ]), f'Publication across the fresh snapshot boundary was skipped or duplicated; observed {labels}')


if __name__ == '__main__':
    unittest.main()

"""Exercise the research-only startup probe with isolated temporary state files.

Requires the dedicated Compose web container; never touches player data or the
handler's real state file.
"""
from concurrent.futures import ThreadPoolExecutor
import base64
import json
from pathlib import Path
import subprocess
import threading
import unittest
import uuid


ROOT = Path(__file__).resolve().parents[2]
COMPOSE = ['docker', 'compose', '-f', str(ROOT / 'compose.research.yaml')]
HANDLER = '/var/www/html/tools/research/server/online.php'


def literal(value):
    return "'" + value.replace('\\', '\\\\').replace("'", "\\'") + "'"


def php(code):
    result = subprocess.run(
        COMPOSE + ['exec', '-T', 'web', 'php', '-r', code],
        cwd=ROOT, check=True, capture_output=True, text=True, timeout=30)
    return result.stdout


class OfflineSdkProbeTests(unittest.TestCase):
    def setUp(self):
        self.directory = '/tmp/pocket-test-offline-sdk-' + uuid.uuid4().hex
        self.state = self.directory + '/state.json'
        php('if (!mkdir(' + literal(self.directory) + ', 0700)) exit(1);')
        self.addCleanup(self.remove_temporary_files)

    def remove_temporary_files(self):
        # Enumerate only this test's UUID directory; never use the real state.
        php('$dir=' + literal(self.directory) + ';'
            'foreach (scandir($dir) as $name) {'
            'if ($name === "." || $name === "..") continue;'
            '$path=$dir."/".$name;'
            'if (is_dir($path)) rmdir($path); else unlink($path);'
            '} rmdir($dir);')

    def probe(self, offline_once=True, path=None):
        return int(php('require ' + literal(HANDLER) + ';'
                       'echo research_online_status('
                       + ('true' if offline_once else 'false') + ', '
                       + literal(path or self.state) + ');'))

    def write_state(self, content):
        encoded = base64.b64encode(content).decode('ascii')
        php('if (file_put_contents(' + literal(self.state)
            + ', base64_decode(' + literal(encoded) + ')) === false) exit(1);')

    def read_state(self):
        return base64.b64decode(php('echo base64_encode(file_get_contents('
                                   + literal(self.state) + '));'))

    def test_disabled_probe_does_not_create_or_modify_state(self):
        self.assertEqual(self.probe(False), 204)
        self.assertEqual(php('echo file_exists(' + literal(self.state)
                             + ') ? "exists" : "absent";'), 'absent')
        original = b'not valid JSON; disabled mode must leave this alone'
        self.write_state(original)
        self.assertEqual(self.probe(False), 204)
        self.assertEqual(self.read_state(), original)
        self.assertEqual(self.probe(False, self.directory + '/missing/state'), 204)

    def test_first_probe_is_offline_then_count_increases_without_reset(self):
        for count, expected_status in enumerate([503, 204, 204, 204], start=1):
            self.assertEqual(self.probe(), expected_status)
            self.assertEqual(json.loads(self.read_state()),
                             {'schema_version': 1, 'probe_count': count})
        self.assertEqual(self.probe(False), 204)
        self.assertEqual(json.loads(self.read_state())['probe_count'], 4)

    def test_existing_state_continues_its_count(self):
        self.write_state(b'{"schema_version":1,"probe_count":37}')
        self.assertEqual(self.probe(), 204)
        self.assertEqual(json.loads(self.read_state()),
                         {'schema_version': 1, 'probe_count': 38})

    def test_malformed_state_fails_closed_and_is_preserved(self):
        malformed = [b'', b'not-json', b'null', b'[]', b'{}',
                     b'{"schema_version":2,"probe_count":1}',
                     b'{"schema_version":1,"probe_count":0}',
                     b'{"schema_version":1,"probe_count":-1}',
                     b'{"schema_version":1,"probe_count":1.5}',
                     b'{"schema_version":1,"probe_count":"1"}',
                     b'{"schema_version":true,"probe_count":1}',
                     b'{"schema_version":1,"probe_count":true}',
                     b'{"schema_version":1,"probe_count":9223372036854775807}',
                     b'{"probe_count":1,"schema_version":1}',
                     b'{"schema_version":1,"probe_count":1,"unexpected":0}']
        for content in malformed:
            with self.subTest(content=content):
                self.write_state(content)
                self.assertEqual(self.probe(), 503)
                self.assertEqual(self.read_state(), content)

    def test_unwritable_state_location_never_reports_online(self):
        missing_parent = self.directory + '/missing/state.json'
        self.assertEqual(self.probe(path=missing_parent), 503)
        self.assertEqual(self.probe(path=missing_parent), 503)
        self.assertEqual(self.probe(path=self.directory), 503)
        self.assertEqual(php('echo file_exists(' + literal(missing_parent)
                             + ') ? "exists" : "absent";'), 'absent')

    def test_six_concurrent_probes_have_exactly_one_offline_response(self):
        barrier = threading.Barrier(6)

        def request():
            barrier.wait(timeout=10)
            return self.probe()

        with ThreadPoolExecutor(max_workers=6) as executor:
            statuses = list(executor.map(lambda _: request(), range(6)))
        self.assertCountEqual(statuses, [503, 204, 204, 204, 204, 204])
        self.assertEqual(json.loads(self.read_state()),
                         {'schema_version': 1, 'probe_count': 6})
        self.assertEqual(self.probe(), 204)
        self.assertEqual(json.loads(self.read_state())['probe_count'], 7)


if __name__ == '__main__':
    unittest.main()

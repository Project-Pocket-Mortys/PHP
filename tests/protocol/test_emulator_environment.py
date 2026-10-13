"""Contracts specific to the isolated emulator backend, not original-server claims."""
import json
from pathlib import Path
import unittest
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


class EmulatorEnvironmentTests(unittest.TestCase):
    def test_connectivity_probe_has_no_body(self):
        with urllib.request.urlopen('http://127.0.0.1:8087/_research/online', timeout=5) as response:
            self.assertEqual(response.status, 204)
            self.assertEqual(response.read(), b'')

    def test_manifest_only_changes_asset_origin(self):
        source = (ROOT/'Aliases/rat/Android/manifest.json').read_text()
        expected = json.loads(source.replace('https://assets.conspiracyrick.com', 'http://localhost:8087'))
        with urllib.request.urlopen('http://127.0.0.1:8087/Aliases/rat/Android/manifest.json', timeout=5) as response:
            self.assertEqual(json.load(response), expected)


if __name__ == '__main__':
    unittest.main()

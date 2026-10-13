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
        for platform in ('Android', 'iOS'):
            with self.subTest(platform=platform):
                source = (ROOT/f'Aliases/rat/{platform}/manifest.json').read_text()
                expected = json.loads(source.replace('https://assets.conspiracyrick.com', 'http://localhost:8087')
                    .replace('https://github.com/Project-Pocket-Mortys/.github/raw/refs/heads/main', 'http://localhost:8087'))
                with urllib.request.urlopen(f'http://127.0.0.1:8087/Aliases/rat/{platform}/manifest.json', timeout=5) as response:
                    actual = json.load(response)
                self.assertEqual(actual, expected)
                for entry in actual.values():
                    if isinstance(entry, dict) and 'url' in entry:
                        self.assertTrue(entry['url'].startswith('http://localhost:8087/AssetBundles/'))


if __name__ == '__main__':
    unittest.main()

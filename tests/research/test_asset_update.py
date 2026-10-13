"""Prevent stale version-1011 caches from hiding changed upstream bundles."""
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools/research'))
from audit_asset_update import audit


class AssetUpdateTests(unittest.TestCase):
    def test_changed_payloads_invalidate_existing_android_cache(self):
        report = audit('7576d6b')
        self.assertEqual(report['cache_version_collisions'], [])


if __name__ == '__main__':
    unittest.main()

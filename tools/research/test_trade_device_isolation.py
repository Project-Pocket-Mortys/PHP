"""Pure allowlist/path checks; never launches devices or contacts the DB."""
from pathlib import Path
import tempfile
import unittest

from native_trade_fixture import ROOT, safe_path
from startup_capture_device import Device, dedicated_path


class TradeDeviceIsolationTests(unittest.TestCase):
    def test_trading_roles_have_distinct_userdata_and_serials(self):
        devices = [Device(role) for role in ('primary', 'peer', 'trade-primary', 'trade-peer')]
        self.assertEqual(len({d.path for d in devices}), 4)
        self.assertEqual(len({d.serial for d in devices}), 4)
        self.assertEqual([d.port for d in devices[2:]], [5564, 5566])
        self.assertTrue(all(d.port not in (5556, 5558) for d in devices))

    def test_original_and_arbitrary_device_names_cannot_be_provisioned(self):
        for name in ('PocketMortys_API30', 'PocketMortys_API30_Peer', '../PocketMortys_API30', 'arbitrary'):
            with self.subTest(name=name), self.assertRaises(ValueError):
                dedicated_path(name)

    def test_fixture_receipts_cannot_target_source_or_external_paths(self):
        for path in (ROOT, ROOT / 'docs/protocol', ROOT / '.research/../docs', Path(tempfile.gettempdir())):
            with self.subTest(path=str(path)), self.assertRaises(ValueError):
                safe_path(path)
        self.assertEqual(safe_path(ROOT / '.research/trade-test-unused-path'),
                         ROOT / '.research/trade-test-unused-path')


if __name__ == '__main__':
    unittest.main()

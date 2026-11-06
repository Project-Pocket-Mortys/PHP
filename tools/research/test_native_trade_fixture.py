"""Pure account binding checks; never contacts the database or devices."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from native_trade_fixture import database, manifest_player, validate_account


class NativeTradeFixtureAccountTests(unittest.TestCase):
    def manifest(self, account):
        return {'version': 1, 'account': account,
                'snapshot': {'users': [{'username': account, 'player_id': 'test-player'}]}}

    def test_only_dedicated_trade_accounts_are_allowed(self):
        for account in ('PMTrade01', 'PMTrade02'):
            self.assertEqual(validate_account(account), account)
        for account in ('PMStartup01', 'PMStartup02', 'pmtrade01', 'PMTrade03', '', None):
            with self.subTest(account=account), self.assertRaises(ValueError):
                validate_account(account)

    def test_manifest_binds_selected_account_and_snapshot_owner(self):
        for account, other in (('PMTrade01', 'PMTrade02'), ('PMTrade02', 'PMTrade01')):
            manifest = self.manifest(account)
            self.assertEqual(manifest_player(manifest, account), 'test-player')
            with self.assertRaises(ValueError):
                manifest_player(manifest, other)
            manifest['snapshot']['users'][0]['username'] = other
            with self.assertRaises(ValueError):
                manifest_player(manifest, account)

    def test_manifest_rejects_multiple_owners_and_unsupported_version(self):
        manifest = self.manifest('PMTrade01')
        manifest['snapshot']['users'] *= 2
        with self.assertRaises(ValueError):
            manifest_player(manifest, 'PMTrade01')
        manifest = self.manifest('PMTrade01')
        manifest['version'] = 2
        with self.assertRaises(ValueError):
            manifest_player(manifest, 'PMTrade01')

    @patch('native_trade_fixture.subprocess.run')
    def test_database_defaults_legacy_calls_and_passes_selected_account(self, run):
        run.return_value = SimpleNamespace(returncode=0, stdout='{}')
        for payload, expected in (({'action': 'observe'}, 'PMTrade01'),
                                  ({'action': 'observe', 'account': 'PMTrade02'}, 'PMTrade02')):
            original = dict(payload)
            self.assertEqual(database(payload), {})
            self.assertEqual(json.loads(run.call_args.kwargs['input'])['account'], expected)
            self.assertEqual(payload, original)

    @patch('native_trade_fixture.subprocess.run')
    def test_database_rejects_other_accounts_before_launching_process(self, run):
        with self.assertRaises(ValueError):
            database({'action': 'prepare', 'account': 'PMStartup01'})
        run.assert_not_called()


if __name__ == '__main__':
    unittest.main()

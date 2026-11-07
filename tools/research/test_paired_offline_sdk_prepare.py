"""Pure preparation tests: no Docker, ADB, network, or retained app changes."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

import prepare_offline_sdk_device as prepare


class PairedOfflineSDKPreparationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        handler = self.root / 'tools/research/server/online.php'
        handler.parent.mkdir(parents=True)
        handler.write_text('fixture source')
        self.output = self.root / '.research/fresh-preparation'
        self.device = MagicMock(name='retained_device')
        self.device.name = 'retained-avd'
        self.device.serial = 'emulator-test'
        self.device.adb.return_value.stdout = b'package:retained.apk\n'
        self.run = self.start_patch('subprocess.run')
        self.run.return_value.returncode = 0
        self.device_type = self.start_patch('Device', return_value=self.device)
        self.urlopen = self.start_patch('urllib.request.urlopen')
        self.urlopen.return_value.__enter__.return_value.status = 200
        self.start_patch('ROOT', self.root)

    def start_patch(self, name, *args, **kwargs):
        patcher = patch.object(prepare, name, *args, **kwargs) if '.' not in name else patch(
            'prepare_offline_sdk_device.' + name, *args, **kwargs)
        value = patcher.start()
        self.addCleanup(patcher.stop)
        return value

    def assert_routing(self, role, instance, service, port):
        prepare.prepare(role, self.output, instance)
        command = self.run.call_args.args[0]
        self.assertEqual(command[-7:], ['exec', '-T', service, 'test', '!', '-e',
                                       '/tmp/pocket-research-offline-sdk-once.json'])
        self.assertEqual(command.count('-f'), 2 if instance == 'peer' else 1)
        if instance == 'peer':
            self.assertIn(str(self.root / 'compose.research-trade-pair.yaml'), command)
        self.urlopen.assert_called_once_with(f'http://localhost:{port}/time', timeout=10)
        self.device_type.assert_called_once_with(role)
        self.device.verify.assert_called_once_with()
        self.device.install.assert_called_once_with()  # Existing-package hash verification.
        self.device.network.assert_called_once_with(False)
        self.device.adb.assert_any_call('reverse', 'tcp:8087', f'tcp:{port}')
        self.device.adb.assert_any_call('reverse', 'tcp:8089', f'tcp:{port}')
        record = json.loads((self.output / 'preparation.json').read_text())
        self.assertEqual((record['instance'], record['service'], record['host_port']),
                         (instance, service, port))
        for flag in ('package_reinstalled', 'app_data_cleared', 'consent_edited', 'probe_state_reset'):
            self.assertIs(record[flag], False)
        for call in self.device.adb.call_args_list:
            self.assertNotIn('install', call.args)
            self.assertNotIn('clear', call.args)

    def test_peer_has_independent_service_and_port(self):
        self.assert_routing('trade-peer', 'peer', 'offline-sdk-peer', 8093)

    def test_primary_instance_remains_compatible(self):
        self.assert_routing('trade-primary', 'primary', 'offline-sdk-web', 8091)

    def test_default_instance_is_unchanged_for_all_roles(self):
        for role in prepare.DEVICES:
            with self.subTest(role=role):
                output = self.output / role
                prepare.prepare(role, output)
                self.assertEqual(self.run.call_args.args[0][-5], 'offline-sdk-web')
                self.device.adb.assert_any_call('reverse', 'tcp:8087', 'tcp:8091')

    def test_peer_rejects_every_other_role_before_actions(self):
        for role in prepare.DEVICES:
            if role != 'trade-peer':
                with self.subTest(role=role), self.assertRaises(ValueError):
                    prepare.prepare(role, self.output, 'peer')
        self.run.assert_not_called()
        self.device_type.assert_not_called()

    def test_unknown_instance_rejected_before_actions(self):
        with self.assertRaises(ValueError):
            prepare.prepare('trade-peer', self.output, 'unknown')
        self.run.assert_not_called()

    def test_used_or_unavailable_peer_never_resets_or_touches_device(self):
        self.run.return_value.returncode = 1
        with self.assertRaisesRegex(RuntimeError, 'Fresh offline-sdk-peer required'):
            prepare.prepare('trade-peer', self.output, 'peer')
        self.run.assert_called_once()
        self.urlopen.assert_not_called()
        self.device_type.assert_not_called()
        self.assertFalse(self.output.exists())

    def test_unhealthy_peer_does_not_touch_device(self):
        self.urlopen.return_value.__enter__.return_value.status = 503
        with self.assertRaisesRegex(RuntimeError, 'not healthy'):
            prepare.prepare('trade-peer', self.output, 'peer')
        self.device_type.assert_not_called()

    def test_existing_evidence_is_preserved_before_actions(self):
        self.output.mkdir(parents=True)
        with self.assertRaisesRegex(ValueError, 'already exists'):
            prepare.prepare('trade-peer', self.output, 'peer')
        self.run.assert_not_called()


if __name__ == '__main__':
    unittest.main()

"""Device selection must fail closed and provisioning must preserve saves."""
import contextlib
import importlib.util
import io
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'tools/research' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


setup = load_tool('emulator_setup')
installer = load_tool('install_research_client')


class EmulatorToolsTests(unittest.TestCase):
    def test_devices_have_separate_userdata_and_reprovision_preserves_saves(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(setup, 'WORK', Path(directory)):
            primary = setup.provision_avd('PocketMortys_API30')
            primary_config = (primary / 'config.ini').read_bytes()
            save = primary / 'userdata-qemu.img'
            save.write_bytes(b'existing save')
            peer = setup.provision_avd('PocketMortys_API30_Peer')
            self.assertNotEqual(primary, peer)
            self.assertIn('AvdId=PocketMortys_API30_Peer', (peer / 'config.ini').read_text())
            self.assertFalse((peer / 'userdata-qemu.img').exists())
            setup.provision_avd('PocketMortys_API30')
            self.assertEqual((primary / 'config.ini').read_bytes(), primary_config)
            self.assertEqual(save.read_bytes(), b'existing save')

    def test_setup_rejects_shared_locator_and_arbitrary_avd(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(setup, 'WORK', Path(directory)):
            primary = setup.provision_avd('PocketMortys_API30')
            locator = primary.parent / 'PocketMortys_API30_Peer.ini'
            locator.write_text(f'path={primary}\n')
            with self.assertRaisesRegex(ValueError, 'dedicated directory'):
                setup.provision_avd('PocketMortys_API30_Peer')
            with self.assertRaises(ValueError):
                setup.provision_avd('../OtherDevice')

    def test_installer_maps_serial_and_rejects_mismatched_pair(self):
        self.assertEqual(installer.parse_args([]).serial, 'emulator-5556')
        self.assertEqual(installer.parse_args(['--avd', 'PocketMortys_API30_Peer']).serial,
                         'emulator-5558')
        with contextlib.redirect_stderr(io.StringIO()):
            for argv in (['--avd', 'OtherDevice'], ['--serial', 'emulator-5558'],
                         ['--avd', 'PocketMortys_API30_Peer', '--serial', 'emulator-5556']):
                with self.assertRaises(SystemExit) as error:
                    installer.parse_args(argv)
                self.assertEqual(error.exception.code, 2)

    def test_adb_targets_selected_device_on_dedicated_server(self):
        with patch.object(installer, 'SERIAL', 'emulator-5558'), patch.object(installer.subprocess, 'run') as run:
            installer.adb('shell', 'true')
        self.assertEqual(run.call_args.args[0][1:],
                         ['-P', '5038', '-s', 'emulator-5558', 'shell', 'true'])

    @unittest.skipUnless(shutil.which('powershell'), 'Windows PowerShell required')
    def test_launcher_rejects_mismatched_port_before_using_adb(self):
        result = subprocess.run(['powershell', '-NoProfile', '-File',
                                 str(ROOT / 'tools/research/emulator.ps1'),
                                 '-Avd', 'PocketMortys_API30_Peer', '-Port', '5556'],
                                capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('restricted to emulator port 5558', result.stderr)


if __name__ == '__main__':
    unittest.main()

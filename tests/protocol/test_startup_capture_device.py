"""Startup tooling must refuse original devices and redirected userdata."""
import importlib.util
import hashlib
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[2] / 'tools/research/startup_capture_device.py'
SPEC = importlib.util.spec_from_file_location('startup_capture_device', SOURCE)
device = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(device)


class StartupDeviceGuards(unittest.TestCase):
    def test_original_names_refused(self):
        for name in ('PocketMortys_API30', 'PocketMortys_API30_Peer', '../escape'):
            with self.assertRaises(ValueError):
                device.dedicated_path(name)
        self.assertEqual({port for _, port in device.DEVICES.values()}, {5560, 5562})

    def test_redirected_locator_refused_before_adb(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(device, 'AVDS', Path(tmp)):
            selected = device.Device('primary')
            (Path(tmp) / (selected.name + '.ini')).write_text('path=' + str(Path(tmp) / 'original.avd'))
            with patch.object(selected, 'adb') as adb:
                with self.assertRaises(ValueError):
                    selected.verify()
                adb.assert_not_called()

    def test_config_cannot_redirect_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            config = path / 'config.ini'
            config.write_text('AvdId=PocketMortys_API30_Startup\n'
                              'image.sysdir.1=system-images/android-30/google_apis/x86_64/\n'
                              'disk.dataPartition.path=C:/original/userdata.img\n')
            with self.assertRaises(ValueError):
                device.validate_config(path, 'PocketMortys_API30_Startup')

    def test_wrong_device_identity_refused(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(device, 'AVDS', Path(tmp)):
            selected = device.Device('peer')
            selected.path.mkdir()
            (Path(tmp) / (selected.name + '.ini')).write_text('path=' + str(selected.path))
            with patch.object(device, 'validate_config'), patch.object(selected, 'adb') as adb:
                adb.return_value.stdout = b'PocketMortys_API30_Peer\nOK\n'
                with self.assertRaises(ValueError):
                    selected.verify()

    def test_existing_package_identity_mismatch_never_reinstalls(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(device, 'WORK', Path(tmp)):
            signed = Path(tmp) / 'research-signed'
            signed.mkdir()
            for name in ('base-aligned-debugSigned.apk', 'split_config.armeabi_v7a-aligned-debugSigned.apk'):
                (signed / name).write_bytes(name.encode())
            selected = device.Device('primary')
            def output(*args, **kwargs):
                if args[:3] == ('shell', 'pm', 'path'):
                    return SimpleNamespace(stdout=b'package:/data/app/example/base.apk\npackage:/data/app/example/split_config.armeabi_v7a.apk\n')
                if args[:2] == ('shell', 'sha256sum'):
                    return SimpleNamespace(stdout=(hashlib.sha256(b'foreign APK').hexdigest() + '  /data/app/example/base.apk\n').encode())
                self.fail('Unexpected command, including any install: ' + repr(args))
            with patch.object(selected, 'verify'), patch.object(selected, 'adb', side_effect=output):
                with self.assertRaisesRegex(ValueError, 'identity differs'):
                    selected.install()


if __name__ == '__main__':
    unittest.main()

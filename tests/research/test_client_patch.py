"""Validate byte-preserving research patches against the supplied APK (if present)."""
import hashlib
import importlib.util
from pathlib import Path
import struct
import unittest
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('research_client', ROOT/'tools/research/research_client.py')
client = importlib.util.module_from_spec(spec)
spec.loader.exec_module(client)


@unittest.skipUnless((ROOT/'.research/android/base.apk').exists(), 'Extract the supplied APKM first')
class ResearchPatchTests(unittest.TestCase):
    def test_multiplayer_probe_only_overrides_two_onboarding_queries(self):
        original = (ROOT/'.research/android/split_config.armeabi_v7a/lib/armeabi-v7a/libil2cpp.so').read_bytes()
        transport = client.patch_arm32_transport(original)
        probe = client.patch_arm32_transport(original, multiplayer_probe=True)
        allowed = set(range(0xb05e9c, 0xb05ea4)) | set(range(0xb05ed0, 0xb05ed8))
        changed = {i for i, pair in enumerate(zip(transport, probe)) if pair[0] != pair[1]}
        self.assertTrue(changed and changed <= allowed)
        for address in (0xb05e9c, 0xb05ed0):
            self.assertEqual(probe[address:address+8], bytes.fromhex('0100a0e31eff2fe1'))
        with self.assertRaises(ValueError):
            client.patch_arm32_transport(probe, multiplayer_probe=True)

    def test_transport_profile_preserves_hostname_guard_and_changes_one_native_byte(self):
        library = ROOT/'.research/android/split_config.armeabi_v7a/lib/armeabi-v7a/libil2cpp.so'
        original = library.read_bytes()
        patched = client.patch_arm32_transport(original)
        self.assertEqual(len(original), len(patched))
        self.assertEqual([i for i, pair in enumerate(zip(original, patched)) if pair[0] != pair[1]], [0xeea0cc])
        self.assertEqual(patched[0xeea0cc:0xeea0d8], bytes.fromhex('001100e3000096e5b812c4e1'))
        with zipfile.ZipFile(ROOT/'.research/android/base.apk') as apk:
            metadata = apk.read(client.METADATA)
        _, changes = client.redirect_metadata(metadata, local_transport=True)
        self.assertEqual(len(changes), 7)
        self.assertEqual([x['after'] for x in changes if x['before'] == '*.bps-pmnet.com'], ['localhost'])
        self.assertTrue(all(x['after'].startswith('http://localhost:8087') for x in changes if x['before'].startswith('https:')))

    def test_http_setting_only_changes_reviewed_field(self):
        with zipfile.ZipFile(ROOT/'.research/android/base.apk') as apk:
            original = apk.read(client.PLAYER_SETTINGS)
        patched = client.allow_local_http(original)
        self.assertEqual(len(patched), len(original))
        self.assertEqual([i for i in range(len(original)) if original[i] != patched[i]], [209724])
        self.assertEqual(struct.unpack_from('<I', patched, 209724)[0], 2)

    def test_only_declared_dex_ranges_change_and_checksums_validate(self):
        total = 0
        with zipfile.ZipFile(ROOT/'.research/android/base.apk') as apk:
            for name in ('classes.dex', 'classes2.dex', 'classes3.dex'):
                original = apk.read(name)
                patched, records = client.patch_dex(original)
                total += len(records)
                expected = bytearray(original)
                for record in records:
                    offset = record['instruction_offset']
                    before, after = bytes.fromhex(record['before']), bytes.fromhex(record['after'])
                    self.assertEqual(before, original[offset:offset+len(before)])
                    self.assertEqual(len(before), len(after))
                    expected[offset:offset+len(after)] = after
                if records:
                    expected[12:32] = hashlib.sha1(expected[32:]).digest()
                    struct.pack_into('<I', expected, 8, zlib.adler32(expected[12:]) & 0xffffffff)
                self.assertEqual(patched, expected)
        self.assertEqual(total, 2)

    def test_metadata_preserves_layout_and_changes_only_six_literals(self):
        with zipfile.ZipFile(ROOT/'.research/android/base.apk') as apk:
            original = apk.read(client.METADATA)
        patched, changes = client.redirect_metadata(original)
        self.assertEqual(len(changes), 6)
        self.assertEqual(len(patched), len(original))
        table, size, data_start = struct.unpack_from('<3I', original, 8)
        changed = {c['literal_index']: c for c in changes}
        for index in range(size // 8):
            old_len, old_offset = struct.unpack_from('<II', original, table+index*8)
            new_len, new_offset = struct.unpack_from('<II', patched, table+index*8)
            self.assertEqual(old_offset, new_offset)
            value = patched[data_start+new_offset:data_start+new_offset+new_len]
            if index in changed:
                self.assertEqual(value, changed[index]['after'].encode())
            else:
                self.assertEqual(new_len, old_len)
                self.assertEqual(value, original[data_start+old_offset:data_start+old_offset+old_len])


if __name__ == '__main__':
    unittest.main()

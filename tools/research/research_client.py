"""Build an author-authorized, local-only startup research APK; keep originals intact.

Only the inspected 2.41.0 base is accepted. Licensing initialization is skipped
and an unavailable billing client reports failure. Optional local transport also
changes one ARM32 constructor byte while retaining a localhost-only allowlist.
"""
import hashlib
import argparse
import json
from pathlib import Path
import shutil
import struct
import zipfile
import zlib

ROOT = Path(__file__).resolve().parents[2]
BASE_SHA = 'b44f255bdd58b3196d73ff811c3e645d68edcbd76366a39f5c4489bc538ebf74'
CLASS = 'Lcom/pairip/licensecheck/LicenseClient;'
METHOD = 'initializeLicenseCheck'
BILLING_CLASS = 'Lcom/prime31/GoogleIABPlugin;'
METADATA = 'assets/bin/Data/Managed/Metadata/global-metadata.dat'
PLAYER_SETTINGS = 'assets/bin/Data/globalgamemanagers'


def allow_local_http(original):
    # UnityPy 1.25.0: PlayerSettings object starts at 208864, field at +860.
    # Re-serializing that object changes only this byte (NotAllowed -> AlwaysAllowed).
    if hashlib.sha256(original).hexdigest() != 'fcc8db5017b103ed7b93c50327aa77695164bd00a4a9b0ea8bf160831f978dd2':
        raise ValueError('Unexpected PlayerSettings asset')
    data = bytearray(original)
    if struct.unpack_from('<I', data, 209724)[0] != 0:
        raise ValueError('Unexpected insecureHttpOption')
    struct.pack_into('<I', data, 209724, 2)
    return bytes(data)


def redirect_metadata(original, local_transport=False):
    data = bytearray(original)
    magic, version, table, size, base, _ = struct.unpack_from('<6I', data)
    if (magic, version) != (0xfab11baf, 31):
        raise ValueError('Unexpected metadata header')
    redirects = {
        b'https://clients3.google.com/generate_204': b'http://127.0.0.1:8087/_research/online',
        b'https://{0}.game.bps-pmnet.com': b'http://127.0.0.1:8087',
        b'https://assets.bps-pmnet.com/Aliases/{0}/{1}': b'http://127.0.0.1:8087/Aliases/{0}/{1}',
        b'https://assets.bps-pmnet.com/Status': b'http://127.0.0.1:8087/Status',
        b'https://newc137.bps-pmnet.com/is-gdpr': b'http://127.0.0.1:8087/is-gdpr',
        b'https://newc137.bps-pmnet.com/time?a=pm_{0}': b'http://127.0.0.1:8087/time?a=pm_{0}',
    }
    if local_transport:
        redirects = {key: value.replace(b'127.0.0.1', b'localhost') for key, value in redirects.items()}
        redirects[b'*.bps-pmnet.com'] = b'localhost'
    changes = []
    for entry in range(table, table + size, 8):
        length, index = struct.unpack_from('<II', data, entry)
        before = bytes(data[base + index:base + index + length])
        if before not in redirects:
            continue
        after = redirects[before]
        if len(after) > length:
            raise ValueError('Replacement exceeds literal storage')
        data[base + index:base + index + length] = after.ljust(length, b'\0')
        struct.pack_into('<I', data, entry, len(after))
        changes.append({'literal_index': (entry-table)//8, 'before': before.decode(),
                        'after': after.decode()})
    if len(changes) != len(redirects):
        raise ValueError('Did not find all expected URL literals')
    return bytes(data), changes


def patch_arm32_transport(original):
    """Allow HTTP while retaining hostname validation restricted to localhost."""
    if hashlib.sha256(original).hexdigest() != 'd51c2884f6a3045febfa1434ffdc83e4775ebaa8790fe4153fa1a1660b3742e7':
        raise ValueError('Unexpected ARM32 library')
    offset = 0xeea0cc
    # NetworkHTTP constructor: movw r1,#0x101; ... strh r1,[r4,#0x28].
    # Low byte is enforceHTTPSOnly; high byte is enableHostnameValidation.
    if original[offset:offset+4] != bytes.fromhex('011100e3'):
        raise ValueError('Unexpected constructor instruction')
    data = bytearray(original)
    data[offset:offset+4] = bytes.fromhex('001100e3')  # movw r1,#0x100
    return bytes(data)


def patch_dex(original):
    data = bytearray(original)
    def u32(offset):
        return struct.unpack_from('<I', data, offset)[0]
    def leb(offset):
        value = 0
        for shift in range(0, 35, 7):
            byte = data[offset]
            offset += 1
            value |= (byte & 127) << shift
            if byte < 128:
                return value, offset
        raise ValueError('Invalid ULEB128')
    strings = []
    for index in range(u32(56)):
        _, start = leb(u32(u32(60) + index * 4))
        end = data.index(0, start)
        strings.append(data[start:end].decode('utf-8', errors='replace'))
    types = [strings[u32(u32(68) + i * 4)] for i in range(u32(64))]
    methods = []
    for index in range(u32(88)):
        cls, proto, name = struct.unpack_from('<HHI', data, u32(92) + index * 8)
        methods.append((types[cls], strings[name], proto))
    fields = []
    for index in range(u32(80)):
        cls, typ, name = struct.unpack_from('<HHI', data, u32(84) + index * 8)
        fields.append((types[cls], strings[name]))
    matches = []
    for index in range(u32(96)):
        offset = u32(100) + index * 32
        if types[u32(offset)] not in (CLASS, BILLING_CLASS):
            continue
        cursor = u32(offset + 24)
        counts = []
        for _ in range(4):
            value, cursor = leb(cursor)
            counts.append(value)
        for _ in range(counts[0] + counts[1]):
            _, cursor = leb(cursor)
            _, cursor = leb(cursor)
        for count in counts[2:]:
            method_index = 0
            for _ in range(count):
                difference, cursor = leb(cursor)
                method_index += difference
                _, cursor = leb(cursor)
                code, cursor = leb(cursor)
                cls, name, proto = methods[method_index]
                if cls == BILLING_CLASS and name == 'queryInventory':
                    proto_offset = u32(76) + proto * 12
                    parameters = u32(proto_offset + 8)
                    if not parameters or u32(parameters) != 1:
                        continue
                    typ = struct.unpack_from('<H', data, parameters + 4)[0]
                    if types[typ] != '[Ljava/lang/String;':
                        continue
                    start = code + 16
                    before = bytes(data[start:start + 26])
                    registers, inputs = struct.unpack_from('<HH', data, code)
                    if (registers, inputs) != (6, 2) or [before[i] for i in (0,6,8,14,16,20)] != [0x6e,0x0c,0x6e,0x0c,0x1a,0x71]:
                        raise ValueError('Unexpected billing logging prologue')
                    billing = fields.index((BILLING_CLASS, 'billingClient'))
                    reason = fields.index((BILLING_CLASS, 'BILLING_NOT_RUNNING_ERROR'))
                    callback = strings.index('queryInventoryFailed')
                    send = [i for i,m in enumerate(methods) if m[:2] == (BILLING_CLASS, 'UnitySendMessage')]
                    if len(send) != 1:
                        raise ValueError('Ambiguous UnitySendMessage')
                    # Preserve initialized behavior by branching to the first instruction
                    # after the original logging prologue. Missing service reports failure.
                    units = [0x4054,billing, 0x0039,11, 0x001a,callback,
                             0x0162,reason, 0x306e,send[0],0x0104, 0x000e,0x0000]
                    after = struct.pack('<13H', *units)
                    data[start:start + 26] = after
                    matches.append({'method': BILLING_CLASS+'->queryInventory([Ljava/lang/String;)V',
                                    'code_offset':code, 'instruction_offset':start,
                                    'before':before.hex(), 'after':after.hex()})
                    continue
                if (cls, name) != (CLASS, METHOD):
                    continue
                proto_offset = u32(76) + proto * 12
                if types[u32(proto_offset + 4)] != 'V' or u32(proto_offset + 8) != 0:
                    raise ValueError('Unexpected method prototype')
                start = code + 16
                before = bytes(data[start:start + 4])
                if before[:2] != b'\x62\x00':
                    raise ValueError('Expected inspected sget-object v0 instruction')
                # Replace the complete two-code-unit instruction: return-void; nop.
                data[start:start + 4] = b'\x0e\x00\x00\x00'
                matches.append({'method': CLASS + '->' + METHOD + '()V',
                                'code_offset': code, 'instruction_offset': start,
                                'before': before.hex(), 'after': '0e000000'})
    if not matches:
        return original, []
    if len({m['method'] for m in matches}) != len(matches):
        raise ValueError('Ambiguous patch target')
    data[12:32] = hashlib.sha1(data[32:]).digest()
    struct.pack_into('<I', data, 8, zlib.adler32(data[12:]) & 0xffffffff)
    return bytes(data), matches


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--local-server', action='store_true')
    parser.add_argument('--local-transport', action='store_true',
                        help='ARM32: permit HTTP to the localhost-only hostname allowlist')
    args = parser.parse_args()
    if args.local_transport:
        args.local_server = True
    source = ROOT / '.research/android/base.apk'
    if hashlib.sha256(source.read_bytes()).hexdigest() != BASE_SHA:
        raise ValueError('Only the inspected original 2.41.0 base APK is supported')
    output = ROOT / '.research/emulator/research-client'
    output.mkdir(parents=True, exist_ok=True)
    records = []
    redirects = []
    with zipfile.ZipFile(source) as src, zipfile.ZipFile(output / 'base.apk', 'w') as dest:
        for entry in src.infolist():
            if entry.filename.startswith('META-INF/'):
                continue
            content = src.read(entry)
            if entry.filename.endswith('.dex'):
                content, patches = patch_dex(content)
                records.extend(dict(p, dex=entry.filename) for p in patches)
            if args.local_server and entry.filename == METADATA:
                content, redirects = redirect_metadata(content, args.local_transport)
            if args.local_server and entry.filename == PLAYER_SETTINGS:
                content = allow_local_http(content)
            dest.writestr(entry, content)
    if len(records) != 2:
        raise ValueError('Expected exactly two startup patches')
    for name in ['split_config.armeabi_v7a.apk', 'split_config.arm64_v8a.apk']:
        shutil.copy2(ROOT / '.research/android' / name, output / name)
    if args.local_transport:
        name = 'split_config.armeabi_v7a.apk'
        with zipfile.ZipFile(ROOT / '.research/android' / name) as src, zipfile.ZipFile(output / name, 'w') as dest:
            for entry in src.infolist():
                if entry.filename.startswith('META-INF/'):
                    continue
                content = src.read(entry)
                if entry.filename == 'lib/armeabi-v7a/libil2cpp.so':
                    content = patch_arm32_transport(content)
                dest.writestr(entry, content)
    report = {'original_base_sha256': BASE_SHA, 'patches': records, 'url_redirects': redirects,
              'insecureHttpOption': 2 if args.local_server else 'unchanged',
              'local_transport': args.local_transport,
              'native_patch': {'architecture': 'ARM32', 'offset': '0xeea0cc',
                               'before': '011100e3', 'after': '001100e3'} if args.local_transport else None,
              'scope': 'Local startup research; does not confer a Play license or purchase entitlement.'}
    (output / 'patch.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))

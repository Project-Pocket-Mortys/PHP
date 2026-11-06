"""Export only the documented OneTrust startup methods and two direct-call scans.

No native execution, device access, or consent/cache writes. Capstone is loaded
from the existing ignored research dependency directory.
"""
import bisect
import re
import hashlib
import json
import struct
import sys
from pathlib import Path

EXPECTED_METADATA = "b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10"
EXPECTED_SCRIPT = "a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb"
METHOD_NAMES = (
    'App$$GetDataUseConsent',
    'AssetBundleState$$CheckForInternetConnection',
    'BrazeController$$Awake',
    'BrazeController$$SDKConsentChange',
    'ConsentState.<>c$$<ActivateComplete>b__3_0',
    'ConsentState.<ActivateComplete>d__3$$MoveNext',
    'FirebaseController$$Awake',
    'FirebaseController$$SDKConsentChange',
    'IronSourceController$$Awake',
    'IronSourceController$$SDKConsentChanged',
    'OneTrust.CMPSDK$$.cctor',
    'OneTrust.CMPSDK$$OTSDK_logger',
    'OneTrust.CMPSDK$$allowedToDownload',
    'OneTrust.CMPSDK$$getConsentStatusForCategory',
    'OneTrust.CMPSDK$$get_DomainData',
    'OneTrust.CMPSDK$$get_domainData_Groups',
    'OneTrust.CMPSDK$$get_shouldShowBanner',
    'OneTrust.CMPSDK$$loadCache',
    'OneTrust.CMPSDK$$sdkVersion',
    'OneTrust.CMPSDK$$setFactoryDefaults',
    'OneTrust.CMPSDK$$updateGroupsArray',
    'OneTrust.CMPSDK.<StartSDK>d__112$$MoveNext',
    'OneTrust.CMPSDK.<initOTSDKDataAsync>d__221$$MoveNext',
    'OneTrustController$$.ctor',
    'OneTrustController$$<Awake>b__14_0',
    'OneTrustController$$<UpdateSDKs>b__34_0',
    'OneTrustController$$<WriteBannerData>b__35_0',
    'OneTrustController$$<WritePreferenceCenterData>b__36_0',
    'OneTrustController$$Awake',
    'OneTrustController$$SDKEventHandler',
    'OneTrustController$$ShowBanner',
    'OneTrustController$$UpdateSDKs',
    'OneTrustController$$get_Initialized',
    'OneTrustController.<>c$$<get_Initialized>b__1_0',
    'OneTrustController.<CopyFileFromStreamingToPersistentDirectory>d__42$$MoveNext',
    'OneTrustController.<CopySDKFiles>d__40$$MoveNext',
)

sys.path.insert(0, '.research/python')
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

if sys.argv[1:] == ['--filter']:
    print('|'.join(re.escape(name) for name in METHOD_NAMES))
    raise SystemExit(0)
if len(sys.argv) != 2:
    raise SystemExit('Usage: onetrust-recovery-bounded.py OUTPUT_DIR | --filter | --verify-inputs')
verify_only = sys.argv[1] == '--verify-inputs'
out = None if verify_only else Path(sys.argv[1])
if out is not None:
    for filename in ('arm64.txt', 'methods.json', 'direct-callers.json'):
        if (out / filename).exists():
            raise SystemExit(f'Refusing to overwrite evidence: {out / filename}')
binary = Path('.research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so').read_bytes()
digest = lambda data: hashlib.sha256(data).hexdigest()
assert digest(binary) == 'ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326'
metadata = Path('.research/android/base/assets/bin/Data/Managed/Metadata/global-metadata.dat').read_bytes()
assert struct.unpack_from('<II', metadata) == (0xFAB11BAF, 31)
script = Path('.research/dumper/script.json').read_bytes()
assert digest(metadata) == EXPECTED_METADATA, 'Metadata hash mismatch'
assert digest(script) == EXPECTED_SCRIPT, 'Dumper mapping hash mismatch'
if verify_only:
    print('OneTrust inputs verified: ARM64 binary, IL2CPP v31 metadata, dumper mapping')
    raise SystemExit(0)
inspection = json.loads((out/'artifact.json').read_text())
assert inspection['subject']['digest']['sha256'] == digest(binary)
assert (out/'rea-version.txt').read_text().strip() == '6.8.0'
mapping = json.loads(script)
methods = {m['Address']: m for m in mapping['ScriptMethod']}
boundaries = sorted(set(mapping['Addresses']) | set(methods))
phoff = struct.unpack_from('<Q', binary, 32)[0]
stride, count = struct.unpack_from('<HH', binary, 54)
segments = [struct.unpack_from('<IIQQQQQQ', binary, phoff+i*stride) for i in range(count)]
records, lines = [], []
decompiled = json.loads((out/'ghidra.json').read_text())
assert {m['method'] for m in decompiled} == set(METHOD_NAMES), 'Unexpected/missing methods'
assert len(decompiled) == len(METHOD_NAMES), 'Duplicate methods'
decompile_errors = [{k: m[k] for k in ('method', 'error')} for m in decompiled if 'error' in m]
selected_addresses = {int(m['native_rva'], 16) for m in decompiled}
for address in sorted(selected_addresses):
    end = next(a for a in boundaries if a > address)
    method = methods[address]
    segment = next(s for s in segments if s[0] == 1 and s[3] <= address < s[3]+s[5])
    offset = segment[2]+address-segment[3]
    body = binary[offset:offset+end-address]
    record = dict(method=method['Name'], native_rva=hex(address), end_rva=hex(end), body_bytes=len(body), body_sha256=digest(body), signature=method['Signature'])
    records.append(record)
    lines.append(json.dumps(record))
    for ins in Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(body, address):
        target = methods.get(int(ins.op_str[1:], 16)) if ins.mnemonic in ('b','bl') and ins.op_str.startswith('#0x') else None
        lines.append(f'{ins.address:x}: {ins.mnemonic} {ins.op_str}' + (' ; '+target['Name'] if target else ''))
(out/'arm64.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
(out/'methods.json').write_text(json.dumps(dict(binary_sha256=digest(binary), metadata_version=31, metadata_sha256=digest(metadata), script_sha256=digest(script), decompile_errors=decompile_errors, methods=records), indent=2)+'\n', encoding='utf-8')
# Inspect direct calls to two fixed entry points without building a program index.
# This does not establish indirect-call coverage or runtime execution.
entries = sorted(methods)
targets = {0x1493DB4: 'OneTrustController$$UpdateSDKs',
           0x1655694: 'AssetBundleState$$CheckForInternetConnection'}
callers = []
for segment in segments:
    if segment[0] != 1 or not segment[1] & 1:
        continue
    offset, va, size = segment[2], segment[3], segment[5]
    for file_offset in range(offset, offset + size - 3, 4):
        word = struct.unpack_from('<I', binary, file_offset)[0]
        if word >> 26 not in (5, 37):
            continue
        immediate = word & 0x3FFFFFF
        if immediate & 0x2000000:
            immediate -= 0x4000000
        address = va + file_offset - offset
        target = address + immediate * 4
        if target not in targets:
            continue
        index = bisect.bisect_right(entries, address) - 1
        callers.append(dict(call_rva=hex(address), target=targets[target],
                            containing_metadata_method=methods[entries[index]]['Name'] if index >= 0 else None))
(out/'direct-callers.json').write_text(json.dumps(callers, indent=2)+'\n', encoding='utf-8')
print('Bounded methods:', len(records), '; direct calls to selected targets:', len(callers),
      '; decompiler errors retained:', len(decompile_errors))

"""Bound each selected Android 2.41 ARM64 method by the next metadata entry."""
import hashlib
import json
import struct
import sys
from pathlib import Path

sys.path.insert(0, '.research/python')
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

out = Path(sys.argv[1])
binary = Path('.research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so').read_bytes()
digest = lambda data: hashlib.sha256(data).hexdigest()
assert digest(binary) == 'ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326'
inspection = json.loads((out/'artifact.json').read_text())
assert inspection['subject']['digest']['sha256'] == digest(binary)
metadata = Path('.research/android/base/assets/bin/Data/Managed/Metadata/global-metadata.dat').read_bytes()
assert struct.unpack_from('<II', metadata) == (0xFAB11BAF, 31)
script = Path('.research/dumper/script.json').read_bytes()
mapping = json.loads(script)
methods = {m['Address']: m for m in mapping['ScriptMethod']}
boundaries = sorted(set(mapping['Addresses']) | set(methods))
phoff = struct.unpack_from('<Q', binary, 32)[0]
stride, count = struct.unpack_from('<HH', binary, 54)
segments = [struct.unpack_from('<IIQQQQQQ', binary, phoff+i*stride) for i in range(count)]
records, lines = [], []
selected_addresses = {int(m['native_rva'], 16) for m in json.loads((out/'ghidra.json').read_text())}
selected_addresses.update(a for a,m in methods.items() if m['Name'] == 'Best.HTTP.HTTPResponse$$get_IsSuccess')
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
(out/'methods.json').write_text(json.dumps(dict(binary_sha256=digest(binary), metadata_version=31, metadata_sha256=digest(metadata), script_sha256=digest(script), methods=records), indent=2)+'\n', encoding='utf-8')
print('Bounded methods:', len(records))

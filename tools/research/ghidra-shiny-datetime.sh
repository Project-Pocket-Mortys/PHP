#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# REA records root identity; exact metadata-bounded Capstone supplies semantics.
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > .research/rea-shiny-datetime-6.8.0-artifact.json
RESEARCH_PYTHON_EXE="${POCKET_WINDOWS_PYTHON:-/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe}"
"$RESEARCH_PYTHON_EXE" -X utf8 -B - <<'PY'
import hashlib, json, struct, sys
from pathlib import Path
sys.path.insert(0, '.research/python')
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

binary = Path('.research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so')
metadata = Path('.research/android/base/assets/bin/Data/Managed/Metadata/global-metadata.dat')
script = Path('.research/dumper/script.json')
blob = binary.read_bytes()
digest = lambda data: hashlib.sha256(data).hexdigest()
expected = 'ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326'
assert digest(blob) == expected, 'Build-specific RVAs require Android 2.41.0 ARM64'
assert struct.unpack_from('<II', metadata.read_bytes()) == (0xFAB11BAF, 31)
inspection = json.loads(Path('.research/rea-shiny-datetime-6.8.0-artifact.json').read_text())
assert inspection['subject']['digest']['sha256'] == expected
methods = json.loads(script.read_text())['ScriptMethod']
by_address = {m['Address']: m for m in methods}
entries = sorted(by_address)
selected = {
    0x15901b4: 'MPPlayerData$$SetFromDict',
    0x165f148: 'MPShinyPotionData$$SetupFromDict',
    0x165f33c: 'MPShinyPotionData$$SetShinyPotion',
    0x165f0bc: 'MPShinyPotionData$$CheckIfShinyPotionDone',
    0x25fc9e4: 'System.DateTime$$Parse',
    0x260cd68: 'System.DateTimeParse$$ParseISO8601',
    0x260d5f0: 'System.DateTimeParse$$DetermineTimeZoneAdjustments',
    0x260db9c: 'System.DateTimeParse$$AdjustTimeZoneToLocal',
    0x25fe1e0: 'System.DateTime$$op_LessThan',
    0x25fe24c: 'System.DateTime$$op_LessThanOrEqual',
    0x25fe0a8: 'System.DateTime$$op_Subtraction',
    0x164bc90: 'MPWorldUI$$SetUp',
    0x162c8b0: 'ShinyPotionUI$$Setup',
    0x162c9f0: 'ShinyPotionUI$$Update',
    0x16bb060: 'TagGamesUtils$$GetPrettyStringTimeLeftUntilDateTime',
    0x16c4df8: 'TagGamesUtils$$GetTimeSpanRemainingUntilDateTime',
}
header = struct.unpack_from('<Q', blob, 32)[0]
stride, count = struct.unpack_from('<HH', blob, 54)
segments = [struct.unpack_from('<IIQQQQQQ', blob, header + i * stride) for i in range(count)]
lines, records = [], []
for address, name in selected.items():
    method = by_address[address]
    assert method['Name'] == name, (hex(address), method['Name'], name)
    end = next(entry for entry in entries if entry > address)
    segment = next(s for s in segments if s[0] == 1 and s[3] <= address < s[3] + s[5])
    offset = segment[2] + address - segment[3]
    body = blob[offset:offset + end - address]
    record = {'method': name, 'native_rva': hex(address), 'body_bytes': len(body),
              'body_sha256': digest(body), 'signature': method['Signature']}
    records.append(record)
    lines.append(json.dumps(record, sort_keys=True))
    for instruction in Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(body, address):
        target = None
        if instruction.mnemonic in ('b', 'bl') and instruction.op_str.startswith('#0x'):
            target = by_address.get(int(instruction.op_str[1:], 16))
        annotation = ' ; ' + target['Name'] if target else ''
        lines.append(f'{instruction.address:x}: {instruction.mnemonic} {instruction.op_str}{annotation}')
report = {'binary_sha256': expected, 'metadata_version': 31,
          'metadata_sha256': digest(metadata.read_bytes()), 'script_sha256': digest(script.read_bytes()),
          'method_count': len(records), 'methods': records,
          'limit': 'Bounds end at the next actual dumper method entry; padding can be included. REA root inspection does not establish method semantics.'}
Path('.research/shiny-datetime-methods.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
Path('.research/shiny-datetime-arm64.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
print('Verified methods:', len(records))
for filename in ('shiny-datetime-methods.json', 'shiny-datetime-arm64.txt'):
    print(filename, digest(Path('.research', filename).read_bytes()))
PY

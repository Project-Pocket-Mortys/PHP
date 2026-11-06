#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > .research/rea-shared-battle-startup-6.8.0-artifact.json
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-shared-battle-startup.json" \
  'NetworkBattleAPI\$\$(Disconnected|Enter|Leave|SelectingMove|UpdateTimeOut)|NetworkBattleAPI\$\$.*SelectingMove.*|NetworkSessionAPI\$\$(Disconnect|Connect|ESStartHandler|ESClosedHandler|ESEndedHandler)|NetworkSessionAPI.*Connect.*(MoveNext|b__0)|MPBattleState\$\$.*(Disconnect|Cancel).*|MPWorldState\$\$.*Disconnect.*|MPState\$\$.*Disconnect.*'
RESEARCH_PYTHON_EXE="${POCKET_WINDOWS_PYTHON:-/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe}"
"$RESEARCH_PYTHON_EXE" -X utf8 -B - <<'PY'
import hashlib, json, struct, sys
from pathlib import Path
sys.path.insert(0, '.research/python')
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
digest = lambda b: hashlib.sha256(b).hexdigest()
binary = Path('.research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so').read_bytes()
metadata = Path('.research/android/base/assets/bin/Data/Managed/Metadata/global-metadata.dat').read_bytes()
assert digest(binary) == 'ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326'
assert struct.unpack_from('<II', metadata) == (0xFAB11BAF, 31)
inspection = json.loads(Path('.research/rea-shared-battle-startup-6.8.0-artifact.json').read_text())
assert inspection['subject']['digest']['sha256'] == digest(binary)
script = Path('.research/dumper/script.json').read_bytes()
by_address = {m['Address']: m for m in json.loads(script)['ScriptMethod']}
entries = sorted(by_address)
ghidra = json.loads(Path('.research/ghidra-shared-battle-startup.json').read_text())
selected = {int(m['native_rva'], 16) for m in ghidra}
# Include actual generic ready-request constructor bodies and metadata fields.
selected.update(a for a,m in by_address.items() if 'f__AnonymousType' in m['Name'] and any('Type'+n+'<' in m['Name'] for n in ('3',)) and m['Name'].endswith('$$.ctor'))
phoff = struct.unpack_from('<Q', binary, 32)[0]
stride, count = struct.unpack_from('<HH', binary, 54)
segments = [struct.unpack_from('<IIQQQQQQ', binary, phoff+i*stride) for i in range(count)]
lines, records = [], []
for address in sorted(selected):
    method = by_address[address]
    end = next(a for a in entries if a > address)
    segment = next(s for s in segments if s[0] == 1 and s[3] <= address < s[3]+s[5])
    offset = segment[2]+address-segment[3]
    body = binary[offset:offset+end-address]
    record = {'method': method['Name'], 'native_rva':hex(address), 'end_rva':hex(end), 'body_bytes':len(body), 'body_sha256':digest(body), 'signature':method['Signature']}
    records.append(record)
    lines.append(json.dumps(record))
    for ins in Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(body,address):
        target = by_address.get(int(ins.op_str[1:],16)) if ins.mnemonic in ('b','bl') and ins.op_str.startswith('#0x') else None
        lines.append(f'{ins.address:x}: {ins.mnemonic} {ins.op_str}' + (' ; '+target['Name'] if target else ''))
Path('.research/shared-battle-startup-arm64.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
Path('.research/shared-battle-startup-methods.json').write_text(json.dumps({'binary_sha256':digest(binary),'metadata_version':31,'metadata_sha256':digest(metadata),'script_sha256':digest(script),'methods':records,'limitation':'Capstone ends at next actual metadata method entry; Ghidra output can over-follow exception fallthrough.'},indent=2)+'\n',encoding='utf-8')
print('Verified bounded ARM64 methods:',len(records))
PY

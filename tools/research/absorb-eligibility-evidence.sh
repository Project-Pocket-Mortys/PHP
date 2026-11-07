#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > .research/rea-absorb-eligibility-6.8.0-artifact.json
RESEARCH_PYTHON_EXE="${POCKET_WINDOWS_PYTHON:-/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe}"
"$RESEARCH_PYTHON_EXE" -X utf8 -B - <<'PY'
import hashlib, struct, sys
from pathlib import Path
sys.path.insert(0, '.research/python')
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
blob = Path('.research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so').read_bytes()
assert hashlib.sha256(blob).hexdigest() == 'ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326'
header = struct.unpack_from('<Q', blob, 32)[0]
stride, count = struct.unpack_from('<HH', blob, 54)
segments = [struct.unpack_from('<IIQQQQQQ', blob, header+i*stride) for i in range(count)]
# Metadata-bounded bodies; SetFromDict bound is also in ghidra-capture-rules.json.
methods = [
    ('MPStorageCombineUI.<CreateAbsorbMortyCells>b__35_0', 0x15ebb94, 0x88),
    ('MPMortyDefs.CanBeBlended', 0x176b998, 0x3c),
    ('MPOpponentMortyData.get_variant', 0x158e478, 0x90),
    ('MPOpponentMortyData.SetFromDict', 0x158cb1c, 0xba0),
    ('String.Equals(string)', 0x24b4e98, 0x40),
    ('Enum.Parse(Type,string)', 0x264d958, 0x68),
]
lines = []
for name, address, size in methods:
    segment = next(s for s in segments if s[0] == 1 and s[3] <= address and address+size <= s[3]+s[5])
    offset = segment[2]+address-segment[3]
    lines.append(name+' '+hex(address))
    lines.extend(f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in
                 Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(blob[offset:offset+size], address))
out = Path('.research/absorb-eligibility-arm64.txt')
out.write_text('\n'.join(lines)+'\n', encoding='utf-8', newline='\n')
print(out.name, hashlib.sha256(out.read_bytes()).hexdigest())
PY

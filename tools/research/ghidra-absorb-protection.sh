#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > .research/rea-absorb-protection-6.8.0-artifact.json
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-absorb-protection.json" \
  'NetworkPlayerAPI\$\$AbsorbMorties|NetworkPlayerAPI.*<AbsorbMorties>b__0|MPMortyDefs\$\$CanBeBlended|MPStorageCombineUI\$\$(CreateEvolveMortyCells|CreateAbsorbMortyCells|TryAbsorb|RefreshAbsorbCellStates|UpdateMenuForSelectedEvolveMorty|AbsorbScrollCellSelectedHandler)|MPStorageCombineUI.*<(CreateAbsorbMortyCells|CreateEvolveMortyCells|TryAbsorb)>b__.*|MPPlayerData\$\$(IsMortyInParty|GetActiveDeckCount|GetActiveDeckAliveCount)|MPOpponentData\$\$(RemoveMortys|UpdateMorty)|MPPlayerData\$\$SetDecks|MPMortyCell\$\$(SetUp|Refresh|SetSelect)|CellBase\$\$(SetEnabled|SetUsed|SetSelect)'
RESEARCH_PYTHON_EXE="${POCKET_WINDOWS_PYTHON:-/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe}"
"$RESEARCH_PYTHON_EXE" -X utf8 -B - <<'PY'
import hashlib, json, struct, sys
from pathlib import Path
sys.path.insert(0, '.research/python')
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
blob = Path('.research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so').read_bytes()
assert hashlib.sha256(blob).hexdigest() == 'ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326'
header = struct.unpack_from('<Q', blob, 32)[0]
stride, count = struct.unpack_from('<HH', blob, 54)
segments = [struct.unpack_from('<IIQQQQQQ', blob, header+i*stride) for i in range(count)]
methods = json.loads(Path('.research/ghidra-absorb-protection.json').read_text())
lines = []
for method in methods:
    address = int(method['native_rva'], 16)
    segment = next(s for s in segments if s[0] == 1 and s[3] <= address < s[3]+s[5])
    offset = segment[2]+address-segment[3]
    lines.append(method['method']+' '+hex(address))
    lines.extend(f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in
                 Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(blob[offset:offset+method['body_bytes']], address))
Path('.research/absorb-protection-arm64.txt').write_text('\n'.join(lines), encoding='utf-8', newline='\n')
for filename in ('ghidra-absorb-protection.json','absorb-protection-arm64.txt'):
    print(filename, hashlib.sha256(Path('.research',filename).read_bytes()).hexdigest())
PY

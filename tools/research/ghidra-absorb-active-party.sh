#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# A new output directory prevents replacement of any earlier investigation.
OUTPUT_DIR="$(mktemp -d "$PWD/.research/absorb-active-party-XXXXXX")"
echo "Evidence directory: $OUTPUT_DIR"
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > "$OUTPUT_DIR/rea-6.8.0-artifact.json"
bash tools/research/ghidra-targeted.sh "$OUTPUT_DIR/methods.json" \
  'MPStorageCombineUI\$\$TryAbsorb|MPStorageCombineUI.*<TryAbsorb>b__.*|MPPlayerData\$\$(GetAllPartyMortyDatas|GetPartyMortyData|GetDeckCount|GetActiveDeck|GetDeckMortyDatas|GetActiveDeckIDs|GetDeckMortyIDs|IsMortyInParty)|MPPlayerData.*<(GetPartyMortyData|GetDeckMortyDatas)>b__.*|MPOpponentData\$\$(GetMortyData|GetAllPartyMortyDatas)|MPOpponentData.*<GetMortyData>b__.*' > "$OUTPUT_DIR/ghidra.log" 2>&1
RESEARCH_PYTHON_EXE="${POCKET_WINDOWS_PYTHON:-/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe}"
"$RESEARCH_PYTHON_EXE" -X utf8 -B - "$(wslpath -w "$OUTPUT_DIR")" <<'PY'
import hashlib, json, struct, sys
from pathlib import Path
sys.path.insert(0, '.research/python')
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
output = Path(sys.argv[1])
blob = Path('.research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so').read_bytes()
assert hashlib.sha256(blob).hexdigest() == 'ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326'
header = struct.unpack_from('<Q', blob, 32)[0]
stride, count = struct.unpack_from('<HH', blob, 54)
segments = [struct.unpack_from('<IIQQQQQQ', blob, header+i*stride) for i in range(count)]
methods = json.loads((output/'methods.json').read_text())
assert methods and not any('error' in m for m in methods)
# The existing Ghidra driver skips property accessors. Bound the getter using
# the same dumper address inventory and export its actual instructions directly.
mapping = json.loads(Path('.research/dumper/script.json').read_text())
getter = next(m for m in mapping['ScriptMethod'] if m['Name'] == 'MPOpponentMortyData$$get_isFainted')
boundaries = sorted(set(mapping['Addresses']) | {m['Address'] for m in mapping['ScriptMethod']})
address = getter['Address']
methods.append(dict(method=getter['Name'], native_rva=hex(address), body_bytes=next(a for a in boundaries if a>address)-address))
lines = []
for method in methods:
    address = int(method['native_rva'], 16)
    segment = next(s for s in segments if s[0] == 1 and s[3] <= address < s[3]+s[5])
    offset = segment[2]+address-segment[3]
    lines.append(method['method']+' '+hex(address))
    lines.extend(f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in
                 Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(blob[offset:offset+method['body_bytes']], address))
(output/'arm64.txt').write_text('\n'.join(lines), encoding='utf-8', newline='\n')
for filename in ('methods.json', 'arm64.txt'):
    print(filename, hashlib.sha256((output/filename).read_bytes()).hexdigest())
print('Ghidra functions:', len(methods)-1)
PY

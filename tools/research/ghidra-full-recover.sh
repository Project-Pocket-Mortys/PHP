#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > .research/rea-full-recover-6.8.0-artifact.json
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-full-recover.json" \
  'MPItemDefs\$\$(CanItemBeApplyedToMorty|GetItemUsedResultText)|MPOpponentMortyData\$\$SetFromDict|NetworkPlayerAPI.*<UseItem>b__52_0|MPPartyState\$\$NetUserUseItemsHandler|MPPartyUI.*UseItemCo.*MoveNext|MPBattleActItemData\$\$SetFromDict|MPBattleUI.*(TurnActItem|StartTurnAct).*MoveNext'
# The pinned UnityPy/Capstone installation contains Windows CPython extensions.
RESEARCH_PYTHON_EXE="${POCKET_WINDOWS_PYTHON:-/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe}"
"$RESEARCH_PYTHON_EXE" -X utf8 -B - <<'PY'
import hashlib, json, struct, sys
from pathlib import Path
sys.path.insert(0, '.research/python')
sys.path.insert(0, 'tools/research')
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from export_item_effects import load_text

blob = Path('.research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so').read_bytes()
header = struct.unpack_from('<Q', blob, 32)[0]
stride, count = struct.unpack_from('<HH', blob, 54)
segments = [struct.unpack_from('<IIQQQQQQ', blob, header + i * stride) for i in range(count)]
methods = json.loads(Path('.research/ghidra-full-recover.json').read_text())
lines = []
for method in methods:
    address = int(method['native_rva'], 16)
    segment = next(s for s in segments if s[0] == 1 and s[3] <= address < s[3] + s[5])
    offset = segment[2] + address - segment[3]
    lines.append(method['method'] + ' ' + hex(address))
    lines.extend(f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in
                 Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(blob[offset:offset + method['body_bytes']], address))
Path('.research/full-recover-arm64.txt').write_text('\n'.join(lines))
items, mp_source = load_text('mpdata.assetbundle', 'ItemInfo')
language, text_source = load_text('text.assetbundle', 'EN')
report = {'sources': [mp_source, text_source],
          'item': next(i for i in items if i['item_id'] == 'ItemFullRecover'),
          'english': language['Item']['ItemFullRecover'],
          'text': {k: v for k, v in language['TextDefs'].items() if 'CURE' in k}}
Path('.research/full-recover-metadata.json').write_text(json.dumps(report, indent=2))
for filename in ('ghidra-full-recover.json', 'full-recover-arm64.txt', 'full-recover-metadata.json'):
    print(filename, hashlib.sha256(Path('.research', filename).read_bytes()).hexdigest())
PY

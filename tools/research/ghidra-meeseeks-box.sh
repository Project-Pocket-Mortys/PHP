#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
test "$(bash tools/research/rea.sh --version | tr -d '\r\n')" = '6.8.0'
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > .research/rea-meeseeks-box-6.8.0-artifact.json
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-meeseeks-box.json" \
  'MPBagUI\$\$ScrollMenuCellSelectedHandler|MPBagState\$\$UIUseHandler|NetworkBattleAPI\$\$SelectMove$|MPBattleActItemData\$\$SetFromDict|MPBattleUI.*(StartTurnAct|TurnActItem).*MoveNext|MPItemDefs\$\$GetItemUsedResultText|MPOpponentData\$\$SetItemsFromDicts|MPBattleState\$\$UITurnFinishedHandler'
RESEARCH_PYTHON_EXE="${POCKET_WINDOWS_PYTHON:-/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe}"
"$RESEARCH_PYTHON_EXE" -X utf8 -B - <<'PY'
import hashlib, json, struct, sys
from pathlib import Path
sys.path[:0] = ['.research/python', 'tools/research']
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM
from export_item_effects import load_text

digest = lambda value: hashlib.sha256(value).hexdigest()
blob = Path('.research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so').read_bytes()
expected = 'ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326'
assert digest(blob) == expected
metadata = Path('.research/android/base/assets/bin/Data/Managed/Metadata/global-metadata.dat').read_bytes()
assert struct.unpack_from('<II', metadata) == (0xFAB11BAF, 31), 'Expected IL2CPP metadata version 31'
receipt = json.loads(Path('.research/rea-meeseeks-box-6.8.0-artifact.json').read_text())
assert receipt['subject']['digest']['sha256'] == expected
script = Path('.research/dumper/script.json').read_bytes()
by_address = {m['Address']: m for m in json.loads(script)['ScriptMethod']}
entries = sorted(by_address)
header = struct.unpack_from('<Q', blob, 32)[0]
stride, count = struct.unpack_from('<HH', blob, 54)
segments = [struct.unpack_from('<IIQQQQQQ', blob, header + i * stride) for i in range(count)]
functions = json.loads(Path('.research/ghidra-meeseeks-box.json').read_text())
assert len(functions) == 9, 'The targeted selection must remain bounded to nine methods'
assert all(not function.get('error') for function in functions), 'Every selected method must decompile successfully'
lines = []
for function in functions:
    address = int(function['native_rva'], 16)
    assert by_address[address]['Name'] == function['method']
    end = next(entry for entry in entries if entry > address)
    segment = next(s for s in segments if s[0] == 1 and s[3] <= address < s[3] + s[5])
    offset = segment[2] + address - segment[3]
    body = blob[offset:offset + end - address]
    lines.append(json.dumps({'method': function['method'], 'native_rva': hex(address),
                             'body_bytes': len(body), 'body_sha256': digest(body)}))
    for instruction in Cs(CS_ARCH_ARM64, CS_MODE_ARM).disasm(body, address):
        target = None
        if instruction.mnemonic in ('b', 'bl') and instruction.op_str.startswith('#0x'):
            target = by_address.get(int(instruction.op_str[1:], 16))
        annotation = ' ; ' + target['Name'] if target else ''
        lines.append(f'{instruction.address:x}: {instruction.mnemonic} {instruction.op_str}{annotation}')
Path('.research/meeseeks-box-arm64.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
items, mp_source = load_text('mpdata.assetbundle', 'ItemInfo')
language, text_source = load_text('text.assetbundle', 'EN')
item = next(item for item in items if item['item_id'] == 'ItemMrMeeseek')
report = {'binary_sha256': expected, 'script_sha256': digest(script),
          'sources': [mp_source, text_source], 'item': dict(item, english=language['Item'][item['item_id']]),
          'limit': 'REA inspection establishes root identity only; method bounds end at the next dumper entry. Native code consumes server HP, not an original server damage formula.'}
Path('.research/meeseeks-box-metadata.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
for filename in ('ghidra-meeseeks-box.json', 'meeseeks-box-arm64.txt', 'meeseeks-box-metadata.json'):
    print(filename, digest(Path('.research', filename).read_bytes()))
PY

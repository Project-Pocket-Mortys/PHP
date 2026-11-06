#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > .research/rea-stat-items-6.8.0-artifact.json
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-stat-items.json" \
  'MPItemDefs\$\$(CanItemBeApplyedToMorty|GetItemUsedResultText)|NetworkPlayerAPI\$\$(UseGeneralItem|<UseGeneralItem>b__53_0)'
RESEARCH_PYTHON_EXE="${POCKET_WINDOWS_PYTHON:-/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe}"
"$RESEARCH_PYTHON_EXE" -X utf8 -B - <<'PY'
import hashlib, json, sys
from pathlib import Path
sys.path.insert(0, 'tools/research')
from export_item_effects import load_text
items, mp_source = load_text('mpdata.assetbundle', 'ItemInfo')
language, text_source = load_text('text.assetbundle', 'EN')
report = {'sources': [mp_source, text_source], 'items': [
    dict(item, english=language['Item'].get(item['item_id'])) for item in items
], 'text': {key: value for key, value in language['TextDefs'].items()
           if 'ITEM_APPLY' in key or key == 'MORTY_MAX_LEVEL_REACHED'}}
Path('.research/stat-items-metadata.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
for filename in ('ghidra-stat-items.json', 'stat-items-metadata.json'):
    print(filename, hashlib.sha256(Path('.research', filename).read_bytes()).hexdigest())
PY

#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > .research/rea-shared-battle-stream-6.8.0-artifact.json
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-shared-battle-stream.json" \
  'NetworkBattleAPI\$\$(Disconnected|Leave)|NetworkEventSource\$\$(Open|Close|AddEvents|RemoveEvents|OnMessageHandler|OnStateChangedHandler|OnRetryHandler|OnClosedHandler)|NetworkSessionAPI\$\$(AddEventSourceEvents|RemoveEventSourceEvents|ESClosedHandler|ESEndedHandler|ESErrorHandler|Disconnect)|Best.ServerSentEvents.EventSource\$\$(Open|Close|CreateInternalRequest|CallOnRetry|SetClosed|Retry|OnRequestFinished|OnMessageReceived|Best.HTTP.Shared.Extensions.IHeartbeat.OnHeartbeatUpdate)|MPBattleState\$\$(AddEvents|RemoveEvents)|MPUserSignInState\$\$(Activate|TransitionInComplete|UISignInBtnHandler|JoinRoom)|MPUserSignInState\$\$.*(UISignInBtnHandler|JoinRoom).*|MPServerMessageState\$\$LoadNextState|.*\$\$NetSessionDisconnectedHandler'
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
inspection = json.loads(Path('.research/rea-shared-battle-stream-6.8.0-artifact.json').read_text())
assert inspection['subject']['digest']['sha256'] == digest(binary)
script = Path('.research/dumper/script.json').read_bytes()
by_address = {m['Address']: m for m in json.loads(script)['ScriptMethod']}
entries = sorted(by_address)
ghidra = json.loads(Path('.research/ghidra-shared-battle-stream.json').read_text())
selected = {int(m['native_rva'], 16) for m in ghidra}
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
Path('.research/shared-battle-stream-arm64.txt').write_text('\n'.join(lines)+'\n', encoding='utf-8')
Path('.research/shared-battle-stream-methods.json').write_text(json.dumps({'binary_sha256':digest(binary),'metadata_version':31,'metadata_sha256':digest(metadata),'script_sha256':digest(script),'methods':records,'limitation':'Capstone ends at next actual metadata method entry; Ghidra output can over-follow exception fallthrough.'},indent=2)+'\n',encoding='utf-8')
# Resolve only pointer slots used to identify the retry callback and disconnect UI.
# Slots are zero in the raw ELF: their R_AARCH64_RELATIVE addends identify metadata.
mapping = json.loads(script)
metadata_entries = {m['Address']:m for k in ('ScriptMetadata','ScriptMetadataMethod','ScriptString') for m in mapping[k]}
slots = {0x2f79798,0x2f797a0,0x2f797a8,0x2f797b0,0x2f797b8,0x2f797c0,0x2f797c8,0x2f797d0,0x2f91df8,0x2f91e10,0x2f920f0,0x2f80c68}
shoff = struct.unpack_from('<Q',binary,40)[0]
shstride,shcount = struct.unpack_from('<HH',binary,58)
relocations = []
for i in range(shcount):
    section = struct.unpack_from('<IIQQQQIIQQ',binary,shoff+i*shstride)
    if section[1] != 4:
        continue
    for j in range(section[5]//24):
        address,info,addend = struct.unpack_from('<QQq',binary,section[4]+j*24)
        if address in slots:
            assert info & 0xffffffff == 1027 # R_AARCH64_RELATIVE
            relocations.append({'slot_rva':hex(address),'addend':hex(addend),'metadata':metadata_entries[addend]})
assert len(relocations) == len(slots)
Path('.research/shared-battle-stream-relocations.json').write_text(json.dumps(relocations,indent=2)+'\n',encoding='utf-8')
print('Verified bounded ARM64 methods:',len(records))
PY

#!/usr/bin/env python3
"""Bounded ARM64 disassembly with dumper labels and literal-pointer references.

The linear ADRP/ADD/LDR tracker produces candidates, not control-flow proofs.
"""
import bisect
import json
from pathlib import Path
import struct
import sys
import re

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.research/python'))
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_ARM

def main():
    data = (ROOT / '.research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so').read_bytes()
    script = json.loads((ROOT / '.research/dumper/script.json').read_text())
    methods = {m['Address']: m['Name'] for m in script['ScriptMethod']}
    strings = {s['Address']: s['Value'] for s in script['ScriptString']}
    metadata = {s['Address']: s['Name'] for s in script.get('ScriptMetadataMethod', [])}
    addresses = sorted(set(script['Addresses']) | set(methods))
    phoff = struct.unpack_from('<Q', data, 32)[0]
    phsize, phnum = struct.unpack_from('<HH', data, 54)
    segments = []
    for i in range(phnum):
        ptype, flags, offset, vaddr, _, size, _, _ = struct.unpack_from('<IIQQQQQQ', data, phoff + i*phsize)
        if ptype == 1:
            segments.append((vaddr, vaddr + size, offset))
    def offset_of(address):
        for start, end, offset in segments:
            if start <= address < end:
                return offset + address - start
        raise ValueError(hex(address))
    # ELF's on-disk GOT slots are zero before RELA relocations are applied.
    relocations = {}
    shoff = struct.unpack_from('<Q', data, 40)[0]
    shsize, shnum = struct.unpack_from('<HH', data, 58)
    for i in range(shnum):
        _, kind, _, _, off, length, _, _, _, entsize = struct.unpack_from('<IIQQQQIIQQ', data, shoff+i*shsize)
        if kind == 4 and entsize == 24:
            for pos in range(off, off+length, entsize):
                target, info, addend = struct.unpack_from('<QQq', data, pos)
                if info & 0xffffffff == 1027:
                    relocations[target] = addend
    def pointer(address):
        if address in relocations:
            return relocations[address]
        try:
            return struct.unpack_from('<Q', data, offset_of(address))[0]
        except (ValueError, struct.error):
            return None
    dump = (ROOT / '.research/dumper/dump.cs').read_text(encoding='utf-8-sig')
    anonymous = {m[1]: re.findall(r'<(\w+)>j__TPar', m[2]) for m in re.finditer(
        r'class (<>f__AnonymousType\d+)<([^\n]+)> // TypeDefIndex', dump)}
    results = []
    md = Cs(CS_ARCH_ARM64, CS_MODE_ARM)
    for address, name in methods.items():
        if not name.startswith(('Network', 'Udp', 'MPNodeUdp')):
            continue
        index = bisect.bisect_right(addresses, address)
        end = addresses[index] if index < len(addresses) else address + 4
        size = min(end-address, 24000)
        try:
            offset = offset_of(address)
        except ValueError:
            continue
        instructions, refs, calls, registers, generic_refs = [], [], [], {}, []
        for ins in md.disasm(data[offset:offset+size], address):
            operands = ins.op_str.split(', ')
            literal_address = None
            if ins.mnemonic == 'adrp' and len(operands) == 2:
                registers[operands[0]] = int(operands[1].lstrip('#'), 0)
            elif ins.mnemonic == 'add' and len(operands) == 3 and operands[1] in registers and operands[2].startswith('#'):
                registers[operands[0]] = registers[operands[1]] + int(operands[2][1:], 0)
            elif ins.mnemonic == 'ldr' and len(operands) >= 2:
                base = operands[1].lstrip('[').rstrip(']')
                if base in registers:
                    displacement = int(operands[2].rstrip(']').lstrip('#'), 0) if len(operands) == 3 else 0
                    literal_address = registers[base] + displacement
                value = pointer(literal_address) if literal_address is not None else None
                if value is not None:
                    registers[operands[0]] = value
                else:
                    registers.pop(operands[0], None)
            if literal_address in strings:
                refs.append({'instruction': hex(ins.address), 'pointer': hex(literal_address), 'literal': strings[literal_address]})
            if literal_address in metadata:
                generic_refs.append({'instruction': hex(ins.address), 'pointer': hex(literal_address), 'name': metadata[literal_address]})
            if ins.mnemonic in ('bl', 'b'):
                target = int(ins.op_str.lstrip('#'), 0)
                calls.append({'instruction': hex(ins.address), 'target': hex(target), 'name': methods.get(target)})
                if ins.mnemonic == 'bl':
                    registers = {r:v for r,v in registers.items() if r in ('x19','x20','x21','x22','x23','x24','x25','x26','x27','x28')}
            instructions.append(f'{ins.address:x}: {ins.mnemonic} {ins.op_str}')
        results.append({'method': name, 'address': hex(address), 'file_offset': hex(offset),
            'literal_candidates': refs, 'calls': calls, 'instruction_count': len(instructions),
            'generic_method_candidates': generic_refs,
            'anonymous_body_candidates': [anonymous[m[0]] for c in calls if c['name'] and
                (m := re.findall(r'<>f__AnonymousType\d+', c['name'])) and m[0] in anonymous and c['name'].endswith('$$.ctor')],
            'limitations': ['linear literal tracking; native decompilation/capture required to establish field use']})
        out = ROOT / '.research/disassembly' / (hex(address)+'.txt')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text('\n'.join(instructions))
    (ROOT / 'docs/protocol/native-transport.json').write_text(json.dumps(results, indent=2) + '\n')
    print(len(results), 'ARM64 transport functions disassembled')

if __name__ == '__main__':
    main()

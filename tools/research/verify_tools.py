#!/usr/bin/env python3
"""Verify downloaded research tools against the reviewed SHA-256 lock."""
import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--wsl-tools', type=Path, default=Path.home()/'.local/share/pocket-research')
args = parser.parse_args()
lock = json.loads((ROOT/'tools/research/toolchain.lock.json').read_text())
paths = {'cpp2il':ROOT/'.research/tools/Cpp2IL.exe','il2cppdumper':ROOT/'.research/tools/dumper.zip',
    'node':args.wsl_tools/'node.tar.xz', 'ghidra':args.wsl_tools/'ghidra.zip',
    'jdk':args.wsl_tools/'jdk.tar.gz', 'jadx-headless-mcp':args.wsl_tools/'jadx-headless-mcp-0.7.1-all.jar'}
failed = False
for name,path in paths.items():
    if not path.exists():
        print(name, 'MISSING', path)
        failed = True
        continue
    matches = hashlib.sha256(path.read_bytes()).hexdigest() == lock[name]['sha256']
    print(name, 'OK' if matches else 'HASH MISMATCH')
    failed |= not matches
raise SystemExit(1 if failed else 0)

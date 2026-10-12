#!/usr/bin/env python3
"""Validate generated evidence links and syntax; run HTTP tests separately."""
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
for file in (ROOT/'docs/protocol').glob('*.json'):
    json.loads(file.read_text())
inventory = json.loads((ROOT/'docs/protocol/inventory.json').read_text())
assert len({e['path'] for e in inventory['endpoints']}) == len(inventory['endpoints'])
for endpoint in inventory['endpoints']:
    source = endpoint.get('server_evidence')
    if source:
        assert hashlib.sha256((ROOT/source['file']).read_bytes()).hexdigest() == source['sha256'], source['file']
native = json.loads((ROOT/'docs/protocol/native-transport.json').read_text())
methods = {m['method']:m for m in native}
reviewed = json.loads((ROOT/'docs/protocol/contracts.json').read_text())
for path, contract in reviewed['http'].items():
    method = methods[contract['native_constructor']]
    assert method['address'] == contract['address']
    assert any(ref['literal'] == path for ref in method['literal_candidates'])
    assert any(set(contract['request']['properties']) == set(fields) for fields in method['anonymous_body_candidates'])
summary = json.loads((ROOT/'docs/protocol/native-analysis.json').read_text())
assert all('error' not in m for m in summary['methods'])
for method in summary['methods']:
    assert int(method['address'],16) - int(method['image_base'],16) == int(method['native_rva'],16)
    assert method['body_bytes'] == methods[method['method']]['instruction_count'] * 4, method['method']
for path in (ROOT/'tools/research').glob('*.py'):
    compile(path.read_text(), str(path), 'exec')
print('JSON, source hashes, reviewed constructor fields, ARM64/Ghidra boundaries and Python syntax validated')

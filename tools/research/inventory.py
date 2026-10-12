#!/usr/bin/env python3
"""Generate an evidence index, not an assertion that inferred contracts are verified."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/protocol'
CS = ROOT / '.research/cpp2il/DiffableCs/Assembly-CSharp'

def write(name, value):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def evidence(path, text, position=0):
    return {'file': path.relative_to(ROOT).as_posix(),
            'line': text[:position].count('\n') + 1,
            'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}

def main():
    endpoints, events, constants, types, methods = {}, {}, [], [], []
    for path in sorted(CS.rglob('*.cs')):
        text = path.read_text(encoding='utf-8-sig')
        for match in re.finditer(r'const string (\w+) = "([^"\n]*)"', text):
            key, value = match.groups()
            if path.name == 'NetworkDefs.cs' or value.startswith(('http://', 'https://')):
                constants.append({'symbol': key, 'value': value, 'evidence': evidence(path, text, match.start())})
            if key.startswith('EP_') and value.startswith('/'):
                endpoints.setdefault(value, {'path': value, 'client_evidence': []})['client_evidence'].append(
                    {'symbol': key, **evidence(path, text, match.start())})
            if key in ('CONSENT_SEND_ENDPOINT', 'CONSENT_IS_REQUIRED_ENDPOINT'):
                route = urlsplit(value).path
                endpoints.setdefault(route, {'path':route,'client_evidence':[]})['client_evidence'].append(
                    {'symbol':key, **evidence(path,text,match.start())})
            if key.startswith('ES_'):
                events.setdefault(value, {'name': value, 'client_evidence': []})['client_evidence'].append(
                    {'symbol': key, **evidence(path, text, match.start())})
        if ('Response' in path.stem or path.stem.startswith(('Network', 'MPBattle', 'MPOwned', 'MPPlayer'))):
            fields = []
            for match in re.finditer(r'^\tpublic (?!static |const )([^;\n]+?) (\w+);', text, re.M):
                fields.append({'name': match[2], 'managed_type': match[1],
                    'wire_name': 'unknown; confirm serializer attributes/native parser',
                    'required': 'unknown', 'nullable': 'unknown',
                    'evidence': evidence(path, text, match.start())})
            types.append({'type': path.stem, 'fields': fields, 'evidence': evidence(path, text),
                'contract_mapping': 'unresolved unless explicitly mapped in reviewed contracts'})
        if path.stem.startswith(('Network', 'Udp')):
            for match in re.finditer(r'^\t(?:public|private|internal|protected) (?:static )?[^\n]+\([^\n]*\) \{ \}', text, re.M):
                methods.append({'signature': match[0].strip(), 'type': path.stem,
                    'evidence': evidence(path, text, match.start()), 'mapping': 'unresolved'})

    native_transport = json.loads((OUT / 'native-transport.json').read_text()) if (OUT / 'native-transport.json').exists() else []
    for method in native_transport:
        for literal in method['literal_candidates']:
            route = literal['literal']
            if re.fullmatch(r'/[a-zA-Z][a-zA-Z0-9/_-]*', route):
                entry = endpoints.setdefault(route, {'path': route, 'client_evidence': []})
                entry.setdefault('native_request_candidates', []).append({'method': method['method'],
                    'address': method['address'], 'literal_instruction': literal['instruction'],
                    'body_field_candidates': method['anonymous_body_candidates'],
                    'confidence': 'derived by linear disassembly; review before treating as wire contract'})
    files = subprocess.check_output(['git', 'ls-files', '--cached', '--others', '--exclude-standard'], cwd=ROOT, text=True).splitlines()
    for path in sorted(ROOT / f for f in files if f.endswith('.php')):
        rel = path.relative_to(ROOT)
        if rel.parts[0].startswith('.') or rel.parts[0] in ('tools', 'tests', 'lib'):
            continue
        if path.name != 'index.php':
            continue
        route = '/' + rel.parent.as_posix().replace('.', '').strip('/')
        text = path.read_text(encoding='utf-8-sig')
        entry = endpoints.setdefault(route, {'path': route, 'client_evidence': []})
        input_fields = sorted(set(re.findall(r'\$(?:body|data|input)\s*\[\s*[\'"]([^\'"]+)[\'"]\s*\]', text)))
        entry.update({'server_evidence': evidence(path, text),
            'implementation_status': 'stub' if len(text.strip()) < 550 else 'partial',
            'status_basis': 'provisional source triage; small static responses may be legitimate',
            'evidence_confidence': 'statically established (server behavior only)',
            'http_method': 'unknown; PHP route does not necessarily enforce method',
            'input_field_candidates': input_fields,
            'query_fields': sorted(set(re.findall(r'\$_GET\[[\'"]([^\'"]+)', text))),
            'response_key_candidates': sorted(set(re.findall(r'[\'"]([^\'"\n]+)[\'"]\s*=>', text))),
            'http_status_candidates': sorted(set(map(int, re.findall(r'http_response_code\((\d+)\)', text)))),
            'table_candidates': sorted(set(re.findall(r'\b(?:FROM|JOIN|UPDATE|INTO)\s+`?(\w+)', text, re.I))),
            'events_published': sorted(set(re.findall(r'publish_event\([^;]+?[\'"]([a-z-]+:[a-z-]+)[\'"]', text))),
            'authentication': 'session lookup present' if 'WHERE session_id' in text else 'requires review',
            'unresolved': ['HTTP method', 'complete response schema', 'error compatibility', 'retry semantics', 'runtime verification']})
    for entry in endpoints.values():
        if 'server_evidence' not in entry:
            entry.update({'implementation_status': 'absent', 'evidence_confidence': 'statically established constant; reachability unverified',
                'unresolved': ['request constructor', 'response parser', 'runtime reachability', 'server behavior']})
    completed = {
        '/session/collect-pickup': 'Fix item spawning', '/session/owned_morties/absorb': 'Evolve Mortys',
        '/session/heal': 'Healing', '/session/decks/slots/buy': 'Buy deck slots',
        '/session/owned_morties/learn-attacks': 'Learn Attacks', '/session/buy-item': "Salesman Rick\'s"}
    for route, feature in completed.items():
        if route in endpoints:
            endpoints[route]['implementation_status'] = 'implemented'
            endpoints[route]['status_basis'] = 'README Completed: ' + feature + '; runtime compatibility not yet verified'
    for path in (ROOT / 'lib/events.php', ROOT / 'sse/index.php'):
        text = path.read_text()
        for match in re.finditer(r'[\'"]([a-z][a-z-]+:[a-z][a-z-]+)[\'"]', text):
            item = events.setdefault(match[1], {'name': match[1], 'client_evidence': []})
            item.setdefault('server_evidence', []).append(evidence(path, text, match.start()))
    for event in events.values():
        event['schema_status'] = 'unresolved; see client-types.json and reviewed contracts'
        event['delivery_semantics'] = 'unknown until handler trace and runtime capture'
    native_path = ROOT / '.research/dumper/script.json'
    native = json.loads(native_path.read_text()) if native_path.exists() else {}
    native_methods = [m for m in native.get('ScriptMethod', []) if m['Name'].startswith(('Network', 'Battle', 'MPBattle'))]
    write('inventory.json', {'schema_version': 1, 'scope': 'all PHP index routes plus recovered EP constants',
        'readme_completed_features': re.findall(r'<s>(.*?)</s>', (ROOT/'README.md').read_text()),
        'limitations': ['heuristic PHP extraction includes comment/string candidates', 'not all dynamically built routes are proven covered'],
        'endpoints': sorted(endpoints.values(), key=lambda e:e['path']), 'events': sorted(events.values(), key=lambda e:e['name'])})
    write('client-types.json', types)
    write('transport-methods.json', methods)
    write('native-methods.json', native_methods)
    write('client-constants.json', constants)
    origins = {}
    literal_path = ROOT/'.research/dumper/stringliteral.json'
    if literal_path.exists():
        for literal in json.loads(literal_path.read_text()):
            for value in re.findall(r'https?://[^\s"<>]+', literal['value']):
                try:
                    host = urlsplit(value).hostname
                except ValueError:
                    continue
                if not host:
                    continue
                service = origins.setdefault(host, {'host':host,
                    'classification':'first-party backend' if host.endswith('.bps-pmnet.com') else 'external/SDK/documentation candidate',
                    'observed_traffic':False, 'startup_dependency':'unknown; literal presence does not establish a request',
                    'literal_addresses':[]})
                if literal['address'] not in service['literal_addresses']:
                    service['literal_addresses'].append(literal['address'])
    write('external-services.json', sorted(origins.values(), key=lambda item:item['host']))
    static = []
    for pattern in ('Aliases/**/*.json', 'Status/*.json', 'AssetBundles/**/*data.assetbundle'):
        for path in sorted(ROOT.glob(pattern)):
            static.append({'path':'/'+path.relative_to(ROOT).as_posix(), 'method':'GET',
                'size':path.stat().st_size, 'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                'status':'empty file; client handling unresolved' if path.stat().st_size == 0 else 'existing static content'})
    write('static-content.json', static)
    paths = {}
    for route, entry in sorted(endpoints.items()):
        if route.startswith('/support'):
            continue
        paths[route] = {'description': 'Unverified contract. See inventory.json for source evidence.',
            'x-implementation-status': entry['implementation_status'], 'x-method-unresolved': True}
    write('openapi.json', {'openapi': '3.1.0', 'info': {'title': 'Pocket Mortys Android 2.41.0 protocol inventory',
        'version': '0.1.0', 'description': 'Discovery index. Unknown methods and schemas are not fabricated; reviewed operations are in contracts.json.'},
        'paths': paths})
    lines = ['# Protocol coverage', '', 'Generated by `tools/research/inventory.py`. Status is provisional source triage, not client certification.', '',
        '| Path | Status | Client constant | Server source |', '|---|---|---|---|']
    for e in sorted(endpoints.values(), key=lambda e:e['path']):
        lines.append(f"| `{e['path']}` | {e['implementation_status']} | {'yes' if e['client_evidence'] else 'not found'} | {e.get('server_evidence', {}).get('file', 'absent')} |")
    (OUT / 'coverage.md').write_text('\n'.join(lines) + '\n')
    print(f'{len(endpoints)} routes; {len(events)} events; {len(types)} types; {len(methods)} transport methods; {len(native_methods)} native mappings')

if __name__ == '__main__':
    main()

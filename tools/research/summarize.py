#!/usr/bin/env python3
"""Persist small evidence summaries without committing complete native dumps."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
def read(path):
    raw = path.read_bytes()
    return json.loads(raw.decode('utf-16' if raw.startswith((b'\xff\xfe',b'\xfe\xff')) else 'utf-8-sig'))

def main():
    source = ROOT/'.research/ghidra-protocols.json'
    methods = read(source)
    result = {'binary_sha256':'ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326',
        'provider':'Ghidra 12.1.4 targeted headless import', 'full_automatic_analysis':'cancelled; prolonged FindNoReturnFunctionsAnalyzer repair',
        'methods': [{key:value for key,value in m.items() if key != 'pseudocode'} | {
            'pseudocode_sha256': hashlib.sha256(m.get('pseudocode','').encode()).hexdigest(),
            'pseudocode_characters':len(m.get('pseudocode',''))} for m in methods],
        'raw_evidence':'.research/ghidra-protocols.json',
        'limitations':['Selected methods only; not whole-program analysis',
            'Managed parameter types not imported; inspect assembly for argument widths',
            'Tail calls and one build-specific non-return thunk explicitly annotated']}
    for label, name in [('rea_native_smoke','rea-smoke.json'),('rea_android','rea-android.json')]:
        item = read(ROOT/'.research'/name)
        result[label] = {k:item.get(k) for k in ('evidence_id','subject','confidence','limitations')}
        result[label]['subject'].pop('local_path',None)
    (ROOT/'docs/protocol/native-analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    package = read(ROOT/'.research/rea-android.json')
    normalized = package['normalized_result']
    normalized.pop('manifest',None)
    (ROOT/'docs/protocol/android-package.json').write_text(json.dumps({'evidence_id':package['evidence_id'],
        'result':normalized,'limitations':package['limitations']},indent=2)+'\n')

if __name__ == '__main__':
    main()

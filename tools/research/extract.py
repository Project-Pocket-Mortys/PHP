#!/usr/bin/env python3
"""Extract analysis inputs without executing or modifying the supplied APKM."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import struct
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[2]

def digest(data):
    return hashlib.sha256(data).hexdigest()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--output', type=Path, default=ROOT / '.research/android')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    raw = args.archive.read_bytes()
    report = {'schema_version': 1, 'repository_commit': subprocess.check_output(
        ['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'archive': {'name': args.archive.name, 'sha256': digest(raw), 'size': len(raw)},
        'files': [], 'evidence_kind': 'archive inspection; not runtime verification'}
    with zipfile.ZipFile(io.BytesIO(raw)) as outer:
        report['package'] = json.loads(outer.read('info.json'))
        for entry in outer.infolist():
            if not entry.filename.endswith('.apk'):
                continue
            apk = outer.read(entry)
            apk_name = Path(entry.filename).name
            (args.output / apk_name).write_bytes(apk)
            with zipfile.ZipFile(io.BytesIO(apk)) as inner:
                for item in inner.infolist():
                    name = item.filename
                    selected = (name.endswith(('libil2cpp.so', 'global-metadata.dat',
                        'globalgamemanagers', 'boot.config', 'ScriptingAssemblies.json')))
                    if not selected:
                        continue
                    target = (args.output / apk_name.removesuffix('.apk') / name).resolve()
                    if not target.is_relative_to(args.output.resolve()):
                        raise ValueError(f'Unsafe archive path: {name}')
                    data = inner.read(item)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)
                    report['files'].append({'apk': apk_name, 'path': name,
                        'size': len(data), 'sha256': digest(data)})
                    if name.endswith('global-metadata.dat'):
                        magic, version = struct.unpack_from('<II', data)
                        if magic != 0xFAB11BAF:
                            raise ValueError('Unrecognized metadata header')
                        report['metadata_version'] = version
                    if name.endswith('globalgamemanagers'):
                        match = re.search(rb'20\d\d\.\d+\.\d+[a-z]\d+', data[:256])
                        report['unity_version'] = match[0].decode() if match else None
    destination = ROOT / 'docs/protocol/artifacts.json'
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(destination)

if __name__ == '__main__':
    main()

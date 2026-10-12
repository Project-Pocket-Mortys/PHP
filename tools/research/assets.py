#!/usr/bin/env python3
"""Catalog Unity data provenance; export TextAssets to the ignored workspace."""
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.research/python'))
import UnityPy

def main():
    output = ROOT / '.research/assets'
    output.mkdir(parents=True, exist_ok=True)
    sources = sorted((ROOT / 'AssetBundles').rglob('*data.assetbundle'))
    sources += [ROOT / '.research/android/base/assets/bin/Data/globalgamemanagers']
    catalog = []
    for source in sources:
        digest = hashlib.sha256(source.read_bytes()).hexdigest()
        item = {'source': source.relative_to(ROOT).as_posix(), 'sha256': digest, 'objects': [], 'errors': []}
        try:
            env = UnityPy.load(str(source))
            for obj in env.objects:
                if obj.type.name not in ('TextAsset', 'MonoBehaviour'):
                    continue
                entry = {'path_id': obj.path_id, 'type': obj.type.name,
                    'serialized_file': obj.assets_file.name, 'unity_version': obj.assets_file.unity_version}
                try:
                    if obj.type.name == 'TextAsset':
                        data = obj.read()
                        raw = data.m_Script.encode('utf-8', errors='surrogateescape') if isinstance(data.m_Script, str) else bytes(data.m_Script)
                        entry.update({'name': data.m_Name, 'sha256': hashlib.sha256(raw).hexdigest(), 'size': len(raw)})
                        target = output / digest[:16] / (entry['sha256'] + '.bin')
                        target.parent.mkdir(parents=True, exist_ok=True)
                        target.write_bytes(raw)
                        entry['export'] = target.relative_to(ROOT).as_posix()
                        try:
                            parsed = json.loads(raw)
                            entry['json_shape'] = {'type': type(parsed).__name__,
                                'keys': list(parsed)[:50] if isinstance(parsed, dict) else [],
                                'count': len(parsed) if isinstance(parsed, (dict, list)) else None}
                            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                                entry['json_shape']['record_fields'] = sorted({key for row in parsed if isinstance(row, dict) for key in row})
                        except (ValueError, UnicodeError):
                            pass
                    else:
                        tree = obj.read_typetree()
                        entry['name'] = tree.get('m_Name', '')
                        entry['fields'] = list(tree)
                except Exception as error:
                    entry['limitation'] = str(error)[:300]
                item['objects'].append(entry)
        except Exception as error:
            item['errors'].append(str(error))
        catalog.append(item)
        print(source.name, len(item['objects']), 'objects', len(item['errors']), 'errors', flush=True)
        (ROOT / 'docs/protocol/assets.json').write_text(json.dumps(catalog, indent=2) + '\n')
    # Inventory embedded carriers without eagerly deserializing all textures/audio.
    with zipfile.ZipFile(ROOT / '.research/android/base.apk') as apk:
        embedded = [{'path': e.filename, 'size': e.file_size, 'zip_crc32': f'{e.CRC:08x}'} for e in apk.infolist()
                    if e.filename.startswith('assets/') and not e.is_dir()]
    (ROOT / 'docs/protocol/embedded-assets.json').write_text(json.dumps({'status':'carrier inventory; individual hashed Unity files not yet decoded',
        'files':embedded}, indent=2)+'\n')
    (ROOT / 'docs/protocol/assets.json').write_text(json.dumps(catalog, indent=2) + '\n')

if __name__ == '__main__':
    main()

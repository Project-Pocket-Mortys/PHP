"""Read-only comparison of supplied bundle copies with repository manifests."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
from audit_asset_update import bundle_path

ROOT = Path(__file__).resolve().parents[2]


def sha(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    args = parser.parse_args()
    source = args.directory.resolve(strict=True)
    manifest_path = ROOT / 'Aliases/rat/Android/manifest.json'
    manifest = json.loads(manifest_path.read_text())
    expected = {}
    for key, value in manifest.items():
        if not isinstance(value, dict) or 'url' not in value:
            continue
        # Match the repository's Apache rewrite for Windows-safe bundle folders.
        relative = bundle_path(value['url'])
        path = (ROOT / relative).resolve()
        if not path.is_relative_to(ROOT):
            raise ValueError('Manifest path escapes repository')
        if not path.is_file():
            raise FileNotFoundError(path)
        expected[path.name] = {'id': key, 'sha256': sha(path)}
    groups = []
    for folder in sorted(source.iterdir()):
        if not folder.is_dir():
            continue
        files = [p for p in folder.rglob('*') if p.is_file()]
        record = {'folder': folder.name, 'files': len(files),
                  'bytes': sum(p.stat().st_size for p in files),
                  'extensions': dict(Counter(p.suffix for p in files))}
        # Keep historical versions distinct. Do not silently merge by filename.
        direct = [p for p in files if p.parent == folder and p.suffix == '.assetbundle']
        if direct:
            entries = []
            for p in sorted(direct):
                digest = sha(p)
                match = expected.get(p.name)
                entries.append({'file': p.name, 'bytes': p.stat().st_size, 'sha256': digest,
                                'matches_repository': bool(match and match['sha256'] == digest)})
            record['bundles'] = entries
            record['matching_repository_bundles'] = sum(e['matches_repository'] for e in entries)
            record['missing_manifest_files'] = sorted(set(expected) - {p.name for p in direct})
        else:
            record['nested_directories'] = sorted(p.name for p in folder.iterdir() if p.is_dir())
            record['limitation'] = 'Recursive size/count only; historical payload hashes not yet cataloged.'
        groups.append(record)
        print(folder.name, record['files'], 'files;', record.get('matching_repository_bundles', 'not hashed'), 'matches')
    saved_manifests = []
    for path in sorted((source / 'bundles').glob('*/AssetBundle.dat')):
        raw = path.read_bytes()
        # Extract only the embedded JSON string. Never deserialize BinaryFormatter data.
        start = raw.find(b'{')
        parsed, end = json.JSONDecoder().raw_decode(raw[start:].decode('utf-8', errors='replace'))
        export = ROOT / '.research/assets/saved-manifests' / (path.parent.name + '.json')
        export.parent.mkdir(parents=True, exist_ok=True)
        export.write_text(json.dumps(parsed, indent=2)+'\n')
        normalized = json.loads(json.dumps(parsed).replace('https://assets.bps-pmnet.com',
                                                          'https://assets.conspiracyrick.com'))
        saved_manifests.append({'source': path.relative_to(source).as_posix(), 'sha256': sha(path),
                               'version': parsed.get('version'),
                               'matches_repository_except_asset_origin': normalized == manifest,
                               'json_start_byte': start, 'export': export.relative_to(ROOT).as_posix()})
    report = {'source_label': 'User-supplied Pocket Mortys/dat directory',
              'manifest': manifest_path.relative_to(ROOT).as_posix(),
              'manifest_sha256': sha(manifest_path), 'manifest_version': manifest['version'],
              'manifest_bundle_count': len(expected),
              'method': 'SHA-256 of file bytes; not Unity CRC verification or original-server provenance proof.',
              'saved_manifests': saved_manifests, 'groups': groups}
    (ROOT / 'docs/protocol/asset-copy-comparison.json').write_text(json.dumps(report, indent=2)+'\n')


if __name__ == '__main__':
    main()

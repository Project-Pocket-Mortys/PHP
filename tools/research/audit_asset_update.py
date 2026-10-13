"""Compare tracked Android bundle bytes and cache versions with a Git baseline."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[2]
MANIFEST = 'Aliases/rat/Android/manifest.json'


def bundle_path(url):
    path = unquote(urlsplit(url).path)
    marker = '/AssetBundles/'
    if marker not in path:
        raise ValueError('Expected AssetBundles URL')
    relative = 'AssetBundles/' + path.split(marker, 1)[1]
    relative = relative.replace('android:', 'android_').replace('ios:', 'ios_')
    resolved = (ROOT / relative).resolve()
    if not resolved.is_relative_to(ROOT / 'AssetBundles'):
        raise ValueError('Asset path escapes bundle directory')
    return resolved.relative_to(ROOT).as_posix()


def audit(baseline):
    commit = subprocess.check_output(['git', 'rev-parse', '--verify', baseline + '^{commit}'],
                                     cwd=ROOT, text=True).strip()
    def original(path):
        return subprocess.check_output(['git', 'show', commit + ':' + path], cwd=ROOT)
    before = json.loads(original(MANIFEST))
    after = json.loads((ROOT / MANIFEST).read_text())
    changes = []
    for name, current in after.items():
        previous = before.get(name)
        if not isinstance(current, dict) or 'url' not in current or not isinstance(previous, dict):
            continue
        old_hash = hashlib.sha256(original(bundle_path(previous['url']))).hexdigest()
        new_hash = hashlib.sha256((ROOT / bundle_path(current['url'])).read_bytes()).hexdigest()
        if old_hash != new_hash:
            changes.append({'bundle': name, 'before_sha256': old_hash, 'after_sha256': new_hash,
                            'before_version': previous['version'], 'after_version': current['version'],
                            'cache_version_changed': str(previous['version']) != str(current['version'])})
    return {'baseline_commit': commit, 'before_manifest_version': before['version'],
            'after_manifest_version': after['version'], 'changed_bundles': changes,
            'cache_version_collisions': [row['bundle'] for row in changes if not row['cache_version_changed']],
            'scope': 'Tracked Android payload/version comparison; not Unity CRC or gameplay validation.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', default='7576d6b')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    report = audit(args.baseline)
    if args.output:
        args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps(report, indent=2))
    return bool(report['cache_version_collisions'])


if __name__ == '__main__':
    raise SystemExit(main())

"""Read original APK prefab transforms; write evidence to a fresh ignored path.

Requires pinned UnityPy 1.25.0 in .research/python. Does not load a device or DB.
Reported positions are serialized prefab coordinates, not runtime observations.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.research/python'))
import UnityPy


def vector(value):
    return [value[k] for k in ('x', 'y', 'z')]


def placement(obj, objects):
    chain = []
    seen = set()
    while obj:
        if obj.path_id in seen:
            raise ValueError('Cyclic transform hierarchy')
        seen.add(obj.path_id)
        tree = obj.read_typetree()
        ref = tree['m_GameObject']
        if ref['m_FileID'] != 0:
            raise ValueError('External GameObject reference')
        go = objects[ref['m_PathID']].read_typetree()
        chain.append({'game_object_id': ref['m_PathID'], 'transform_id': obj.path_id,
                      'name': go['m_Name'], 'active_self': go['m_IsActive'],
                      'local_position': vector(tree['m_LocalPosition']),
                      'local_rotation': tree['m_LocalRotation'],
                      'local_scale': vector(tree['m_LocalScale'])})
        parent = tree['m_Father']
        if parent['m_FileID'] != 0:
            raise ValueError('External parent transform')
        obj = objects[parent['m_PathID']] if parent['m_PathID'] else None
    # Do not silently sum positions through scaled or rotated ancestors.
    identity = all(c['local_rotation'] == {'x': 0, 'y': 0, 'z': 0, 'w': 1}
                   and c['local_scale'] == [1, 1, 1] for c in chain[1:])
    return {'hierarchy': chain, 'all_serialized_ancestors_active': all(c['active_self'] for c in chain),
            'prefab_position': [sum(c['local_position'][i] for c in chain) for i in range(3)] if identity else None,
            'position_limit': None if identity else 'Ancestor rotation/scale requires composed transform; inspect hierarchy'}


def inspect(data):
    result = []
    env = UnityPy.load(data)
    for assets in env.files.values():
        if not hasattr(assets, 'objects'):
            continue
        objects = assets.objects
        for go in objects.values():
            if go.type.name != 'GameObject':
                continue
            tree = go.read_typetree()
            if tree['m_Name'] != 'MPTradeKiosk':
                continue
            transforms = [objects[c['component']['m_PathID']] for c in tree['m_Component']
                          if c['component']['m_FileID'] == 0
                          and objects[c['component']['m_PathID']].type.name == 'Transform']
            if len(transforms) != 1:
                raise ValueError('Expected one kiosk Transform')
            node = placement(transforms[0], objects)
            children = transforms[0].read_typetree()['m_Children']
            node['interaction_points'] = []
            for ref in children:
                if ref['m_FileID'] != 0:
                    raise ValueError('External kiosk child')
                child = objects[ref['m_PathID']]
                ctree = child.read_typetree()
                cgo = objects[ctree['m_GameObject']['m_PathID']].read_typetree()
                if cgo['m_Name'] == 'InteractionPoint':
                    point = placement(child, objects)
                    point['layer'] = cgo['m_Layer']
                    point['colliders'] = []
                    for component in cgo['m_Component']:
                        cref = component['component']
                        if cref['m_FileID'] != 0:
                            raise ValueError('External interaction-point component')
                        collider = objects[cref['m_PathID']]
                        if not collider.type.name.endswith('Collider'):
                            continue
                        value = collider.read_typetree()
                        point['colliders'].append({'path_id': collider.path_id,
                            'type': collider.type.name, 'enabled': value.get('m_Enabled'),
                            'is_trigger': value.get('m_IsTrigger'), 'center': value.get('m_Center'),
                            'size': value.get('m_Size')})
                    node['interaction_points'].append(point)
            node['serialized_file'] = assets.name
            result.append(node)
    return result


def resource_mapping(apk):
    entry = 'assets/bin/Data/globalgamemanagers'
    data = apk.read(entry)
    env = UnityPy.load(data)
    rows = []
    for obj in env.objects:
        if obj.type.name != 'ResourceManager':
            continue
        for path, ref in obj.read_typetree()['m_Container']:
            if not path.startswith('world/multiplayer/dimensions/mpdimension'):
                continue
            if not 1 <= ref['m_FileID'] <= len(obj.assets_file.externals):
                raise ValueError('Invalid dimension resource reference')
            external = obj.assets_file.externals[ref['m_FileID'] - 1]
            rows.append({'resource_path': path, 'external_file': external.path,
                         'game_object_id': ref['m_PathID']})
    return {'entry': entry, 'sha256': hashlib.sha256(data).hexdigest(),
            'dimensions': rows}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apk', type=Path, default=ROOT / '.research/android/base.apk')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / '.research').resolve()) or output.exists():
        raise SystemExit('Output must be a fresh file inside .research')
    if UnityPy.__version__ != '1.25.0':
        raise SystemExit('Expected pinned UnityPy 1.25.0')
    report = {'schema_version': 1, 'unitypy': UnityPy.__version__,
              'apk_sha256': hashlib.sha256(args.apk.read_bytes()).hexdigest(),
              'evidence_kind': 'Original APK serialized prefab placement; runtime activation unverified',
              'scan': 'All assets/bin/Data entries searched for ASCII MPTradeKiosk; matching carriers decoded',
              'carriers': [], 'limitations': []}
    with zipfile.ZipFile(args.apk) as apk:
        report['resource_mapping'] = resource_mapping(apk)
        for entry in apk.infolist():
            if not entry.filename.startswith('assets/bin/Data/') or entry.is_dir():
                continue
            data = apk.read(entry)
            if b'MPTradeKiosk' not in data:
                continue
            row = {'entry': entry.filename, 'size': len(data),
                   'sha256': hashlib.sha256(data).hexdigest()}
            try:
                row['kiosks'] = inspect(data)
            except Exception as error:
                row['error'] = str(error)[:300]
            report['carriers'].append(row)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(f"Wrote {len(report['carriers'])} matching carriers to {output}")


if __name__ == '__main__':
    main()

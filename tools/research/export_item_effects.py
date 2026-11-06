#!/usr/bin/env python3
"""Print Android MP item metadata joined to shipped English descriptions.

Read-only: loads workspace bundles and writes JSON to stdout. Descriptions
are evidence, not executable formulas; percentage rounding is not inferred.
"""
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / '.research/python'))
import UnityPy

BUNDLES = ROOT / 'AssetBundles/AssetBundle-android_1011-ios_1011__7b175320/Android'


def load_text(bundle_name, asset_name):
    source = BUNDLES / bundle_name
    env = UnityPy.load(str(source))
    for obj in env.objects:
        if obj.type.name != 'TextAsset':
            continue
        asset = obj.read()
        if asset.m_Name != asset_name:
            continue
        raw = asset.m_Script
        if isinstance(raw, str):
            raw = raw.encode('utf-8', errors='surrogateescape')
        raw = bytes(raw)
        return json.loads(raw), {
            'source': source.relative_to(ROOT).as_posix(),
            'bundle_sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'asset_name': asset_name,
            'asset_sha256': hashlib.sha256(raw).hexdigest(),
            'path_id': obj.path_id,
            'serialized_file': obj.assets_file.name,
            'unity_version': obj.assets_file.unity_version,
        }
    raise ValueError(f'{asset_name} not found in {source}')


def main():
    items, mp_source = load_text('mpdata.assetbundle', 'ItemInfo')
    language, text_source = load_text('text.assetbundle', 'EN')
    rows = []
    for item in items:
        if item.get('effect_type') not in ('RestoreHP', 'RestorePP', 'Revive', 'Cure', 'StatIncrease'):
            continue
        localized = language['Item'][item['item_id']]
        rows.append({**item, 'english_name': localized['name'],
                     'english_description': localized['description']})
    print(json.dumps({'sources': [mp_source, text_source], 'items': rows}, indent=2))


if __name__ == '__main__':
    main()

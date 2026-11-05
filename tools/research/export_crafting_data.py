#!/usr/bin/env python3
"""Export the Android multiplayer RecipeInfo table into the runtime catalog.

Requires UnityPy (the research environment keeps it under .research/python).
No APK, bundle, or extracted TextAsset is written by this command.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
BUNDLE = ROOT / 'AssetBundles/AssetBundle-android_1011-ios_1011__7b175320/Android/mpdata.assetbundle'
OUTPUT = ROOT / 'config/crafting_recipes.json'
EXPECTED = {
    'RecipeInfo': 'e2a9a5dc4e33eb333d360ac7df2d0263afedadfb016b7ad6aa4df2331fd1c504',
    'ItemInfo': 'ab713ae7e06f8b492628d10b73580d4016756d57072d04b5be43f271e7305a39',
}
RECIPE_FIELDS = {'recipe_id', 'sortorder', 'item_id_1', 'item_id_2', 'item_id_3', 'item_id_result'}


def export():
    sys.path.insert(0, str(ROOT / '.research/python'))
    import UnityPy

    tables = {}
    for obj in UnityPy.load(str(BUNDLE)).objects:
        if obj.type.name != 'TextAsset':
            continue
        asset = obj.read()
        if asset.m_Name not in EXPECTED:
            continue
        raw = asset.m_Script
        if isinstance(raw, str):
            raw = raw.encode('utf-8', errors='surrogateescape')
        if hashlib.sha256(raw).hexdigest() != EXPECTED[asset.m_Name]:
            raise ValueError(f'{asset.m_Name} hash changed; review new data before exporting')
        if asset.m_Name in tables:
            raise ValueError(f'duplicate {asset.m_Name} TextAsset')
        tables[asset.m_Name] = json.loads(raw)
    if set(tables) != set(EXPECTED):
        raise ValueError('required multiplayer TextAssets missing')
    items = {row['item_id']: row for row in tables['ItemInfo']}
    if len(items) != 51 or len(tables['RecipeInfo']) != 22:
        raise ValueError('unexpected multiplayer table size')
    recipes = {}
    for row in sorted(tables['RecipeInfo'], key=lambda r: r['sortorder']):
        if set(row) != RECIPE_FIELDS:
            raise ValueError('recipe fields changed; quantity semantics need review')
        ingredients = Counter(row[key] for key in ('item_id_1', 'item_id_2', 'item_id_3') if row[key] is not None)
        result = row['item_id_result']
        for item in [*ingredients, result]:
            if item not in items or items[item]['type'] not in ('ITEM', 'PART'):
                raise ValueError(f'unsupported crafting item: {item}')
        if any(not items[item]['use_craft'] for item in ingredients):
            raise ValueError('ingredient is not craftable')
        if not ingredients or row['recipe_id'] in recipes:
            raise ValueError('empty ingredients or duplicate recipe ID')
        recipes[row['recipe_id']] = {
            'ingredients': dict(ingredients),
            'result': {'item_id': result, 'quantity': 1},
        }
    return json.dumps(recipes, indent=2) + '\n'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='fail if the committed catalog differs')
    args = parser.parse_args()
    expected = export()
    if args.check:
        if not OUTPUT.exists() or OUTPUT.read_text(encoding='utf-8') != expected:
            raise SystemExit('crafting catalog is stale; run export_crafting_data.py')
        print('22 multiplayer recipes match the pinned Android TextAssets')
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(expected, encoding='utf-8', newline='\n')
        print(f'wrote {OUTPUT.relative_to(ROOT)} (22 multiplayer recipes)')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Export MP avatar/item identifiers with shipped TextAsset provenance.

Run with the explicit research Python and UnityPy 1.25.0. This consumes only
mpdata.assetbundle and prints deterministic JSON; no account or DB access.
"""
import json

from export_item_effects import load_text
import UnityPy


def identifiers(rows, key):
    values = [row[key] for row in rows]
    if any(not isinstance(value, str) or not value for value in values):
        raise ValueError(f'Invalid {key}')
    if len(values) != len(set(values)):
        raise ValueError(f'Duplicate {key}')
    return sorted(values)


def main():
    if UnityPy.__version__ != '1.25.0':
        raise RuntimeError('Reproduction requires UnityPy 1.25.0')
    avatars, avatar_source = load_text('mpdata.assetbundle', 'PlayerAvatarInfo')
    items, item_source = load_text('mpdata.assetbundle', 'ItemInfo')
    avatar_ids = identifiers(avatars, 'player_avatar_id')
    item_ids = identifiers(items, 'item_id')
    default_avatar = 'AvatarRickDefault'
    if default_avatar not in avatar_ids:
        raise ValueError('Default avatar absent from MP catalog')
    print(json.dumps({
        'schema_version': 1,
        'sources': [avatar_source, item_source],
        'default_player_avatar_id': default_avatar,
        'counts': {'player_avatar_ids': len(avatar_ids), 'item_ids': len(item_ids)},
        'player_avatar_ids': avatar_ids,
        'item_ids': item_ids,
    }, indent=2))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Read Android MP capture prerequisites; print metadata, never write assets or DB.

Run with Windows `py -3.14`; UnityPy 1.25.0 is pinned in .research/python.
`--check` additionally checks the audited identities and learnset references.
This is evidence tooling, not a runtime balance or captured-Morty generator.
"""
import argparse
import json

from export_item_effects import ROOT, UnityPy, load_text


def field_types(rows):
    return {key: sorted({type(row[key]).__name__ for row in rows if key in row})
            for key in sorted(set().union(*(row.keys() for row in rows)))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if UnityPy.__version__ != '1.25.0':
        raise SystemExit('Expected pinned UnityPy 1.25.0')
    catalog = json.loads((ROOT / 'docs/protocol/assets.json').read_text())
    historical = next(row for row in catalog if row['source'].endswith('/mpdata.assetbundle'))
    names = [row['name'] for row in historical['objects'] if row.get('type') == 'TextAsset']
    tables, summaries = {}, []
    for name in names:
        rows, source = load_text('mpdata.assetbundle', name)
        tables[name] = rows
        prior = next(row for row in historical['objects'] if row.get('name') == name)
        summaries.append({**source, 'count': len(rows),
                          'field_types': field_types(rows),
                          'historical_asset_sha256': prior['sha256'],
                          'matches_historical_asset': source['asset_sha256'] == prior['sha256']})
    morties, learnsets, attacks = (tables[name] for name in ('MortyInfo', 'MortyAttacksInfo', 'AttackInfo'))
    morty_ids = {row['morty_id'] for row in morties}
    attack_ids = {row['attack_id'] for row in attacks}
    issues = []
    if len(morty_ids) != len(morties):
        issues.append('Duplicate MortyInfo IDs')
    if {row['morty_id'] for row in learnsets} != morty_ids or len(learnsets) != len(morties):
        issues.append('Learnset species differ from MortyInfo')
    unknown_attacks = sorted({attack['attack_id'] for row in learnsets for attack in row['attacks']} - attack_ids)
    if unknown_attacks:
        issues.append({'unknown_attack_ids': unknown_attacks})
    expected = {'MortyInfo': '96072cc81591577cc31245c6f0ef7518d6ef1b5b5b47e261fd93163caba5ea99',
                'MortyAttacksInfo': '4b98487f06f6bdeb75eca0370ae736311741563fdc45327f1a9f591d91a79d7f',
                'AttackInfo': 'ee1ce3bd8451e46a7cd29244eba26b275d4f564dc92b92b8c577bc00553d1d51'}
    for summary in summaries:
        name = summary['asset_name']
        if name in expected and summary['asset_sha256'] != expected[name]:
            issues.append(f'{name} payload differs from audited source')
    report = {'unitypy': UnityPy.__version__, 'historical_bundle_sha256': historical['sha256'],
              'tables': summaries, 'learnset_entry_types': field_types([a for r in learnsets for a in r['attacks']]),
              'capture_and_cure_items': [r for r in tables['ItemInfo'] if r.get('effect_type') in ('Capture', 'Cure')],
              'issues': issues,
              'conclusion': 'MP identity, learnsets and attack definitions available; MP stat/XP generation and capture probability absent from these tables.'}
    print(json.dumps(report, indent=2))
    if args.check and issues:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

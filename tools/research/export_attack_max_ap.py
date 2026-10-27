#!/usr/bin/env python3
"""Export only attack IDs and AP maxima from the inspected Android MP bundle."""
import argparse
import json
from pathlib import Path

from export_item_effects import ROOT, load_text

EXPECTED_ASSET = 'ee1ce3bd8451e46a7cd29244eba26b275d4f564dc92b92b8c577bc00553d1d51'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Verify the tracked catalog without writing it')
    args = parser.parse_args()
    rows, source = load_text('mpdata.assetbundle', 'AttackInfo')
    if source['asset_sha256'] != EXPECTED_ASSET:
        raise SystemExit('Unexpected AttackInfo hash; review the new client version before exporting')
    maxima = {}
    for row in rows:
        attack, maximum = row['attack_id'], row['pp_stat']
        if attack in maxima or not isinstance(attack, str) or type(maximum) is not int:
            raise SystemExit('Invalid or duplicate attack entry')
        maxima[attack] = maximum
    # Keep the sentinel -1 entry; callers must reject nonpositive maxima.
    target = ROOT / 'config/attack_max_ap.json'
    encoded = json.dumps(dict(sorted(maxima.items())), indent=2) + '\n'
    if args.check:
        if target.read_text(encoding='utf-8') != encoded:
            raise SystemExit('Tracked attack AP catalog differs from the inspected asset')
        print(f'Verified {len(maxima)} attack AP maxima; asset SHA-256 {EXPECTED_ASSET}')
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(encoded, encoding='utf-8', newline='\n')
        print(f'Exported {len(maxima)} attack AP maxima; asset SHA-256 {EXPECTED_ASSET}')


if __name__ == '__main__':
    main()

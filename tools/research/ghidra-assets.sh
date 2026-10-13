#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-assets.json" \
  'AssetBundleState\$\$.*|AssetBundleController\$\$(Load.*|.*Manifest.*)|ServerTimeController.*MoveNext'

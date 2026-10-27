#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-ap-maxima.json" \
  'MPOpponentMortyData\$\$GetTotalMaxPP|MPAttackDefs\$\$(PP|GetNode|SetUp)|MPAttackData\$\$(RestorePPFull|SetFromDict)'

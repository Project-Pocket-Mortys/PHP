#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-onboarding.json" \
  'SaveDataController\$\$(IsCampaignTutorialComplete|IsMultiplayerUnlocked)|SplashState.*MoveNext|MainMenuState\$\$.*'

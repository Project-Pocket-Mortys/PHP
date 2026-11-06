#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-morty-release.json" \
  'NetworkPlayerAPI\$\$(AttemptReleaseMortys|ReleaseMortys)|NetworkPlayerAPI.*<(AttemptReleaseMortys|ReleaseMortys)>b__0|MPOpponentData\$\$RemoveMortys|MPPlayerData\$\$(SetDecks|GetActiveDeckCount|GetActiveDeckAliveCount|IsMortyInParty)|MPMortyStatsState\$\$(UIReleaseHandler|ReleaseConfirmButtonClickedHandler)|MPMortyStatsUI\$\$(TryRelease|Refresh)|MPStorageEditDeckState\$\$(UIReleaseHandler|ConfirmationOfReleaseHandler|ReleaseConfirmButtonClickedHandler|ReleaseMortys)|MPStorageEditDeckState.*<ReleaseConfirmButtonClickedHandler>b__16_[12]|MPStorageEditDeckUI\$\$(TryRelease|IsAllMortyValidForRelease|IsAllSelectedMortysUnlocked|HandleSingleSelectMenuInputs|HandleMultiSelectMenuInputs)'

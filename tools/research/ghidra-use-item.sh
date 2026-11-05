#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-use-item.json" \
  'NetworkPlayerAPI\$\$UseItem|NetworkPlayerAPI.*<UseItem>b__52_0|MPPartyState\$\$NetUserUseItemsHandler|MPItemDefs\$\$(GetItemUsedResultText|CanItemBeApplyedToMorty)|MortyData\$\$RestoreAllPP|MPOpponentData\$\$(SetMortiesFromDicts|SetItemsFromDicts)|MPOpponentMortyData\$\$(SetFromDict|SetAttacksFromDicts)|MPAttackData\$\$SetFromDict|MPAttacksToLearnData\$\$.ctor|MPPartyUI.*UseItemCo.*MoveNext|ItemDefs\$\$(ApplyItemToMorty|ApplyRestoreHPItemToMorty|ApplyPPItemToMorty|ApplyReviveItemToMorty)|NetworkDefs\$\$ParseHTTPResponse<Int32Enum, object>|NetworkDefs\$\$ParseHTTPError<Int32Enum>'

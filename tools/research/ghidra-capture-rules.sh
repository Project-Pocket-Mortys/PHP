#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-capture-rules.json" \
  'MPOpponentMortyData\$\$(SetFromDict|SetAttacksFromDicts|ResetBattleValues|\.ctor)|MPAttackData\$\$(SetFromDict|\.ctor)|MPMortyDefs\$\$(GetAttacksForMorty|SetUp)|MPItemDefs\$\$(CanItemBeApplyedToMorty|SetUp)|ItemDefs\$\$ApplyCaptureItemToMorty|MortyData\$\$(SetLevel|GenerateIVs|GenerateEVs|RandomizeAttacks)|MortyDefs\$\$(GetXPTarget|GetNewMortyData)|NetworkBattleAPI\$\$BattleStartHandler|MPBattleUI.*UseItemCapture.*MoveNext'
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-status-cure.json" \
  'MPItemDefs\$\$(CanItemBeApplyedToMorty|GetItemUsedResultText)|MPOpponentMortyData\$\$SetFromDict|NetworkPlayerAPI.*<UseItem>b__52_0|MPPartyState\$\$NetUserUseItemsHandler|MPPartyUI.*UseItemCo.*MoveNext'

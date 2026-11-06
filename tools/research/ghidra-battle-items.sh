#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > .research/rea-battle-items-6.8.0-artifact.json
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-battle-items.json" \
  'MPPartyState\$\$(UIItemHandler|UIUseItemFinishedHandler|UIMortySelectedHandler)|MPPartyUI\$\$(RequestUseItem|MortyCellSelectedHandler|MainMenuBattleForceSwitchBtnPressedHandler|MainMenuItemBtnPressedHandler)|MPBagState\$\$(UIUseHandler|UIItemSelectedHandler)|MPBagUI\$\$(SetUp|RefreshUseBtn)|MPBattleActItemData\$\$SetFromDict|MPBattleUI.*(TurnActItem|StartTurnAct).*MoveNext|MPBattleUI\$\$UseItem.*|MPItemDefs\$\$(CanItemBeApplyedToMorty|GetItemUsedResultText)|MPBattleState\$\$UITurnFinishedHandler|MPOpponentData\$\$SetItemsFromDicts'

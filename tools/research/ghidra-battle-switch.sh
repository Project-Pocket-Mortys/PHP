#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > .research/rea-battle-switch-6.8.0-artifact.json
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-battle-switch.json" \
  'MPBattleAct(Switch)?Data\$\$SetFromDict|NetworkBattleAPI\$\$(SelectMove|Persist|BattleTurnResultHandler)|MPBattleState\$\$(UISwitchBtnHandler|UITurnFinishedHandler)|MPBattleUI\$\$(SelectingSwitchMoveRequest|SwitchMenuBtnPressedHandler|SelectMoveRequest)|MPBattleUI.*(TurnActSwitch|SwitchBringMortyIn|SwitchSendMortyOut|StartTurn|FinishTurn).*MoveNext|MPBattleOpponent\$\$.*|MPOpponentData\$\$SetMortiesFromDicts'
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-battle-switch-party.json" \
  'MPPartyState\$\$(SetBackToBattleState|UIMortySelectedHandler|UISwitchHandler)|MPBattleState\$\$(TransitionInComplete|Activate)|MPPartyUI\$\$(MainMenuBattleSwitchBtnPressedHandler|MainMenuBattleForceSwitchBtnPressedHandler|RequestSwitchOrder)|NetworkBattleAPI\$\$SelectingMove'
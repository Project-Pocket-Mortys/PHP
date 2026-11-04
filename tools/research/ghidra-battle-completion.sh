#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-battle-completion.json" \
  'NetworkBattleAPI\$\$(BattleTurnResultHandler|EndBattle|Persist|SelectMove)|MPBattleTurnOpponentData\$\$.*|MPRewardData\$\$.*|MPPlayerData\$\$(ApplyRewardData|ApplyMortyRewardData)|MPBattleActItemData\$\$.*|ConvertExt\$\$ToEnum.*|BattleMove.*Request\$\$|MPBattleUI.*FinishBattleWildMorty.*MoveNext|MPBattleUI.*UseItemCapture.*MoveNext'
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-battle-empty-rewards.json" \
  'MPBattleState\$\$(UIBattleFinishedHandler|UITurnFinishedHandler)|MPBattleUI.*(AwardXPDatas|StartTurn|FinishBattle).*MoveNext|NetworkBattleAPI.*SelectMove.*b__0'

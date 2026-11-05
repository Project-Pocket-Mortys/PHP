#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > .research/rea-battle-timeouts-6.8.0-artifact.json
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-battle-timeouts.json" \
  'NetworkBattleAPI\$\$(Update|StartTimeOut|StopTimeOut|UpdateTimeOut|UpdateBattleTurnTimer|Leave|EndBattle|BattleMoveTimeHandler|BattleTurnResultHandler)|MPBattleTimerData\$\$(ManualUpdate|\.ctor)|MPBattleState\$\$(NetBattleTurnResultHandler|UIBattleFinishedHandler|UITurnFinishedHandler)|MPBattleUI.*(FinishBattle|StartTurn).*MoveNext'
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-battle-timeouts-ui.json" \
  'MPBattleTimer\$\$(Start|Update|NetBattleMoveTimerStartedHandler)|.*\$\$NetBattleComeBackHandler|NetworkBattleAPI\$\$(SelectMove|SelectingMove|Disconnected)|MPBattleTurnOpponentData\$\$\.ctor|MPOpponentData\$\$SetItemsFromDicts'

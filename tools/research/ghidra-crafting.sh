#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-crafting.json" \
  'NetworkPlayerAPI\$\$CraftRecipe|NetworkPlayerAPI\..*\$\$<CraftRecipe>b__0|MPRewardData\$\$(Cast|\.ctor)|MPPlayerData\$\$ApplyRewardData[s]?|RewardData\$\$\.ctor|MPOpponentData\$\$SetItemsFromDicts|MPItemDefs\$\$GetBagLimit|MPRecipeDefs\$\$(GetCombinationForRecipeID|GetCraftableQuantity|ResultID|IsIDActive)|MPCraftRecipeUI\$\$(TryCraft|TryCraftFailed|RecipeCellSelectedHandler|CreateRecipeCells|AddRecipeCell)|MPCraftRecipeState.*\$\$(UICraftHandler|<UICraftHandler>b__0)|MPUserData\$\$.*Recipe.*|MPRecipeCell\$\$.*'

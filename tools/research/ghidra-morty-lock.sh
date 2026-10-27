#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-morty-lock.json" \
  'NetworkPlayerAPI\$\$LockMorty|NetworkPlayerAPI.*<LockMorty>b__0|NetworkDefs\$\$ParseHTTPResponse<Int32Enum, object>|NetworkDefs\$\$ParseHTTPError<Int32Enum>|MPPlayerData\$\$SetDecks|MPOpponentData\$\$GetMortyData'

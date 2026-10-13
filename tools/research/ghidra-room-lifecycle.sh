#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-room-lifecycle.json" \
  'NetworkRoomAPI\$\$(Leave|ClearRoom|CloseComs)|NetworkRoomAPI.*<Leave>b__0|NetworkSessionAPI.*SendPingCo.*MoveNext'

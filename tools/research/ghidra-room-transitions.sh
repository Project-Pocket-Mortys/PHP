#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-room-transitions.json" \
  'NetworkRoomAPI\$\$(Join|SetUpRoom|OpenComs|CloseComs)|NetworkRoomAPI.*<Join>b__0'

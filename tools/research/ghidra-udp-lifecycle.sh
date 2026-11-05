#!/usr/bin/env bash
# Bounded Android 2.41.0 ARM64 UDP lifecycle review: exactly 20 methods.
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-udp-lifecycle.json" \
  'UdpNodeSender\$\$(SendPosition|UpdatePositionHistory|DebugPositionHistory|DebugLog|\.ctor)|NetworkRoomAPI\$\$(Awake|Disconnected|Join|SetUpRoom|Leave|ClearRoom|OpenComs|CloseComs)|UdpRoomReceiver\$\$ClearLastSeqNumDict|UdpChannel\$\$(Open|Close|OnDestroy)|NetworkController\$\$(Awake|OnDestroy|NetSessionDisconnectedHandler)'

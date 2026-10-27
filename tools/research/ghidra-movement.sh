#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-movement.json" \
  'UdpNodeSender\$\$(SendPosition|UpdatePositionHistory)|UdpRoomReceiver\$\$(PacketReceivedHandler|PlacementReceivedHandler|GetPositionHistoryCoords|IsSequenceMoreRecent)|UdpChannel\$\$(Open|Send)|NetworkEventSource\$\$(Open|OnRetryHandler|CheckKeepaliveTimeout|OnErrorHandler)|Utils.BitConverter\$\$(GetBytes|ToGuid|ToUInt16)|Best.ServerSentEvents.EventSource\$\$.*Retry.*'

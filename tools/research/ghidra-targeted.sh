#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TOOL_ROOT="${POCKET_TOOL_ROOT:-$HOME/.local/share/pocket-research}"
export JAVA_HOME="$TOOL_ROOT/jdk"
export PATH="$JAVA_HOME/bin:$PATH"
EXPECTED_BINARY=ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326
ACTUAL_BINARY="$(sha256sum "$REPO_ROOT/.research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so" | cut -d' ' -f1)"
if [ "$ACTUAL_BINARY" != "$EXPECTED_BINARY" ]; then
  echo 'The build-specific analysis annotations only apply to the inspected Android 2.41.0 ARM64 binary.' >&2
  exit 1
fi
PROJECT_ROOT="$(mktemp -d /tmp/pocket-protocols-XXXXXX)"
"$TOOL_ROOT/ghidra_12.1.4_PUBLIC/support/analyzeHeadless" "$PROJECT_ROOT" pocket \
  -import "$REPO_ROOT/.research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so" \
  -noanalysis -scriptPath "$REPO_ROOT/tools/research/ghidra" \
  -postScript PocketProtocols.java "$REPO_ROOT/.research/dumper/script.json" "$REPO_ROOT/.research/ghidra-protocols.json"
echo "Analysis project retained at $PROJECT_ROOT for review."

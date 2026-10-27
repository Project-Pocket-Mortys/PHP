#!/usr/bin/env bash
set -euo pipefail
TOOL_ROOT="${POCKET_TOOL_ROOT:-$HOME/.local/share/pocket-research}"
export PATH="$TOOL_ROOT/node-v24.20.0-linux-x64/bin:$PATH"
if [ -d "$TOOL_ROOT/jdk" ]; then
  export JAVA_HOME="$TOOL_ROOT/jdk"
  export PATH="$JAVA_HOME/bin:$PATH"
fi
export GHIDRA_INSTALL_DIR="$TOOL_ROOT/ghidra_12.1.4_PUBLIC"
export REA_GHIDRA_INSTALL_DIR="$GHIDRA_INSTALL_DIR"
export REA_GHIDRA_STARTUP_TIMEOUT_MS=900000
export REA_JADX_MCP_JAR="$TOOL_ROOT/jadx-headless-mcp-0.7.1-all.jar"
exec "$TOOL_ROOT/rea/node_modules/.bin/rea" "$@"

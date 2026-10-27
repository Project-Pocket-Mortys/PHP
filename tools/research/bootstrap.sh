#!/usr/bin/env bash
# Run under the default WSL Ubuntu with curl, tar and Python 3.
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
TOOL_ROOT="${POCKET_TOOL_ROOT:-$HOME/.local/share/pocket-research}"
mkdir -p "$TOOL_ROOT"
cd "$TOOL_ROOT"
verify() {
  python3 - "$REPO_ROOT/tools/research/toolchain.lock.json" "$1" "$2" <<'PY'
import hashlib, json, pathlib, sys
lock, name, path = sys.argv[1:]
expected = json.loads(pathlib.Path(lock).read_text())[name]['sha256']
if hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest() != expected:
    raise SystemExit('Tool hash mismatch: ' + name)
PY
}
if [ ! -f node.tar.xz ]; then
  curl -fL --retry 2 https://nodejs.org/dist/v24.20.0/node-v24.20.0-linux-x64.tar.xz -o node.tar.xz
fi
verify node node.tar.xz
if [ ! -x node-v24.20.0-linux-x64/bin/node ]; then
  tar xf node.tar.xz
fi
export PATH="$TOOL_ROOT/node-v24.20.0-linux-x64/bin:$PATH"
if [ ! -f ghidra.zip ]; then
  curl -fL --retry 2 https://github.com/NationalSecurityAgency/ghidra/releases/download/Ghidra_12.1.4_build/ghidra_12.1.4_PUBLIC_20260921.zip -o ghidra.zip
fi
verify ghidra ghidra.zip
if [ ! -d ghidra_12.1.4_PUBLIC ]; then
  python3 -m zipfile -e ghidra.zip .
fi
chmod +x ghidra_12.1.4_PUBLIC/support/launch.sh ghidra_12.1.4_PUBLIC/support/analyzeHeadless ghidra_12.1.4_PUBLIC/Ghidra/Features/Decompiler/os/linux_x86_64/decompile
if [ ! -f jdk.tar.gz ]; then
  curl -fL --retry 2 'https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz' -o jdk.tar.gz
fi
verify jdk jdk.tar.gz
if [ ! -x jdk/bin/java ]; then
  mkdir -p jdk
  tar xf jdk.tar.gz --strip-components=1 -C jdk
fi
if [ ! -f jadx-headless-mcp-0.7.1-all.jar ]; then
  curl -fL --retry 2 https://github.com/1013503897/jadx-headless-mcp/releases/download/v0.7.1/jadx-headless-mcp-0.7.1-all.jar -o jadx-headless-mcp-0.7.1-all.jar
fi
verify jadx-headless-mcp jadx-headless-mcp-0.7.1-all.jar
npm install --prefix rea --save-exact rea-agents@6.4.0

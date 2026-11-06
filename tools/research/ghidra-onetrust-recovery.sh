#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT="${1:-.research/onetrust-recovery-$(date -u +%Y%m%dT%H%M%SZ)}"
OUT="$(realpath -m "$OUT")"
case "$OUT" in "$PWD/.research/"*) ;; *) echo 'Evidence must stay within .research.' >&2; exit 1 ;; esac
if [ -e "$OUT" ]; then echo "Refusing to overwrite evidence directory: $OUT" >&2; exit 1; fi
mkdir -p "$OUT"
OUT="$(realpath "$OUT")"
PY="${POCKET_WINDOWS_PYTHON:-/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe}"
HELPER=tools/research/onetrust-recovery-bounded.py
"$PY" -X utf8 -B "$HELPER" --verify-inputs
bash tools/research/rea.sh --version > "$OUT/rea-version.txt"
if [ "$(tr -d '\r\n' < "$OUT/rea-version.txt")" != '6.8.0' ]; then echo 'This receipt requires REA 6.8.0.' >&2; exit 1; fi
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > "$OUT/artifact.json"
FILTER="$("$PY" -X utf8 -B "$HELPER" --filter | tr -d '\r')"
TOOL_ROOT="${POCKET_TOOL_ROOT:-$HOME/.local/share/pocket-research}"
export JAVA_HOME="$TOOL_ROOT/jdk"
export PATH="$JAVA_HOME/bin:$PATH"
PROJECT_ROOT="$(mktemp -d /tmp/onetrust-recovery-XXXXXX)"
"$TOOL_ROOT/ghidra_12.1.4_PUBLIC/support/analyzeHeadless" "$PROJECT_ROOT" onetrust \
  -import "$PWD/.research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so" \
  -noanalysis -scriptPath "$PWD/tools/research/ghidra" \
  -postScript PocketProtocols.java "$PWD/.research/dumper/script.json" "$OUT/ghidra.json" "$FILTER" include-accessors \
  > "$OUT/ghidra.log" 2>&1
"$PY" -X utf8 -B "$HELPER" "$(wslpath -w "$OUT")"
printf '%s\n' "$PROJECT_ROOT" > "$OUT/ghidra-project.txt"
echo "Evidence: $OUT"

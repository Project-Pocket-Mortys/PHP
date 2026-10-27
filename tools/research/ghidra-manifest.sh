#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-manifest.json" \
  'AssetBundleDefs\$\$GetServerPath|AssetBundleController\.<LoadFromServer>d__52\$\$MoveNext|Network.*\$\$.*Manifest.*|NetworkHTTPRequest\$\$GetURI|NetworkDefs\$\$CombineUri'

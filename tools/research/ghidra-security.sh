#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-security.json" \
  'NetworkHTTP\$\$(ValidateRequestSecurity|ValidateURLStructure|ValidateHostnameAllowed|ConfigureRequestSecurity|\.ctor)|NetworkHTTP.*(ValidateHostnameAllowed|ConfigureRequestSecurity).*b__0'

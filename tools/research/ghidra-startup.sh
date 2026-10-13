#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-startup.json" \
  'SplashState.*|StateBase\.<TransitionCo>d__60\$\$MoveNext|ConsentState.*MoveNext|ConsentState\$\$GoToNextState|App\$\$(Awake|Start|Update)|OneTrustController\$\$.*|NetworkGeneralAPI\$\$IsConsentRequired'

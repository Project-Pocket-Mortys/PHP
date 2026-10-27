#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
tool=.research/tools/uber-apk-signer-1.3.0.jar
if [ ! -f "$tool" ]; then
  mkdir -p .research/tools
  curl -fL --retry 2 https://github.com/patrickfav/uber-apk-signer/releases/download/v1.3.0/uber-apk-signer-1.3.0.jar -o "$tool"
fi
echo 'e1299fd6fcf4da527dd53735b56127e8ea922a321128123b9c32d619bba1d835  .research/tools/uber-apk-signer-1.3.0.jar' | sha256sum -c -
work=$(mktemp -d /tmp/pocket-sign.XXXXXXXX)
mkdir "$work/input"
cp .research/emulator/research-client/*.apk "$work/input/"
"$HOME/.local/share/pocket-research/jdk/bin/java" -jar "$tool" \
  --apks "$work/input" --out "$work/signed" --allowResign
mkdir -p .research/emulator/research-signed
cp "$work/signed/"*-debugSigned.apk .research/emulator/research-signed/
echo "Temporary signing artifacts retained at $work"

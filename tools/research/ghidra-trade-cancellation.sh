#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT="${1:-.research/trade-cancellation-$(date -u +%Y%m%dT%H%M%SZ)}"
if [ -e "$OUT" ]; then echo "Refusing to overwrite evidence directory: $OUT" >&2; exit 1; fi
mkdir -p "$OUT"
OUT="$(realpath "$OUT")"
bash tools/research/rea.sh --version > "$OUT/rea-version.txt"
if [ "$(tr -d '\r\n' < "$OUT/rea-version.txt")" != '6.8.0' ]; then echo 'This receipt requires REA 6.8.0.' >&2; exit 1; fi
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > "$OUT/artifact.json"
bash tools/research/ghidra-targeted.sh "$OUT/ghidra.json" 'NetworkFriendAPI.*(CancelTrade|CheckUpdateTradeOffers).*|NetworkHTTP\$\$(Request|RequestHandler|ConfigureRequestSecurity|ConfigureSecureHTTP|Awake)|NetworkHTTPRequest\$\$(GetPostDataJson|\.ctor)|NetworkDefs\$\$ParseHTTPError<Int32Enum>|MPTradeRequestCreateState\$\$(UICancelHandler|TradeCancelResult)|MPTradeOfferManageState\$\$(UICancelHandler|TradeCancelResult)|MPTrade.*(Cancel|cancel).*|Best.HTTP.HTTPRequest\$\$(\.ctor|EnumerateHeaders)|Best.HTTP.Shared.HTTPManager\$\$\.cctor|.*CookieJar\$\$(\.cctor|SetFromRequest|SetupRequest|Get)'
"${POCKET_WINDOWS_PYTHON:-/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe}" -X utf8 -B tools/research/trade-cancellation-bounded.py "$(wslpath -w "$OUT")"
echo "Evidence: $OUT"

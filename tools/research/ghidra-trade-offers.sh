#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT="${1:-.research/trade-offers-$(date -u +%Y%m%dT%H%M%SZ)}"
if [ -e "$OUT" ]; then echo "Refusing to overwrite evidence directory: $OUT" >&2; exit 1; fi
mkdir -p "$OUT"
OUT="$(realpath "$OUT")"
bash tools/research/rea.sh --version > "$OUT/rea-version.txt"
if [ "$(tr -d '\r\n' < "$OUT/rea-version.txt")" != '6.8.0' ]; then echo 'This receipt requires REA 6.8.0.' >&2; exit 1; fi
bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json > "$OUT/artifact.json"
bash tools/research/ghidra-targeted.sh "$OUT/ghidra.json" 'MPTradeOfferCreateState.*(CreateUI|SetAsCurrentComplete|UIBackHandler|Uncache|OnRequestResult|UISelectHandler|UIConfirmHandler|UICancelHandler)|MPTradeOfferCreateUI.*(SetUp|MenuBtnPressedHandler|SetLabels|OnTradeCellSelected)|MPTradeBrowseState.*(Activate|CreateUI|UISelectHandler)|MPTradeBrowseUI.*(SetUp|TradeRequestCellSelectedHandler|MenuBtnPressedHandler)|MPTradeMortySelectState.*(GetTradeableMortys|UISelectHandler)|MPTradingState.*(Activate|CreateUI)|MPTradeCell.*SetUp|TradePopups.*|NetworkFriendAPI.*(GetTradeData|SubmitMortyTradeOffer|CancelTradeOffer|CheckUpdateTradeOffers).*|MenuBase.*(SetBtnVisible|SetBtnEnabled)' > "$OUT/ghidra.log" 2>&1
SUPPLEMENT='MPTradeOfferCreateState.*<CreateUI>.*|MPTradeMortySelectState.*<GetTradeableMortys>.*|MPTradeMortySelectUI.*MainMenuBtnPressedHandler'
if [ -n "${2:-}" ]; then SUPPLEMENT="$SUPPLEMENT|$2"; fi
"${POCKET_WINDOWS_PYTHON:-/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe}" -X utf8 -B tools/research/trade-cancellation-bounded.py "$(wslpath -w "$OUT")" "$SUPPLEMENT"
echo "Evidence: $OUT"

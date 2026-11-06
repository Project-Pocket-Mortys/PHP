# Android 2.41.0 native trade offer response contract

Recovered 2026-11-06 with REA 6.8.0 and targeted Ghidra 12.1.4 analysis. This is bounded static client evidence, not an original-service capture or a completed device acceptance/transfer test. See [creation](native-trade-creation-contract.md), [offer navigation](native-trade-offer-contract.md), [cancellation/authentication transport](trade-cancellation-contract.md), and [lock lifecycle](trade-lock-lifecycle-contract.md).

## Evidence and reproduction

The original ELF SHA-256 is `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`; metadata version is 31, SHA-256 `b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10`. RVAs below refer to that ELF; Ghidra adds image base `0x100000`. Managed parameter types are not imported. Some shared-generic exception paths decompile beyond their method: use only instructions inside `methods.json` bounds.

Retained ignored receipts:

| Directory under `.research/` | Scope |
| --- | --- |
| `trade-offer-response-20261106T220407Z` | Earlier browse/cell/update-popup evidence; retained unchanged. |
| `trade-offer-response-contract-20261106T232513Z` | Fresh constructor, response callback and predicates, manage UI/state, incoming-offer navigation; 29 bounded methods. |
| `trade-offer-response-parser-final-20261106` | Fresh error parser, shared HTTP request builder and JSON serialization; bounded HTTP success accessor. Artifact/version records copied from the preceding receipt for the same binary/tool installation. |

Each fresh receipt includes `rea-version.txt`, `artifact.json`, `ghidra.json`, `ghidra.log`, `methods.json`, and `arm64.txt`. Raw dumps, original binaries and temporary Ghidra projects stay outside tracked documentation. No emulator or database was changed for this research.

For reproduction, enter the default distribution using `wsl.exe` from PowerShell, then run the following in its Bash shell from the repository directory. Choose a fresh output directory each time:

```bash
set -euo pipefail
OUT=".research/trade-response-review-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$OUT"
bash tools/research/rea.sh --version > "$OUT/rea-version.txt"
test "$(tr -d '\r\n' < "$OUT/rea-version.txt")" = 6.8.0
bash tools/research/rea.sh inspect-artifact \
  .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so \
  --format json > "$OUT/artifact.json"
FILTER='NetworkFriendAPI.*TradeOfferResponse.*|MPTradeOfferManageState.*(CreateUI|UIAcceptHandler|UIDeclineHandler|OnAcceptResult|OnRejectResult|OnRequestResult)|MPTradeOfferBrowseState.*(CreateUI|UISelectHandler)|MPTradeOfferManageUI.*(SetUp|MenuBtnPressedHandler)|NetworkDefs.*ParseHTTPError<Int32Enum>|NetworkHTTP.*Request$|NetworkHTTPRequest.*(GetPostDataJson|\.ctor)'
bash tools/research/ghidra-targeted.sh "$(realpath "$OUT")/ghidra.json" "$FILTER" \
  > "$OUT/ghidra.log" 2>&1
/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe \
  -X utf8 -B tools/research/trade-cancellation-bounded.py \
  "$(wslpath -w "$(realpath "$OUT")")" \
  'MPTradeOfferManageState.*<CreateUI>.*|.*AnonymousType20.*\.ctor'
```

This imports with `-noanalysis` and decompiles only the selected methods; it does not perform full analysis/indexing. The existing bounded exporter validates the binary digest and metadata version and records per-method bounds/hashes. Use the explicit Python executable above, not a Windows alias.

## Request constructor and actor

`NetworkFriendAPI.TradeOfferResponse` (`0x1791548..0x1791708`) takes `string tradeRequestID`, `string tradeOfferID`, `bool requestAccepted`, and `Action<eTradeOfferResponseError> callback`. It constructs a `NetworkHTTPRequest` with path `/trading/offer-response` and this JSON post object:

```json
{"trade_request_id":"<request ID>","trade_offer_id":"<offer ID>","request_accepted":true}
```

The selected request's `trade_id` and offer's `trade_offer_id` supply the strings. `request_accepted` is a JSON boolean: true accepts, false declines. The call at `0x179166c` invokes anonymous Type20's concrete `object,object,bool` constructor (`0x1cc8f84`); the object references come from those string arguments. Metadata names its three properties exactly `trade_request_id`, `trade_offer_id`, `request_accepted`. There is no session, player ID, Morty ID, refund, or role property in this body. `NetworkHTTPRequest.GetPostDataJson` (`0x17bd658`) serializes the supplied object, and the shared `NetworkHTTP.Request` (`0x17b5a44`) selects POST for post data/default method and supplies the JSON content type.

The intended actor is the owner of the request receiving an incoming offer. `MPTradeOfferBrowseState.CreateUI` (`0x15fe1d0`) reads `friendOffersOnOwnTrades` at API offset `+0x98`. Selecting an incoming offer (`UISelectHandler`, `0x15feba0`) installs `tradeOffer` at manage-state `+0xa0` and finds its parent in `ownTrades` (`+0x88`) when the offering player differs from the local player. The same selection function also has an own-offer branch using `friendTrades`; that branch alone does not establish permission to accept another player's request.

`MPTradeOfferManageState.UIAcceptHandler` (`0x16026d4`) calls the API with `trade.trade_id`, `tradeOffer.trade_offer_id`, and true. `UIDeclineHandler` (`0x16027c0`) passes the same IDs and false. These handlers do not send the offerer's identity. Their owner-oriented caches and subsequent callback cleanup establish intended use; they are not server authorization checks.

The shared request path does not inject a session body field or recovered Bearer credential. Best.HTTP supports enabled cookie handling; the exact default cookie setup and request/response hooks are documented with RVAs in the cancellation contract. A replacement server can authenticate these unchanged ID-only bodies using a session cookie applicable to `/trading`. This is a replacement-server transport choice: no original cookie name or original-service handoff was recovered here. Static support does not prove a running native client has received/returned a particular cookie.

## Response parser and supported errors

The fresh response callback (`0x17953b0..0x1795b00`) calls `NetworkDefs.ParseHTTPError<Int32Enum>` at `0x1795560`, invokes its supplied UI callback at `0x1795580`, then compares the result with `NONE=4` at `0x1795584`. It returns without cache changes for any other value. It does not call `ParseHTTPResponse`, deserialize a success record, or consume a completed ID, Morty payload, inventory, token, or currency field from this endpoint.

`ParseHTTPError` (`0x1b569d8..0x1b56de0`) reads the response success byte at `0x1b56ab0`. On success it resolves the enum literal `NONE` without reading JSON. The shared HTTP success accessor (`0x1820fe4..0x1821004`) accepts 200–299 and 304. Thus HTTP 200 with `{}` satisfies the client callback; this does not recover the original service's precise status/body.

On failure the parser gets JSON (`0x1b56bdc`), deserializes it with JsonFx (`0x1b56bec`), accesses dictionary `error` (`0x1b56c0c`), then nested dictionary `code` (`0x1b56c6c`). The code must be a string accepted by `Enum.IsDefined` (`0x1b56cb8`) before parsing (`0x1b56ce0`):

```json
{"error":{"code":"TRADE_NO_OFFER_EXISTS"}}
```

| `eTradeOfferResponseError` name | Value |
| --- | --- |
| `UNKNOWN` | 0 |
| `FAILED` | 1 |
| `TRADE_NO_TRADE_EXISTS` | 2 |
| `TRADE_NO_OFFER_EXISTS` | 3 |
| `NONE` | 4 |

Return a non-success status for rejection. A flat error string/object or `TRADE_REQUEST_NOT_FOUND` / `OFFER_NOT_FOUND` is not this recovered contract. Well-formed unrecognized code strings resolve to `UNKNOWN`; absent/malformed structures can take lookup/cast/exception paths and should not be relied upon. A null response also resolves to `UNKNOWN` because this enum has no `NO_RESPONSE`. The client provides no separate unauthorized, ownership, conflict, already-completed, invalid-boolean, or inventory error name and does not establish their original HTTP status mapping. `FAILED` is the supported generic failure. HTTP 503 has shared retry/disconnect handling and is unsuitable for routine domain failures.

`OnAcceptResult` (`0x1602dd8`) and `OnRejectResult` (`0x16033b0`) show success/rejected popups for `NONE`. Other results enter `OnRequestResult` (`0x16031c4`), which displays the enum's string form. A successful HTTP status carrying an error body would still be treated as success.

## Cache effects, sibling offers, and completed IDs

The API callback finds the selected incoming offer by `trade_offer_id` (predicate `0x1795b10`) and own request by `trade_id` (`0x1795b40`). On `NONE` it requests owned-player details with mask `0x78` (`MORTIES | MORTY_ATTACKS | DECKS | MORTYDEX`) before branching on the original accepted boolean. The UI callback runs before this cleanup, so the acceptance popup can still read the presentation data.

| Successful action | Direct local effects after requesting details |
| --- | --- |
| Decline | Removes the selected record from `friendOffersOnOwnTrades`; removes its offered Morty's presentation record from `tradeMortys` (`0x1795c3c`); retains the own request and sibling incoming offers. |
| Accept | Finds all incoming offers whose `trade_id` equals the request ID (`0x1795b70`), removes each offered presentation Morty (`0x1795c70`) and incoming offer, removes the request Morty from the owned-Morty list (`0x1795ba0`), removes request/selected-offer presentation Morties (`0x1795bd4`, `0x1795c08`), and removes the own request. |

Acceptance of a free trade also initializes local cooldown data if absent and sets its expiry to UTC now plus the configured free-trade cooldown minutes. Both branches finish with `CheckUpdateTradeOffers`. These are cache/presentation effects; the callback does not itself insert the incoming Morty into owned inventory, mutate ownership IDs, alter decks, or transfer currency. The requested details refresh must provide the authoritative owned inventory.

There is no append to `completedTrades` in this callback and no completed ID returned to it. Separately, metadata declares `CompleteTradeData` with string fields `completed_trade_id`, `request_player_id`, `offer_player_id`, `morty_request_id`, `morty_offer_id`, `trade_offer_id`, `trade_request_id`, and bool `is_free_trade`. Completed records are obtained in the separate trade-data refresh path; its dumped `competed_trades` versus server `completed_trades` spelling remains unresolved as described in the offer navigation contract. Do not infer the original completed-ID generation policy or fix that spelling solely from metadata.

The accept cleanup supports a server integrity rule that accepting one offer terminates competing active offers on that same request. It does not prove deletion versus archival in the original database, the treatment of an offer on a different request sharing a Morty, transfer/refund formulas, concurrency/idempotency behavior, or accepted-trade reversal. Server authentication, request-owner checks, parent/offer consistency, active-state checks, and transactional ownership/lock/deck invariants remain server responsibilities. Static UI behavior cannot authorize an unauthenticated caller or a caller-supplied actor ID.

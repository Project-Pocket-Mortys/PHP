# Android 2.41.0 trade cancellation contract

Recovered 2026-11-06 from the ARM64 client, before choosing server behavior. This is client evidence, not a capture of the original service or proof of its authorization policy.

## Reproduction and evidence boundary

From the repository in PowerShell, use the default WSL distribution:

```powershell
wsl.exe -- bash tools/research/ghidra-trade-cancellation.sh
```

The wrapper records REA's version and `inspect-artifact` result, imports the binary into a disposable targeted Ghidra project, then runs the explicit Windows Python executable with `-X utf8 -B` for bounded ARM64 disassembly. Outputs go into a fresh ignored `.research/trade-cancellation-<UTC timestamp>` directory. An optional first argument selects another fresh output directory. No APK, binary, session credential, database snapshot, or device data belongs in this document.

The inspected binary SHA-256 is `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`. REA is 6.8.0; Ghidra is 12.1.4. Existing evidence was retained. Current focused receipt: `.research/trade-cancellation-native-final-20261106/{rea-version.txt,artifact.json,ghidra.json,methods.json,arm64.txt}`. Earlier broader receipts are in the distinct `trade-cancellation-native-20261106` and `trade-cancellation-native-expanded-20261106` directories.

Native RVAs below are relative to the original ELF; Ghidra display addresses may include its image base. Decompiler parameter types are not imported. Especially for shared generic exception paths, Ghidra can follow beyond the actual method; only instructions inside `methods.json` bounds establish behavior. The helper also directly disassembles the short HTTP success accessor that the existing Ghidra script excludes.

## First-party requests

| Endpoint | Native request | JSON body |
| --- | --- | --- |
| `/trading/cancel-trade` | `NetworkFriendAPI.CancelTrade`, RVA `0x1791708` | `{"trade_id":"<string>"}` |
| `/trading/cancel-trade-offer` | `NetworkFriendAPI.CancelTradeOffer`, RVA `0x17918a0` | `{"trade_offer_id":"<string>"}` |

Anonymous types 21 and 22 respectively contain these single fields; the request constructors pass only the selected ID. There is no `session_id`, player ID, refund value, Morty ID, or role in either body. `NetworkHTTP.Request` (`0x17b5a44`) turns a request with post data and default method into POST, serializes JSON, and adds `Content-Type: application/json`.

The caller supplies the existing own-trade ID from `MPTradeRequestCreateState.UICancelHandler` (`0x1604e1c`) and `MPTradeOfferManageState.UICancelHandler` (`0x16028ac`). Own-offer cancellation is called by `MPTradeOfferCreateState.UICancelHandler` (`0x1600794`). These explain intended owner use, but UI selection is not server authorization. Request IDs alone do not prove caller identity.

## Authentication transport: supported cookies, missing original handoff

`NetworkHTTP.Request` adds `X-PMCLIENT`; `ConfigureRequestSecurity` (`0x17bd710`) adds `X-Requested-With`, `User-Agent`, `Cache-Control`, and `Pragma`. Neither injects a session credential, an Authorization header, or a field into the JSON object. `NetworkHTTPRequest.GetPostDataJson` serializes its supplied post object. No native Bearer/session-header handoff was recovered in this path.

The underlying Best.HTTP client does support a server-issued cookie:

* `Best.HTTP.Cookies.CookieJar..cctor`, RVA `0x198c214`, stores the little-endian halfword `0x0100` at static offset `0x10`: `IsSessionOverride=false` at `0x10`, `IsEnabled=true` at `0x11` (field layout in `dump.cs`). Cookies are enabled by default.
* `Best.HTTP.HTTPRequest.EnumerateHeaders` calls `CookieJar.SetupRequest` unconditionally. `SetupRequest` (`0x1989654`) checks `IsEnabled`, selects cookies for the current URI, filters Secure cookies for secure transport, and calls `SetHeader("Cookie", ...)`.
* `CookieJar.SetFromRequest` (`0x198868c`) checks `IsEnabled`, reads response `set-cookie` headers, parses them against the response request URI, and stores/refreshes the cookie jar. `CookieJar.Get` (`0x1989af4`) selects applicable URI cookies.

This establishes native transport capability for a replacement server to issue a session cookie at successful login while preserving the one-ID cancellation bodies. It does **not** identify an original-service cookie name or establish that the current server already sends a cookie. In particular, a JSON login session value does not automatically become an HTTP cookie. A server change must explicitly issue its own authenticated handoff, bind it to the session/player, and verify that the running native client receives and returns it. Native default initialization is static evidence; device receipt, cookie persistence, multiple-account behavior, proxy behavior, and original-service policy remain unverified here. ID-only cancellation must never be enabled as a fallback.

## Response contract and errors

Both callbacks call `NetworkDefs.ParseHTTPError<T>` (`0x1b569d8`), **not** `ParseHTTPResponse<T,TResponse>`. There are no cancellation response list, dictionary, null, inventory, token, or refund fields consumed on success.

`NetworkHTTP.RequestHandler` (`0x17bde00`) copies Best.HTTP's status and `IsSuccess` into `NetworkHTTPResponse`. The bounded accessor at `0x1820fe4..0x1821004` recognizes status 200 through 299, and 304. On success `ParseHTTPError` returns the endpoint enum's `NONE` without deserializing the response body. A normal HTTP 200 with `{}` therefore satisfies both callbacks. This establishes accepted shape, not the original server's precise status/body.

On non-success the parser expects an object with `error.code` containing an enum-name string, for example:

```json
{"error":{"code":"FAILED"}}
```

| Endpoint enum | Recognized values |
| --- | --- |
| `eTradeRequestCancelError` | `UNKNOWN=0`, `FAILED=1`, `NONE=2` |
| `eTradeOfferCancelError` | `UNKNOWN=0`, `FAILED=1`, `TRADE_NO_SUCH_OFFER=2`, `NONE=3` |

Unknown well-formed codes resolve to zero (`UNKNOWN`). A null response also resolves to zero because neither enum defines `NO_RESPONSE`. Malformed/missing error structures should not be relied upon: the parser performs dictionary lookups/casts and has exception paths. Return the exact supported string code with a non-success status for domain errors; the client does not establish an original status mapping for missing, unauthorized, foreign-owner, or already-terminal rows. HTTP 503 has special retry/disconnect behavior in `RequestHandler`, so it is unsuitable for ordinary cancellation rejection.

## Observed side effects and limits

`CancelTrade` callback (`0x1795cf8`) requests player details with mask `0x78` before its success branch, including on failure. This mask is `MORTIES | MORTY_ATTACKS | DECKS | MORTYDEX`; it excludes `CURRENCY` and `ITEMS`.

On `NONE` it finds the trade in `ownTrades` by `trade_id`, removes matching `friendOffersOnOwnTrades` by their `trade_id`, finds the owned Morty by the trade's `morty_trade_id`, clears `MPOpponentMortyData.isTradeLocked` at offset `0x6e`, removes the own trade, calls `CheckUpdateTradeOffers`, and refreshes trade data. Predicate RVAs are `0x1796098`, `0x17960c8`, and `0x17960f8`. The favorite/manual lock is a separate byte, `isLocked` at `0x6d`; cancellation must not conflate it with the trading lock (`is_trading_locked`).

`CancelTradeOffer` callback (`0x1796134`) acts only on `NONE=3`: remove the matching own offer by `trade_offer_id` (predicate `0x1796324`), remove that ID from saved `trade_offer_made_ids`, save multiplayer data with mask `0x80`, then call `CheckUpdateTradeOffers`. That dictionary stores local offer records; it is not the owned-Morty inventory. This callback does not directly clear an owned Morty's trade-lock byte.

`CheckUpdateTradeOffers` (`0x1791a38`) classifies locally saved offers absent from `ownTradeOffers` into completed/declined update lists and can push a trade-update popup. Its bounded body does not mutate owned Morty locks or balances. Calling this helper is not evidence of a currency refund or inventory transfer.

Neither cancellation callback directly adjusts ownership, deck membership, currency, trade tokens, cooldowns, or refunds. The player-details refresh shows that current owned/deck data is reread; it does not prove removal/restoration or a refund formula. Server mutation and refund policy cannot be recovered from these client callbacks alone. In particular, do not implement a speculative token/currency refund based on the word “cancel.” No accepted-trade reversal contract, idempotency policy, concurrent-cancel semantics, or legal server-side terminal state was proven by this pass.

Safe server behavior must independently authenticate the actor, verify the correct owner role and cancellable persisted state, preserve unrelated inventory/decks/manual locks/currency, and derive any release of trading locks from remaining active references. These are server integrity requirements, not claims about unrecovered original backend SQL. Native evidence supports distinct own-trade versus own-offer operations and removal of all displayed offers attached to a cancelled own trade; it cannot establish hidden backend representations.

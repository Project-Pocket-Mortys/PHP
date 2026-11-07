# Android 2.41.0 native offer navigation and response contract

Recovered 2026-11-06 from the ARM64 client. This is bounded static evidence; subsequent [device validation and metadata repair](native-trade-offers.md) are separate observations. This trace alone does not establish successful device behavior, original-service policy, acceptance, ownership transfer or immediate inventory unlock. See [creation](native-trade-creation-contract.md), [cancellation](trade-cancellation-contract.md), and [trading locks](trade-lock-lifecycle-contract.md).

## Reproduction and evidence boundary

From PowerShell in the repository, use the default WSL distribution:

```powershell
wsl.exe -- bash tools/research/ghidra-trade-offers.sh
```

The combined wrapper requires exactly REA 6.8.0, records artifact inspection, runs targeted Ghidra 12.1.4 analysis in a disposable project, and exports metadata-bounded ARM64 instructions using `C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe -X utf8 -B`. It refuses an existing output directory. An optional second argument supplements bounded export with a full-match method regex. The combined wrapper was syntax-checked without repeating Ghidra; findings came from these fresh, retained ignored receipts:

| Receipt under `.research/` | Scope |
| --- | --- |
| `trade-offer-navigation-20261106T220300Z` | Browse selection, offer state/UI, GetTradeData callbacks; 30 bounded methods. |
| `trade-offer-response-20261106T220407Z` | Browse setup, trading entry, offer cells, update popups; 23 bounded methods. |
| `trade-offer-button-20261106T220520Z` | Supplemental bounded MenuBase.SetBtnVisible and HTTP success accessor; 2 methods. Reuses the preceding receipt's artifact/version records; no separate Ghidra analysis. |

The first two contain `rea-version.txt`, `artifact.json`, `ghidra.json`, `ghidra.log`, `methods.json`, and `arm64.txt`. The supplemental receipt has an empty `ghidra.json`, plus bounded exports and copied artifact/version records. Creation/cancellation callback evidence also uses the prior receipts cited by the linked contracts.

ELF SHA-256: `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`; metadata version 31. RVAs refer to the original ELF; Ghidra adds image base `0x100000`. Managed parameter types are not imported. Only instructions inside the bounds in `methods.json` establish behavior; decompiler overrun and inferred types do not.

## Proposed shortest own-offer sequence

Use an existing visible friend's request with `morty_request="any"` and `request_variant="Normal"`, and an owned spare outside the active deck with both lock flags false. No new request, premium slot purchase, incoming offer, acceptance, or transfer is needed.

1. Enter the kiosk, choose Browse, select the friend's request, then Select.
2. On the offer screen, select the Your Offer cell, choose Select, choose the spare in the inventory selector, and select it to return.
3. Confirm the offer. Successful creation returns to Browse.
4. Reopen the same friend's request. Its existing own offer now makes Cancel visible. Choose Cancel; successful cancellation returns to Browse.

This is a proposed test procedure, not a completed native acceptance trace. Capture the authenticated native cancellation and verify the resulting server reference and later owned-details flag independently.

`MPTradeBrowseUI.MenuBtnPressedHandler` (`0x15f8158`) dispatches index 0 to the selected trade and index 1 to Back. `MPTradeBrowseState.UISelectHandler` (`0x15f6f94`) assigns that trade to offer-create state `trade`, offset `+0xa8`, and transitions. For `any`, browse selection (`0x15f7e64`) bypasses its species-specific preliminary inventory check. The actual owned selector still applies the lock/active-deck filter described in the creation contract. The `any` offer path also bypasses setting species/variant selection restrictions in `MPTradeOfferCreateState.UISelectHandler` (`0x16004f4`); it should not be described as independently enforcing Normal for every spare.

## Existing-offer lookup and button prerequisites

`MPTradeOfferCreateState.CreateUI` (`0x15ff9e8`) performs these lookups:

| Destination | Source and equality predicate |
| --- | --- |
| `requestMorty`, `+0x98` | `tradeMortys`: `m.net_id == trade.morty_trade_id`, `0x1600d74`. |
| `offer`, `+0xb0` | `ownTradeOffers`: `o.trade_id == trade.trade_id`, `0x1600d9c`. |
| `offeredMorty`, `+0xa0` | If an own offer exists, `tradeMortys`: `m.net_id == offer.morty_offer_id`, `0x1600dc4`. |

The offer lookup selects the first matching own offer; it does not choose by offered Morty or assert server uniqueness. `SetAsCurrentComplete` (`0x15ff804`) backs out if the selected request is no longer found in `friendTrades`.

`MPTradeOfferCreateUI.SetUp` (`0x15ff708`) initially disables Stats and Select, enables Confirm only when both Morty presentation objects exist, shows Confirm only when `offerData` is null, and shows Cancel only when `offerData` is nonnull. `MenuBase.SetBtnVisible` (`0x16ac610`) directly forwards its bool to `GameObject.SetActive` at `0x16ac650`; the metadata parameter name `isInvisible` is misleading.

Selecting the offer cell enables Select only while state `offer` is null (`OnTradeCellSelected`, `0x160129c`). `MenuBtnPressedHandler` (`0x1601554`) maps 0=Stats, 1=Select, 2=Confirm, 3=Cancel, 4=Back; labels are assigned at `0x1600e84`. The inventory selection handler (`0x15fbeec`) stores its chosen presentation record and transitions back; `Uncache` (`0x15ff650`) moves it into `offeredMorty` and repeats UI setup.

Confirmation (`0x16006a4`) passes selected `net_id` and existing `trade_id` to `SubmitMortyTradeOffer` (`0x1791170`). Cancellation (`0x1600794`) passes the existing offer ID to `CancelTradeOffer` (`0x17918a0`). The creation-success handler (`0x1600960`, `NONE=6`) and cancellation-success handler (`0x1600b4c`, `NONE=3`) both call `UIBackHandler` (`0x15ff910`), explaining why the request must be reopened after creation.

## Response records and actual enrichment consumers

Creation first parses the endpoint error and then deserializes `TradeOfferCreateResponse {offer}`. Its callback (`0x1794924`) appends the returned offer, uses `offer.morty_offer_id` to find owned inventory, reserves that Morty, and uses `offer.trade_offer_id` as the saved offer dictionary key. Cancellation's body-agnostic success contract does not apply to creation.

The metadata declares `MPTradeOfferData` with these fields:

| Field | Offset | Proven use |
| --- | --- | --- |
| `trade_offer_id` | `+0x10` | Saved offer key and exact cancellation ID. |
| `player_id` | `+0x18` | GetTradeData own/friend partition. |
| `morty_offer_id` | `+0x20` | Offered owned-instance ID and presentation lookup. |
| `trade_id` | `+0x28` | Parent request lookup. |
| `request_user_name` | `+0x30` | Update-popup display argument. |
| `offering_morty_id` | `+0x38` | Update-popup species-name lookup. |
| `request_morty_id` | `+0x40` | Update-popup species-name lookup. |

`TradePopups.TradeUpdatePopupHandler` (`0x16bbe18`) loads `+0x38` and calls `MPMortyDefs.Name` at `0x16bbfa8..0x16bbfb0`, then loads `+0x40` and calls Name at `0x16bbfb4..0x16bbfc4`. It loads `+0x30` as the third `String.Format` argument at `0x16bbfc8..0x16bbfdc`. Thus the two enrichment Morty fields are species IDs for display, distinct from `morty_offer_id` and `morty_trade_id` instance IDs. This consumer requires meaningful display values; it does not recover original backend join/authorization policy.

At inspection, PHP `trading/offer-morty/index.php` returned `request_user_name` from the request owner's player ID and `request_morty_id` from the request's owned-instance ID. These do not match the recovered display semantics. `trading/get-trades/index.php` omitted all three enrichment fields. A later list replacement can therefore lose the enriched creation record. No PHP repair was made in this research pass.

`GetTradeData` callback (`0x1794d80`) requires nonnull `trade_requests` and `trade_offers` for partitioning, nonnull `trade_mortys` for iteration, and nonnull `trade_attacks` while attaching attacks to each returned Morty. Empty arrays satisfy those loops. Return matching parent requests and presentation Morties for the lookups above; ID fields alone do not supply the requested/offer cells.

### Completed-list wire key confirmed by subsequent native validation

The dumped `TradeDataResponse` declares `competed_trades` at `+0x30`; PHP originally emitted only `completed_trades`. The callback assigns this deserialized field to completed-trade cache `+0xa8`. At the time of this static pass, the spelling comparison alone was a candidate mismatch.

The available `dump.cs` shows `[Serializable]` on TradeDataResponse and no displayed rename annotation on that field. The actual callback uses `JsonFx.Json.JsonReader.Deserialize`, not the separately bundled Newtonsoft serializer. JsonFx exposes `JsonNameAttribute.GetJsonName` (`0x2471b88`), reader settings with a `TypeCoercionUtility`, and typed reader entry points. The subsequent [bounded navigation trace](native-trade-decision-navigation.md) confirms that the member map uses a nonempty JsonName override or the reflection member name. The field-specific runtime attribute value was not directly dumped; the reconstructed dump alone cannot establish its absence.

Subsequent [native decision validation](native-trade-decisions.md) resolves the practical wire behavior. With an actual rejected offer and no completions, legacy `completed_trades:[]` alone produced an accepted notification. Adding `competed_trades:[]` while retaining the equal legacy array corrected the same unacknowledged saved offer's notification after a normal force-stop/relaunch. No save restoration or cache editing was used. The server now emits both keys for empty and populated results; this correction rests on controlled native behavior rather than metadata spelling alone. The notification's Accept button acknowledges history and does not accept a trade.

## Refresh expectations and limits

Creation callback `0x1794924` sets the owned Morty's trade-lock byte and calls `GetDetails(0x78)` at `0x1794c9c`, then saves multiplayer data and checks offer updates. The returned owned inventory must retain the reservation; a stale false flag can overwrite the local true.

Cancellation callback `0x1796134` removes the successful own offer and saved offer-ID entry, saves mask `0x80`, and checks offer updates. It does not clear the owned inventory lock, call GetDetails, or call GetTradeData. Its UI success path returns to Browse. Browse `CreateUI` (`0x15f6aa0`) supplies cached friendTrades/tradeMortys; Browse Activate (`0x15f6a6c`) has no direct details/trade fetch. Its generic activation coroutine was not fully traced, so broader transition side effects remain a gap.

`MPTradingState.Activate` (`0x1606cc8`) explicitly fetches GetTradeData. That refresh replaces trade caches and does not derive owned-Morty locks. Neither reentering the trade menu nor a successful cancellation alone proves immediate unlock visibility. A subsequent owned-details response is required to observe the server-derived inventory flag; exactly which ordinary native action produces that refresh remains outside this bounded trace. Cancellation does not remove the old presentation Morty from tradeMortys, and that presentation cache is not the owned inventory.

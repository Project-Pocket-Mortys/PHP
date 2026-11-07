# Android 2.41.0 incoming trade decisions and refresh navigation

Recovered 2026-11-06 with REA 6.8.0, targeted Ghidra 12.1.4 and metadata-bounded ARM64 instructions. This document distinguishes static client evidence from the subsequent [native decision validation and notification fix](native-trade-decisions.md). The HTTP body, result enums and cache mutations are documented in the [response contract](native-trade-response-contract.md). The [offer contract](native-trade-offer-contract.md) describes creating an offer on a friend's request.

## Native route to an incoming offer

1. At the Swap Stop root choose **Trade**, menu index 1. **Browse**, index 0, opens friends' requests for making offers.
2. Tap the occupied own request slot, then **Select**, index 0. Selection reads the cached incoming-offer count for that request. A positive count opens its incoming-offer list; zero opens its request editor.
3. Tap the desired incoming-offer row, then **Select**, index 0. This opens the two-Morty decision screen.
4. Choose **Reject**, index 2, or **Accept**, index 1. These submit immediately; this route has no preceding Yes/No or Confirm popup.
5. Close the result popup using its close control. With no incoming offers left on that request, the return destination is the own-slot list. With siblings left, it is that request's incoming-offer list.

There is no separate **Offers** command in the recovered root dispatch. The root has Browse, Trade and Back at indexes 0, 1 and 2. The incoming list is reached through an occupied own slot. Incoming lists and own-slot routing use cached records; selecting a slot does not itself fetch newly submitted offers.

| Screen/method | Recovered dispatch or selection |
| --- | --- |
| `MPTradingUI.MenuBtnPressedHandler`, `0x160868c` | 0 Browse, 1 Trade, 2 Back. `SetLabels`, `0x1607c08`, assigns Browse/Trade. |
| `MPTradingState.UITradesHandler`, `0x1607770` | Transitions to `MPTradeManageState`. |
| `MPTradeManageUI.MenuBtnPressedHandler`, `0x15fabec` | 0 passes selected cell's `trade` (`+0x128`) and slot index to SelectEvent; 1 Back. |
| `MPTradeManageState.UISelectHandler`, `0x15f95c4` | For an existing request, finds incoming offers with matching `trade_id` in `friendOffersOnOwnTrades` (`+0x98`). At `0x15f975c` it tests count; positive sets `MPTradeOfferBrowseState.tradeID` (`+0x98`) from the request's `trade_id`, then transitions to that state. Otherwise sets `MPTradeRequestCreateState.trade` (`+0xa8`) and opens the request editor. |
| `MPTradeOfferBrowseState.CreateUI`, `0x15fe1d0` | Filters `friendOffersOnOwnTrades` by its `tradeID`. Predicate `0x15feff4` compares offer `trade_id` (`+0x28`) with state `tradeID` (`+0x98`). |
| `MPTradeOfferBrowseUI.MenuBtnPressedHandler`, `0x15ff470` | 0 passes selected cell's `tradeOffer` (`+0x130`); 1 Back. Selecting a row enables Select. |
| `MPTradeOfferBrowseState.UISelectHandler`, `0x15feba0` | Assigns selected offer to manage-state `tradeOffer` (`+0xa0`), finds its parent in `ownTrades` for an incoming offer, assigns `trade` (`+0x98`), then opens manage state. |

`MPTradeManageUI.SetUp` (`0x15f8850`) supplies each occupied slot's incoming-offer count to `MPTradeCell.SetUp`. The root tutorial's English text explicitly describes a red indicator on Trade when an offer arrives. The screen's exact visual count placement is an asset/UI observation, not established by the state dispatch alone. The empty-slot branch is trade creation and may involve premium-slot purchase; it is unnecessary for handling an existing incoming offer.

## Decision labels and result popup

`MPTradeOfferManageUI.SetLabels` (`0x1603988`) assigns the headings **Your Offer:** and **Receiving:** and these button titles. `MenuBtnPressedHandler` (`0x1603e6c`) dispatches the corresponding events:

| Index | English label | Event/handler |
| --- | --- | --- |
| 0 | Stats | StatsEvent, with selected presentation Morty. |
| 1 | Accept | AcceptEvent → `UIAcceptHandler`, `0x16026d4`, sends `request_accepted=true`. |
| 2 | Reject | DeclineEvent → `UIDeclineHandler`, `0x16027c0`, sends `request_accepted=false`. |
| 3 | Cancel | CancelEvent; distinct from rejecting the selected incoming offer. |
| 4 | Back | BackEvent. |

**Reject** is the actual English title; “Decline” is the managed event/handler name. Both decision buttons are enabled by `SetUp` (`0x16019a4`) while Stats initially requires selecting a Morty cell. Pressing Accept/Reject dispatches the event and disables decision buttons. `AddEvents` (`0x1601aac`) subscribes those events to the state handlers. None of these bounded methods adds a pre-submit confirmation step. **Confirm** belongs to creating an offer/request, not this incoming decision route.

For response enum `NONE=4`, `OnRejectResult` (`0x16033b0`) displays **Trade Rejected**. `OnAcceptResult` (`0x1602dd8`) displays the localized format:

```text
Trade Successful! {0} went to {1} and {2} has gone to Daycare!
```

The arguments are the request Morty's species name, the offering friend's display name and the offered Morty's species name. The callbacks call `GenericPopupState.SetDisplayValues(text, buttons:null, showCloseBtn:true, showWaiting:false, showCouponHolder:false)`. Thus they configure a close control, not Yes/No buttons. The callback registers `UIBackWrapper` (`0x1602cf0`), which ignores the clicked index, calls `UIBackHandler` and unsubscribes itself. Non-success decision results use the same popup mechanism with the enum's string form.

`UIBackHandler` (`0x1602b3c`) counts remaining cached incoming offers belonging to the current request. Zero selects `MPTradeManageState`; nonzero selects `MPTradeOfferBrowseState`. Generic targets were resolved from ELF RELA addends to `ScriptMetadataMethod`, not guessed from decompiler types. Rejecting the only offer therefore normally returns to the own slots after the popup is closed, retaining the request. Acceptance removes the request and its incoming offers in the API callback, so the same return check resolves to own slots.

## Callback ordering and new incoming offers

The API's successful response callback (`0x17953b0`) runs in this order:

1. Parse the endpoint error, then invoke the UI result callback. The result popup is configured while the presentation caches still exist.
2. Find the selected incoming offer and own request, then start local `NetworkPlayerAPI.GetDetails(0x78)`.
3. Remove the declined offer, or perform the acceptance cleanup described in the response contract.
4. Call `CheckUpdateTradeOffers`.

Starting GetDetails does not wait for its network response. Popup display, trade-cache cleanup and the later inventory response are separate parts of this sequence; closing a popup is not proof that the owned inventory refresh has finished. The response callback does not call GetTradeData or emit an explicit OnTradeOffersUpdated event. Manage-state `OnTradeOffersUpdated` (`0x1603754`) can separately back out if a later trade-data update no longer contains the selected offer.

`MPTradingState.Activate` (`0x1606cc8`) calls GetTradeData before base activation. `MPTradeManageState.UIBackHandler` (`0x15f9c20`) explicitly transitions to `MPTradingState`, providing a normal route back to this fetch: back out from the slots to the kiosk root and allow the request to complete, then enter Trade again. Exiting and reopening the kiosk also activates this state. The child own-slot selection and incoming-list selection read caches directly.

GetTradeData's success callback (`0x1794d80`) replaces `ownTradeOffers`, `friendOffersOnOwnTrades`, `friendTrades`, `ownTrades` and `tradeMortys`, attaches returned attacks, stores completed/cooldown data, checks update popups, then emits the data/request/offer/cooldown events before its supplied completion callback. Incoming-list `OnTradeOffersUpdated` (`0x15fef14`) filters again by the same request ID and rebuilds the list. An empty incoming array makes `MPTradeOfferBrowseUI.SetUp` (`0x15fe358`) call SetBack. Reentering the root and waiting for a successful GetTradeData response is therefore the evidenced way to retrieve a new incoming offer; repeatedly selecting a stale slot is not a fetch.

## Reusing a Morty after rejection

GetDetails in the response callback belongs to the request owner's client. It does not remotely refresh the offering player's loaded inventory. On the offering client, GetTradeData and `CheckUpdateTradeOffers` (`0x1791a38`) can detect a disappeared saved offer and display a rejection update, but neither bounded method requests owned details or clears owned `isTradeLocked` (`+0x6e`). This confirms the [trading-lock refresh gap](trade-lock-lifecycle-contract.md).

For a repeated native offer with the same spare, first establish the rejection and then obtain an authoritative owned-details refresh on the offering client. If normal kiosk reentry updates the offer list but the selector still excludes the spare, a cold app relaunch/login preserving app data is a reasonable device procedure to test. This pass does not establish that a cold relaunch is always necessary or which startup details mask the device will request. Verify the actual refreshed `is_trading_locked` value and eligibility before interpreting a second creation failure. Clearing app data/cache is unnecessary for this static diagnosis and was not performed.

There is also an event-driven refresh path: `TradRequestSummitedHandler`, `TradeOfferdSummitHandler`, `TradOfferAcceptdHandler` and `TradOfferRejectHandler` each start GetTradeData and GetDetails(`0x78`). An event delivered to the offering client can therefore refresh its inventory. This does not establish that the replacement server delivered such an event during any particular test. A targeted scan for direct ARM64 B/BL calls to GetTradeData found these four handlers, root Activate and successful CancelTrade handling; it found no direct login/startup caller. Indirect dispatch and queued events prevent treating that scan as proof that startup cannot fetch trade data.

## Offerer update notifications and completed-list mapping

These notifications differ from the request owner's decision result popup. `CheckUpdateTradeOffers` (`0x1791a38`) iterates saved multiplayer `trade_offer_made_ids`. Offers still present in `ownTradeOffers` are skipped. For a disappeared saved offer, it branches as follows:

| `completedTrades` cache (`+0xa8`) | Classification |
| --- | --- |
| Nonnull, contains `CompleteTradeData.trade_offer_id` equal to the saved offer ID | Completed (`updateCompletedTrades`, `+0xd0`). |
| Nonnull, no matching completed record, including an empty list | Rejected (`updatedRejectedTrades`, `+0xc8`). |
| Null | Completed (`+0xd0`), without calling Any on the null list. |

The null branch is explicit at `0x1791c80..0x1791c8c`, targeting completed insertion at `0x1791cd8`; a nonnull list with no match branches at `0x1791cd4` to rejected insertion at `0x1791d34`. Completed predicate `0x17963ac` compares the record's `trade_offer_id` (`+0x38`) to the saved dictionary key. Thus a null completed cache must not be treated as equivalent to an empty list, nor as evidence of a real accepted transfer.

GetTradeData callback `0x1794d80` copies deserialized response field `+0x30` directly into API cache `+0xa8` before checking updates. Metadata names that response field `competed_trades`; PHP originally emitted only `completed_trades`. Fresh bounded `TypeCoercionUtility.CreateMemberMap` (`0x24747e0..0x2474ac0`) confirms that JsonFx checks public fields for JsonIgnore, asks `JsonNameAttribute.GetJsonName`, and uses the reflection member name if no nonempty override exists. `GetJsonName` (`0x2471b88..0x2471db0`) checks and reads a runtime custom attribute. The field-specific runtime attribute value for `TradeDataResponse.competed_trades` was not directly recovered by this static pass.

Subsequent [device validation](native-trade-decisions.md) resolves the practical wire-key mismatch: with an actual rejected offer, zero completed trades and only legacy `completed_trades: []`, the offering client displayed **was accepted**. The server then added `competed_trades: []` while retaining the legacy property. A normal force-stop/relaunch with the **same unacknowledged saved offer** displayed **was rejected**. Read-only save checkpoints preserved that pending history; no save restoration or app-data/cache editing was used. This establishes the required native response key and the notification correction without claiming that the field's runtime attribute internals were dumped. The popup's **Accept** button remains an acknowledgement, not a trade-acceptance action.

`TradePopups.TryPushTradeUpdateState` (`0x16bc164`) processes rejected records first with `result=false`, then completed records with `result=true`. `TradeUpdatePopupHandler` (`0x16bbe18`) selects these English formats:

```text
Your trade offer of {0} for {1} with {2} was rejected
Your trade offer of {0} for {1} with {2} was accepted, Check your daycare out for your new morty
```

The parameters use species-name fields and the saved request owner's display name. Both notification variants configure **one button titled Accept**, with no close control. Here **Accept acknowledges the notification**; it does not submit an offer response. On that button's callback, `GenericPopupRejectedMortyHandler` (`0x16bc258`) or `GenericPopupCompletedTradeHandler` (`0x16bc538`) removes the displayed offer ID from saved `trade_offer_made_ids`, saves multiplayer mask `0x80`, then checks for another popup. Initial display does not perform that removal.

For a diagnostic device capture, preserve a private read-only save checkpoint before the next GetTradeData and before acknowledging the first popup. Preserve the first popup screenshot and its paired get-trades response before pressing its Accept button. The actual internal save root is Android `Context.getFilesDir().getAbsolutePath()`; `GetInternalStoragePath` (`0x14a6448`) falls back to `/data/data/<package>/files`. For this package, `/data/user/0/com.turner.pocketmorties/files` is the corresponding private-files location. Also preserve the existing external app-files tree and shared preferences if available. The offer dictionary is multiplayer save data; no dedicated PlayerPrefs key was recovered. Copy/hash only; restoring or editing a save is unnecessary for this evidence checkpoint.

## Evidence and reproduction

ELF SHA-256: `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`; metadata version 31. RVAs refer to that ELF; Ghidra's image base is `0x100000`. Only instructions within `methods.json` bounds establish behavior; shared-generic exception paths can make decompiler output extend into adjacent methods.

Fresh ignored receipts:

| Directory under `.research/` | Contents |
| --- | --- |
| `trade-decision-navigation-20261107T0010` | 34 bounded methods; root/own-slot/incoming/manage navigation; `english-labels.json` with original bundle/TextAsset hashes; `generic-targets.json` with RELA/metadata target resolutions. |
| `trade-decision-events-20261107T0018` | 22 bounded methods; GetTradeData callback, disappeared-offer helper, result handlers and six localized getters. The getters are supplementary bounded exports because the Ghidra script excludes accessors by default. |
| `trade-completed-notification-20261107T0037` | 17 bounded methods; update predicates/popups and history consumption, four trading event handlers, save-path accessors and JsonFx member-map/attribute machinery. Direct GetTradeData call-site receipt is retained in the events directory. |
| `trade-offer-response-contract-20261106T232513Z` | Previously retained bounded response constructor/callback and decision handlers, described in the response contract. |

Each fresh receipt has REA version, artifact inspection, targeted Ghidra JSON/log and bounded ARM64/method JSON. English labels were read with UnityPy from original Android `text.assetbundle`, SHA-256 `bbe4b3036a907354dd7cad8122c0f557491e3259b6f4f349eda27caa913bc7a8`, EN TextAsset path ID `2069814988615685635`, TextAsset SHA-256 `841eed65c78a058635eef4993f07b0a5592e8906f77c95027604cc3c57d4e1c4`. Getter literal references resolve to `TRADE_*` English keys despite the managed `MP_TRADE_*` property names.

From PowerShell, use default `wsl.exe -- bash`; in that Bash shell run the following from the repository with a fresh OUT directory:

```bash
set -euo pipefail
OUT=".research/trade-decision-review-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$OUT"
bash tools/research/rea.sh --version > "$OUT/rea-version.txt"
test "$(tr -d '\r\n' < "$OUT/rea-version.txt")" = 6.8.0
bash tools/research/rea.sh inspect-artifact \
  .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so \
  --format json > "$OUT/artifact.json"
FILTER='MPTradingState.*(Activate|UITradesHandler)|MPTradingUI.*(SetLabels|MenuBtnPressedHandler)|MPTradeManageState.*(UISelectHandler|UIBackHandler)|MPTradeManageUI.*(SetUp|SetLabels|TradeCellSelectedHandler|MenuBtnPressedHandler)|MPTradeOfferBrowseState.*(CreateUI|UISelectHandler|OnTradeOffersUpdated)|MPTradeOfferBrowseUI.*(SetUp|SetLabels|MenuBtnPressedHandler)|MPTradeOfferManageState.*(UIBackHandler|UIBackWrapper|OnAcceptResult|OnRejectResult|OnTradeOffersUpdated|AddEvents)|MPTradeOfferManageUI.*(SetLabels|MenuBtnPressedHandler)|NetworkFriendAPI.*(GetTradeData|CheckUpdateTradeOffers).*'
bash tools/research/ghidra-targeted.sh "$(realpath "$OUT")/ghidra.json" "$FILTER" \
  > "$OUT/ghidra.log" 2>&1
/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe \
  -X utf8 -B tools/research/trade-cancellation-bounded.py \
  "$(wslpath -w "$(realpath "$OUT")")" \
  'MPTradeOfferBrowseState.*<CreateUI>.*|MPTradeOfferManageState.*<(UIBackHandler|OnAcceptResult)>.*|MPTextDefs.*get_MP_TRADE_(ACCEPT_BTN|REJECT_BTN|OFFER_TEXT|RECEIVING_TEXT|SUCCESSFUL_MESSAGE|REJECTED_MESSAGE)'
```

The static research changed only this document and ignored receipts. It performed no device, database, endpoint, account, cache or APK mutation, and no full Ghidra analysis/indexing. The subsequent runtime observations and response alias belong to the separately linked decision validation.

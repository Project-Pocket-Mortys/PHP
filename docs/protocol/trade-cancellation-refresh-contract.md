# Android 2.41.0 cancellation refresh boundary

Fresh static recovery on 2026-11-06 used REA 6.8.0, targeted Ghidra 12.1.4 in the default WSL distribution, and metadata-bounded ARM64 instructions. Within the recovered cancellation, navigation and dispatch contracts, there is **no demonstrated safe PHP-only immediate refresh for the voluntarily cancelling offerer**. The HTTP success path neither requests owned details nor supplies an application acknowledgement that PHP can use to order an actor event after saved-history removal. This is an evidence boundary, not a claim that every possible server or native mechanism is impossible.

This static pass performed no database, device, endpoint or account mutations and made no client patch. The later [replacement cancellation validation](trade-cancellation-notifications.md) records the separate native counterpart observations and explicit peer cold-login boundary. See the existing [cancellation](trade-cancellation-contract.md), [lock lifecycle](trade-lock-lifecycle-contract.md), [trade refresh events](trade-refresh-event-contract.md), and [decision navigation](native-trade-decision-navigation.md) contracts for their separate evidence and validation boundaries.

## Voluntary offer cancellation and return state

The fresh bounded chain is:

| Method and ELF RVA bounds | Observed behavior |
| --- | --- |
| `MPTradeOfferCreateState.UICancelHandler`, `0x1600794..0x1600878` | Reads existing `offer.trade_offer_id`, calls `CancelTradeOffer`, then clears its offer and presentation references. |
| `NetworkFriendAPI.CancelTradeOffer`, `0x17918a0..0x1791a38` | Submits `/trading/cancel-trade-offer` with the single offer ID and registers its HTTP callback. |
| `<CancelTradeOffer>b__0`, `0x1796134..0x1796324` | Parses the error; on `NONE=3`, removes the own offer and saved offer-history entry, saves, checks updates, then invokes the supplied UI callback. |
| Cancellation overload of `MPTradeOfferCreateState.OnRequestResult`, `0x1600b4c..0x1600d38` | On `NONE=3`, calls `UIBackHandler`. Failure follows the existing error-popup path. |
| `MPTradeOfferCreateState.UIBackHandler`, `0x15ff910..0x15ff9e8` | Clears the two presentation references and transitions to `MPTradeBrowseState`. |
| `MPTradeBrowseState.Activate`, `0x15f6a6c..0x15f6aa0`, and `CreateUI`, `0x15f6aa0..0x15f6ba0` | Activates the ordinary UI and supplies cached `friendTrades` (`+0x80`) and `tradeMortys` (`+0xa0`) to browse setup. No owned-details request occurs in either body. |

The callback order is established directly by instructions: own-offer `RemoveAll` at `0x1796240`, saved `trade_offer_made_ids.Remove` at `0x179629c`, `Save(0x80)` at `0x17962d4`, `CheckUpdateTradeOffers` at `0x17962e4`, then the supplied delegate invocation. It does not request `GetDetails`, call `GetTradeData`, or clear the owned `isTradeLocked` byte.

The save call was traced explicitly. `SaveDataController.Save` (`0x1497548`) writes `multiplayer.dat` for mask `0x80`, then calls `SaveActiveSaveContainerLocalAndCloud` (`0x14a811c..0x14a82c4`). That helper writes `CloudContainer.dat` and calls `SaveActiveSaveContainerToCloud` with a null completion callback. `SerializeObjectToCloudFile` (`0x14acca0..0x14ad03c`) and `CommitObjectToOpenCloudFile` (`0x14ad03c..0x14ad560`) use `GooglePlayGames.PlayGamesPlatform.get_SavedGame` and the saved-game interface, whose metadata type is `GooglePlayGames.BasicApi.SavedGame.ISavedGameMetadata`. This is local persistence plus an optional platform-cloud save, not a recovered acknowledgement to the replacement PHP trading service. The bounded path supplies no details refresh or cancellation acknowledgement through that save.

The back target is resolved, rather than inferred from the shared generic `Set<object>` body. At `0x15ff9b8..0x15ff9c8`, the code loads the generic method through slot `0x2f84318`; its ELF RELA addend is `0x309d6a8`, whose `ScriptMetadataMethod` name is `StateController.Set<MPTradeBrowseState>()`. The cancellation callback delegate slot `0x2f84398` resolves to metadata `0x3098ff8`, method address `0x1600b4c`. Thus the success path returns to browse; it does not automatically traverse the kiosk-root fetch or establish an owned-inventory refresh.

`ParseHTTPError<Int32Enum>` (`0x1b569d8..0x1b56de0`) returns `NONE` from successful response status without parsing its body. The fresh shared success accessor (`0x1820fe4..0x1821004`) accepts 200–299 and 304. Returning inventory, a lock field, a refresh instruction or an acknowledgement ID in cancellation JSON cannot affect this callback. No supported cancellation response field or header commanding a details refresh was recovered here. The generic HTTP handler removes its pending request and invokes the supplied callback; its inspected successful branch adds no such command.

## Parent cancellation while managing an incoming offer

`MPTradeOfferManageState.UICancelHandler` (`0x16028ac..0x1602984`) calls **`CancelTrade`**, passing `state.trade` (`+0x98`) and that record's `trade_id` (`+0x10`). It does not cancel only the displayed incoming offer. Its delegate slot `0x2f84460` resolves to `MPTradeOfferManageState.TradeCancelResult`, RVA `0x1603568`; `NONE=2` returns through that state's back handler.

The incoming-offer management UI permits this route in the inspected code. `CreateUI` (`0x16017a8..0x16019a4`) finds the requested and offered Morty presentation records and passes both to `MPTradeOfferManageUI.SetUp` (`0x16019a4..0x1601a90`). Setup enables Accept and Reject and disables Stats until selection. It contains no incoming-offer-count condition that hides or disables Cancel. `SetLabels` (`0x1603988..0x1603a88`) labels index 3 Cancel, and `MenuBtnPressedHandler` (`0x1603e6c..0x1603f4c`) dispatches index 3 to `CancelEvent` (`+0x50`). `AddEvents` binds that event through slot `0x2f84420`, relocated to metadata `0x30990b0`, `MPTradeOfferManageState.UICancelHandler`. The native route therefore supports cancelling the parent while viewing an incoming offer; whether a particular runtime screen was rendered or pressed is outside this static pass.

Parent cancellation has a different local refresh contract: `<CancelTrade>b__0` (`0x1795cf8..0x1796090`) requests details with mask `0x78`, clears the request Morty's local trading lock on success, removes the request and associated incoming offers, and refreshes trade data. This difference must not be transferred to voluntary own-offer cancellation.

## Why an actor event is not ordered by HTTP success

The four established trade events all start both `GetTradeData` and `GetDetails(0x78)`, ignoring their payload. An actor echo could therefore start the missing details request, but its trade-data response can observe the removed offer while that offer's ID remains in local saved history. `CheckUpdateTradeOffers` can then classify voluntary withdrawal as rejection, or as completion when the completed list is null. Event-name substitution does not fix this: the fetched state and saved history determine classification.

Supplementary dispatch recovery confirms separate scheduling paths. `HTTPUpdateDelegator.Update` (`0x199de50..0x199ded0`) calls `CallOnUpdate` in its zero threading-mode branch; `CallOnUpdate` (`0x199dd5c..0x199de50`) calls `HTTPManager.OnUpdate`. The bounded manager calls `RequestEventHelper.ProcessQueue` at `0x199c104`. Request state-change processing invokes the request's finished delegate. SSE `OnDownloadStarted` (`0x1a489fc..0x1a48ddc`) starts its `DataProcessor` through `MonoBehaviour.StartCoroutine`; `DataProcessor.MoveNext` (`0x1a49bb4..0x1a49d2c`) feeds stream data and calls `HandleEvents` at `0x1a49c80`. `HandleEvents` (`0x1a499dc..0x1a49a5c`) dequeues messages and dispatches `OnMessageReceived`.

These paths do not establish server-controlled callback order between the cancellation HTTP response and an SSE-driven trade-data response. Serial processing in a Unity update loop would still not mean that sending, flushing or committing an HTTP response has completed the cancellation callback. A transport ACK acknowledges bytes, not the managed saved-history removal. No application acknowledgement after that removal is emitted by the inspected success chain. No deterministic post-success native request in this chain was found that PHP could use as such a barrier. Arbitrary delays, success-body additions and guessed original-server timing therefore do not provide a demonstrated safe fix.

A later successful authoritative owned-details response can apply the released server flag through the existing inventory parser. This audit does not determine when that later refresh occurs or prove selector eligibility immediately after cancellation.

## Counterpart cancellation policy

The following is a **replacement-server policy**, not recovered original-service publication or audience selection:

| Committed cancellation | Recipient | Existing invalidation event |
| --- | --- | --- |
| Parent request removed with its attached offers | Each distinct removed offer's owner, excluding the actor | `trade:offer-rejected` |
| Offer voluntarily removed while its parent exists | The parent request's owner, excluding the actor | `trade:offer-submit` |

The second event invalidates the owner's incoming-offer cache; its name does not claim that a new offer was submitted. Payload `{}` is sufficient for the recovered handlers. Parent cancellation can intentionally produce the ordinary rejection notification on counterpart offerers through saved-history reconciliation; the payload itself does not choose that notification. Deduplicate affected recipients, write invalidation after authoritative removal in the same transaction, deliver only committed state, and preserve existing authenticated account targeting and startup-readiness gates. A successfully cancelled orphan offer has no recovered parent owner to notify and must remain cancellable without inventing a recipient. No actor notification is added by this policy. Original cancellation audiences, payloads, replay and ordering guarantees remain unknown.

## Evidence and reproduction

Ignored fresh receipts under `.research/` are `trade-cancellation-refresh-20261107T0225` (25 selected Ghidra methods, 26 bounded exports), `trade-cancellation-refresh-navigation-20261107T0230` (15 selected, 16 bounded), `trade-cancellation-refresh-dispatch-20261107T0235` (5 selected, 6 bounded), `trade-cancellation-refresh-save-20261107T0240` (1 selected, 2 bounded), and `trade-cancellation-refresh-cloud-20261107T0245` (4 selected, 9 bounded, including explicit supplementary cloud commit/callback exports). Each contains REA version, artifact inspection, targeted Ghidra JSON/log, `methods.json` and `arm64.txt`; no selected Ghidra method reported an error. The first also contains the explicit relocation bindings in `bindings.json`. Ghidra imports used `-noanalysis`; no full indexing was run. Decompiler output can flow beyond metadata bounds or omit switch targets; claims above use the bounded instructions, method metadata and resolved relocations.

Pinned ELF SHA-256 is `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`; metadata version is 31, SHA-256 `b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10`; dumper script SHA-256 is `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb`. RVAs are ELF-relative; Ghidra adds image base `0x100000`.

Key bounded method-body SHA-256 values:

| Method | SHA-256 |
| --- | --- |
| Offer cancellation callback | `389088c518a19a2c117ff32477a1cd071388763817ba29d488c70d43db1a8d0d` |
| Offer cancellation UI result | `b9c06bf835fbc9cb8f4d6d34ea3bf879cafb02e2e3e265fff84639d780e8c0b3` |
| Offer-create back handler | `0420146846f4408842fdd7b74e0bd8dc69344d84bd69dc22ff772a26538bfe85` |
| Browse CreateUI | `f55f3d16e6237c6c91379e08faf5a897f2caa7cb590eee9948eaaa541af8223f` |
| Incoming-offer manage cancel handler | `addbdda49460fd27c7cfdd3b4b855fd4059ece7ff47e1385abddf86d6a3c5133` |

Reproduce from default WSL Bash in the repository, choosing a new output directory:

```bash
set -euo pipefail
OUT=".research/trade-cancellation-refresh-review-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$OUT"
bash tools/research/rea.sh --version > "$OUT/rea-version.txt"
test "$(tr -d '\r\n' < "$OUT/rea-version.txt")" = 6.8.0
bash tools/research/rea.sh inspect-artifact \
  .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so \
  --format json > "$OUT/artifact.json"
FILTER='MPTradeOfferCreateState.*(Activate|Uncache|SetAsCurrentComplete|UIBackHandler|UICancelHandler|OnRequestResult)|MPTradeOfferManageState.*(UICancelHandler|TradeCancelResult)|NetworkFriendAPI.*(CancelTrade|CheckUpdateTradeOffers).*|NetworkHTTP.*(Update|RequestHandler)|NetworkEventSource.*(CallHandlers|OnMessageHandler)|NetworkDefs.*ParseHTTPError<Int32Enum>'
bash tools/research/ghidra-targeted.sh "$(realpath "$OUT")/ghidra.json" "$FILTER" \
  > "$OUT/ghidra.log" 2>&1
/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe \
  -X utf8 -B tools/research/trade-cancellation-bounded.py \
  "$(wslpath -w "$(realpath "$OUT")")"
```

For the navigation supplement, repeat the same commands with a fresh directory and this filter:

```bash
FILTER='MPTradeBrowseState.*(Activate|CreateUI)|MPTradeOfferManageUI.*(SetUp|MenuBtnPressedHandler|SetLabels)|MPTradeOfferManageState.*(CreateUI|AddEvents)|Best.HTTP.Shared.HTTPManager.*OnUpdate|Best.HTTP.Shared.HTTPUpdateDelegator.*(CallOnUpdate|Update)$|Best.HTTP.Hosts.Connections.RequestEventHelper.*(ProcessQueue|HandleRequestStateChange)|Best.ServerSentEvents.EventSource.*(HandleEvents|<DataProcessor>.*MoveNext|IHeartbeat.OnHeartbeatUpdate)'
```

For the dispatch/base-state supplement, use another fresh directory and:

```bash
FILTER='StateBase.*(Activate|CreateUI)$|Best.ServerSentEvents.EventSource.*(OnDownloadStarted|OnMessageReceived)|MPTradeBrowseState.*(AddEvents|OnTradeRequestsUpdated)'
```

For the save supplement, use `FILTER='SaveDataController.*Save$|MultiplayerSaveData.*Save$'`. For the cloud supplement, use `FILTER='SaveDataController.*(SaveActiveSaveContainerLocalAndCloud|SaveActiveSaveContainerToCloud|SerializeAndWriteObjectToFile|<SaveActiveSaveContainerToCloud>.*)'`, and pass a third argument to the bounded exporter: `'SaveDataController.*(SerializeObjectToCloudFile|CommitObjectToOpenCloudFile)|SaveDataController.*DisplayClass95_0.*'`.

The explicit Windows Python executable avoids the Store alias. This establishes the bounded client contracts and the stated replacement policy; it does not validate cancellation notification consumption on a live native client.

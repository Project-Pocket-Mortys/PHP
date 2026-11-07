# Android 2.41.0 trade refresh events

Recovered 2026-11-06 with REA 6.8.0, targeted Ghidra 12.1.4 and metadata-bounded ARM64. The original client subscribes to four trade events. Every handler starts both a trade-data request and an owned-details request. Their payloads do not carry authoritative trade or inventory state. Original-service recipient selection and cancellation publication were not recovered.

See [native navigation and notifications](native-trade-decision-navigation.md), [lock lifecycle](trade-lock-lifecycle-contract.md), and [response contract](native-trade-response-contract.md). Static recovery performed no device, database, endpoint or account mutations. The later synthetic native smoke is described separately below.

## Exact subscriptions and refresh behavior

`NetworkFriendAPI.Connected` (`0x178ee00..0x178f150`) creates these delegates and registers them through `NetworkSessionAPI.On` (`0x17b6980`). `Disconnected` (`0x178f348..0x178f68c`) unregisters the same pairs through `Off` (`0x17b6998`). These are session subscriptions, independent of whether the kiosk UI is open. The bounded Connected method contains no trade cancellation event subscription.

| SSE event name, exact spelling | Bound handler | GetTradeData call | GetDetails tail call |
| --- | --- | --- | --- |
| `trade:request-submit` | `TradRequestSummitedHandler`, `0x17921cc..0x1792280` | `0x179222c` | `0x1792278` |
| `trade:offer-submit` | `TradeOfferdSummitHandler`, `0x1792280..0x1792334` | `0x17922e0` | `0x179232c` |
| `trade:offer-accepted` | `TradOfferAcceptdHandler`, `0x1792334..0x17923e8` | `0x1792394` | `0x17923e0` |
| `trade:offer-rejected` | `TradOfferRejectHandler`, `0x17923e8..0x179249c` | `0x1792448` | `0x1792494` |

All four handlers perform the same work:

1. Read the receiving client's current player ID from `NetworkPlayerAPI.playerData` (`+0x58`), `MPPlayerData.netId` (`+0xa0`), then call `GetTradeData(playerID, callback:null)`.
2. Call the receiving client's `NetworkPlayerAPI.GetDetails(0x78, callback:null)`.

`0x78 = MORTIES(8) | MORTY_ATTACKS(16) | DECKS(32) | MORTYDEX(64)`. The first call starts a request; the handler does not wait for its response before starting details. No payload player ID chooses the refresh target, and no handler directly changes the owned-Morty lock byte.

The string/delegate bindings were resolved from ELF RELA addends and `ScriptMetadataMethod`, then checked against the bounded register loads. For example, Connected uses method-pointer slot `0x2f90598`, relocated to metadata `0x309a7a8`, naming `NetworkFriendAPI.TradOfferRejectHandler` (`0x17923e8`), paired with string slot `0x2f905d8`, relocated to `0x30cec98`, value `trade:offer-rejected`. The other three bindings are retained in `bindings.json`; they are not inferred from the misspelled managed handler names.

## Payload and dispatcher contract

`NetworkEventSource.On` (`0x17b5044`) forwards the name/delegate to its internal registry. `OnMessageHandler` (`0x17b9e1c..0x17b9ee0`) reads the SSE Message's event name at `+0x18` and data string at `+0x20`, then calls `CallHandlers(name, removeOnceCalled:false, data)`.

`CallHandlers` (`0x17b9c44..0x17b9df4`) looks up that exact name in `_registeredHandlers` (`+0x48`), copies the delegate list and invokes the registered delegates with a new `NetworkEventSourceResponse`. It stores the raw data string at response `+0x10`. `NetworkEventSourceResponse..ctor` (`0x17b9df4..0x17b9e1c`) likewise only stores the string. Neither dispatcher method parses JSON. The four trade handlers never read their response argument; they overwrite argument register `x1` with the local player ID before their first request.

Therefore there are **no client-consumed payload fields** for these four events. No trade ID, offer ID, result Boolean, player ID, Morty ID or lock field is required by this bounded path. A conservative compatible invalidation frame is:

```text
event: trade:offer-rejected
data: {}

```

`{}` is a replacement-server payload choice, not a recovered original-service body. The lower SSE parser still needs to dispatch a message; an explicit data line avoids depending on empty-data behavior. JSON syntax and extra keys have no effect on these handlers once dispatched. The event name itself also does not determine an accepted/rejected popup: that classification comes from the later GetTradeData response and saved offer history.

## Recipients: established limits and replacement policy

The client handlers establish what happens **after delivery to a session**. They do not reveal the original server's recipients, friend fanout, actor echo, offline retention, replay, ordering or delivery guarantees. They do not filter payload participants or reject unrelated trade IDs. Recipient authorization must consequently be enforced by the replacement server, and delivery should follow the committed authoritative change.

The following is a focused replacement invalidation policy, not a claim about original publication. Each recipient refreshes its own caches through the original handler above. Account targeting must work across rooms; the affected counterpart need not occupy the actor's current room.

| Committed action | Replacement recipient | Existing event usable as invalidation |
| --- | --- | --- |
| Offer created on a request | Request owner | `trade:offer-submit` |
| Incoming offer rejected | Removed offer's owner | `trade:offer-rejected` |
| Incoming offer accepted | Accepted offer's owner | `trade:offer-accepted` |
| Acceptance removes sibling offers | Owners of removed sibling offers | `trade:offer-rejected` |

This policy covers offer creation and decisions only. Exclude the actor, deduplicate recipients and prefer `trade:offer-accepted` when the winner also owns removed sibling offers. Original audience selection remains unknown. Request creation and both cancellation paths are outside this publication scope. There is no recovered `trade:offer-cancelled` name or cancellation audience, nor evidence here for broadcasting request creation to all friends.

Actor echoes are unnecessary for those counterpart updates: the local successful creation/decision/request-cancellation callbacks already update their caches and request details. Own-offer cancellation is the exception described below. Repeated events are also not free: each starts two network requests, with no deduplication in these bounded handlers.

The inspected pre-change PHP event helper supports room-scoped event rows; `publish_event(..., player_id)` only assigns an explicit private recipient automatically for battle events. `event_is_visible_to_player` honors `only_show_to_player_id` when present, but `player_id` alone is a subject for public events. Thus simply publishing a trade name with the actor/recipient as `player_id` does not establish private, account-global delivery. This source observation describes the inspected baseline, not a required storage design or an implementation claim.

## Startup delivery boundary

Do not equate a sent `session:start` frame with initialized player data. The native `NetworkEventSource.OnOpenHandler` (`0x17ba008..0x17ba080`) invokes OpenedEvent (`+0x28`); `NetworkSessionAPI.ESOpenedHandler` (`0x17b6a10..0x17b6a88`) invokes ConnectedEvent (`+0x20`). `NetworkController.NetSessionConnectedHandler` (`0x17bfef8..0x17bfffc`) dispatches Connected across network components. Thus the trade subscriptions are installed on source opening, before the asynchronous session-start initialization finishes.

`ESStartHandler` (`0x17b5fec`) starts GetDetails(`0x7ff`) at `0x17b61a0`. Its success callbacks then run MigrateSPAvatars (`0x17b6d38`), friend RefreshData (`0x17b6e30`) and GetOwnedDimensions (`0x17b6f28`). Final callback `0x17b7020..0x17b70f4` passes connect result `NONE=11` at `0x17b7070..0x17b7074` only for successful dimensions retrieval. The sign-in success callback `MPUserSignInState.<UISignInBtnHandler>b__16_0` (`0x1609f30`) then calls JoinRoom. The established [shared-stream native contract](shared-battle-stream-contract.md) records that successful connection/join path and the game's disabled same-source automatic retry.

An early trade frame can therefore find a bound handler while `NetworkPlayerAPI.playerData` is still null. `NetworkPlayerAPI.Disconnected` (`0x17a1d48..0x17a2064`) explicitly clears playerData at `0x17a2048`; its constructor does not initialize it, and Connected (`0x17a16cc..0x17a1994`) subscribes events and requests slot configs without populating that field. The four trade handlers require nonnull playerData before their GetTradeData call, and take the native null-exception path otherwise. Marking a revision seen after writing such a frame can lose the effective invalidation for that connection.

A suitable replacement delivery gate for this pinned native sign-in path captures the authenticated session's room-membership generation when opening SSE, then withholds the first trade invalidation until a later authenticated nonempty room membership has a different generation. The successful join advances that generation after the initial details chain. A room ID retained from an earlier session is insufficient. Once ready, keep the connection ready through room moves/leaves so subsequent account invalidations remain independent of room state. This is an internal server readiness policy using an existing native request, not a new wire event or an arbitrary delay. Synthetic clients that never join will not cross this gate; direct poll-unit tests alone do not establish native startup delivery.

## Offer cancellation and the cached lock

`CancelTradeOffer` success callback (`0x1796134`) removes its own offer, removes the corresponding saved `trade_offer_made_ids` entry, saves multiplayer data (`0x80`) and checks offer updates. Its bounded body has no GetDetails call, no GetTradeData call and no clear of owned `isTradeLocked` (`+0x6e`). `GetTradeData` success callback (`0x1794d80`) replaces trade caches and checks notifications but does not reconcile that owned lock. This is why a correct server-side release can remain invisible to a loaded selector after voluntary offer cancellation.

An existing trade event delivered to the offering client's connected session **can start the missing authoritative details refresh**. `MPOpponentMortyData.SetFromDict` (`0x158cb1c`) applies `is_trading_locked` to `+0x6e` at `0x158d4b4`. Therefore a successful fresh details response containing false can clear a stale local true, provided no remaining reservation or legacy flag requires true. Delivery alone is not proof that the response completed, that the selector rebuilt or that the Morty became eligible.

There is a material actor-echo race. If the event's GetTradeData response observes the removed offer before the cancellation callback removes that ID from saved history, `CheckUpdateTradeOffers` (`0x1791a38`) can classify the voluntarily withdrawn offer as rejected (or completed when the completed list is null). HTTP response delivery and SSE delivery are asynchronous; commit-before-publication alone does not order those client callbacks. Choosing `trade:offer-submit` instead of `trade:offer-rejected` does not avoid the race, because all four handlers run identical refreshes and notification classification uses fetched data.

Consequently this research does **not** establish guaranteed immediate self-unlock through a cancellation event. The focused counterpart policy above adds no cancellation publication and leaves that self-cancellation refresh gap explicit. An actor notification would need a demonstrated ordering/deduplication strategy and native validation, including absence of a false rejection popup. Arbitrary delays or guessed original-server cancellation semantics do not supply that proof.

For counterpart removals, an offer-rejected invalidation can intentionally produce the ordinary rejection notification when the removed ID remains in the offerer's history and the fetched native `competed_trades` list is nonnull with no matching completion. The successful native spelling is documented in [decision navigation](native-trade-decision-navigation.md). The payload itself neither chooses nor acknowledges that notification.

## Synthetic native consumer smoke

A subsequent [replacement implementation and validation](trade-refresh-implementation.md) includes one bounded Android consumer smoke on the retained primary profile. After ordinary login/details initialization and a successful room join, the replacement publisher committed one explicitly synthetic `trade:offer-submit` invalidation for that account. No kiosk navigation or captured trade mutation request contributed to this smoke. The native stream received exactly one such event with `{}` and then submitted both expected refresh requests with successful responses.

The strict read-only sanitizer binds the private identity anchor through the captured login secret, rotated session token, trading cookie, session:start payload, current authenticated snapshot and matching native client fingerprint. The startup details request contains eleven include fields; the post-event request contains exactly `morties`, `attacks`, `decks`, `mortydex`, establishing the recovered `0x78` call separately from startup.

| Same-PCAP observation | Seconds relative to first captured packet |
| --- | ---: |
| Login response complete | 22.839838 |
| session:start frame complete | 22.979388 |
| Room join response complete | 23.405084 |
| trade:offer-submit frame complete | 66.236825 |
| GetTradeData request complete | 66.270208 |
| GetTradeData response complete | 66.325347 |
| GetDetails(`0x78`) request complete | 66.352149 |
| GetDetails response complete | 66.381426 |

Android guest PCAP timestamps and Docker/WSL publication UTC use independent clocks. The initial attempt to compare those clocks failed and its diagnostic was retained; no offset was invented. The successful receipt proves only the order within the same PCAP, explicitly sets publication-clock ordering and publication-to-SSE latency claims false, and omits publication UTC from that timeline. The private publication receipt supplies declared synthetic provenance and exact target/event/revision checks.

Ignored smoke artifacts are under `.research/emulator/trade-refresh-events-20261107/`: `primary-smoke-capture/trade-primary-http.pcap`, `guard.json`, `synthetic-publication.json`, `native-consumer-smoke-sanitized.json` and `cross-clock-order-failure.txt`. PCAP SHA-256 is `87794fddb26bcb591fc64b6a8f8f14b0558a445bca121ae6c1334fdf20cd65ec`. The sanitized receipt records all four input hashes and exposes no session, secret, token, player ID or payload records. Reproduction uses `tools/research/sanitize_trade_refresh_smoke.py`; its six synthetic test methods cover identity, include masks, startup/order boundaries, duplicate events, raw chunk offsets, exact TCP ACK pairing, contradictory overlaps and the independent-clock disclosure.

This establishes a synthetic invalidation's native consumer behavior on Android 2.41.0. It does not establish publication from an actual offer/decision mutation, original-service audiences or timing, native rejection/acceptance event coverage, guaranteed delivery, inventory unlock after cancellation or selector eligibility.

## Evidence and reproduction

ELF SHA-256: `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`. Metadata version 31, SHA-256 `b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10`. Dumper script SHA-256: `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb`. RVAs above are ELF-relative; Ghidra adds image base `0x100000`. Only instructions within the recorded metadata method bounds establish behavior.

Fresh ignored receipt: `.research/trade-refresh-events-20261107T0120/`. It contains REA version, artifact inspection, Ghidra JSON/log, 14 bounded methods in `methods.json`/`arm64.txt` (13 selected Ghidra methods and the exporter's supplementary HTTP success accessor), plus `bindings.json`. Key method-body SHA-256 values:

| Method | Body SHA-256 |
| --- | --- |
| Connected | `e68333e40542b9c99c2ef5ea042609fa686abc69c39ad6691c9b8c04d00bfaf0` |
| TradRequestSummitedHandler | `7464191632f57e3904d4ef10153c8b5305321f5ca2bc3c1f34b4f03e1dd3d393` |
| TradeOfferdSummitHandler | `fe7302d73820241ee6e4d3a4f84f4cd05587db9d1bf88919d2f48fd66e1a88af` |
| TradOfferAcceptdHandler | `59ed577f09a0355eb1a0df572bd4998f044610a967742417a9eaf6dd21fb0821` |
| TradOfferRejectHandler | `387e69eb997ae7f7aedb8fbb3e1450c6e5975f6ad019445fbc60786362b1423d` |
| CallHandlers | `581e9bc6a279224f7f9484400253745c739c1e58a8791f1143c9c7253eff86bc` |
| OnMessageHandler | `3c0335971e383537e54c02087fbb24281b5423717b0837fd86057c5c66ae0753` |

Supplementary startup review receipt: `.research/trade-refresh-startup-20261107T0140/`, with six targeted Ghidra methods and 14 bounded methods after explicitly adding the source-open/session-open, player Connected/Disconnected/constructor and GetTradeConfig methods. `ESOpenedHandler` body SHA-256 is `e88b3910e4f8995684d2e688b9259878f2e5b4772953028bf37a98f24d0cc67a`; player Disconnected is `880671e2e63563f3cb1b29922056071764c809b1cedfdc06e22c00ea1f8bbf28`; final initialization callback is `4229a0c324288808ec1abd2eafedeae37af608dff3f283c6a45f595bcbb9ec8f`. The existing shared-battle-stream receipt supplies the sign-in success/JoinRoom branch. This is bounded control-flow evidence, not a fresh live startup validation.

Reproduce from the default WSL Bash shell, entered with `wsl.exe -- bash` from PowerShell, in this repository. Choose a fresh output directory:

```bash
set -euo pipefail
OUT=".research/trade-refresh-review-$(date -u +%Y%m%dT%H%M%SZ)"
mkdir "$OUT"
bash tools/research/rea.sh --version > "$OUT/rea-version.txt"
test "$(tr -d '\r\n' < "$OUT/rea-version.txt")" = 6.8.0
bash tools/research/rea.sh inspect-artifact \
  .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so \
  --format json > "$OUT/artifact.json"
FILTER='NetworkFriendAPI.*(Connected|Disconnected|TradRequestSummitedHandler|TradeOfferdSummitHandler|TradOfferAcceptdHandler|TradOfferRejectHandler)|NetworkSessionAPI\$\$(On|Off)|NetworkEventSource\$\$(On|Off|CallHandlers|OnMessageHandler)|NetworkEventSourceResponse.*'
bash tools/research/ghidra-targeted.sh "$(realpath "$OUT")/ghidra.json" "$FILTER" \
  > "$OUT/ghidra.log" 2>&1
/mnt/c/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe \
  -X utf8 -B tools/research/trade-cancellation-bounded.py \
  "$(wslpath -w "$(realpath "$OUT")")"
```

The existing wrapper imports with `-noanalysis`, decompiles only selected methods and retains a temporary project. It performs no full indexing. Prior bounded lock/cancellation evidence remains in the receipts linked from the lock-lifecycle contract; this pass did not rerun or mutate native flows. No original-service packet capture was available to settle original payload contents, audiences, cancellation publication or timing.

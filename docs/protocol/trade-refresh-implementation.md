# Counterpart trade refresh delivery

Trade offer creation and decisions previously changed authoritative state without
notifying affected counterparts. The original Android client already has four
[refresh-only handlers](trade-refresh-event-contract.md). The replacement now
uses them for committed new offers, acceptance and rejection. HTTP bodies,
paths and gameplay economics are unchanged.

## Publication and privacy

| Successful mutation | Recipient | Event |
| --- | --- | --- |
| Offer creation | Request owner | `trade:offer-submit` |
| Rejection | Removed offer owner | `trade:offer-rejected` |
| Acceptance | Accepted offer owner | `trade:offer-accepted` |
| Acceptance removes sibling offers | Removed sibling owners | `trade:offer-rejected` |
| Own offer withdrawal | Current parent owner, if any | `trade:offer-submit` |
| Parent cancellation | Removed offer owners | `trade:offer-rejected` |

The actor is excluded. Each account receives one revision per mutation; acceptance
wins if the selected offerer also owns removed siblings. The native requester
callback already refreshes itself. Recipient selection is replacement policy,
not recovered original-service audiences. The
[cancellation follow-up](trade-cancellation-notifications.md) adds counterpart
withdrawal invalidations. Its [three-capture native proof](trade-cancellation-refresh-results.json)
verifies both cancellation paths and counterpart trade/details refreshes on the
Android 2.41.0 pair in one world. The peer cold login separates two capture/session
phases; immediate actor cached unlock remains open. No friend broadcast
is added.

`lib/trade_refresh.php` publishes at the end of the existing mutation transaction.
A publisher failure rolls back gameplay and every notification. Failed requests
and retries do not publish. Recipient rows are locked in sorted order, without
adding recipient user locks after parent locks.

Migration `015-trade-refresh-notifications.sql` adds one row per affected account.
Its `VARBINARY(255)` key distinguishes case and trailing-space aliases. Unsigned
revisions remain decimal strings through PHP; overflow fails the transaction.
This is replacement invalidation storage, not an original event history.

## Streaming and startup

SSE polls the exact authenticated account's latest committed revision separately
from room events and checks the live session before/after reading. Wire data is
`{}`; no player, offer, token or revision ID is sent. All four handlers reload
GetTradeData and owned details (`0x78`). They consume no payload fields and
do not classify trade outcomes from the event name.

Initial replay waits for a different authenticated room-membership generation
with a nonempty room. Native OnOpen binds trade handlers before `playerData` is
initialized; a fresh successful join follows asynchronous initialization and
provides the readiness barrier. A retained old room is insufficient. Once ready,
delivery continues across room changes and leaves, independent of room cursors,
snapshot boundaries and `Last-Event-ID`.

A fresh ready stream replays the latest revision. Several revisions may coalesce
because each handler reloads the same authoritative state. Every intermediate
event, ordered HTTP completion and acknowledged receipt are not guaranteed.
Synthetic clients reconnecting without a fresh join remain gated. The researched
Android reconnect performs fresh sign-in/join; other behavior requires validation.

## Verification and reproduction

Run exact modules serially on the isolated research database, with game apps
stopped. Broad protocol discovery includes an older global-reseeding suite.

```powershell
$researchPython = 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$modules = @('test_trade_refresh_events.py', 'test_trade_response_authorization.py',
  'test_trade_listing_protection.py', 'test_trade_party_transitions.py',
  'test_trade_party_guard.py', 'test_trade_offer_metadata.py',
  'test_trade_completed_projection.py', 'test_sse_event_privacy.py')
foreach ($module in $modules) {
  & $researchPython -X utf8 -m unittest discover -s tests/protocol -p $module -v
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
}
& $researchPython -X utf8 tools/research/validate.py
```

The 15 new tests cover HTTP mutation recipients, sibling deduplication, actor
exclusion, retries, overflow and publisher-failure rollback, including failure
on the second recipient. Poll tests cover exact identity/session isolation,
coalescing, read-only behavior, large revisions, concurrent writers and
invisibility before commit. A real HTTP SSE test uses SQL-simulated membership
changes and ordered markers to verify startup gating, ready delivery outside a
room and reconnect replay. That is backend wire evidence, not native UI evidence.

All 116 targeted tests passed: 15 new publication/stream cases, 95 adjacent
regressions (22 response authorization, 28 listing, 26 party transitions, 6 party
guard, 4 metadata, 4 completion projection, 5 event privacy), and 6 smoke-parser
tests. PHP lint and research evidence/source-hash validation also passed.

## Native consumer smoke

The retained Android 2.41.0 diagnostic `trade-primary` performed its ordinary
startup and room join, with the existing offline-SDK profile and unchanged APK
hashes. One explicitly synthetic `trade:offer-submit` invalidation was then
published to PMTrade01 through the helper, without creating or deciding a trade.
The [sanitized receipt](trade-refresh-native-smoke-results.json) verifies one
captured SSE frame followed by native GetTradeData and exact four-field
GetDetails(`0x78`) requests, both successful, under the captured login/session.
The UI stayed at the world-introduction screen; no kiosk reload competed with
the event. This proves the native consumer, not real-mutation publication in a
two-client game or original-service behavior.

The Android packet clock and Docker/WSL publication clock differed. An initial
checker rejected their apparent cross-clock ordering; that diagnostic remains
private. The corrected proof validates all ordering within the same PCAP and
uses the publication receipt only as synthetic provenance. It explicitly does
not establish publication-to-SSE latency or invent a clock offset.

Reproduce from the retained private inputs into a fresh ignored output:

```powershell
$refreshRoot = '.research/emulator/trade-refresh-events-20261107'
& $researchPython -X utf8 tools/research/sanitize_trade_refresh_smoke.py `
  --pcap "$refreshRoot/primary-smoke-capture/trade-primary-http.pcap" `
  --anchor .research/emulator/native-trade-decisions-20261106/pair-fixture-v2/observe-verified-accept-decision-complete.json `
  --auth-snapshot "$refreshRoot/guard.json" `
  --publication "$refreshRoot/synthetic-publication.json" `
  --output "$refreshRoot/reproduced-native-smoke.json"
```

Raw captures, credentials and receipts stay ignored. Startup/save and original
research-account guards passed, as did the accepted trading pair's exact
ownership, party, stats, attacks, items, balances and raw-flag comparison. Only
trade-primary and the optional offline-SDK sidecar were stopped; userdata and
the synthetic revision were retained. No trade setup/reset or save restoration
was performed.

Apply migration 015 before runtime use. Its DDL was applied twice to the isolated
research database and the byte-exact key/unsigned revision verified. Missing or
malformed storage fails closed: publication rolls back and SSE logs/closes without
printing PHP errors. The original SQL dump is unchanged. Regression fixtures
clean up their own notification rows. No production deployment is included.

## Remaining boundaries

The subsequent [live two-client cycle](live-trade-refresh.md) and
[sanitized receipt](live-trade-refresh-results.json) now verify real native
parent creation, a rejected first offer and an accepted second offer. Each
counterpart frame (two `trade:offer-submit`, one `trade:offer-rejected`, one
`trade:offer-accepted`) is followed by successful native GetTradeData and exact
GetDetails(`0x78`) responses. The rejected spare is eligible in the live selector
without restart. Both clients remain in the same world sessions throughout
approximately 679 seconds of continuous capture, bounded at 900 seconds and
flushed with graceful SIGINT. No scripted gameplay mutation substitutes for
native input. Independent offline-SDK sidecars preserve concurrent startup.

The final guard verifies exactly two spare instances swapping owners, the old
completion retained and one added (two total), no parent/offers, and notification
revisions peer 2 / primary 3. This round changes no backend or migration. Its
26 targeted pure tests comprise 18 fixture/proof cases and eight preparation
cases. The earlier synthetic smoke above remains its own historical evidence;
the live cycle supplies the later real-mutation proof. Two-account delivery and
actor exclusion are verified; a native third account, cross-room delivery and
iOS were not exercised.

Immediate self-cancellation unlock remains open: its callback removes saved offer
history without refreshing details. A self notification can race that removal and
incorrectly announce rejection. No arbitrary delay or invented event was added.
The [fresh cancellation callback/save audit](trade-cancellation-refresh-contract.md)
finds no ordering-safe PHP actor acknowledgement in the inspected paths.
Counterpart cancellation publication now has the backend follow-up above.
Request-creation fanout, broader serializers, legacy
stored locks, iOS and original delivery/economic policy remain separate. Root
README attribution and playable baseline claims are preserved.

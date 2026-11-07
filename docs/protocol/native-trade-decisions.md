# Android trade decisions and completion-list compatibility

The dedicated Android pair now exercises requester-side rejection and acceptance
through the native incoming-offer UI. That run exposed and reproduced a notification defect:
the offerer was told that a rejected offer had been accepted. A narrowly scoped
GetTrades response alias fixes the notification without changing stored trades,
economics or client saves. See [native navigation and notification logic](native-trade-decision-navigation.md)
and the existing [authorization](trade-response-implementation.md),
[listing](trade-listing-protection.md) and [party-transition](trade-party-transitions.md)
repairs.

## Native decision and ownership results

The requester rejected the first offer through the incoming-offer menu. Its
captured three-field body used `request_accepted:false`; the response was
`[null,null]`. Only that offer disappeared. The same parent, both collections,
active parties, balances and free-trade expiry remained unchanged.

After the explicitly disclosed intermediate attempt below, the offerer created
a replacement offer in a fresh packet window. The requester reloaded that offer,
opened its two-Morty management screen and selected **Accept**. The captured
body used `request_accepted:true`, again returning `[null,null]`. The native
popup reported **Trade Successful**. Read-only snapshots verified exactly two
spare physical Morty rows exchanging owners, one completion inserted, and the
parent and attached offer removed. Stats, attacks, active parties, saved decks,
items, currencies, friendship and raw lock flags were preserved.

The requester's decision callback refreshed its player details. The offerer
then performed a normal cold login and player-details refresh, and its next
kiosk reload correctly reported **was accepted**. This checks refreshed owned
inventory on each side; it does not establish live trade-event delivery or
availability in every daycare selector. The yellow notification **Accept** was
acknowledged separately after recording the result.

The [sanitized selected-cycle receipt](native-trade-decision-results.json)
validates 12 captures, 33 HTTP exchanges and all 17 append-only observations.
Its selected-decision/refresh flag is true; its uninterrupted full-cycle flag is
false because intermediate attempts remain disclosed. Both post-accept native
details responses match their current owned-instance IDs, unchanged active
party/resources, and boolean false locks. The final offerer GetTrades contains
one completion in each equal alias. The separate
[before/after alias receipt](native-trade-completion-alias-results.json) records
the missing native key before the fix and equal empty arrays afterward.

Unmodified synthetic-account screenshots show the
[incorrect rejection notification](images/native-trade-rejection-before.png),
[corrected same-history notification](images/native-trade-rejection-after.png),
[requester success](images/native-trade-accepted.png), and
[offerer completion notification](images/native-trade-completion-notification.png).
Their visible text supports the UI claims; packet proofs alone do not prove
popup wording.

Original startup/save and research-account guards passed after these operations.
Installed diagnostic APK hashes were rechecked for both trading AVDs; app data
was retained. Their old owner-bound pre-swap guard is superseded by the exact
accepted-pair guard, not reset to a fabricated original ownership state.

## Confirmed response-field repair

Android 2.41.0 declares `TradeDataResponse.competed_trades`, including that
spelling. PHP returned only `completed_trades`. The bounded native trace shows
that a missing/null completed cache classifies a disappeared saved offer as
completed, whereas an empty array classifies it as rejected. JsonFx has member
rename machinery, so metadata spelling alone was previously insufficient to
claim a defect. The controlled native before/after observation resolves the
practical wire behavior here.

After the requester sent a captured `request_accepted:false`, database snapshots
showed only that offer removed, the same parent retained, no completion, and
unchanged protected player data. The offerer's next captured GetTrades returned
`completed_trades:[]` with no native alias. Its popup nevertheless said the
offer **was accepted**.

The popup was left unacknowledged. Small native data files were copied read-only
with stable hashes before/after display; no file was restored or edited. After
adding `competed_trades` with the same array as the retained `completed_trades`,
a normal force-stop/relaunch and captured reload of the same pending history
displayed **was rejected**. The native alias was an empty array and equalled the
existing array. This is runtime behavior on the diagnostic client, not a claim
that field-specific runtime attributes were independently dumped.

Both response keys are now emitted for empty and populated results. Existing
completion row fields, booleans, ordering and visibility SQL are unchanged.
The popup's yellow **Accept** button acknowledges the notification and removes
its saved history entry; it does not submit an acceptance decision. The actual
trade decision is the request owner's separate Accept/Reject menu.

## Accounts, transport and evidence boundary

Only retained `trade-primary`/5564 and `trade-peer`/5566 AVDs were used, with
synthetic PMTrade01 and PMTrade02. Each had one native registration starter in
its unchanged active deck and one previously prepared non-party copy. These
fixture values do not recover multiplayer generation formulas. The requester
was PMTrade02 and offerer PMTrade01. Their existing accepted friendship was
preserved; no social setup is newly claimed as native.

The Android 2.41.0 ARM32 diagnostic APKs retain the prior transport/startup
profile. Preparation verifies their installed/source hashes and never reinstalls
or clears app data. The original ARM64 ELF used for REA 6.8.0/Ghidra analysis is
identified in the navigation contract. No new trade-method patch or runtime
instrumentation was added. iOS is not covered.

Each cold launch uses a fresh lifetime of the optional offline-SDK fixture,
with external traffic denied and device 8087/8089 reversed to host 8091. Only
one game app runs at a time; the normal backend and retained other AVDs remain
untouched. This conditional startup path is not stock online-SDK compatibility
or consent. The raw APK identities, cookies, tokens, account/instance IDs,
packets, screenshots and native data checkpoints stay under ignored
`.research/emulator/native-trade-decisions-20261106/`.

The fixture observer uses read-only consistent snapshots and fixed account,
starter, spare and physical-row anchors. Only the two named spare ownership
fields may swap at acceptance. Stats, attacks, decks, items, friendship and
protected user fields remain fixed; native session/room/presence dynamics are
explicitly bounded and reported. Original account/save guards are separate.

The first attempted baseline used a receipt predating accepted friendship and
failed. The preserved immutable post-friendship receipt passed without relaxing
the friendship comparison. A later offer was submitted outside its capture
window; its snapshot and missing-wire limitation are preserved, and that offer
was withdrawn through native rejection before repeating the final setup.

A missed UI input also left the offer unchanged when a rejected-stage snapshot
was requested. Its failed receipt remains immutable. Offline resumption is
allowed only when that snapshot independently passes the previous successful
offer-stage comparison, with no protected change. The resumption links both
hashes/sequences, and later observations retain the failed raw hash in their
chain. Unexpected resource/ownership changes still halt. This records a missed
research transition, not a server decision failure or permission to ignore errors.

Selected-cycle packet proofs do not claim continuous capture of every
intermediate attempt. TCP streams remain per-file; reply pairing requires an
exact ACK, complete selected HTTP messages, native headers and matching login
cookies. Cross-file order uses actual packet timestamps. Unrelated chunked SSE
responses are excluded by ACK before body parsing; selected unsupported
responses and unknown trading mutations fail closed.

## Reproduction and verification

Use the default WSL and the exact bounded trace command in the
[navigation evidence](native-trade-decision-navigation.md#evidence-and-reproduction).
Run database suites serially with both game apps stopped; use exact module
discovery to avoid unrelated account-seeding suites:

```powershell
$researchPython = 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_completed_projection.py -v
& $researchPython -X utf8 -m unittest discover -s tools/research -p test_native_trade_decision_fixture.py -v
& $researchPython -X utf8 -m unittest discover -s tools/research -p test_native_trade_decisions_sanitizer.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_offer_metadata.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_cooldown.py -v
& $researchPython -X utf8 tools/research/validate.py
```

The four additive completed-projection HTTP tests initially failed with seven
assertions including subtests, then passed after the alias. They cover empty
arrays, complete records for both participants, unrelated callers, booleans and
read-only repeated projection. Native captures validate the consumer separately.
Generated IDs and canned stats in pure/integration fixtures are synthetic.
The final targeted run passed 37 tests: 4 projection, 4 metadata, 3 cooldown,
12 observer and 14 packet-proof tests. PHP lint and research evidence validation
also passed. The PHP file's existing CRLF bytes were preserved; whitespace
review uses `git -c core.whitespace=blank-at-eol,blank-at-eof,space-before-tab,cr-at-eol diff --check`.

With the retained private captures, reproduce the selected receipt into a fresh
ignored output. These inputs include the original baseline listings without the
alias as well as the corrected final listing; their differing presence is
intentional. This command reads evidence only:

```powershell
$decisionRoot = '.research/emulator/native-trade-decisions-20261106'
$captureNames = @(
  'peer-parent-startup-capture', 'peer-parent-create-capture',
  'primary-first-offer-startup-capture', 'primary-first-offer-create-capture',
  'peer-reject-startup-capture', 'peer-reject-decision-capture',
  'primary-verified-startup-capture', 'primary-verified-offer-create-capture',
  'peer-verified-accept-startup-capture', 'peer-verified-accept-reload-capture',
  'peer-verified-accept-decision-capture', 'primary-postaccept-startup-capture'
)
$proofArgs = @('--fixture-dir', "$decisionRoot/pair-fixture-v2",
  '--accept-prefix', 'verified-accept', '--output', "$decisionRoot/reproduced-proof.json")
foreach ($captureName in $captureNames) {
  $captureRole = if ($captureName.StartsWith('peer-')) { 'trade-peer' } else { 'trade-primary' }
  $proofArgs += @('--pcap', "$decisionRoot/$captureName/$captureRole-http.pcap")
}
& $researchPython -X utf8 tools/research/sanitize_native_trade_decisions.py @proofArgs
```

`native_trade_decision_ui.py` accepts only the two dedicated trading roles,
bounded on-screen input and fresh private PNG outputs. `capture_shared_startup.py`
uses fresh 30..180-second captures. Establish the UI state first, let any prior
same-device capture finish, then start a short capture immediately before a
mutation. A screenshot filename or database change alone cannot replace missing
request packets.

The current pair is a retained research fixture, not an account reset recipe.
Do not replay old prepare/reset scripts or restore its native checkpoints.
The read-only observer and sanitizer require their immutable private anchors;
another developer must prepare an independently guarded isolated pair using
the preceding fixture documentation. Ordinary client refresh, trade event
delivery/reconnection, original economics and other battle modes remain separate.
No deployment, schema migration or main/master merge is included, and root
README claims/attribution are preserved.

# Native offers, cancellation and display metadata

Two disposable Android 2.41.0 accounts now exercise a friend's request through
native offer creation, reopening and cancellation. The repaired cycle also
reloads GetTrades while the offer exists, retaining the correct display metadata
and Cancel button. The parent request, both collections, parties, items, coupons,
expiry values and raw locks remain unchanged during each offer cycle. No transfer
or approval was exercised. The [strict packet proof](native-trade-offer-results.json)
records both the original and repaired cycles.

![Native offer cancellation button](images/native-offer-cancel-button.png)

## Confirmed metadata repair

The [REA 6.8.0 native trace](native-trade-offer-contract.md) distinguishes owned
instance IDs used for lookup/cancellation from species IDs used for display.
`TradePopups.TradeUpdatePopupHandler` passes the two enrichment Morty IDs to
`MPMortyDefs.Name`, then formats the requester name. Existing creation returned
the request owner's player ID as its name and the request's owned-instance ID as
a species. GetTrades dropped the enrichment entirely.

| Field | Creation before repair | Repaired creation and reload |
| --- | --- | --- |
| `request_user_name` | Request owner's player ID | Request owner's username |
| `offering_morty_id` | Offered species | Offered species, retained on reload |
| `request_morty_id` | Request's owned-instance ID | Species of the Morty being traded by the request owner |

`request_morty_id` identifies the actual parent Morty's species; an `any` desired
request is not a substitute. The new read-only metadata helper resolves the
parent, requester and both owner-scoped species. Creation resolves it inside its
existing transaction; listing decorates existing offer rows. Scalar aggregates
avoid multiplying offers through nonunique legacy keys. Missing/ambiguous parent
or source data produces absent metadata keys, rather than NULL or fabricated
player/instance-ID labels. Valid records receive all three string fields.

Offer identity fields, paths, authentication and mutation behavior remain as
before. The helper does not decide authorization or eligibility. Existing list
visibility and transfer policy require separate checks. No schema migration,
refund, currency, stat, capture or combat formula change is included. Popup
display semantics are statically established and wire values are observed;
acceptance/completion popup rendering was not exercised.

## Observed native flow

PMTrade02 registered through a fresh `trade-peer`/5566 installation. Its own
native-registration starter/attack were copied into one synthetic non-party
spare using the allowlisted fixture. PMTrade01/5564 reused its prepared spare
from the preceding request-cancellation work. Scripted friend request/approval
established their accepted relationship; this run does not claim native social
setup. PMTrade02 then created the parent `any`/`Normal` free request in the UI.

PMTrade01 entered Swap Stop → Browse → selected that friend request → selected
its spare → Confirm. The offer appeared with a check mark. Reopening the request
exposed Cancel; pressing it removed only the offer and its check mark, leaving
the parent request. Both mutations returned HTTP 200; cancellation sent exactly
`{trade_offer_id}` with the native scoped session cookie. Creation sent the four
fields recovered in the native contract. Owned details after creation supplied
Boolean trading lock `true` for the selected spare.

The repaired complete cycle exited to the world and reentered the kiosk while
the offer existed. Two native GetTrades responses retained the same offer IDs
and all three corrected metadata strings. The client rendered the offer again,
exposed Cancel and successfully cancelled it. Per-cycle database offer counts
were `0 → 1 → 1 → 0`; parent counts stayed one. Both cycles used the same parent
and spare. Packet ordering and exact TCP acknowledgement pairing are verified;
scripted requests are not substituted for these native operations.

One intermediate repaired capture ended before cancellation. It is retained and
identified as creation/reload-only evidence. The final short confirmation capture
contains the complete repaired cycle; the strict checker rejected the incomplete
input before that new capture. No truncated streams were stitched into a proof.

## Inventory refresh gap remains

Cancellation succeeded, but the immediate subsequent selector was empty despite
the durable offer being gone. Neither complete offer-cycle capture contains an
owned-details request after cancellation. This agrees with the bounded callback:
it removes the offer/saved offer ID but does not clear the owned lock or directly
request inventory details. Ordinary cold login restored the sole spare without
clearing saves, consent, caches or installation data.

![Empty selector after cancellation](images/native-offer-stale-selector.png)

![Spare visible after ordinary cold login](images/native-offer-reconnected-selector.png)

The screenshots are manual UI evidence, separate from the packet checker. This
metadata repair does **not** repair immediate unlock visibility. Trace ordinary
inventory/SSE refresh behavior before choosing a remedy; do not invent an SSE
event or silently patch the APK. Broader serializers and unknown legacy true
flags remain outside this change.

## Reproduce with isolated fixtures

The existing diagnostic ARM32 APKs retain their earlier local transport and
multiplayer-unlock probes; installed hashes were verified unchanged for both
devices. Original 5556/5558 and retained startup 5560/5562 userdata were untouched.
Use the [startup fixture](onetrust-startup-recovery.md) sequentially, with a fresh
SDK-service lifetime for each cold client startup. Do not share the first-probe
fixture between simultaneous initializations or reset client data.

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 tools/research/startup_capture_device.py launch --role trade-peer
# Wait for Android boot before first installation; native registration uses PMTrade02.
& $researchPython -X utf8 tools/research/startup_capture_device.py install --role trade-peer
# Stop only this dedicated app before preparing its extra instance.
& $researchPython -X utf8 tools/research/native_trade_fixture.py snapshot --account PMTrade02 --output .research/trade-offer-next/peer-fixture
& $researchPython -X utf8 tools/research/native_trade_fixture.py prepare --account PMTrade02 --output .research/trade-offer-next/peer-fixture
& $researchPython -X utf8 tools/research/native_trade_offer_fixture.py snapshot --output .research/trade-offer-next/pair-fixture
```

The account extension defaults to PMTrade01 for existing callers, permits only
PMTrade01/PMTrade02 and rejects mismatched manifests before database operations.
Preparation is one-shot and append-only. The paired helper is read-only: one
consistent transaction captures both uniquely resolved accounts, four instances,
attacks, decks, items, globally related requests/offers, completed trades,
friendship and relevant events. Observations anchor identities to its immutable
baseline. Full rows and credentials remain ignored and private.

For fresh setup, use `/session/friend/request` with the primary session and peer
player ID, then `/session/friend/response` with the peer session, primary player ID
and `approve: true`. Use only these disposable identities. Reload the peer to
fetch its spare, create the parent natively, then stop that app before starting
the primary with a fresh SDK fixture. Preserve existing accounts/receipts rather
than deleting them to replay registration or preparation.

Start capture **before** pressing Confirm. Finish creation, native kiosk reload
and cancellation within the bounded recording; use a fresh recording if needed.
`observe --output <pair-fixture> --label <label>` records `before-offer-create`,
`offer-created`, `before-offer-cancel` and `offer-cancelled`. A repaired cycle uses
a separate prefix such as `confirmation-`; older receipts are never overwritten.

```powershell
& $researchPython -X utf8 tools/research/capture_shared_startup.py --role trade-primary --duration 180 --screens 5 --output .research/trade-offer-next/offer-cycle-capture
& $researchPython -X utf8 tools/research/sanitize_native_trade_offers.py --baseline-pcap .research/emulator/native-trade-offers-20261106/primary-offer-cycle-capture/trade-primary-http.pcap --fixed-pcap .research/emulator/native-trade-offers-20261106/primary-confirmation-offer-cycle-capture/trade-primary-http.pcap --fixture-dir .research/emulator/native-trade-offers-20261106/pair-fixture --fixed-label-prefix confirmation- --output .research/trade-offer-proof-next.json
wsl.exe -- bash tools/research/ghidra-trade-offers.sh
```

The proof requires native headers, exact request shapes, authenticated identity,
Cookie/session binding, returned IDs matching snapshots, parent preservation,
typed locks and corrected metadata in a reload between creation and cancellation.
It emits only allowlisted facts and whole-input hashes, with no IDs, credentials,
header values or raw bodies. The native completed-list member spelling remains
an [unresolved JsonFx mapping question](native-trade-offer-contract.md); no wire
key was renamed based on the reconstructed field name alone.

## Verification and retirement

All 44 targeted backend tests passed serially: metadata 4, cancellation 19,
durable references 12, cooldown 3 and trade-party guards 6. The first two metadata
tests failed/errored against the old responses. New cases cover different species
on each side, read-only reloads for both friends, ambiguous names without offer
fanout and orphan cancellation. One older cancellation test's two incorrect
enrichment expectations were corrected using recovered display consumers;
authentication and cancellation expectations were retained.

All 16 pure cases passed: account allowlist 5, paired fixture 6 and packet proof
5, including malformed identity/Cookie, lock types, ambiguous ACKs, ordering,
metadata and snapshot tampering. PHP handler/helper and embedded-fixture lint,
Python/shell syntax, source fingerprints, screenshot/privacy and incremental
whitespace checks passed. Existing PHP CRLF formatting is allowed by the check.
Independent metadata review found no blocking issue.

After all native captures, scripted exact-owner-cookie cancellation retired the
temporary peer parent. It is explicitly **not** native cleanup evidence. Final
paired checks found zero active requests/offers and zero completed transfers;
prepared collections, parties, resources, raw flags, both expiries and accepted
friendship were preserved. Both original-account guards and retained startup
save/history guard passed. Only verified trading AVDs 5564/5566 and the optional
SDK sidecar were stopped, retaining userdata and evidence. No merge or production
deployment is included.

Next: acceptance authorization/request-offer binding and server-side eligibility,
then native inventory refresh after offer cancellation, list privacy and
JsonFx completed-list mapping. Original economics and real transfer behavior
remain separate. This branch starts from main `9ff1a11`, explicitly fast-forwarding
PR #53 at `8463f15`; repair `0660798`, research tools `e752c2f`. Root README
completed-feature claims and attribution are preserved.

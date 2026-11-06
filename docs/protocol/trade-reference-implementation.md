# Durable trade references and collection safety

Successful native request and offer creation set an owned Morty's trading lock
and immediately refresh player details. PHP returned only the stored flag,
which these creation routes do not update. That could overwrite the local lock
with false. Absorption also checked only stored flags, allowing a pending-trade
Morty to be consumed or modified. The [native contract](trade-lock-lifecycle-contract.md)
establishes those callbacks and the separate manual/trading lock fields.

Player details now returns the existing legacy flag conversion OR any persisted
request/offer reference to that instance ID. The flag remains a JSON boolean;
no response fields or stored flags are added or rewritten. SQL computes a
separate EXISTS result; PHP combines it with the legacy flag, avoiding MySQL's
numeric conversion of strings such as `true`. The read uses the same statement
snapshot as the Morty/attack projection.

References match globally using database collation, including orphan offers and
stale declared owners. This conservative policy matches release's existing
reference guard. It does not grant authority to the listing owner over a
different player's collection. Existing true flags remain protected after the
last reference disappears; their provenance is unknown. Manual locks never
become a source for the trading flag.

Absorption now checks the recipient and actual eligible owned donors under its
existing user/instance transaction locks. Explicit current locking reads check
requests before offers. Missing or foreign input IDs retain existing filtering;
they do not cause rejection of an otherwise valid batch. A referenced recipient
or donor rejects the whole batch with 409 FAILED before points, attacks, Morties
or decks change. Creators already serialize on the authenticated owner's user
lock, so a concurrent creation cannot silently race through consumption.

Owner-scoped offer cancellation now permits withdrawal of an existing orphan
offer when its parent is absent. It still revalidates the exact offer, owner and
row identity under locks. Foreign owners fail 403; ambiguity fails 409; a missing
offer or replay remains 404 TRADE_NO_SUCH_OFFER. No transfer, currency, refund or
stored-lock mutation is introduced. The final reference-derived lock disappears
on the next player-details response when the stored legacy flag is false.

Migration 014 adds only a nonunique index on `trade_offers.morty_offer_id`, for
the correlated projection/current reference checks. Requests already have the
equivalent index. The original schema dump is unchanged. The migration was
applied twice to a full schema-only copy before isolated application; existing
offer rows remained byte-for-byte identical in the query comparison.

## Verification

All 57 relevant additive tests passed serially: 12 new reference cases, 19
cancellation cases, 6 trade party guards, 12 absorption-protection cases, 5
Morty-lock cases and 3 battle/world guards. The new suite first reproduced 12
failing assertions against the old handlers, including a creation/absorption
race that allowed both to succeed. The final suite preserves existing request
costs, free cooldowns, raw flags, manual locks, ownership and collection state.
An additional offer-creation/absorption race passed independently after the
initial 11-case suite. No global reseeding or changes to older expected responses
were needed. Four touched PHP files passed lint; protocol source hashes and
research Python syntax validated. Both original-account guards and the dedicated
retained save/history guard passed. The dedicated SDK cache and profile remained
byte-identical. Only the verified dedicated primary emulator and opt-in SDK
sidecar were stopped; their data remains retained.

Source implementation: `efbd871`, on `hayward/trade-lock-lifecycle`, starting
from main `9ff1a11` with prerequisite PR #50 (`3e0c568`) fast-forwarded explicitly.

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_references.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_cancellation.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_party_guard.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_morty_absorb_protection.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_morty_lock.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_battle_world_guards.py -v
& $researchPython -X utf8 tools/research/validate.py
```

## Native reachability and remaining work

Later verification: [native kiosk entry](trading-kiosk-reachability.md) now reaches
Barter Rick, Trade slots and Browse's empty state. The earlier bounded failure
below remains historical evidence; cancellation and refresh are still unverified.

Static navigation identifies world interaction `TRADE_KIOSK=18`, then
`MPWorldState.AttemptToOpenTrade` and `MPTradingState`; the root UI has Browse
and Trades actions. It is not the Phone Friends menu. A guarded same-hub Android
inspection did not visually verify a Swap Shop kiosk. It used 13 UI actions and
no A interactions, battles, purchases or trade mutations. The dedicated immutable
save/history guard passed before and afterward. This bounded failure to find a
kiosk is not proof that the feature was removed or unreachable everywhere.
The [sanitized reachability receipt](trade-navigation-reachability.json) records
the world-only pass and private screenshot fingerprints; preceding Phone/Friends
inspection is outside its 13-action count.

Native cancellation-button acceptance therefore remains open. No fixture trade
rows were injected into the retained account to manufacture a visible result.
Immediate offer-cancel cache refresh, other full-Morty serializers (heal, items,
active deck, learn-attacks, room/join and battle views), legacy true-flag repair,
acceptance authorization and request/offer binding remain separate. README
baseline features and attribution are preserved; no gameplay formulas, refund
rules or bulk stale-row cleanup were invented.

# Protected trade request and offer creation

Both creation endpoints previously allowed locked or active-party instances to
be listed. Offer creation also accepted instances that did not match a specific
request's species or variant. The [recovered native selector](trade-listing-protection-contract.md)
excludes these choices; its UI restrictions did not protect the PHP handlers.
The server now validates eligibility in the transaction that inserts the listing.
ConspiracyRick's existing success responses and economic behavior are retained.

## Checks and transaction

`/trading/request-morty` and `/trading/offer-morty` require POST and validate JSON
types before database work. Sessions and logical player/instance IDs must resolve
exactly and unambiguously in the legacy nonunique schema. Provided player IDs
must match the authenticated actor. Native request creation sends six fields;
legacy callers may still omit `player_id`, requested species, variant and free
flag. Those omissions retain authenticated-owner, `any`, `Normal` and false
defaults. Provided nulls, arrays, invalid variants or coerced booleans are rejected.
Offer creation retains its four required native fields.

Both routes lock the actor before checking the parent, owned instance, active
deck and global durable trade references. This serializes competing request and
offer creation for the same actor and coordinates with existing collection and
deck writers. Ownership/deck changes committed while a creator waits must be
observed before insertion. The actor's shared battle membership blocks creation.
The parent lock still coordinates offers with cancellation and acceptance.

A candidate must belong to the actor, have neither manual nor stored trading
lock, have no request/offer reference anywhere, and be outside the active deck.
References include orphan offers and stale declared owners, matching the
existing effective trading-lock policy. Legacy false/null flags remain usable;
unknown flag strings fail closed. Stored flags are never rewritten.

Only active-deck membership excludes a candidate. Membership in an inactive
saved deck is allowed. Missing, duplicate or malformed active decks cannot
establish eligibility and fail without writes. Escaped legacy JSON arrays remain
supported. Active-deck aliases that SQL collates to the candidate are excluded
conservatively; native string equality does not establish that collation policy.

For a specific requested species, both species and variant must match. Normal,
Shiny and Pulsing use equality, not absorption's directional compatibility matrix.
`any` bypasses both criteria. Existing null/empty parent criteria still project
as `any`/`Normal`, matching GetTrades; owned NULL variants project as `Normal`,
matching player details. Byte-exact canonical species validation is replacement
server policy; native uses `String.Compare`.

## Responses and effects

Successful request and offer envelopes, identifiers and display metadata remain
unchanged. A request still uses the existing one-coupon paid cost or writes the
existing `time()+3600` free expiry. This repair does not establish those values as
original rules or introduce new cooldown/slot enforcement. Offers consume no
new resources. No inventory, attacks, deck membership or raw locks are changed.

Errors use the native `error.code` envelope. Request locks, existing reservations
and active membership use `TRADE_MORTY_LOCKED`. Offer ineligibility uses `FAILED`;
there is no locked-offer enum. Specific criteria failures use
`TRADE_MORTY_NOT_MATCH_CRITERIA`. Ownership/missing-listing errors use the exact
endpoint enum names in the linked native contract. Generic failures, insufficient
coupons and unexpected errors now use `FAILED`, replacing unsupported error
strings. Unexpected details are logged privately.

Replacement status policy is 400 malformed input, 401 unknown session, 403 wrong
actor/owner, 404 missing offered instance/parent, 405 non-POST, 409 ambiguity or
ineligibility, and 500 unexpected failure. Missing requested instances retain
ownership rejection at 403. Original validation order/status parity is unknown.
Every failed transaction rolls back its listing, charge and expiry writes.

## Verification and limits

Run exact suites serially against the isolated stack; never broad discovery:

```powershell
$researchPython = 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_listing_protection.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_references.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_cancellation.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_start_context_writer_guards.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_offer_metadata.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_cooldown.py -v
& $researchPython -X utf8 tools/research/validate.py
```

The exploratory 21-method baseline produced 78 failing assertions including
subtests against `b0170b2`. This initial set also contained provisional status
expectations and a legacy-battle freeze probe subsequently excluded from the
repair, so that count is not a count of confirmed defects. Raw output stays in
ignored `.research/trade-listing-baseline-tests.txt`.
Regression fixtures use additive UUID rows and scoped cleanup, with distinct
active-party and spare instances. Older cancellation/reference/context tests now
use eligible spares while preserving their original race, cost and rollback
assertions. Synthetic fixture stats are not recovered generation formulas.

All 74 unique cases pass across the recorded suite runs and focused follow-ups:
28 new eligibility cases, 12 durable-reference cases, 19 cancellation cases,
eight resource/context guards, four offer-metadata cases and three cooldown
cases. The [verification receipt](trade-listing-protection-results.json) records
the initial timestamp/wait-monitor assertion failures and successful reruns.
Only successful request updates permit the schema's automatic actor `last_seen`
change; rejected operations and successful offers retain exact snapshots.
PHP lint, wrapper syntax, evidence/source/helper hashes and retained account/save
guards pass. No retained collections, parties, resources or installations changed.

This establishes eligibility **at creation**, not the entire transfer lifecycle.
Later deck writers can still activate a listed instance; acceptance-time party
revalidation and that reverse transition need a separate repair. Raw legacy
ACTIVE battle rows are not newly blanket-blocked: some represent old terminal
battles, and safe policy requires the existing evidence-based reconciliation.
Shared membership protection is retained. Parent-owner/collection integrity,
friendship/duplicate-offer policy, free-slot/cooldown rules, original economics,
completed-list spelling and immediate post-cancel refresh remain explicit gaps.

The prior native create/cancel captures are supporting evidence for existing
successful bodies; they are not new captures of these checks. No Android
accept/reject, original-service traffic, migration, emulator reset or deployment
is claimed. Mixed legacy lock order can still deadlock; failures roll back and
automatic retries are not added. Root README completion claims and attribution
remain unchanged.

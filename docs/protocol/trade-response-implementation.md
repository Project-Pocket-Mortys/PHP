# Authenticated trade offer responses

Follow-up: [party transitions](trade-party-transitions.md) now recheck both
current active parties during acceptance while preserving rejection/cancellation.
Native accept/reject and full living-party policy remain separate.

Follow-up: [protected listing creation](trade-listing-protection.md) now enforces
lock/active-deck and offer criteria at insertion. The response milestone below
remains separate from later deck transitions and native acceptance verification.

`/trading/offer-response` previously accepted unauthenticated decisions and did
not bind the selected offer to the supplied request. A caller could therefore
reject someone else's offer or combine unrelated listings in an ownership swap.
The [native contract](native-trade-response-contract.md) establishes the existing
three-field body and the distinction between accepting a request and declining
one offer. The repair retains the existing successful `[null,null]` response and
ownership-transfer implementation while enforcing requester authorization.

## Request and authentication

POST an object containing string `trade_request_id`, string `trade_offer_id`,
and a JSON boolean `request_accepted`. Missing booleans, strings such as
`"false"`, numbers, arrays, empty identifiers and identifiers longer than the
existing 64-character listing columns are rejected. Extra body fields do not
grant identity or replace transport credentials.

Authentication uses the replacement server's existing login-issued
`session_id` cookie scoped to `/trading/`, or an explicit Bearer session.
Both credentials must agree when present. This is replacement-server policy,
not a recovered original-service session mechanism. Native cookie transmission
was observed during the preceding offer/cancellation milestone; a native
acceptance or rejection capture is not claimed here. Existing clients need a
fresh login to receive the cookie.

Only the exact, unambiguous request owner may decide. The session, player,
request, offer and owned-instance logical identities must resolve without
duplicates or case aliases in the legacy database collation. The offer must
belong to the exact supplied request. Both decisions retain the existing shared
battle membership guard for declared and actual owners. Acceptance additionally
requires both exchanged instances still belong to their declared owners.

## Transaction and responses

The existing guard acquires sorted participant user locks before current
listing and inventory locks. Authentication and parent/child binding are
checked again under those locks. A session rotated while the operation waits
cannot authorize a later write. Ownership updates, completion insertion and
listing deletion either commit together or roll back together.
Legacy writers acquire some user locks in a different order; an InnoDB deadlock
can therefore return `500 FAILED` after rollback. Automatic retry is not added.

Acceptance swaps the two selected owned-instance owners, inserts one completion,
and removes the parent and all attached offers. The native acceptance callback
removes all incoming offers for the fulfilled request; retaining them would
leave orphan reservations. Rejection removes only the exact selected offer.
Unrelated parents and offers remain. Repeated decisions cannot transfer twice.
No stored lock flags, decks, attacks, items, balances, cooldowns or SSE events
are rewritten by this repair.

Errors now use the native parser's nested envelope, for example
`{"error":{"code":"FAILED"}}`. Missing requests use
`TRADE_NO_TRADE_EXISTS`; missing offers use `TRADE_NO_OFFER_EXISTS`.

| Status | Replacement-server meaning |
| --- | --- |
| 400 | Malformed body, identifier or decision |
| 401 | Missing, invalid, malformed or conflicting authentication |
| 403 | Authenticated actor is not the request owner |
| 404 | Request or offer no longer exists |
| 405 | Method other than POST |
| 409 | Ambiguous identity, changed state, mismatched binding or shared battle reservation |
| 500 | Unexpected failure; transaction rolled back and details logged privately |

These statuses are replacement integrity policy; original status parity is
unknown. Success bodies are ignored by the recovered native callback. Flat
error strings previously returned by PHP do not satisfy its `error.code` parser.

## Verification and remaining scope

Run the exact additive UUID suites serially against the isolated research stack:

```powershell
$researchPython = 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_response_authorization.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_party_guard.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_cancellation.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_offer_metadata.py -v
& $researchPython -X utf8 tools/research/validate.py
```

Before the repair, the initial 16 response tests produced 47 failing assertions,
including unauthorized mutations, unrelated request/offer pairing, coerced
booleans, incompatible errors and orphan sibling offers. Raw test output stays
in ignored `.research/trade-response-baseline-tests.txt`.

All 51 regression tests pass: 22 response cases across the initial 19-case run
and three focused follow-ups, six existing trade membership/transfer cases,
19 cancellation cases and four offer-metadata cases. The existing transfer
tests now send authenticated requests and expect native error envelopes.
The [sanitized verification receipt](trade-response-results.json) records the
scope and individual runs. Coverage includes duplicate
acceptance, session rotation while waiting, both stale owner sides, aliased
sibling parent IDs, and completion/late-deletion failure rollback. Fixtures are
additive UUID rows with scoped cleanup; retained native saves are not reseeded.

This is an authorization and binding repair, not complete trading acceptance.
Remaining work includes native accept/reject presentation and inventory refresh,
completed-trade wire-name mapping, original cooldown/reward policy, and protected
listing creation/active-party eligibility. The existing transfer does not edit
decks or clear legacy true lock flags; malformed legacy listings may therefore
still require a separate eligibility repair. Do not infer original server
economics or party policy from the synthetic regression fixtures. Root README
completion claims and attribution remain unchanged. No database migration or
deployment is included.

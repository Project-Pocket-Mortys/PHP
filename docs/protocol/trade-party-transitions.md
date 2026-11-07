# Trade reservations across party changes and acceptance

A listing could previously be created for a spare, then that saved deck could
be activated before acceptance. Acceptance also transferred legacy active-party
instances without checking either player's current party. This repair closes
those transitions while preserving current successful deck/transfer responses,
withdrawal paths and existing economic behavior.

The [native trace](trade-party-transition-contract.md) establishes the trade-lock
check during party addition and the deck request/response/error contracts.
Saved-deck activation has no recovered native trade-lock check. Its new rejection
and acceptance-time active-party revalidation are replacement-server integrity
policies derived from the existing creation-time active-party exclusion, rather
than claims about original-service validation.

## Deck edit and activation

Nonempty `/session/deck/edit` writes also set the active deck in the existing PHP
implementation. Both that path and `/session/deck/set-active` now resolve every
target instance globally and exactly, confirm current ownership, and check
stored trading locks plus durable request/offer references before writing.
Orphan offers, stale declared owners and collated references still reserve an
instance. Ambiguous instance identities, duplicate target deck rows and malformed
saved parties fail without writes. A target cannot activate an unowned instance.

The handlers retain the authenticated owner's user lock and recheck exact
session identity under current locking reads. Candidate/deck/reference checks
share the write transaction. A reservation or ownership change committed while
the writer waits cannot be bypassed by an older snapshot.

Only the target party is checked. A different inactive saved deck may still
contain a listed instance; unrelated party changes remain allowed. Empty edit
continues to remove the selected deck without changing the active index, as
before. Removing/rejecting/cancelling unsafe legacy listings remains available.
Stored lock flags, other decks and owned attacks are not rewritten.

Manual/favorite `is_locked` alone remains allowed by the existing backend's deck
writes. This is a compatibility choice, not a claim that every native storage UI
permits withdrawing a favorite: the normal selection button can check both lock
flags, while lower-level addition checks trading lock and save/activation do not
reread either flag. This repair does not add a blanket manual-lock prohibition.

New transition failures return HTTP 409 with
`{"success":false,"error":{"code":"FAILED"}}`. Native deck callbacks consume
the nested `error.code`; the extra `success` field is preserved for compatibility.
Existing unrelated deck failure envelopes remain unchanged, including their
older flat-error compatibility gaps. Successful bodies retain their profile
fields, `active_deck_id`, and nonempty `decks` array. The client clears and
repopulates cached decks for a nonnull array, so omitted selected decks are not
safe success responses.

Saved target validation accepts the repository's escaped legacy JSON arrays.
Both deck response projections now use the same fallback decoding for those
arrays, without converting stored data. The initial integration regression
reproduced successful activation with the selected deck missing from the body;
the correction keeps that deck present for native cache replacement.

## Acceptance

After existing requester/binding/ownership checks and sorted participant user
locks, `/trading/offer-response` now reads both current active decks under locks.
Neither outgoing instance may belong to its owner's current active party.
Missing, duplicate or malformed active deck rows fail as HTTP 409 with native
`error.code=FAILED`, before either ownership update or completion insertion.
The existing active-deck decoder remains authoritative: no new living-party
minimum or duplicate-member invariant is introduced.

This check runs only for acceptance. Rejecting or cancelling a listing does not
require safe transfer parties. Own listing references are expected during
acceptance, and legacy stored true flags have unknown provenance; reusing the
entire creation-eligibility predicate would reject all valid reserved trades.
Acceptance therefore rechecks active membership without clearing or blindly
rejecting those flags. Existing ownership swap, single completion, competing
offer cleanup and successful `[null,null]` body remain unchanged. No deck is
rewritten during transfer, including inactive decks that retain old instance IDs.

## Verification and limits

Use exact additive suites serially against the isolated research stack:

```powershell
$researchPython = 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_party_transitions.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_response_authorization.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_party_guard.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_party_writer_guards.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_listing_protection.py -v
& $researchPython -X utf8 tools/research/validate.py
```

The initial 19-method baseline against `db4d236` produced 34 failing assertions
including subtests. Raw output stays in ignored
`.research/trade-party-transition-baseline-tests.txt`. All fixtures use additive
UUIDs and scoped cleanup. Older positive transfer tests now retain separate
active parties and exchange spares; their authorization, ambiguity, retry,
shared membership and rollback assertions are preserved.

All 60 regression cases pass: 26 new transition cases, 22 existing authenticated
trade-response cases, six trade membership/transfer cases and six existing party
writer guards. Tests cover simultaneous listing/activation, acceptance versus
activation, committed reference/party changes during lock waits, escaped deck
projections and withdrawal paths. The [sanitized verification receipt](trade-party-transition-results.json)
records each run and both baseline boundaries. PHP lint for all four files,
wrapper syntax, evidence/source validation and retained-account/save guards pass.

No Android accept/reject or deck-edit capture is claimed by the static trace or
synthetic tests. Original status parity, legacy raw ACTIVE-battle reconciliation,
full living-party policy, original cooldown/economics, completed-list spelling,
post-cancel refresh, legacy references on other parents and stored true-flag
provenance remain unresolved. Other
collection/party writers remain separate audit obligations. Mixed legacy lock
order may still deadlock and roll back; no automatic retry is introduced.
No migration, save reset, root README change, deployment or main/master merge
is included.

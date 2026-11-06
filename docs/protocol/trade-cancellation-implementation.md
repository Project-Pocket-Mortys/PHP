# Owner-scoped trade cancellation

Later native acceptance: a [separate disposable client](native-trade-cancellation.md)
created and cancelled its own free request with the ID-only cookie-authenticated
body and lock refresh. Offer cancellation remains unverified. Its captured
cooldown projection defect is repaired in that follow-up.

Later verification: [isolated startup recovery](onetrust-startup-recovery.md)
now passes native login and [actual trading cookie transmission](onetrust-recovery-cookie-handoff.json).
The earlier failed captures below remain historical evidence. Cancellation
buttons and wider trade authorization remain separate. Subsequent
[durable-reference protection](trade-reference-implementation.md) derives the
player-details trading flag, guards absorption and permits exact owner withdrawal
of orphan offers. It preserves raw flags; other serializers and unknown legacy
true flags remain unresolved. This page records the earlier cancellation scope.

`/trading/cancel-trade` previously deleted a request and its offers without
requiring a valid session. `/trading/cancel-trade-offer` was missing. Both now
require a current, unambiguous session and the listing owner's identity before
deletion. The request owner may remove its request and dependent offers; only
an offer's owner may cancel that offer. Unrelated listings remain unchanged.

The [native contract](trade-cancellation-contract.md) establishes POST bodies
containing only `trade_id` or `trade_offer_id`. It also establishes automatic
Best.HTTP cookie handling, enabled by default. The backend now issues a host-only
`session_id` cookie at successful login, scoped to `/trading/`, HttpOnly,
SameSite=Lax, with session lifetime. Secure follows the configured public HTTPS
origin. This cookie handoff is replacement authentication policy, not recovered
original-server provisioning. Existing installations need a fresh login to
receive it; cancellation never falls back to trusting a listing ID alone.

Explicit Bearer sessions remain supported. Multiple credentials must agree,
and malformed explicit Authorization is rejected even with a valid cookie.
Apache's `getallheaders()` supplies Authorization where server variables do not.
Body identity/session additions are rejected; native single-ID bodies remain
unchanged. Slashless POSTs rewrite internally without dropping their body.

The existing HTTP 200 `{"error":"None"}` success is retained for both routes;
native callbacks ignore the success body. Non-success responses use native
`error.code` enums: FAILED, or TRADE_NO_SUCH_OFFER for a missing/replayed offer.
Missing/invalid authentication is 401, foreign owners 403, malformed bodies 400,
ambiguous identities/listings 409, and missing/replayed listings 404. Methods
other than POST return 405. Original status-code parity remains unknown.

Cancellation locks the actor, parent request, then dependent offers and commits
deletion atomically. Offer creation now holds the same parent lock through its
insert, preventing a cancelled request from gaining an orphan offer. Failed
deletions roll back the whole batch. No persistent ownership, manual/trade lock,
deck, attack, item, currency, cooldown or reward mutation is introduced. The
native callbacks update local trade caches, but do not establish refunds.

Persistent trade-lock reconciliation remains a separate gap: current request/offer
creation does not consistently maintain the stored flag, and cancellation must
not blindly clear a flag while another active reference or shared battle exists.
The native local unlock is not claimed as a complete persisted lock lifecycle.

Trade acceptance authorization, offer/request binding, protected-donor creation,
full transfer/party correctness, and original cooldown/refund policy remain
separate gaps. This change does not claim the whole trading system is complete.

## Verification

Run the additive UUID suites serially against the isolated research stack:

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_cancellation.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_party_guard.py -v
& $researchPython -X utf8 -m unittest discover -s tools/research -p test_trade_cookie_handoff.py -v
& $researchPython -X utf8 tools/research/validate.py
```

Nineteen cancellation cases passed across scoped runs, including the real HTTP
login/CookieJar flow, owner checks, malformed credentials/bodies, ambiguity,
replays, injected rollback, concurrent parent/offer cancellation and offer
creation versus cancellation. The initial tests reproduced unauthenticated
deletion. Seventeen cases initially passed; the two Authorization cases exposed
Apache header extraction and passed after correction. The strengthened creation
race was rerun successfully. Six existing trade membership/transfer guards passed.
Six pure capture-sanitizer cases passed without accessing a device or database.

Native outgoing-cookie verification is separate from backend cancellation tests.
No native cancellation-button capture is claimed here.

## Native smoke limitation and handoff

Both retained-client attempts stopped at the initial loading screen before
login. Their successful local startup APIs and seven time-bounded OneTrust
initialization exception stacks per attempt are recorded in the
[sanitized blocker receipt](trade-cancellation-startup-blocker.json). The first
used host 8087; restoring the previously working 8089 routing did not resolve
the spinner. Root cause is not established. Neither capture contains a login
or trading request, and the cookie sanitizer emitted no success receipt.
This is not evidence that cancellation or cookie transport failed.

When startup is restored without deleting the retained save, capture a real
login and subsequent trading request with the existing bounded capture helper.
The pure sanitizer requires the immutable account fixture, matching login
secret/JWT identity, an issued scoped cookie and its actual later native Cookie
header, plus exact TCP request/response acknowledgement pairing:

```powershell
& $researchPython -X utf8 tools/research/sanitize_trade_cookie_handoff.py --pcap .research/emulator/trade-cookie-next/primary-capture/primary-http.pcap --fixture .research/emulator/paired-selection-complete-20261106/fixture/startup-fixture.json --output .research/trade-cookie-next-proof.json
```

Inspect that private proof before publishing it. A trading error can still
prove Cookie transport; it does not prove successful cancellation. Verify the
native cancellation button, refreshed lists and persistent trading-lock
reconciliation separately. Never substitute a scripted request for native
transmission or clear app data to bypass the startup blocker.

All five touched PHP files passed PHP 8.3 lint; protocol/source hashes, Python
and shell syntax and whitespace checks passed. The dedicated retained-account
save/history guard and both original-account guards passed. Only the dedicated
primary AVD and opt-in sidecar were stopped afterward; their data and all raw
captures remain preserved. No schema change, account reset, merge or deployment
is included. README changes relative to the prerequisite are empty.

This branch starts from current main `9ff1a11`, explicitly fast-forwarding pending
PR #48 at `1590e7e`. The tested implementation is commit `9684227`. Keep this
change in draft review until native cookie/cancellation acceptance is complete;
the wider trading authorization and lock-lifecycle gaps are not resolved here.

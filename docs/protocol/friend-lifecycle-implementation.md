# Friend request lifecycle

The previous response handler could approve or reject either orientation of a
pending row, so a sender could accept their own outgoing request. Only the
intended recipient may now respond. Request, response and removal cooperate
on pair locks and transactions. This supplies a social prerequisite for friend
battles; their invitations and combat remain separate.

[Native evidence](friend-lifecycle-contract.md) establishes request fields,
list directions, polling and errors. Successful mutation bodies are preserved:
request returns its pending relationship object, response returns JSON `1`,
and remove returns its existing success object. Those bodies are ignored by
the native mutation callbacks. Errors require `error.code`, so previous plain
strings are replaced by native enum names. Auth failures retain HTTP401 but
use `FAILED`, a member of all five enums, instead of `NOT_AUTHENTICATED`.

## State and authorization

The existing convention remains A=sender, B=recipient. A sees B in sent requests;
B sees A in received requests. Only B can respond with `player_id=A` and
`approve:true` or `false`. Approval accepts the row; rejection deletes it.
An outgoing request can be cancelled through remove. Accepted friends appear
to both participants and either can remove the relationship. Third accounts
cannot respond to or remove it.

Mutations require unambiguous session/player IDs, lock both users in stable
order, then revalidate authentication after waiting. All three writers use
that order. Pair reads occur afterward without unnecessary locking scans over
the legacy text columns. Crossed requests create one row. Duplicate stored
pairs reject without speculative consolidation or orientation migration.
Writes use the exact relation row ID and commit atomically; insert, approval,
decline or removal failure rolls back. Replays cannot recreate deleted rows.

Lists use one repeatable-read snapshot so pending and accepted projections do
not disagree within a response. Collections remain arrays and the top-level
donation object remains nonnull. Level/wins/losses are integers. Legacy online
strings and the five-minute last-seen policy remain compatible with native
`Convert.ToBoolean`. Per-friend donation representation is retained.

The native UI polls using `poll_period:5`; no friend SSE event is invented.
The existing advertised limit30 remains, without adding unverified server
quota rules. Native counts include sent pending requests. Exact-name search
preserves its public profile result and legacy empty HTTP200 no-result body;
the nullable callback is known but the empty decoder behavior remains uncertain.
PHP warnings and exception internals are not emitted to clients.

## Verification

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_friend_lifecycle.py -v
& $researchPython -X utf8 tools/research/validate.py
wsl -- bash tools/research/ghidra-friend-lifecycle.sh
```

The sender-approval regression failed before the repair. Thirteen new UUID
cases passed across the recorded runs: eleven in 77.066 seconds, the added
identity case in 4.070 seconds, and changed auth/list cases in 14.383 seconds.
Coverage includes direction, decline/cancel/removal, replay, crossed requests,
accept/remove races, third-account privacy, malformed input, session revocation
while waiting, and forced rollback. Nine existing SSE session/privacy cases
passed in 24.556 seconds: 22 distinct checked cases. PHP 8.3 lint passed for
all 37 changed/new PHP files including prerequisites.

[Two-client Android checks](android-friend-lifecycle.md) record native search
and lifecycle observations. The fixture preserves all original friend rows
and gameplay state; native removal must restore the initial pair state.

Based on main `9ff1a11` with pending prerequisite PR #35 at `6161410` and its
dependency history. No migration is added. README-completed features and
attribution are retained. Original quotas, ambiguous legacy orientation,
donations/trades and friend battles remain follow-up work. No deployment or
real purchases are included.

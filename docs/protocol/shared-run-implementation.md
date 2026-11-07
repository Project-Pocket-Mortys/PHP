# Research initial friend-battle RUN

The opt-in shared battle service now accepts a voluntary RUN before the runner
has selected its first ATTACK. Both clients must have completed initial ready,
and both original private start publication attempts must exist. This supplies
one terminal action after the [first ATTACK storage](paired-selection-contract.md)
foundation; it does not enable playable combat, later turns or public invitation
acceptance. The [bounded native contract](shared-run-contract.md) establishes
the request and consumer behavior. Surrender adjudication and transport delivery
below are explicit replacement-server policy.

## Request and atomic decision

With `PM_RESEARCH_SHARED_BATTLE_STREAM=1`, a known shared battle ID routes through
`friend_battle_forfeit_submit` in `lib/friend_battle_forfeit.php` when the move
type is RUN. The body has exactly five fields:

```json
{"session_id":"current-session","battle_id":"shared-battle","type":"RUN","owned_morty_id":"initial-active-owned-id","move_id":null}
```

The owned ID must be the runner's unchanged initial living active Morty. Null is
required for `move_id`; a missing field, empty string or extra key rejects. The
current session must authenticate the stored participant. Both initial ready
timestamps, READY state, both original start intents/attempts, exact shared
claims, frozen party/private-view integrity and live original stream bindings
are revalidated under the existing ordered locks. The fixed startup deadline
must still be live after the writes. A runner with an existing own ATTACK
selection rejects; a peer's zero or one pending ATTACK is allowed and remains
inert. A completed ATTACK pair never becomes a RUN decision.

One transaction stores a hashed immutable decision and two hashed recipient
terminal intents, retires startup intents and any pending selection history,
sets the shared session to CANCELLED/STARTUP_RUN, returns both users to WORLD,
and releases only the exact original claims. The ACCEPTED invitation remains
history. HP, AP/PP, ailments, party, items, currency, XP, ranking and gameplay
counters are unchanged. No action, damage formula, AI turn, reward or timer is
created. Any insertion, retirement, final lease or integrity failure rolls the
whole operation back.

HTTP success stays exactly `{"success":true}`. It exposes no decision ID,
selection, peer resources or result payload. The internal receipt has a stable
decision ID. An exact own retry reauthenticates the current owner and validates
the frozen terminal history, returning that same receipt without recreating
intents, renewing leases or consulting the peer's current session/state/claims.
It therefore cannot disturb newer battles or claims. A conflicting actor,
changed owned ID or damaged history rejects. Concurrent opposing RUNs choose
one actor; a same-actor ATTACK/RUN race cannot commit both.

## Private terminal and publication attempts

The runner receives this recipient-specific result; the implementation retains
the battle ID as an envelope field:

```json
{"battle_id":"shared-battle","outcome":"RUN","battle_abandoned":false,"turn_datas":[],"player_datas":{"player":{},"opponent":{}}}
```

The peer receives outcome `"WIN"` and `battle_abandoned:true`; the native handler
maps that to ABANDONED presentation. Empty player/opponent objects are deliberate:
missing item/XP/reward/optional-state fields are safe on the reviewed native
paths and preserve client inventory. No optional arrays or `move_log` values
are fabricated. The native result handler provides no battle-ID replay fence;
the extra envelope ID is not an acknowledgement or client deduplication key.

Each terminal is eligible only for its recipient's original bound stream and
session generation. The publisher locks the current recipient, validates frozen
history, records one terminal-attempt row and mirrors its timestamp into the
intent, then commits before the SSE write. Missing, redirected or inconsistent
attempt history fails closed. Deleting an attempt row cannot reopen an already
marked intent. No ordinary room queue broadcasts either private result.

This is **at-most-once publication attempt**, not exactly-once delivery. A crash
after the marker commits but before the write can lose the terminal
presentation. The broken connection follows the existing disconnect/fresh-login
path into the already-committed WORLD state. There is no terminal replay on the
original stream, a fresh stream or a rotated session, and no battle resume or
native terminal acknowledgement is claimed.

After the attempt, polls keep the stream open, return no terminal event and
refresh only the recipient's own heartbeat. They do not require a live peer or
immediately emit `session:end`. This lets native finish presentation complete.
The existing one-shared-startup-per-stream rule remains unchanged.

A newer legacy wild start on the same live original generation returns 409
while its old terminal has no publication attempt. The check precedes legacy
reconciliation and all new start mutations. Once that attempt is committed,
later polls cannot send the old terminal. An expired or superseded generation
cannot receive it and does not block a new wild start. This ordering fence
prevents the old result from being delivered after a newer battle registers
its native result handler; it does not acknowledge native consumption.
The fence checks existing research history on both the normal and opt-in
services, so a normal-service wild POST cannot bypass a pending research
terminal. It does not create or publish research results with the gate off.
The binding/session discovery uses `FOR UPDATE NOWAIT`; lock contention and
deadlocks return retryable 409 instead of waiting in a reversed lock order.

## Schema and rollout boundary

Apply additive migration
`tools/research/server/migrations/016-shared-battle-forfeit.sql` after the
existing prerequisite migrations. It creates:

| Table | Durable purpose |
| --- | --- |
| `friend_battle_forfeits` | One decision ID, runner/owned identity, normalized decision JSON/hash and timestamp per battle. |
| `friend_battle_terminal_intents` | Exactly two recipient delivery IDs and private payloads/hashes, with an attempt anchor. |
| `friend_battle_terminal_attempts` | At most one original-stream publication attempt per battle/recipient, with the mirrored timestamp. |

The normal service keeps the research gate off and retains its legacy shared-ID
behavior. Its wild-start fence also protects existing live research terminal
history; accounts without that history retain their ordinary behavior.
Public pending invitation acceptance remains HTTP 501, with existing
already-accepted conflicts unchanged. No deployment, public gameplay enablement,
account reset or Android RUN capture is part of this implementation.

## Verification

The additive `tests/protocol/test_friend_battle_forfeit.py` module covers both
roles, exact native null input, readiness/start-attempt prerequisites, immutable
selection limits, authenticated retries, concurrent decisions, expiry/lease
boundaries, rollback, corrupt/missing history, privacy, generation fencing,
publication attempts, legacy-start ordering and a real private SSE connection
that remains open through a heartbeat. Its schema-copy case applies migration
016 repeatedly to connection-local copies rather than recreating shared tables.
The pre-change additive fixture reached both ready signals/start attempts, then
submitted the exact native RUN/null shape expecting HTTP 200; it received
400/FAILED. This is a synthetic backend baseline, not an Android UI capture.
The pre-application repeatable schema-copy check passed in 0.340 seconds.
All 31 unique new cases are validated across the original run and focused
reruns: 30 behavioral cases and the one pre-application schema-copy case.
The original run's only failing case was premature EOF in the third-account
SSE observer; setting that local reader's timeout before connecting and safely
closing its worker corrected the harness. The focused real-SSE case passed in
79.966 seconds, lock contention in 8.844, cross-host drain in 9.369 and
superseded-stream handling in 8.720. The observer repair supplies backend SSE
evidence; no Android RUN capture was made.

All 77 adjacent cases also pass serially, for **108 unique cases validated**:

| Exact adjacent module | Cases | Seconds |
| --- | ---: | ---: |
| `test_friend_battle_selections.py` | 18 | 287.689 |
| `test_friend_battle_transport.py` | 16 | 129.154 |
| `test_friend_battle_startup.py` | 19 | 197.468 |
| `test_battle_lifecycle.py` | 24 | 40.866 |

All six changed/new PHP files pass lint. The protocol evidence validator passes
JSON parsing, endpoint source hashes, reviewed request constructors, bounded
native addresses and research Python syntax. These backend checks preserve the
separate Android/public-approval acceptance boundary.

Use the isolated research stack and run exact modules serially; preserve all
retained accounts and do not run another database-mutating suite concurrently:

```powershell
$researchPython = 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$runModules = @(
    'test_friend_battle_forfeit.py',
    'test_friend_battle_selections.py',
    'test_friend_battle_transport.py',
    'test_friend_battle_startup.py',
    'test_battle_lifecycle.py'
)
foreach ($runModule in $runModules) {
    & $researchPython -X utf8 -m unittest discover -s tests/protocol -p $runModule -v -f
    if ($LASTEXITCODE -ne 0) { throw "Failed: $runModule" }
}
& $researchPython -X utf8 tools/research/validate.py
if ($LASTEXITCODE -ne 0) { throw 'Protocol validation failed' }
wsl bash tools/research/ghidra-shared-run.sh
if ($LASTEXITCODE -ne 0) { throw 'Bounded native reproduction failed' }
```

The 33-method bounded native wrapper reproduces request, presentation,
subscription and omitted-field checks using default WSL REA 6.8.0 and targeted
Ghidra without whole-program analysis. It changes no device or database. A
future two-client Android run must separately verify native Run confirmation,
both actual presentations, world return and interruption recovery before making
those acceptance claims. Public approval, later-turn identity and combat remain
separate work.

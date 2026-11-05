# Battle selection timeout recovery

An idle PvWM battle previously announced a 30-second selection timer but never
resolved it. The Android client then refused to send another move, including
RUN, and eventually disconnected on a separate watchdog. The replacement server
now abandons the expired selection without penalties or gameplay mutations.
[Native evidence](battle-timeout-contract.md) distinguishes these two timers and
establishes ABANDONED's ordinary finish and Party/Bag return paths. The choice
to cancel at 30 seconds without penalties is an explicit replacement policy.

## Selection lifecycle

Apply additive migration `004-battle-move-deadline.sql` before loading the new
handlers. It adds nullable `battles.move_deadline` with microsecond precision
and a `(state, move_deadline)` index. It never arms historical battles or changes
the original SQL dump. UTC timestamps and expiry comparisons use the database
clock, independently of PHP or client timezone.

READY locks the session user and owned ACTIVE battle, verifies the original
private PvWM start/current room and unambiguous BATTLE spawn claim, then arms
one 30-second deadline and queues one private `battle:move-timer-started` event
in the same transaction. Repeating READY acknowledges without extending the
deadline or republishing the timer. Ambiguous users or multiple ACTIVE battles
for the same player reject. Failure to queue the timer rolls back the deadline.
Existing READY failure bodies are retained for malformed input, invalid sessions,
foreign/missing battles and missing rooms; new consistency/expiry failures use
the existing `{"success":false}` form.

A successful ATTACK, SWITCH, ITEM or RUN clears the deadline in its existing
transaction. Rejected moves keep it. The next successful READY opens the next
selection. Expired READY or MOVE requests cancel under the same user/battle
locks and return HTTP 409 after committing the cancellation. A late item cannot
consume stock and a late attack cannot spend AP or deal damage. Native clients
may send neither request after local expiry, so those hooks are supplementary.

The active SSE poll checks for that session's due selections about once per
second. It rechecks session identity under the user lock; a revoked stream
cannot process its replacement session's battle. A bounded standalone research
worker handles disconnected clients. Candidate queries are only hints: expiry
rechecks the current persisted deadline and all ownership/origin/spawn state
under locks. Worker keyset paging moves past preserved ambiguous records rather
than letting them monopolize the earliest batch.

Expiry sets the battle CANCELLED with no winner or deadline, returns the user
and spawn to WORLD, and queues public state notifications plus exactly one
initiator-private result in one transaction:

```json
{
  "battle_id": "the existing battle ID",
  "outcome": "ABANDONED",
  "battle_abandoned": false,
  "turn_datas": [],
  "player_datas": {"player": {}, "opponent": {}}
}
```

No move, HP/AP/status update, item charge, XP, currency or reward is fabricated.
Both player data values are JSON objects, not arrays. Failed persistence/event
insertion rolls back the entire cancellation. Competing ready/move/SSE/worker
attempts cannot publish a second terminal result. This is transactional queue
uniqueness, not a claim of exactly-once SSE delivery.

## Reproduction and checks

The reviewed runner avoids the older globally reseeding test classes. Use the
installed interpreter directly to avoid Windows Store aliases:

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/migrate.php
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_battle_timeouts.py -v
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/battle-timeouts.php --once
```

Optional continuous disconnected-client recovery in the isolated environment:

```powershell
docker compose -f compose.research.yaml --profile battle-timeouts up -d battle-timeouts
```

The CLI is restricted to the research database. `--once` processes up to 100
due candidates; the continuous service retains its cursor across bounded batches
and wraps after reaching the end. It is off by default and no public deployment
is performed. Connected clients recover through SSE without enabling it.

The additive timeout suite covers duplicate ready, expiry and re-entry, late
item/attack, concurrent workers/ready/move, state/origin/claim guards, timer and
terminal insertion rollback, revoked sessions, stale candidates, fairness,
live two-account SSE privacy and disconnected CLI recovery. Migration checks
apply it twice to a disposable table created from the original SQL definition,
preserving legacy data with a null deadline. Fixtures use fresh UUID accounts.

On 2026-11-05, all 24 timeout cases passed in 48.716 seconds. The preceding
targeted integration run passed 94 cases in 314.155 seconds: 22 timeout cases
and 72 existing battle/item/switch/lifecycle/world-guard/ailment cases. The final
timeout run includes the two additional migration and worker-paging cases.
Those runs account for 96 distinct targeted regressions. Nine additional SSE
session/privacy cases passed in 28.081 seconds. A final legacy READY error-body
regression and five affected READY cases passed in 12.406 seconds after retaining those envelopes,
bringing coverage to 106 distinct cases, including 25 timeout cases.
PHP 8.3 lint passed for
all 28 changed/new PHP files including prerequisites; Compose configuration,
bounded analysis script syntax and protocol evidence checks passed.

Native Android checks passed natural expiry on the ordinary battle screen,
in Bag and in Party. Each emitted only READY, then received one ABANDONED result
through its actual SSE stream and returned to WORLD. No move or synthetic RUN
was used. Guarded cleanup and the two-account baseline comparison confirmed
exact original account restoration after each case; see the separate Android
record for captures, synthetic fixture provenance and loading retry details.

## Limits and provenance

This branch starts from main `9ff1a11` with explicit pending prerequisite PR #31
at `89a4c7d`, including its dependency history. Existing completed README features
and project attribution remain the baseline.

Only selections armed by READY expire. There is no inferred start or animation
deadline and no automatic rewrite of ambiguous historical battles. The native
constructor has no turn nonce: a delayed READY arriving after a successful move
cannot be distinguished from the next selection. Original grace periods,
penalties and cooldowns remain unknown. This work does not implement a complete
interrupted-battle reconnect/replay protocol; a previously advanced shared SSE
cursor can still limit replay of a result after reconnect. It does not recover
combat, capture or reward formulas. Android acceptance is recorded separately
in [the live timeout checks](android-battle-timeouts.md).

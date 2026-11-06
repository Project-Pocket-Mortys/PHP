# Missing gameplay features: implementation order

ConspiracyRick's playable backend and README-completed features remain the
baseline. An unverified feature is not automatically broken. Work now prioritizes
missing player actions; broad transport research is deferred unless a reproduced
failure blocks gameplay or exposes another player's data.

| Order | Feature | Next deliverable and acceptance |
|---|---|---|
| 1 | Lock/unlock Morties | Toggle/persistence and release/absorption protection implemented (`absorb-protection-implementation.md`); same-species/variant absorption checks now reject incompatible batches (`absorb-eligibility-implementation.md`). Inspect remaining destructive/trade interfaces separately. |
| 2 | Use items | Eight HP items, full revival/AP restoration and targeted poison/paralysis cures work in world and battle (`battle-item-implementation.md`); Pure Curum combined HP/ailment recovery is implemented (`full-recover-implementation.md`). Account Shiny Potion activation/expiry is implemented (`shiny-potion-implementation.md`). Finish percentage variants, stat/damage/general items and authentic timing; remaining numeric evidence gaps are in `remaining-item-evidence.md`. |
| 3 | Release Morties | World preview/confirmation implemented; Android Stats cancel/release verified. Batch contracts, locks, trade and party guards pass tests (`morty-release-implementation.md`). |
| 4 | Crafting | 22 multiplayer recipes implemented atomically; Android Serum Quick Craft and inventory verified (`crafting-implementation.md`). |
| 5 | Wild battles and catching | Durable attack/run/victory/defeat, party switching/forced replacement and safe selection expiry implemented (`battle-timeout-implementation.md`). Recover trustworthy stats/attacks, capture consumption/owned records and rewards; original combat rules and reconnect remain. |
| 6 | Bot/friend battles | Invitations, internal membership/deadlines and immutable parties/writer guards now work (`battle-party-snapshots.md`, migration009). Private recipient start views and frozen profile/inventory policy are implemented internally (`private-battle-start-views.md`, migration010). Acceptance remains unavailable; private publication/readiness/reconnect and terminal cleanup remain. Human combat and bot modes are separate. |
| 7 | Challenges, raids and events | Implement claims and event battles after their underlying battle/reward flows work; no invented success responses. |

This order favors independently usable additions and their dependencies; it is
not a claim that battles are less valuable. A reproducible player-blocking battle
defect can take priority. Remaining protocol research is listed in
[backlog.md](backlog.md).

## Lock/unlock delivered

`POST /session/owned_morties/lock` now accepts `session_id`, `owned_morty_id` and
a JSON boolean `is_locked`. It authenticates and locks the account/Morty rows,
persists only that owned Morty's flag, and returns the complete existing decks
and active deck ID. Repeated requests set the requested state again without
changing inventory, HP, trading lock or deck membership. Slashless client POSTs
use an internal Apache rewrite. No schema migration is required.

Five additive tests cover lock/unlock/retries, player-details persistence,
cross-player and missing IDs, invalid sessions, strict booleans, slashless POSTs,
and empty/legacy-escaped decks:

```powershell
py -m unittest discover -s tests/protocol -p test_morty_lock.py -v
```

The initial four cases failed against the absent route. All five final tests
pass. [Native evidence](morty-lock-contract.md) establishes the success fields
and error envelope; exact original HTTP error codes remain unknown.

Android 2.41.0 on the primary research emulator was exercised through the normal
menu: Your Mortys, select Morty, Stats, Lock, then Unlock. The padlock appeared,
Release became disabled, and the button changed to Unlock; unlocking reversed
those changes. Both slashless requests returned HTTP 200. The database changed
from legacy `false` to `1` to `0`, restoring the logical unlocked state while
normalizing its storage. HP stayed 20 and active deck stayed 0. The account was
returned to the world without a save reset. See the sanitized
[capture](morty-lock-capture.json); raw screenshots/captures remain ignored.

This delivers the toggle and persistence, not universal server enforcement of
protection: [absorption now protects consumed donors](absorb-protection-implementation.md), and
release enforces both lock flags (`morty-release-implementation.md`). Other destructive
interfaces remain separate; this is not universal protection. No original-server capture,
production deployment or client relaunch persistence test is claimed.

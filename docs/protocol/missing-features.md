# Missing gameplay features: implementation order

ConspiracyRick's playable backend and README-completed features remain the
baseline. An unverified feature is not automatically broken. Work now prioritizes
missing player actions; broad transport research is deferred unless a reproduced
failure blocks gameplay or exposes another player's data.

| Order | Feature | Next deliverable and acceptance |
|---|---|---|
| 1 | Lock/unlock Morties | Implemented and Android-tested in this branch; enforce protection in destructive operations separately. |
| 2 | Use items | Eight world healing items now implemented (`use-item-implementation.md`); finish revive/AP/cure/stat items and battle synchronization. General items have a separate client endpoint. |
| 3 | Release Morties | Recover attempt/confirmation contracts, protect locked/deck/trading Morties, remove associated data atomically. Test cancel, confirmation, invalid ownership and retry without deleting unrelated records. |
| 4 | Crafting | Recover recipe response and asset ingredients/output; deduct ingredients and grant output atomically. Test insufficient materials and retries, then Android UI. |
| 5 | Wild battles and catching | Complete run/victory/defeat/capture persistence, item consumption and rewards. Preserve playable behavior; distinguish recovered rules from replacement formulas. |
| 6 | Bot/friend battles | Replace stubs after recovering opponent/invitation lifecycle, participant events and disconnect behavior. |
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
protection: the existing absorb handler still ignores locks, and release is not
implemented. README retains that outstanding work. No original-server capture,
production deployment or client relaunch persistence test is claimed.

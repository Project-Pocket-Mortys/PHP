# Wild battle party switching

The PvWM path now supports voluntary and forced party switches. The
[native contract](battle-switch-contract.md) establishes the exact request:
`owned_morty_id` is the outgoing active ID and `move_id` is the incoming ID.
The SWITCH result action identifies the incoming member in `owned_morty_id`.
It changes battle identity, not deck order.

Party membership comes from the private initial `battle:start` snapshot, so
editing the current deck cannot add or remove participants in that battle.
Start validates the entire party's ownership, global ID uniqueness and stored
HP/max HP before publishing it in deck order. Existing CSV IDs still accept
surrounding whitespace. ATTACK/SWITCH lock and validate all initial owned rows;
broken bench data rejects rather than silently completing a false defeat.

When damage faints the active member and another initial participant lives,
the result is FORCE_SWITCH with battle/user/spawn still ACTIVE/BATTLE.
ATTACK then rejects until a valid replacement. The client's intervening ready
call preserves that phase. Forced switching selects the stored HP/status and
returns CONTINUE; defeat occurs only when the initial party is exhausted.

The replacement policy is explicit: voluntary switching spends the action and
the existing placeholder AI hits the incoming member for 1..3; forced replacement
receives no additional AI attack. Original initiative and switch turn cost were
not recovered. Player damage 20 and wild stats/AI/AP remain placeholders.
Switching spends no player AP/items/XP/currency and preserves both ailments.

State changes and one private result commit together. Self/stale switches
return 409, foreign/out-of-party choices 403, and malformed IDs 400, without
mutation. Concurrent duplicates serialize. RUN remains an origin-bound escape
even with missing owned rows or pending replacement; the forced native menu
does not expose it. Missing-roster legacy starts retain ATTACK/RUN only while
current active equals initial active. Malformed present rosters reject.
Legacy terminal reconciliation accepts switched roster members and old CAUGHT
markers without replaying rewards.

Pending replacement is derived from ACTIVE plus zero owned/cache HP, so no
new schema is needed. It survives ready/rejected requests/rollback, but does
not restore the UI after client restart. Capture, ASK_SWITCH/opponent
replacement, combat formulas, battle items, rewards and reconnect remain gaps.

Run `py -3 -m unittest discover -s tests/protocol -p test_battle_switching.py -v`.
The additive UUID tests first reproduced 400 for the exact native SWITCH body;
they cover both switch paths, party exhaustion, post-switch attack/RUN,
ownership/roster integrity, mutable decks, legacy states and concurrency.
The reviewed integration runner includes this suite and excludes global reseeds.

This branch starts from main `9ff1a11` with explicit pending prerequisite
`160d67e` (PR #29). No public deployment is included.

## Validation on 2026-11-04

All 58 targeted regressions passed in 175.577 seconds, including 20 switch
cases, the existing lifecycle, world-action guards, ailment snapshots, SSE
privacy and join ownership. PHP 8.3 lint passed for all 24 changed/new PHP files
including the prerequisite. JSON/source-hash/native-constructor checks and
bounded script syntax checks passed.

[Android acceptance](android-battle-switching.md) used a synthetic cloned
one-HP bench and private encounter, followed by real UI switches. The voluntary
switch produced SWITCH then AI ATTACK, fainted the temporary member and opened
the forced menu. The forced switch returned the real primary at 20/20 with no
additional AI attack. Native RUN completed the battle; all six ready/move
requests returned 200. Guarded cleanup restored both research accounts'
HP/AP, items, decks and progression exactly. No original stat formula was
inferred from this controlled fixture.

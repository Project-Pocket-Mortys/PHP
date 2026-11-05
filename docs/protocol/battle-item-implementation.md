# Battle healing, revival, AP restoration and cures

The existing PvWM `/session/battle/move` path now accepts ITEM for the twelve
effects already supported by the world item route: eight HP items, full revival,
full AP restoration, and targeted poison/paralysis cures. Current MP metadata
permits all twelve in battle. [Native evidence](battle-item-contract.md)
establishes that `owned_morty_id` is the selected target, active or bench,
while `move_id` is the item ID. This differs from SWITCH's outgoing/incoming IDs.

The selected target must belong to the immutable initial private party.
The current active member must be living, with owned HP matching the battle
cache. Pending forced replacement rejects supported ITEM requests; it does not
let a revive bypass the forced-party selection. Missing/foreign/ambiguous
records, invalid HP, ineffective effects and missing/duplicate/invalid stock
reject before consumption or AI action. Capture and other unsupported effects
retain 501 ITEM_UNUSABLE, including the legacy unsupported-capture interface.

## Ordered and durable effects

The shared world effect planner supplies the same amounts and applicability.
One transaction locks the user, battle, initial party and stock; applies the
effect; consumes exactly one unit; computes the counterattack; updates the
active HP/cache and outcome; and queues one private turn result. Full AP reads
and serializes only locked attack rows, validates unique IDs/position keys and
catalog maxima, and preserves sparse positions such as 2 and 7. Its current
one-to-four-row bound is a replacement validation policy, not a recovered
original database constraint. Stale saved maxima are repaired only while
filling a real AP deficit; metadata repair alone never consumes an item.

The ITEM action uses `success:true`, target `owned_morty_id`, `item_id`, and
`effect_value`, with the target's post-item HP/status/AP in its attacker Morty
array. The later AI action carries its separate final HP snapshot. Remaining
inventory is absolute in `player_datas.player.owned_items`, including zero.
The client applies those snapshots before their respective animations.

The explicit replacement policy is that an effective item consumes an action
and the existing placeholder AI hits the current active member for 1..3,
even when the item targeted the bench. Original retaliation, initiative and
cooldown rules remain unrecovered. Bench use retains active identity; a revived
bench member counts as a survivor if the counterattack faints the active member.
That yields FORCE_SWITCH rather than a false defeat. Player AP is not spent.

Full-HP healing, an already living revive target, a missing ailment and full AP
are ineffective and do not spend or trigger AI. Two requests competing for the
last stock cannot both consume it. Identical requests that each remain effective
may both succeed: the native constructor contains no request identity.

## Validation and reproduction

The exact native Serum request initially returned 501. UUID fixtures now cover
all supported HP amounts, active/bench targets, full revival/AP, both cures,
stock/type/ownership/roster/cache guards, pending replacement, retries, concurrency
and post-switch use/RUN. A UUID-scoped event-insert failure verifies rollback
after AP restoration, inventory consumption, AI damage and terminal world/event
writes. No research account is reseeded.

Use the installed interpreter directly to avoid Windows Store execution aliases:

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_battle_items.py -v
& $researchPython -X utf8 tools/research/validate.py
wsl -- bash tools/research/ghidra-battle-items.sh
```

This branch starts at main `9ff1a11` with explicit pending prerequisite
`8a64835` (PR #30). It adds no migration beyond the prerequisite's ailment
migration 003. World item behavior is retained. Capture, percentage variants,
cure-all/stat/damage/general items, battle ailment application/ticks, true combat
formulas, timeout resolution, rewards and reconnect UI restoration remain gaps.
No public deployment or real purchase is included.

## Acceptance on 2026-11-05

All 72 targeted regressions passed in 269.014 seconds, including 20 new battle
item cases, switching, lifecycle, world guards and ailment snapshots. PHP 8.3
lint passed for all 25 changed/new PHP files including prerequisites. Native
body/Capstone evidence, bounded script syntax and protocol source checks pass.

[Android acceptance](android-battle-items.md) verified active Serum, bench full
revival, bench AP restoration and both bench cures through native UI requests.
Ordered snapshots, final persisted effects and inventory depletion agree.
Temporary clones absorbed every counterattack; all original account rows, raw
decks and stock were restored exactly, followed by a fresh client reload.
Two expired-timer probes used explicitly labeled nonnative recovery RUN and
do not count as native move acceptance. The final AP/cure case used native RUN.

# Android battle healing-item acceptance

Acceptance uses Android 2.41.0 on the dedicated `PocketMortys_API30` AVD (`emulator-5556`, ADB port 5038) against the isolated replacement server at `http://localhost:8087`. These observations validate the replacement implementation, not original-server turn or damage policy. Static native/data evidence is documented in [the battle-item contract](battle-item-contract.md).

## Synthetic setup and preservation

`tools/research/battle_item_fixture.py` clones the primary research Morty's complete stored stats and attack rows into two fresh owned IDs using explicit-column `INSERT ... SELECT`. The temporary active member starts at HP10/20; the temporary bench starts fainted with both ailments and Outburst AP1/12. `--bench-alive` starts that bench at HP20 for an independent AP/cure case. Temporary stock adds one unit of each representative item without using an upsert. Both temporary members precede the original party, so no original member needs to become active.

Battle initiation is synthetic: a private HP1 wild spawn and the existing battle-start endpoint. Item selection and successful ITEM requests below originate from actual Android touches. No player ATTACK is used. Cleanup requires an ended RUN battle, validates every original persistent account row, reconstructs temporary HP/status/AP and stock changes from the recorded ITEM/AI action snapshots, repeats account/battle/event comparisons under locks, restores the exact original raw deck, and removes only temporary owned rows, stock, battle and events. It refuses cleanup while a battle is ACTIVE. The peer AVD is untouched.

On Windows use the explicit interpreter `$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe`; avoid Windows Python execution aliases. The helper supports `prepare`, `start`, `screen`, `record`, `cleanup`, and an explicitly labeled `recover-run` fallback. Output must remain inside ignored `.research` and each capture directory is preserved. Guard transactions are sent through PHP stdin because multiple recorded battle events can exceed Windows' command-line limit.

## Observations on 2026-11-05

The successful active/bench capture is `.research/emulator/battle-items-20261105-fast/`. Sanitized HTTP capture `revive-http.json` records:

| Native item | Target | Persisted result | Later AI action |
| --- | --- | --- | --- |
| Serum | Temporary active | HP10 → 20, actual healing value10 | Active HP20 → 17 |
| Pure Halzinger | Temporary bench, distinct owned ID | HP0 → 20, revive value100 | Active HP17 → 15 |

Both requests returned HTTP 200 with `success:true`; native request `move_id` contains the item ID and `owned_morty_id` contains the selected target ID. The active identity stays on the first clone for the bench revive. Native screenshots show the Serum syringe and “You used the Serum on Morty!” and the bench revive text “You used the Pure Halzinger on Morty!”. The later bag omits Pure Halzinger after its last unit is consumed, matching the absolute quantity 0 merge. Consecutive ITEM turns were available in this capture.

The first exploratory capture (`battle-items-20261105/`) exceeded the native 30-second turn timer before confirming an item. After expiry, item selection and RUN confirmation returned to the battle menu without emitting a move HTTP request. The fast capture later exceeded the next timer during AP-menu inspection, again without an AP request. Both cases used the helper's explicitly recorded `NONNATIVE-recovery-run.json` to end the battle, followed by verified exact cleanup. Those recovery calls are not native RUN acceptance. No timeout behavior or clock was modified. Advancing item/AI dialogue and batching 200 ms stationary touches inside the next timer window is required for reproduction.

The independent bench-alive capture is `.research/emulator/battle-items-20261105-effects/`. `final-http.json` records three more native ITEM requests and native RUN, all HTTP 200 with `success:true`. Every ITEM target is the same temporary bench ID, distinct from the active ID used for RUN.

| Native item | Bench result | Active HP after AI | Remaining stock |
| --- | --- | --- | --- |
| Pure Plutonic Rock | Outburst AP1 → 12, `pp_stat:12`, value100; both ailments retained | 10 → 9 | 0 |
| Poison Cure | Poison true → false; paralysis retained; value0 | 9 → 7 | 0 |
| Paralyze Cure (`ItemParalysisCure`) | Paralysis true → false; poison stays false; value0 | 7 → 4 | 0 |

Bench HP remains20 throughout. Each event orders ITEM before the AI ATTACK and reports the authoritative target state at that action. The final battle is CANCELLED with RUN outcome and `battle_abandoned:true`; this case has no synthetic recovery move. `cleanup.json` verifies the original account rows and raw deck were restored exactly, as did both preceding captures.

`poison-confirm.png` shows both status icons on the selected bench; `paralysis-confirm.png` subsequently shows only its paralysis icon, establishing that the native client merged the poison cure without clearing paralysis. The bag captures show consumed AP/poison stacks disappearing. The AP/cure `*-action.png` captures were taken while “Waiting for opponent...” was displayed, so they do not establish the exact subsequent effect dialogue. Their successful request, action snapshot, persisted effect and later native menu/target state are captured; the Serum/revive screenshots separately establish visible item animation/dialogue. `restored-world.png` records the returned world UI after native RUN and fixture cleanup.

For timed reproduction, prepare and restart the app before starting the synthetic battle. On the 1280×720 research display, open ITEM at `(510,560)`, select the bag row, press Use `(565,580)`, select active `(490,65)` or bench `(490,165)`, then press Use Item `(565,580)`. Use 200 ms stationary touches and approximately 850 ms between menu transitions. Swipe the bag to its bottom to reach Pure Plutonic Rock. Advance the item and AI dialogue promptly; each next native `battle/ready` starts another 30-second window. Coordinate batches used for the final case are preserved in ignored `.research/emulator/native_battle_item_taps.py`. No native APK, save, emulator clock, timeout policy or real owned stats were changed for these checks.

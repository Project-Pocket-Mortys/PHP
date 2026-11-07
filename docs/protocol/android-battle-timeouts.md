# Android battle selection timeout acceptance

These checks use Android 2.41.0 on `PocketMortys_API30` (`emulator-5556`, ADB port5038), connected to the isolated replacement server at `http://localhost:8087`. They establish replacement behavior, not original-server timeout policy.

`tools/research/battle_timeout_fixture.py` creates a fresh owned ID by copying the primary research Morty's complete stored stat and attack rows with explicit-column `INSERT ... SELECT`. It temporarily prepends that clone to the original raw deck. No stock is added, no original member becomes active, and no battle moves are necessary. A private wild spawn and battle initiation are synthetic; the Android client sends ready and its ordinary SSE connection receives expiry. The helper never posts ready, ITEM, ATTACK, SWITCH or RUN.

The server arms a persisted 30-second selection deadline on ready. On natural expiry the connected SSE poll cancels the battle, returns the player and wild spawn to WORLD, and publishes one private `battle:turn-result` with outcome `ABANDONED` (native enum 9), `battle_abandoned:false`, empty `turn_datas`, and empty player/opponent data objects. Native code remaps WIN with a true flag to ABANDONED; the false flag here uses explicit abandonment directly. The native outcome handler also raises its abandoned event to close submenus.

Cleanup requires CANCELLED with no winner/deadline, exactly one ABANDONED result and one timer, a successful native ready and no move HTTP requests. It compares the complete prepared account snapshot, including every original row, clone HP/AP, inventory and deck, then repeats account/battle/event comparisons under row locks. Only the temporary clone, its attacks and the fixture battle/events are removed; the exact original raw deck is restored. Active or unexpectedly mutated fixtures are preserved for investigation. No synthetic RUN recovery is provided.

On Windows use `C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe -X utf8`. Each case has a new ignored `.research` directory. Preserve `.research/battle-item-accounts-before.json`; run the existing `.research/battle_item_account_guard.py compare` before preparation and after cleanup. The helper supports `prepare`, `start`, `screen`, `record` and `cleanup`. `discard-unstarted` can restore a prepared fixture only before any start intent exists; it requires exact prepared rows under locks and records no acceptance claim. Restarting the app refreshes the temporary deck without clearing its data, then select Multiplayer and dismiss its tutorial overlays. Start the synthetic battle and advance its introduction. Leave the normal battle menu open, or open ITEM/SWITCH without choosing a move, and allow the actual 30 seconds to pass. Do not change emulator clocks or saved stats.

## Observations on 2026-11-05

The normal battle-menu capture is `.research/emulator/battle-timeout-menu-20261105/`. `menu.png` shows the native timer and full-health clone20/20. `expired.png` shows the world scene with its existing tutorial overlay after natural expiry. `expired-http.json` contains native ready and no move request. The recorded battle is CANCELLED with one ABANDONED result and unchanged HP/AP/inventory. `native-sse.pcap` captures the actual Android TCP stream containing the abandonment event. `cleanup.json` and the two-account baseline comparison verify exact restoration.

The Bag capture is `.research/emulator/battle-timeout-bag-20261105/`. `bag.png` shows Your Items open with the native timer and no selected item. After natural expiry `expired.png` shows the returned WORLD scene with its tutorial overlay; the Bag has closed. `expired-http.json` contains only successful native ready, with no ITEM or other move. The recorded CANCELLED battle has one ABANDONED result. Clone HP/AP, stock and original account rows are unchanged, and guarded cleanup plus the two-account baseline comparison passed. `native-sse.pcap` preserves the native stream. One ordinary app relaunch was needed after a slow Multiplayer loading screen before this battle; no app data, emulator or account was reset.

The Party capture is `.research/emulator/battle-timeout-party-20261105/`. `party-open.png` shows Select a Morty with the full-health clone marked Out, no selected member and the native timer. `expired.png` shows the returned WORLD scene with the tutorial overlay; the Party submenu has closed. Its HTTP, DB, native SSE pcap and guarded cleanup demonstrate the same single abandonment and zero move, HP, AP or inventory changes. Both research accounts match the preserved baseline after all three cleanups. The peer emulator was untouched throughout.

## Reproduce with tracked tools

The additional two-account baseline/guard mentioned above is private local
bookkeeping. The tracked fixture independently saves its full before/prepared
snapshots and performs its own locked comparisons and exact restoration, so
another developer does not need that ignored guard script. First establish the
isolated research stack, supplied APK and primary AVD/account as described in
the [emulator handoff](emulator.md); apply migration 004. Choose a new output directory:

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 tools/research/battle_timeout_fixture.py prepare --output .research/emulator/battle-timeout-repro
```

Restart the app normally to load the temporary deck, select Multiplayer and
reach WORLD. Then initiate the private synthetic encounter:

```powershell
& $researchPython -X utf8 tools/research/battle_timeout_fixture.py start --output .research/emulator/battle-timeout-repro --label start
```

Advance the introduction in Android. Remain on the battle screen, or open ITEM
or SWITCH without confirming a selection. After the native timer expires and
the client returns to WORLD, capture the recorded HTTP/DB result and screen,
then restore the fixture:

```powershell
& $researchPython -X utf8 tools/research/battle_timeout_fixture.py record --output .research/emulator/battle-timeout-repro --label expired
& $researchPython -X utf8 tools/research/battle_timeout_fixture.py cleanup --output .research/emulator/battle-timeout-repro
```

Use a fresh directory for each case. Cleanup refuses an ACTIVE battle or any
unexpected resource/account mutation. Reload the app afterward to remove the
temporary deck from its client cache. Raw artifacts stay ignored.

After the final cleanup the app was restarted normally and rejoined Multiplayer using the restored original deck. Party capture artifacts `restored-world.png` and `restored-world-clear.png` show the returned world before and after dismissing its existing tutorial overlay. The final two-account baseline comparison passed after this reload.

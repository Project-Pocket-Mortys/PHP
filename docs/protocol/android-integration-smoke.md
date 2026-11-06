# Android integration smoke

On 2026-11-04, the existing Android 2.41.0 ARM32 research client on
`PocketMortys_API30` (`emulator-5556`) passed a bounded startup/SSE/native RUN
smoke against `hayward/gameplay-integration`, HEAD
`4175e0ca0d05e4e8969180ac73d45ccc713d8004` with the current integration working
tree. These are replacement-server runtime observations, not original-server
captures. The peer emulator was untouched.

The primary app was force-stopped and relaunched with its existing data. Its
PID changed from 6309 to 7340. The title screen appeared, Multiplayer used the
existing `PMResearch01` account, and the server recorded `WORLD` in its existing
room. A freshly inserted UUID private wild spawn and a synthetic HTTP battle
start then delivered `battle:start` through the new SSE connection. Android
opened the battle UI and sent `/session/battle/ready` with HTTP 200.

The successful fixture was initiated synthetically; its move came from the
Android UI. A 200 ms touch on the visible Run confirmation produced the native
`/session/battle/move` request at 16:13:34 UTC: `type: "RUN"`, an owned Morty ID,
and `move_id: null`. The response was HTTP 200, the fixture became `CANCELLED`,
and its turn-result outcome was `RUN`. The app returned to the world scene;
the existing tutorial dialogue overlay remained visible. No separate run-away
dialogue frame was retained. Natural encounter collision was not tested.

An earlier fixture received native ready but quick UI taps produced no native
move. It was ended with a **synthetic HTTP RUN solely for fixture recovery**;
that request is not Android move acceptance. Both fixtures passed the helper's
guarded cleanup, which verified exact original player stats, active deck ID,
Morty HP/stats, attack PP and items, then removed only their own terminal battle
and recorded event rows. No HP or PP restoration was needed. Deck membership
was not edited. No emulator restart, data clearing, login reset, purchase,
crafting, item use or release operation was performed. This smoke does not
establish UDP peer liveness or any unsupported battle timeout behavior.

Ignored local evidence:

- `.research/emulator/integration-android-20261104/`: fresh startup/title/world
  frames, first fixture, synthetic recovery provenance, and `cleanup.json`.
- `.research/emulator/integration-android-20261104-prompt/`: native ready/RUN HTTP
  records, source events, exact snapshots, confirmation/world screenshots,
  `cleanup.json`, and `integration-provenance.json` containing capture/client
  SHA-256 hashes. Raw per-app logs remain ignored and may contain credentials.

Reproduction uses the manual
[`capture_battle_lifecycle.py`](../../tools/research/capture_battle_lifecycle.py)
sequence documented in [Android battle lifecycle](android-battle-lifecycle.md),
with fresh output directories and `cleanup --case RUN` for RUN-only captures.
Inspect the actual confirmation before touching Run; very short taps were
unreliable in this capture. The helper never sends moves itself.

The existing client provenance and source hash guard are documented in
[research client](research-client.md), [local transport](local-transport.md),
and [transport artifact hashes](local-transport-results.json). This smoke used
the existing installed client and did not rebuild or reinstall it; local patch
manifest and APK hashes are recorded in the ignored integration provenance.

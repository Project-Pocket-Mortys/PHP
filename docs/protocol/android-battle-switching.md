# Android battle switching acceptance

On 2026-11-04, the existing ARM32 research client on the primary
`PocketMortys_API30` emulator (`emulator-5556`) completed voluntary switching,
forced replacement, and RUN against the replacement PHP server. The account
was `PMResearch01`. The peer emulator was untouched. This is replacement-server
interoperability evidence, not an original-server response capture.

Initiation was **synthetic**: the helper inserted a private UUID wild spawn in
the account's existing room and started it by HTTP. The opponent retained the
existing 1 HP placeholder. To exercise replacement without damaging a real
owned member, the helper copied the primary's complete stored Morty stats and
attacks into a fresh owned UUID, set only that temporary member's HP to 1, and
appended it to the same active deck. Its 20 maximum HP and attack data came
from the existing primary; they were not derived from placeholder wild stats.
The app was restarted without clearing data or restarting the emulator to load
fresh player details before battle initiation.

Every tested SWITCH and RUN request came from Android taps. No synthetic move
or recovery request was needed.

| Step | Native request and server result | Android observation |
| --- | --- | --- |
| Voluntary switch | `type: "SWITCH"`, outgoing primary in `owned_morty_id`, incoming temporary bench in `move_id`; HTTP 200 | Selected the 1/20 bench in the ordinary party menu and switched it into battle. |
| Retaliation and faint | Ordered actions were SWITCH to bench, then AI ATTACK (`AttackVileSpew`, placeholder damage 2); `outcome: "FORCE_SWITCH"`; DB active bench HP 0, battle ACTIVE | Automatically opened the forced party menu, showing bench 0/20 and original primary 20/20; this menu had Switch and Stats, without the ordinary Back button. |
| Forced replacement | Native SWITCH reversed the outgoing/incoming IDs; HTTP 200; `outcome: "CONTINUE"`, one SWITCH action, no AI action; DB active primary HP 20 | Selected the original primary, displayed its 20/20 HP and returned to ordinary battle selection. |
| Exit | Native RUN with primary ID and `move_id: null`; HTTP 200; `outcome: "RUN"`, battle CANCELLED, player WORLD | Displayed the successful escape dialogue, then returned to the world. |

Both SWITCH result actions identified the incoming member in
`turn_datas[].owned_morty_id`. The client also sent a successful native ready
request while replacement was pending, and another after replacement. The
original primary retained 20 HP, its original PP and status values throughout;
all original owned rows, items and player stats remained unchanged. The wild
opponent remained at 1 HP throughout. The damage and turn-cost policy are
explicit replacement-server behavior; this capture does not recover original
server combat formulas or prove natural encounter initiation.

## Evidence and reproduction

Ignored evidence is in `.research/emulator/battle-switch-20261104/`:

- `fixture.json` and `prepared.json`: original account snapshot and temporary
  party preparation, including the original raw deck representation.
- `voluntary-result.json`, `forced-result.json`, `run-result.json`: battle
  identity/HP, ordered source events and account snapshots at each stage.
- `run-http.json`: all six sanitized native ready/move requests for this battle,
  each HTTP 200; session IDs are removed.
- `party.png`, `retaliation.png`, `forced.png`, `run.png`, `clean-world.png`:
  ordinary party, forced party/fainted bench, healthy restored primary, escape
  dialogue and returned world. Intermediate frames and per-app logcat are also
  retained.
- `cleanup.json`: exact original owned rows, attacks/PP, inventory, user stats
  and raw deck restoration verified after guarded cleanup.

The helper supports this manual sequence:

```text
py tools/research/battle_switch_fixture.py prepare --output .research/emulator/<fresh-directory>
# Restart only the app, enter multiplayer and finish its existing dialogue.
py tools/research/battle_switch_fixture.py start --label battle-start --output .research/emulator/<fresh-directory>
# Android: advance intro, SWITCH, select HP1 bench, Switch, advance turn dialogue.
py tools/research/battle_switch_fixture.py record --label voluntary --output .research/emulator/<fresh-directory>
# Android forced party: select original healthy primary and Switch.
py tools/research/battle_switch_fixture.py record --label forced --output .research/emulator/<fresh-directory>
# Android: advance dialogue, RUN, confirm Run, advance escape dialogue.
py tools/research/battle_switch_fixture.py record --label run --output .research/emulator/<fresh-directory>
py tools/research/battle_switch_fixture.py cleanup --output .research/emulator/<fresh-directory>
```

Use `screen --label <unique-name>` for intermediate screenshots. The helper
checks the primary AVD and isolated research backend, requires WORLD and no
active battle before preparation, copies an explicit column whitelist using
SQL without rewriting original rows, and requires a fresh capture directory.
Use 200 ms stationary swipe touches; very short taps were unreliable in this
emulator. Make party selections promptly because the native timer continues.

Cleanup locks and rechecks exact current account, terminal fixture battle and
recorded event rows in the same transaction. It permits only the temporary
member's expected HP1-to-0 change with unchanged temporary PP, requires original
rows and the exact appended deck to match, deletes the temporary owned member,
its attacks, fixture battle and captured fixture events, and restores the
original deck string byte for byte. It refuses an active battle. If a later
manual attempt becomes stuck, `recover-run` sends a separately labelled
**nonnative** RUN only for this fixture battle; it cannot count as Android
acceptance. Raw captures and manifests can contain credentials and remain
ignored.

See [the switch contract](battle-switch-contract.md) for recovered request and
result semantics and [battle lifecycle acceptance](android-battle-lifecycle.md)
for the earlier native RUN/WIN evidence.

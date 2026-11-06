# Android battle lifecycle acceptance

On 2026-11-04, the existing ARM32 research client on the primary
`PocketMortys_API30` emulator (`emulator-5556`) completed RUN and a one-hit WIN
against the replacement PHP server. The account was `PMResearch01`; the peer
emulator was not changed. This is replacement-server interoperability evidence,
not an original-server response capture.

Each initiation was **synthetic**: a fresh UUID private wild spawn was inserted
in the account's existing room, then an HTTP request started that encounter.
The Android client received `battle:start` through its ordinary SSE connection,
sent its own `/session/battle/ready`, and displayed the battle UI. All tested
move requests came from Android taps, not a synthetic `/battle/move` call.
Natural collision/encounter initiation was not tested.

| Case | Native request and server result | Android observation |
| --- | --- | --- |
| Initial RUN, before fix | `type: "RUN"`, valid `owned_morty_id`, `move_id: null`; HTTP 400 | Remained at “Waiting for opponent move.” |
| RUN, after fix | Same nullable move shape; HTTP 200; `CANCELLED`, `outcome: "RUN"`, player `WORLD` | Displayed “You ran away from the wild Morty!” and returned to the world after advancing the dialogue. |
| WIN | Android selected ATTACK then Outburst (`AttackOutburst`); HTTP 200; `COMPLETED`, `outcome: "WIN"`, player `WORLD` | Displayed the attack animation, “You defeated wild Morty!”, and returned to the world. |

The WIN payload contained one player action, no AI action, `xp_datas: []`, and
`rewards: []`. The client completed that sequence with those empty lists.
The fixture opponent had 1 HP. The player's HP stayed 20/20, Outburst PP changed
from 12 to 11, and owned items, player stats, XP and Morty stats were unchanged.
RUN spent no PP. These observations do not validate real combat balance,
reward calculation, or a reward-bearing victory screen. LOSE has not been
accepted on Android in this milestone.

The failed initial RUN fixture was cancelled only for recovery after capturing
its HTTP 400 and verifying unchanged HP, PP and items. The app was restarted
without clearing data or restarting the emulator. Fresh fixtures were used for
the successful RUN and WIN.

## Artifacts and reproduction

Ignored local evidence is in:

- `.research/emulator/battle-lifecycle-20261104/`: initial failure, sanitized
  native request shape, screenshots, logcat, and guarded recovery/cleanup record.
- `.research/emulator/battle-lifecycle-20261104-fixed/`: successful RUN/WIN
  snapshots, source events, sanitized native HTTP records, screenshots, per-app
  logcat and `cleanup.json`.

`tools/research/capture_battle_lifecycle.py` supports a manual capture sequence:

```text
python tools/research/capture_battle_lifecycle.py prepare --output .research/emulator/<fresh-directory>
python tools/research/capture_battle_lifecycle.py start --case RUN --output .research/emulator/<fresh-directory>
# Inspect Android, select RUN and confirm, then advance its completion dialogue.
python tools/research/capture_battle_lifecycle.py record --case RUN --output .research/emulator/<fresh-directory>
python tools/research/capture_battle_lifecycle.py start --case WIN --output .research/emulator/<fresh-directory>
# Inspect Android, select ATTACK and one available move, then advance completion.
python tools/research/capture_battle_lifecycle.py record --case WIN --output .research/emulator/<fresh-directory>
python tools/research/capture_battle_lifecycle.py cleanup --case WIN --output .research/emulator/<fresh-directory>
```

Use `screen --label <name>` to retain intermediate frames. The helper checks
the primary AVD identity, snapshots the real account before adding fixtures,
does not send battle moves, and refuses cleanup of active battles or unexpected
account changes. Cleanup rechecks the account snapshot under row locks in the
same transaction as its updates, permits exactly one PP decrement for one
recorded WIN, and restores that PP conditionally. It deletes only fixture battle
IDs and recorded source event IDs. The completed capture verified the original
HP, PP, items and player stats after cleanup.

Raw logcat and server captures can contain credentials and remain ignored.
The helper's fixture HTTP extracts omit `session_id`.

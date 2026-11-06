# Android FullRecover acceptance

`ItemFullRecover` is **Pure Curum** in Android 2.41.0. Its native `Cure/All`
effect restores a living eligible Morty to maximum HP and clears poison and
paralysis. It preserves attack AP. The Cure result uses `effect_value:0`; that
value does not represent the amount of HP restored. Static evidence and runtime
policy are described in [the FullRecover contract](full-recover-contract.md).

## Guarded reproduction

Use the isolated replacement server at `http://localhost:8087`, primary research
account `PMResearch01`, and `PocketMortys_API30` (`emulator-5556`, ADB port 5038).
These checks exercise replacement-server behavior, not the original service.
Use a fresh ignored capture directory for each independent world or battle case.

```powershell
$fixturePython = "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\python.exe"
& $fixturePython -X utf8 tools/research/full_recover_fixture.py prepare --mode world --output .research/emulator/<fresh-world-directory>
# Reload Android. Your Items > Pure Curum > Use > second clone > Use Item.
& $fixturePython -X utf8 tools/research/full_recover_fixture.py record --label used --output .research/emulator/<fresh-world-directory>
& $fixturePython -X utf8 tools/research/full_recover_fixture.py cleanup --world-used --output .research/emulator/<fresh-world-directory>
# Reload Android to fetch the restored account.

& $fixturePython -X utf8 tools/research/full_recover_fixture.py prepare --mode battle --output .research/emulator/<fresh-battle-directory>
# Reload Android before starting the synthetic battle.
& $fixturePython -X utf8 tools/research/full_recover_fixture.py start --output .research/emulator/<fresh-battle-directory>
# Native ITEM > Pure Curum > Use > second clone > Use Item. Advance dialogue.
# Leave through native RUN, or let the unchanged native move timer abandon it.
& $fixturePython -X utf8 tools/research/full_recover_fixture.py record --label ended --output .research/emulator/<fresh-battle-directory>
& $fixturePython -X utf8 tools/research/full_recover_fixture.py cleanup --output .research/emulator/<fresh-battle-directory>
# Reload Android again. Verify original account rows and peer account baseline.
```

The tracked helper clones the original party leader's complete stored stats and
all attack rows into two fresh IDs, then changes only the clones to HP10/20,
both ailments, and AP1. It prepends them to the original raw party, ensuring the
active and bench targets are synthetic. It supplies exactly one temporary unit
of FullRecover, updating an existing stack or inserting one row; the schema has
no logical-stack uniqueness constraint, so it never uses an upsert.

Battle initiation uses a synthetic private HP1 spawn and the existing start
endpoint. All item use and exit moves must come from Android. AI placeholder
damage remains the existing 1–3 per consumed action. The helper never posts
ready, item, attack, or RUN moves and never changes time or app data.

Cleanup refuses active battles, reconstructs the permitted clone effects and
stock use, verifies AP is unchanged, and compares complete account, battle and
event rows again under transaction locks. It restores the exact original raw
deck and stock and removes only the temporary clones and battle artifacts.
Unexpected changes stop cleanup. A no-use fixture can be cleaned without an
acceptance claim. Private original-account baseline guards are additional
bookkeeping; the tracked fixture contains the reproduction and cleanup logic.

## Observations on 2026-11-05

The world capture is `.research/emulator/full-recover-world-20261105/`.
Native `/session/use-item` at 16:31:10 UTC returned HTTP200, `is_success:true`,
`effect_value:0`, HP20, both status flags false, Outburst AP1/12 and absolute
FullRecover quantity0. The selected second clone began at HP10/20 with both
status icons. `dialogue.png` shows HP20/20, neither icon and **“Your Morty is
fully restored.”** The next bag screenshot omits the consumed Pure Curum row.
The first clone and every original row remained unchanged.

The successful bench battle capture is
`.research/emulator/full-recover-battle-20261105-fast/`. Native ITEM at
16:37:25 UTC targeted the second clone, distinct from the battle's active ID.
Its HTTP200 response and ITEM action report success, value0, HP20 and both
flags false. That action precedes the separate AI ATTACK: damage3 to the active
clone, HP10 → 7. The bench remains at HP20 with AP1/12, stock becomes0, and
active identity does not change. `dialogue.png` reads **“You used the Pure Curum
on Morty!”** `post-battle-party.png` shows both icons retained on the active
HP7 member and neither on the full-HP bench. `post-battle-stats.png` confirms
bench HP20/20 and Outburst AP1/12. Native RUN at 16:37:36 UTC returned HTTP200;
the final battle is CANCELLED with RUN outcome. No synthetic exit was used.

The earlier `.research/emulator/full-recover-battle-20261105/` attempt touched
ITEM during the intro transition and reached the bag without selecting a row.
It emitted native ready only, consumed no stock, and ended through the unchanged
timer with ABANDONED outcome. Its no-use cleanup verified both clones unchanged.
That attempt is not item or RUN acceptance.

Every cleanup restored exact original account rows, raw deck and inventory
under locks. The additional private two-account baseline comparison passed
before preparation and after every cleanup; the peer AVD was untouched. The
primary app was reloaded after the final cleanup to fetch original state.
All raw HTTP records, row snapshots, screenshots and cleanup evidence remain
ignored under `.research`.

On the 1280×720 research display, enter the bag with ITEM `(510,560)`, select
Pure Curum `(580,450)`, press Use `(565,580)`, select the bench `(490,165)`,
then Use Item `(565,580)`. Let the intro/menu transition settle before ITEM:
the successful batch waited five seconds after start, advanced at `(640,680)`,
waited another 2.5 seconds, then opened ITEM and waited 1.5 seconds. Use 200 ms
stationary touches and advance the item/AI dialogue promptly before native RUN.
Fresh app loads also display onboarding overlays; dismiss those locally before
starting the battle. No timeout, clock, APK, app data or original owned stats
were changed.

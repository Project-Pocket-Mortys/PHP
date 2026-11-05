# Android account Shiny Potion acceptance

This guarded exercise targets the isolated research backend at localhost:8087,
Android 2.41.0 on `PocketMortys_API30`, ADB port 5038,
`emulator-5556`, and existing account `PMResearch01`. The helper compares
`PMResearch02` throughout; its emulator is untouched. Raw snapshots,
HTTP records, logs and screenshots remain inside ignored `.research`.

## Evidence and boundary

The helper reads actual MP `ItemInfo` and English `EN` TextAssets with
`export_item_effects.load_text`. It pins the MP bundle SHA-256
`f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413`
and ItemInfo SHA-256
`ab713ae7e06f8b492628d10b73580d4016756d57072d04b5be43f271e7305a39`
(path ID `8663868515058661470`). The English bundle SHA-256 is
`bbe4b3036a907354dd7cad8122c0f557491e3259b6f4f349eda27caa913bc7a8`,
EN SHA-256
`841eed65c78a058635eef4993f07b0a5592e8906f77c95027604cc3c57d4e1c4`
(path ID `2069814988615685635`). Both use Unity 2022.3.62f1.

`ItemShinyPotion` has effect `ShinyPotion`, `use_world=true`,
`use_account=true`, `use_self=false`, and `use_battle=false`. Its shipped
description explicitly specifies two hours. No encounter probability appears
in these records; this exercise makes no spawn probability change or claim.

The native contract uses `/session/use-shiny-potion` with only `session_id`.
Its response contains `quantity`, `shiny_potion_active`, `end_usage_time` and
`shiny_potion_item_id`. Startup player details hydrate active state from
`play_shiny_potion: [{"end_usage_time":"<UTC wall time without Z>"}]`; inactive state
uses `play_shiny_potion: null` to clear the native model.

The helper adds one explicitly synthetic temporary stock row only after
confirming both original expiry fields are NULL and no original potion stack
exists. It snapshots all original Morties, HP, attacks/AP, raw inventory rows,
decks, progression and the new `users.shiny_potion_expires_at` column for both
accounts. Activation must originate in native UI. The helper never calls an
activation API. No purchases, capture, currency spending, reset, wipe, reseed,
clock advancement or two-hour wait belongs to this exercise.

## Reproduction

Complete server tests before preparation; run the fixture serially because
existing unindexed lock scans can interfere with concurrent tests. Use the
explicit Python executable to avoid Windows Store aliases:

```powershell
$python = 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$capture = '.research/emulator/shiny-potion-<fresh-label>'
& $python -X utf8 tools/research/shiny_potion_fixture.py prepare --output $capture
```

For optional appearance acceptance, add `--appearance-position x,y` only for
a reviewed visible empty world tile. In the same guarded transaction the
helper publishes one fresh synthetic `MortyDefault` identity through the
existing event helper, with base `Normal` and `shiny_if_potion=true`, then
restricts the new event row to the primary account before commit. This is a
deterministic fixture flag, not a recovered encounter probability. Capture its
ordinary appearance before activation and shiny appearance while active,
without entering battle, capturing or attacking. The exact event row is
recorded, compared throughout and locked again during cleanup; only its
recorded ID and UUID may be deleted. The final fresh reload removes its
client model. The peer receives no synthetic event.

If preparation committed but its final snapshot was interrupted,
`finish-prepare` checks the exact original accounts plus exactly one temporary
quantity-one potion and records that state without database mutation.

Freshly restart the app and enter multiplayer. Open the PDA, choose Items,
select Shiny Potion and activate using its account item UI. Record the
countdown and zero remaining stock. If a paid purchase is required to reach
activation, stop without buying and retain the missing eligible-path evidence.

```powershell
& $python -X utf8 tools/research/shiny_potion_fixture.py record --output $capture --label native-active
```

Restart the app again and return to multiplayer WORLD. Verify the countdown
rehydrates from the same server deadline, without a second activation request
or stock charge. If the UI offers activation while already active, capture
its disabled/no-request behavior. This check does not invent stock or spend
currency to expose another purchase path.

```powershell
& $python -X utf8 tools/research/shiny_potion_fixture.py record --output $capture --label active-reloaded
& $python -X utf8 tools/research/shiny_potion_fixture.py cleanup --output $capture --used
```

Cleanup accepts exactly one successful native activation whose request body
contains only `session_id`, quantity is zero and UTC deadline is approximately
7200 seconds after capture time. The entire two-account state must equal the
reconstructed state: only the synthetic stack quantity and primary account
expiry may differ. It repeats every guard under row locks, requires exact
zero quantity and recorded deadline, removes only the temporary stock row,
and restores the original raw expiry. It refuses unexplained changes.
If no activation occurred, omit `--used`; the exact prepared state is required.

Freshly restart again, enter multiplayer WORLD, and verify the native potion
has cleared before running the final independent checks:

```powershell
& $python -X utf8 tools/research/shiny_potion_fixture.py verify --output $capture --label inactive-reloaded
& $python -X utf8 .research/battle_item_account_guard.py compare
```

## Native observations, 2026-11-05

Raw evidence is retained in `.research/emulator/shiny-potion-20261105/`.
The original independent two-account baseline comparison passed. A short
outbound native UDP capture, decoded with the existing placement decoder,
located the primary at tile (30,35). One private synthetic Normal/flagged
MortyDefault was published at adjacent tile (28,35); no battle was entered.
Its exact original event row is retained in `prepared-event.json`.

`prepared-items.png` and `potion-selected.png` show Shiny Potion stock 1/10,
its shipped two-hour description and enabled account Use button. Initial
native Use probes reached the slashless URL but returned Apache 404 before
the endpoint rewrite existed. Both accounts remained exactly equal to the
prepared snapshot: no charge or expiry. A subsequent UUID-only routing
regression shares the capture log but belongs to a separate synthetic account;
its quantity-one response is excluded by the native fixture's zero-stock and
exact recorded-deadline checks.

After the route fix, one native Use returned quantity zero and active true.
`activated-native.png` shows the new potion icon and `1h 59m` countdown plus
the native first-use dialogue. The app's dialogue independently states two
hours. `stock-zero.png` shows only the original Chip and Serum; Android hides
the consumed zero-stock potion. Therefore a second-use button is unavailable
in this fixture, and no purchase or extra stock was introduced to expose it.

The private world Morty displayed a purple star both before and after use
(`inactive-world.png`, `active-world.png`). That world icon denotes division,
not a proven Shiny material change. No world appearance transition is claimed.
The conditional model getter is established separately by
[native contract research](shiny-potion-contract.md); private PvWM variant
regression tests exercise the server's corresponding battle snapshot policy.
The inspected material consumer is a following-Morty actor, so this exercise
does not claim a demonstrated native battle visual effect.

An initial fresh restart received the active startup array and unchanged
persisted deadline, but showed no countdown (`active-reloaded.png`,
`active-reloaded-http.json`). Emulator and server UTC clocks agreed within
one second; the emulator's local time zone was UTC-5. Native startup uses
`DateTime.Parse` with default styles, which converts a Z-suffixed timestamp
to local wall time, then compares its ticks with `UtcNow`. That comparison
incorrectly cleared the unexpired potion in this time zone. This capture is
retained as failed reload evidence.

The compatibility fix changes only startup serialization: it sends the stored
UTC wall time without a zone suffix, preserving its ticks through that native
parse/compare sequence. The typed activation response retains its ISO UTC Z
timestamp; the database expiry remains unchanged. After another fresh app
restart, `startup-compatible-world.png` shows the potion countdown at
`1h 49m`. Its HTTP capture records the same deadline's UTC wall time, and its
account snapshot matches exactly the reconstructed one-use state. There was
no additional native activation or charge. Zero-stock inventory remains
hidden, so an already-active Use control is unavailable in this fixture.

Cleanup then passed the exact reconstructed two-account guards under row
locks, verified quantity zero and the original native activation deadline,
deleted only the temporary stock row and recorded private event ID, and
restored the original NULL expiry. `cleanup.json` records that result.
After a final fresh app restart, `final-inactive-verified.png` shows multiplayer
WORLD with neither potion HUD nor the synthetic private wild. The latest
native player-details response contains `play_shiny_potion: null`.
`inactive-reloaded-verified.json` and the independent preexisting two-account
baseline comparison both pass, including original HP/AP, inventory, decks and
progression; the helper additionally verifies the explicit expiry column and
private event absence. The peer emulator was untouched throughout.

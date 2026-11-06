# Shiny Potion activation and durable expiry

The missing `POST /session/use-shiny-potion` endpoint now consumes one owned
`ItemShinyPotion` and activates it for two hours. Duration, dedicated request,
inventory merge and timer consumers come from [native and MP data evidence](shiny-potion-contract.md).
Existing spawn variants and `shiny_if_potion` flags are preserved; no encounter-rate
formula is introduced.

## Wire and persistence

The request contains only `session_id`. Success is the typed, unwrapped object:

```json
{"quantity":0,"shiny_potion_active":true,"end_usage_time":"2026-11-05T18:00:00.000000Z","shiny_potion_item_id":"ItemShinyPotion"}
```

`quantity` is actual absolute remaining stock. The callback merges it before
setting the local active flag/end time. The illustrated date is replaced with
the actual persisted database expiry, including an explicit UTC suffix.

Apply additive migration `005-shiny-potion-expiry.sql` before loading the new
handlers. It adds nullable UTC `users.shiny_potion_expires_at` with microsecond
precision; historical accounts remain inactive. It is repeatable and leaves
the original SQL dump unchanged.

Activation locks exactly one matching session user, verifies an unambiguous
player identity, then locks its one matching inventory row. Missing, duplicate,
invalid or empty stock cannot be charged. An unexpired activation rejects
without consumption or extension. Stock and `now + 2 hours` commit together;
a forced late stock-write failure rolls back the deadline. Numeric row ID and
owner predicates prevent broad expiry writes. Concurrent uses cannot consume
twice while the first activation remains active.

Expiry comparisons use the database UTC clock. Expiration needs no worker or
cleanup write: past values are inactive. A later use starts two hours from
current time. Reads do not extend the timer.

Active `player-details.play_shiny_potion` uses a dictionary array with UTC wall
time and no timezone suffix:

```json
[{"end_usage_time":"2026-11-05T18:00:00.000000"}]
```

Inactive, expired or ambiguous identity reads return `null`. Never return `[]`:
the native setup function indexes element zero. Fresh login and app restart
rehydrate the timer without another charge. Client expiry callbacks clear the
local active state using its UTC end time. The suffix difference is intentional:
the raw startup parser uses `DateTimeStyles.None`, converts zoned strings to
local time, then compares unnormalized ticks with `UtcNow`. A plain UTC wall
string preserves the required ticks independently of device timezone. The
typed activation response retains `Z`. Both describe the exact same stored
deadline; neither extends it. See [native DateTime evidence](shiny-potion-datetime.md).

Errors use actual `eUseShinyPotionError` names: HTTP409
`NOT_ENOUGH_SHINY_POTIONS` or `ALREADY_ACTIVE_SHINY_POTION`; malformed, invalid
session, method/state or internal failures use `UNKNOWN` with 400/401/405/409/500
statuses. Their envelope is `{"error":{"code":"..."}}`. HTTP choices and the
world/unresolved-battle restriction are replacement policies, not proven
original-service parity. The native constructor itself has no battle-state check.

## Wild variant compatibility

Native code applies the existing flag to Normal wild Morties while the local
potion is active. Shiny/Pulsing and owned Morties retain their variants. Current
battle DTOs use spawn UUIDs rather than the native wild sentinel, so a new PvWM
snapshot explicitly promotes Normal to Shiny when this player's persisted
potion is active and the existing flag is true. Battle and owned IDs, shared
base variants/flags and other accounts remain unchanged. Running battles keep
their selected variant after expiry. This follows the native conditional rule
while retaining the server's established identity contract.

Capture, stat generation, XP and encounter-rate formulas remain unresolved;
this does not enable capture or establish original spawn probabilities.

## Reproduction and checks

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/migrate.php
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_shiny_potion.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_shiny_potion_battles.py -v
& $researchPython -X utf8 tools/research/validate.py
wsl -- bash tools/research/ghidra-shiny-potion.sh
```

The missing endpoint first failed activation; the previous battle snapshot
failed the active flagged-variant case. Thirteen activation/identity cases now
pass, covering expiry/reactivation, concurrency, role/stock guards, startup
shape/privacy, rollback and migration on an original-schema copy. Four battle
variant cases pass (9.906 seconds), and 29 existing lifecycle and ailment/player
data cases passed in the preceding combined run: 46 distinct verified cases.
The additional native slashless POST test first reproduced Apache404, then
passed (2.549 seconds) after adding the exact internal rewrite. It verifies
the URL/body remain intact with no redirect. The earlier activation/identity
runs passed in 48.283 seconds plus the focused ambiguity checks (10.616 seconds).
The startup timezone regression first failed with a `Z` value and then passed
(2.799 seconds); three affected activation/expiry cases passed in 9.740 seconds.
No emulator account is reseeded. [Android acceptance](android-shiny-potion.md)
records the separate native UI checks.

Android activation consumed one temporary potion, hid its zero stock and
displayed the two-hour dialogue/countdown. A fresh restart in UTC-5 reproduced
the initial zoned-startup failure; after the startup-only compatibility fix,
another restart restored `1h49m` from the same persisted deadline without a
second use. Guarded cleanup restored original stock and NULL expiry for both
accounts and removed the private synthetic event. A final fresh WORLD reload
had no potion HUD or synthetic wild. Both account guards passed independently.
No immediate WORLD Shiny material transition is claimed from the screenshots.

This branch starts from main `9ff1a11` with pending prerequisite PR #34 at
`d87a15e`, including its dependency history. Completed README features and
attribution remain the baseline. No deployment or real purchase is included.

The [remaining item audit](remaining-item-evidence.md) explains the unresolved
seed amounts, stat caps, growth/XP and percentage rounding. Single-player
values are not substituted for missing multiplayer contracts.

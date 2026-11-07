# Learn-attacks preserves empty slots

Native attack edits with one to three moves now store only actual attacks at
their original positions. Android 2.41.0 submits four entries, with JSON null
for each empty slot. The route previously cast null to an empty string and
inserted invisible attack rows. A later full AP rock examined those rows and
rejected the unknown empty attack ID, preventing restoration of valid moves.
The [bounded native contract](learn-attack-slots-contract.md) establishes the
request shape, lab slot holes and response position handling.

For example, `attack_ids:["AttackLick",null,"AttackFlail",null]` now persists
two rows at positions 0 and 2. The reply and subsequent player-details read
retain those positions. Skipping null while retaining the position counter
also handles leading, adjacent and trailing holes. Existing dense arrays of
up to four attacks continue to work.

The route keeps the first four submitted entries. An entry whose retained
slots are all null is skipped before deleting any attacks, matching the
existing empty-entry behavior. This is replacement-server policy for such
entries, not proof of an original-service delete-all operation. Strict null
is the sole newly recognized empty-slot value; other legacy input handling
is unchanged. No historical invalid rows are migrated.

Existing authentication, ownership checks, transaction and shared-battle
membership guard still apply. The response continues to preserve canonical
legacy booleans and durable trade reservations. This change adds no fee,
coupon debit, species/level eligibility rule or `morty_labs` behavior. Native
lab requests set that flag true and level-up requests set it false; the
replacement route retains its existing behavior of ignoring it.

The existing `pp=pp_stat=8` remains a placeholder. The native client locally
initializes new attacks from static maxima, but its request sends no AP and
the original server's AP reset/preservation policy remains unknown. Removing
empty attack rows closes one AP-rock failure: attacks whose static maximum
is below 8 can still fail the rock's consistency checks. This repair does
not establish AP-learning parity or repair every AP-restoration failure.

## Verification

The focused regression module is
[`test_learn_attack_slots.py`](../../tests/protocol/test_learn_attack_slots.py).
Its baseline reproduces a native-shaped edit succeeding before Pure Plutonic
Rock returns HTTP 409 because of the newly stored empty-ID rows. The tests
use valid attacks with maxima at least 8 (`AttackLick=18`, `AttackFlail=10`,
`AttackOutburst=12`) to isolate that defect from the retained PP placeholder.
They cover slot positions, persistence, all-null preservation and existing
integrity behavior with additive disposable fixtures.

All 35 selected backend cases pass: 12 new slot regressions, 5 existing
mutation-flag cases, 12 full-restore cases and 6 party-writer guard cases.
The new cases include full AP-rock use in world and PvWM battle after a
native-shaped edit, with real attack maxima and preserved positions. Eleven
new cases passed first in 28.620 seconds; the added battle case then passed
in 5.577 seconds. The adjacent module durations were 25.984, 128.706 and
42.341 seconds, respectively. PHP route lint, source-hash/research validation
and the fresh native wrapper pass. Read-only retained-account/save guards
also pass; these checks do not constitute a new Android gameplay capture.

The [native receipt](learn-attack-slots-contract.md) uses REA 6.8.0, a pinned
Android 2.41.0 ARM64 binary and metadata-bounded Ghidra/disassembly. There is
no new Android interaction or original-service capture in this round.
This repair adds no schema migration or public deployment. The branch starts at
`0560ed8` (PR #64), above main `9ff1a11`; original completed-feature claims
and attribution remain intact.

Against the existing isolated research stack, reproduce serially:

```powershell
$researchPython = 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$slotModules = @(
    'test_learn_attack_slots.py',
    'test_mutation_morty_flags.py',
    'test_full_restore_items.py',
    'test_party_writer_guards.py'
)
foreach ($slotModule in $slotModules) {
    & $researchPython -X utf8 -B -m unittest discover -s tests/protocol -p $slotModule -v -f
    if ($LASTEXITCODE -ne 0) { throw "Failed: $slotModule" }
}
docker compose -f compose.research.yaml exec -T web php -l /var/www/html/session/owned_morties/learn-attacks/index.php
if ($LASTEXITCODE -ne 0) { throw 'Learn-attacks route lint failed' }
& $researchPython -X utf8 -B tools/research/validate.py
if ($LASTEXITCODE -ne 0) { throw 'Protocol validation failed' }
wsl -- bash tools/research/ghidra-learn-attack-slots.sh
if ($LASTEXITCODE -ne 0) { throw 'Bounded native evidence reproduction failed' }
```

Do not run another database-mutating suite alongside the regression module.

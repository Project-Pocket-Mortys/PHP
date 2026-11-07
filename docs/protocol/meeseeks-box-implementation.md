# Mr. Meeseeks Box in wild battles

The backend adds one bounded player action: use an owned `ItemMrMeeseek` to
defeat the current wild Morty in the existing PvWM battle flow. The
[native and asset contract](meeseeks-box-contract.md) establishes the battle-only
enemy effect, the request actor, and the partial enemy HP snapshot. It introduces
no damage, accuracy, reward, growth or capture formula.

## Request and committed result

The existing `POST /session/battle/move` body uses `type:"ITEM"`,
`move_id:"ItemMrMeeseek"`, and `owned_morty_id` equal to the player's current
active owned Morty. That field identifies the actor for this non-self item;
it does not accept the wild spawn ID or a bench target.

The ITEM result carries `success:true`, an empty `attacker_morty_datas`, and
`defender_morty_datas` containing the wild spawn's `owned_morty_id` and `hp:0`.
`effect_value` reports the enemy HP before the item. This numeric convention is
explicit replacement-server policy: the recovered DamageHP result message does
not read its magnitude. The existing partial-snapshot consumer applies enemy HP.

Successful use consumes exactly one unit and completes the battle with WIN.
There is no AI counterattack. Player and bench HP, AP, statuses, active identity,
decks, XP and currency remain unchanged. The existing terminal flow removes the
wild snapshot, restores the user to WORLD, and queues the room notifications
and one initiator-private terminal result in the transaction. The result retains
the existing empty XP and reward arrays and reports absolute item stock,
including zero.

## Integrity and boundaries

The existing user/battle locks, initial private start evidence, active-party
identity, deadline, pending replacement, room and wild-spawn checks apply.
Absent, duplicate, malformed or insufficient stock rejects without consumption.
The effect, stock charge, terminal record and event queue inserts must commit
together. Failure rolls back all of them. A completed-battle retry cannot spend
another unit or publish another terminal result; this does not establish a
general active-turn nonce or interrupted-battle replay protocol.

Native menu filtering permits ordinary wild opponents and excludes RAID_BOSS
and MOVING_MORTY. This implementation covers the existing PvWM route only.
World use keeps its existing unsupported response; shared/friend/bot/event
battles, purchases, capture, original combat balance and original reward rules
remain separate. No migration or public deployment is added.

## Verification

The operation inventory records refreshed route and helper source hashes.
All 17 additive Meeseeks cases pass in 73.686 seconds, including depletion to
zero, completed retry, concurrency and late event-insert rollback. Both changed
PHP files pass lint; protocol JSON, constructor fields and source evidence
validation pass. The full serial run passes all 106 cases: 17 new Meeseeks,
20 existing battle-item, 20 switching, 24 lifecycle and 25 timeout cases.
The [Android follow-up](android-meeseeks-box.md) now verifies native item use,
the Meeseeks animation, victory and depletion to zero with guarded synthetic
setup. It preserves the original account rows after fixture-only cleanup.
This does not establish natural encounter initiation or original-service rules.

Against the dedicated Compose research backend with its existing prerequisite
migrations, run these five exact modules serially. Each uses isolated fixtures;
do not run another database-mutating suite alongside this sequence. The
recorded module durations were 73.686, 111.871, 84.620, 40.955 and 47.727 seconds
in that order.

```powershell
$researchPython = 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$battleModules = @(
    'test_battle_meeseeks.py',
    'test_battle_items.py',
    'test_battle_switching.py',
    'test_battle_lifecycle.py',
    'test_battle_timeouts.py'
)
foreach ($battleModule in $battleModules) {
    & $researchPython -X utf8 -m unittest discover -s tests/protocol -p $battleModule -v -f
    if ($LASTEXITCODE -ne 0) { throw "Failed: $battleModule" }
}
docker compose -f compose.research.yaml exec -T web php -l /var/www/html/lib/battle_items.php
if ($LASTEXITCODE -ne 0) { throw 'Item helper lint failed' }
docker compose -f compose.research.yaml exec -T web php -l /var/www/html/session/battle/move/index.php
if ($LASTEXITCODE -ne 0) { throw 'Battle route lint failed' }
& $researchPython -X utf8 tools/research/validate.py
if ($LASTEXITCODE -ne 0) { throw 'Protocol validation failed' }
wsl -- bash tools/research/ghidra-meeseeks-box.sh
if ($LASTEXITCODE -ne 0) { throw 'Bounded native evidence reproduction failed' }
```

The branch is based on `48d0c50` (PR #62) above main `9ff1a11`. Existing
prerequisite migrations remain required; this feature adds no schema change.
The root README's completed-feature claims and attribution are preserved.

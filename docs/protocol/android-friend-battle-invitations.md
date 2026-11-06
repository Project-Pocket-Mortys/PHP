# Android friend battle invitation acceptance

This exercise targets the isolated replacement backend at
`http://localhost:8087`, Android 2.41.0, and the existing research accounts.
ADB port 5038 connects `emulator-5556` (`PocketMortys_API30`, primary) and
`emulator-5558` (`PocketMortys_API30_Peer`, peer). Preserve both apps' userdata.
Raw snapshots, tokens, screenshots and capture records stay in ignored
`.research`; they must not be copied into published documentation.

The [native contract](friend-battle-invite-contract.md) establishes the actual
invitation routes and UI callbacks. The
[implementation](friend-battle-invitation-implementation.md) documents the
replacement server's policies. This acceptance covers native send, recipient
decline and sender cancellation. It does not select Accept or start combat.

## Guard and reproduction

Finish the HTTP, SSE and regression suites first. Run this exercise serially:
the HTTP capture middleware redacts reply tokens, so concurrent invitation tests
would make native response attribution ambiguous.

```powershell
$python = 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$capture = '.research/emulator/friend-battle-invitations-<fresh-label>'
& $python -B -X utf8 tools/research/friend_battle_invite_fixture.py preflight --output $capture
& $python -B -X utf8 tools/research/friend_battle_invite_fixture.py prepare --output $capture
```

Preparation retains complete original saves and all touching friendship,
battle and invitation rows before its first mutation. It requires both players
in WORLD, no active battle in either participant column, no pending original
invitation, an absent original pair and NULL potion expiry. It reuses the
guarded social probe to create and approve one new friendship through synthetic
social APIs. Those setup calls are explicitly separate from native invitation
evidence. Original save fields, HP/AP, inventory, decks, progression and room
and world IDs remain compared; connection fields may change during fresh login.

Freshly force-stop and launch both existing apps so they establish SSE
connections using the current server implementation. Enter multiplayer WORLD,
then open both Friends screens and select the other research account. Prepare
both views before sending: the default invitation lifetime is 60 seconds.
Do not reset, reinstall, clear storage, alter saves or use purchases.

Start the bounded observer in a separate process and wait for both readiness
messages. It opens additional authenticated replacement-server SSE connections;
it does not capture the Android apps' network sockets. It stores only session
readiness and invitation/battle events, with raw payloads kept private.

```powershell
& $python -B -X utf8 tools/research/friend_battle_invite_fixture.py observe --output $capture --label decline --duration 60
```

Tap Battle on the primary's native friend controls. Verify the primary waiting
popup and peer incoming invitation popup, retaining screenshots with unique
labels. Tap the peer's native Deny control. Confirm both popups clear and record
again. The sanitized research HTTP log must show native create with `PvF` and
response with Boolean `accept:false`, both HTTP 200. The persisted invitation
must be `DECLINED`.

Repeat with observer label `cancel`. Send another invitation using the primary's
native Battle button, verify both popups, then use the primary waiting popup's
Cancel control. The native revoke request must return HTTP 200 and the second
invitation must become `REVOKED`.

```powershell
& $python -B -X utf8 tools/research/friend_battle_invite_fixture.py record --output $capture --label native-declined --screens
& $python -B -X utf8 tools/research/friend_battle_invite_fixture.py record --output $capture --label native-cancelled --screens
& $python -B -X utf8 tools/research/friend_battle_invite_fixture.py acceptance --output $capture
```

The fixture adopts only new canonical primary-to-peer UUIDs matched to captured
native create results. It retains exact tokens and immutable row identity for
cleanup checks. Acceptance requires two native creates, one decline and one
revoke; both observer captures must show recipient-only received delivery with
the recipient token and public sender fields, then ID-only terminal events to
both intended roles. No observer may see accepted or battle-start events.
Paired native screenshots establish UI consumption separately from the
additional observer connections.

Cleanup first removes only the exact newly created friendship through the
social API. It then takes sorted user locks, verifies complete invitation rows
and terminal state against the tracked records, and deletes only those two new
invitation IDs. Original invitations are never deleted or restored. Unexpected
actors, rows, state or tokens stop cleanup for inspection.

```powershell
& $python -B -X utf8 tools/research/friend_battle_invite_fixture.py cleanup --output $capture
```

Freshly reload both apps again, enter WORLD and confirm the synthetic friend is
absent after the normal friend-list refresh. Perform final checks after those
reloads, including the independent preexisting account guard:

```powershell
& $python -B -X utf8 tools/research/friend_battle_invite_fixture.py verify --output $capture --label final-reloaded --screens
& $python -B -X utf8 .research/battle_item_account_guard.py compare
```

## Execution status

The serial 2026-11-05 run used
`.research/emulator/friend-battle-invitations-20261105/`. Preflight found both
original accounts in WORLD, the original friendship absent, no touching battle
rows and no touching invitation rows. Preparation retained those baselines and
created exactly one accepted friend pair through the social setup APIs.
Both apps were freshly launched with their existing userdata and returned to
WORLD. Existing tutorial messages were dismissed without changing gameplay.
Both Friends screens showed the other account ONLINE before invitation actions.

`decline-pending-primary.png` shows the waiting-for-reply popup, and
`decline-pending-peer.png` shows the incoming battle invitation naming the
primary account. The peer's red dismissal button sent Boolean `accept:false`.
`native-declined-primary.png` shows “The battle invite was declined.” and
`native-declined-peer.png` shows the cleared incoming popup. The first exact
canonical invitation row became `DECLINED`.

`cancel-pending-*.png` shows the corresponding waiting and incoming popups for
the second invitation. The primary's waiting-popup dismissal sent revoke.
`native-cancelled-*.png` shows both popups cleared, and the second row became
`REVOKED`. All four native invitation POSTs returned HTTP 200, in exact order:
create, response with `accept:false`, create, revoke. No Accept action was used.

`acceptance.json` passed. Separate `decline-*-observer.jsonl` and
`cancel-*-observer.jsonl` captures verify one received event for each invitation
on the peer observer, with the exact recipient token, `PvF`, positive remaining
TTL and the four public sender fields. The primary observer received no incoming
invitation or recipient token. Both observers received their appropriate ID-only
terminal events, and none received accepted or battle-start events. These are
additional replacement-server session streams, not a native wire capture;
paired screenshots and native HTTP records separately establish app behavior.

Cleanup removed only the exact setup friendship through the social API, then
deleted only the two tracked terminal invitation rows after full-row checks under
sorted user locks. `cleanup.json` confirms the original save, friend, battle,
private battle-event and invitation baselines, including the initially empty
invitation rows. No original account or friend data was restored through SQL.

Both apps were then force-stopped and freshly launched again, returned through
multiplayer login to WORLD, and showed empty Friends lists after native refresh
(`final-empty-friends-primary.png` and
`final-empty-friends-peer-confirmed.png`). `final-reloaded-*.png` shows both
original named accounts back in WORLD. `final-reloaded-verified.json` confirms
exact original save fields, all original touching friend rows, both-column
battle rows, private battle events and invitation rows after those reloads.
Both potion expiry fields remain NULL. The independent preexisting
`battle_item_account_guard.py compare` also passed after final reload, preserving
HP/AP, items, decks, progression and room/world membership. All additional SSE
observer processes completed normally. No Accept action, combat, purchase,
reset, reinstall, wipe, save restoration or original-row cleanup was used.

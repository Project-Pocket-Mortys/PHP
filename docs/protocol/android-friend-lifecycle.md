# Android friend lifecycle acceptance

The isolated research backend is `http://localhost:8087`. Use Android 2.41.0
on ADB port 5038: `PocketMortys_API30` (`emulator-5556`, `PMResearch01`) and
`PocketMortys_API30_Peer` (`emulator-5558`, `PMResearch02`). Existing login
data and usernames must remain intact. Raw HTTP records, account snapshots,
pair rows and screenshots belong only in ignored `.research`.

The [recovered native contract](friend-lifecycle-contract.md) sends
`/session/friend/request` with `session_id`
and target `player_id`, `/session/friend/response` with those fields plus a
Boolean `approve`, and `/session/friend/remove` with the target ID. Their
success callbacks do not deserialize the response body. `/session/friend/list`
hydrates `requests_sent`, `requests_received` and `friends`; the server supplies
`poll_period: 5`. A is the sender and B is the recipient in persisted pairs.
The sender's legitimate outgoing UI cannot approve its own request; that
server authorization boundary therefore requires the separate UUID runtime
regression, alongside this native acceptance exercise.

## Guard and reproduction

Finish server tests first and run this exercise serially. The helper performs
no SQL mutations and calls no friend mutation API. Preparation takes a locked
snapshot of both accounts and every friend row touching either player. It
refuses a preexisting relationship between the pair. It preserves every user
save field (including explicit NULL `shiny_potion_expires_at`), Morty, attack/AP,
inventory and deck row. Only connection fields `session_id`, `state`,
`last_event_id`, `last_seen` and `room_membership_generation` are excluded from save comparisons to permit
fresh native logins; every guard separately requires WORLD and no active battle.
Original room and world IDs remain compared. The initial run's room IDs were
added from the preexisting independent account baseline; its initial manifest
is preserved intact as `fixture-initial-before-room-guard.json`.

```powershell
$python = 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$capture = '.research/emulator/friend-lifecycle-<fresh-label>'
& $python -X utf8 tools/research/friend_lifecycle_fixture.py prepare --output $capture
```

Open each native PDA and Friends UI. Search for exact username `PMResearch02`
from the primary. Send the request using the native button; record primary
outgoing and peer incoming views after the normal list poll. Decline from the
peer, record the empty pair, then send again from the primary and approve from
the peer. Record both Friends lists containing the other account. Remove the
relationship using the native UI and confirm both lists clear. Optionally send
one more request and cancel it from the outgoing UI.

```powershell
& $python -X utf8 tools/research/friend_lifecycle_fixture.py record --output $capture --label outgoing-incoming --screens
# Repeat with unique labels after decline, acceptance and removal.
& $python -X utf8 tools/research/friend_lifecycle_fixture.py cleanup --output $capture
& $python -X utf8 tools/research/friend_lifecycle_fixture.py acceptance --output $capture
```

Each record checks all save data and original friend rows under locks, retaining
the exact current pair and friend HTTP evidence matched by the pair's UUIDs.
Unattributed empty list polls are retained separately; unrelated UUID runtime
fixture traffic is excluded. Session IDs and usernames
are redacted by the existing server capture middleware. Pair UUIDs remain in
requests, search/list responses and saved pair rows. Because session IDs are
redacted, an empty list poll alone cannot identify the caller; use the serial
native action order, paired screenshots and public peer UUIDs as evidence.
Check list metadata, response status and native rendering, and ensure peer
records contain only public fields. Never publish raw snapshots or credentials.

Cleanup requires all original friend rows and both accounts to match exactly;
complete native remove/cancel if the test pair still exists. The helper never
deletes even a newly created pair. Reload both apps, enter multiplayer WORLD,
then run final verification and the preexisting independent save guard:

```powershell
& $python -X utf8 tools/research/friend_lifecycle_fixture.py verify --output $capture --label reloaded --screens
& $python -X utf8 .research/battle_item_account_guard.py compare
```

No battle, trade, donation, purchase, stock injection, HP/AP change, deck edit,
progression change, account reset, reseed or emulator wipe belongs to this test.

## Execution status

The 2026-11-05 preparation at
`.research/emulator/friend-lifecycle-20261105/` passed: the pair was absent,
both potion expiry fields were NULL, and original save/friend rows were retained
under locks. The independent original two-account save comparison also passed.
The primary native Friends screen rendered an empty list, and exact username
search found `PMResearch02`, level 1, with its Send Request button enabled
(`primary-search-result.png`). No request was sent during preparation.
After serial release the native Send Request succeeded with HTTP 200 and exactly
one canonical pending pair. `outgoing-pending-primary.png` shows the recipient,
level, awaiting-response message and cancellation control. The peer cold start
required the correct Braze launcher activity; power diagnostics confirmed Awake,
display ON and the expected resumed activity. Its loading spinner coincided with
Wi-Fi enabled but disconnected. Ordinary wake/unlock, foregrounding and reconnect
to the existing AndroidWifi network preserve all app data and account saves.
The emulated access point repeatedly timed out association, so the dedicated
peer emulator was gracefully stopped through its verified console and restarted
with the existing headless launcher, same AVD/userdata and `-no-snapshot`.
No wipe, reinstall or cache deletion occurred. After this ordinary restart,
Wi-Fi connected and validated; the captured research firewall restrictions and
ADB reverse were restored before app launch. The new self-interface address
`10.0.2.16` received only the documented local TCP 8087 allowance. A fresh guard
confirmed the same pending pair and all original accounts/friend rows unchanged.

`incoming-visible-peer.png` shows the incoming sender `PMResearch01`; selecting
the row exposed native Accept and Deny controls (`peer-incoming-controls.png`).
Deny emitted `approve:false`, returned HTTP 200 with scalar `1`, and deleted
the first pending pair. Both lists cleared (`native-declined-*.png`).

The primary searched again and sent a second request. The peer's native Accept
emitted `approve:true`, returned HTTP 200 with scalar `1`, and changed the new
canonical pair to accepted. `native-accepted-primary.png` and
`native-accepted-peer.png` show the other account ONLINE, level 1, with integer
0/0 battle records. The Battle button was not used. The peer's red X opened an
explicit Remove confirmation; confirming it removed the accepted pair through
the native `/session/friend/remove` request. Both lists cleared after refresh.

An additional primary request exercised outgoing cancellation. The pending
row's red X opened the same Remove confirmation; confirming removed only that
new pending pair (`outgoing-cancel-ready-*.png`, `outgoing-remove-confirm.png`,
`native-cancelled-*.png`). All seven friend mutations returned HTTP 200.
`acceptance.json` validates their exact order, Boolean response requests,
canonical sender/recipient, both accepted friend projections, five-second poll
metadata and public peer field allowlists. The observed pending row fields are
`player_id`, `username`, `player_avatar_id`, `level` and `_created`; accepted
rows additionally project `wins`, `losses`, `online` and `donation_request`.
No account secret, session, inventory, deck or Morty details appear in them.

`cleanup.json` confirms exact original save state and every original friend row
under locks. The fixture issued no cleanup SQL writes: all three test pairs
were removed through the native decline/remove/cancel paths. The only excluded
connection-generation changes follow ordinary room rejoins and were never
restored or decremented. Both apps were then freshly force-stopped, launched
through the correct native activity and returned to multiplayer WORLD.
`final-reloaded-primary.png` and `final-reloaded-peer.png` show their original
account names in WORLD; `final-reloaded-verified.json` confirms original room and
world IDs, every save field, raw HP/AP/inventory/decks and all original friend
rows still match. Both original potion expiry values remain NULL. The independent
preexisting two-account account guard passed again after these final reloads.

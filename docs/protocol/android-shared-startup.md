# Android shared-startup and recovery capture

Two fresh Android 2.41.0 diagnostic clients rendered a `PvF` startup, each sent
its own successful ready request, and both automatically signed in and rejoined
the world after startup expiry. Neither client selected a move. The
[sanitized packet receipt](android-shared-startup-results.json) records the
observed sequence and capture hashes. This is replacement-server evidence, not
an original-server capture or a playable human battle implementation.

## Observed sequence

| Observation | Primary | Peer |
| --- | --- | --- |
| Private `battle:start`, correct local/opponent IDs | 1 | 1 |
| Native `POST /session/battle/ready`, HTTP 200 | 1 | 1 |
| Native battle move requests | 0 | 0 |
| `session:end {}` and clean EOF | 1 | 1 |
| Automatic login, new session, room join; HTTP 200 | 1 | 1 |
| Replayed battle starts after reconnect | 0 | 0 |

The native ready requests arrived about 8.6 seconds after each complete start
frame. Both clients displayed the other account's name and the starter Morty
at level 5, HP 20/20. The shared session reached READY. Its fixed 45-second
research lease then expired; the backend recorded CANCELLED/STARTUP_TIMEOUT,
released both claims and retired both intents. `session:end` contained an empty
object; TCP terminal chunk, FIN and client acknowledgement establish clean EOF
without reset. Automatic login and successful room rejoin followed about six
seconds later. New authentication sessions matched the recovered SSE tokens
and room-join requests. No input was supplied during startup or recovery.

The packet decoder uses each capture's first matching packet as its time origin;
times from separate role captures must not be treated as a shared clock. It
deduplicates consistent TCP overlap and rejects gaps/conflicting bytes. The
original SSE connection began before recording, so its first partial/midstream
frame is not promoted to evidence. Complete later frames, including start/end,
are decoded along with the recovered HTTP-header SSE connection.

![Primary native startup, before any move](images/shared-startup-primary-battle.png)

![Peer native startup with the opposite account](images/shared-startup-peer-battle.png)

After automatic recovery, the fresh accounts' introductory world dialogue
appeared again. This reflects their incomplete multiplayer tutorial; it does
not show a completed campaign or human battle.

![Primary world after automatic recovery](images/shared-startup-primary-recovered.png)

## Account and client isolation

The capture used new `PocketMortys_API30_Startup` and
`PocketMortys_API30_Startup_Peer` AVDs on emulator ports 5560/5562, ADB server
5038. Their userdata directories were created from the existing emulator
configuration and pinned system image, without copying either original save.
The Android API 30 Google APIs x86_64 image runs the ARM32 diagnostic build by
translation. The retained 5556/5558 clients and their mappings were untouched.

Both installed APK hashes exactly matched the existing signed diagnostic inputs;
the receipt records those hashes. This profile includes the previously documented
local transport and multiplayer-unlock probes. No battle/ready/recovery method
was patched for this capture. Fresh native registration created `PMStartup01`
and `PMStartup02`; their existing registration party, inventory and trainer data
were used unchanged. No synthetic battle stats, attacks or rewards were added.

Friendship/invitation setup used scripted HTTP calls. Reservation, party/view
capture and activation used the internal research CLI with a 45-second startup
lease. **Native approval was not exercised successfully**; public acceptance
remains 501. Startup rendering, ready, subsequent login and room join came from
the Android processes, with no scripted ready or login substituting for them.

The peer also sent `accept:false` to `/session/battle-invite/response` around the
start and received 409 TOKEN_NOTVALID. The sanitized receipt retains that boolean,
status and timing. It did not prevent the observed start/ready/recovery. The
capture does not establish why the client declined or what the original server
returned; investigate the complete native invitation/approval flow before
changing that policy. No invented success response was added.

## Reproduction

Start the existing research database/backend, then its opt-in stream service.
Use the explicit Windows Python executable; the Store aliases are unnecessary.

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
docker compose -f compose.research.yaml --profile shared-battle-stream up -d --no-deps stream-web
& $researchPython -X utf8 tools/research/startup_capture_device.py launch --role primary
& $researchPython -X utf8 tools/research/startup_capture_device.py launch --role peer
& $researchPython -X utf8 tools/research/startup_capture_device.py install --role primary
& $researchPython -X utf8 tools/research/startup_capture_device.py install --role peer
& $researchPython -X utf8 tools/research/startup_capture_device.py network --role primary --sdk-network
& $researchPython -X utf8 tools/research/startup_capture_device.py network --role peer --sdk-network
```

The helper only accepts those fresh AVD names/ports. Existing app data is
preserved, and installed APK hash mismatches are refused. Its separate UID
firewall permits local research traffic and optional required OneTrust endpoints;
it does not modify the original devices' firewall chains. On these new AVDs only,
device ports 8087 and 8089 reverse to host 8089. No reinstall, save reset or cache
clear is part of this workflow.

Launch the package with `adb -P 5038 -s SERIAL shell monkey -p
com.turner.pocketmorties 1`. Decline optional Play Games installation, complete
the normal app startup, select Multiplayer and register the dedicated names.
Commit the keyboard input before Play; dismiss introductory prompts and wait
for both clients' WORLD scenes/live streams. The fixture is deliberately
first-run-only: do not delete its manifest or accounts to bypass its safeguards.
Retain it for status/verification after the recorded run.

```powershell
& $researchPython -X utf8 tools/research/android_startup_fixture.py snapshot --output .research/emulator/shared-startup-20261106/fixture
& $researchPython -X utf8 tools/research/android_startup_fixture.py prepare --output .research/emulator/shared-startup-20261106/fixture
```

In separate terminals start the two captures, then promptly run activation before
the invitation expires. Output directories must be fresh; raw PCAPs, logs,
screenshots and credential snapshots stay ignored.

```powershell
& $researchPython -X utf8 tools/research/capture_shared_startup.py --role primary --duration 90 --screens 3 --output .research/emulator/shared-startup-20261106/primary-capture
& $researchPython -X utf8 tools/research/capture_shared_startup.py --role peer --duration 90 --screens 3 --output .research/emulator/shared-startup-20261106/peer-capture
& $researchPython -X utf8 tools/research/android_startup_fixture.py reserve-activate --startup-seconds 45 --output .research/emulator/shared-startup-20261106/fixture
```

For this zero-move startup baseline, do not select Attack, Item, Switch or Run.
The separate [paired-selection reproduction](paired-selection-contract.md#native-paired-reproduction)
now covers the first native ATTACK from each participant without resolution.
Use fixture `status`/`verify` during READY and after expiry. They compare all owned
rows and persistent trainer fields while allowing native authentication/cursor
rotation. If necessary, its `cancel` command calls the existing paired cleanup
without deleting accounts or evidence.

```powershell
& $researchPython -X utf8 tools/research/android_startup_fixture.py verify --output .research/emulator/shared-startup-20261106/fixture
& $researchPython -X utf8 tools/research/export_android_startup.py --capture-root .research/emulator/shared-startup-20261106 --output docs/protocol/android-shared-startup-results.json
```

The exporter emits only role labels, field names, statuses, relative timings,
safe party fields and artifact hashes. It checks recovered login identity,
session-token/SSE/join correlation and clean EOF; it does not publish packet
bytes or credentials. Five parser tests cover stream boundaries, chunked framing,
overlap, gaps and both ports. Five device-guard tests cover original-device
refusal, redirected paths, unexpected serial identity and APK mismatch.

## Preservation and remaining work

Fixture verification passed before and after recovery: owned Morties/attacks,
items, decks and other owned records, currencies and progression stayed exact.
Both independent original-account guards passed. The two fresh AVDs were shut
down with userdata retained, and the temporary stream server was stopped.
Their dedicated accounts and terminal history remain for audit; no active shared
claims remain. The original two emulators and normal backend were retained.

This branch starts from main `9ff1a11`, explicitly fast-forwarding prerequisite
PR #45 `446a1e7` and its dependency history. It changes research tooling/evidence,
not backend gameplay or public acceptance. Follow-up research-gated
[first ATTACK storage/pairing](paired-selection-contract.md) now passes backend
tests, and [two native inputs, waiting and fixed-expiry recovery](android-paired-selection-results.json)
are verified on these dedicated registration parties. This earlier receipt remains
the zero-move baseline. Later
selection phase/replay identity and the remaining combat/terminal contracts, full native
send/approval, packet loss and broader parties still need separate validation.

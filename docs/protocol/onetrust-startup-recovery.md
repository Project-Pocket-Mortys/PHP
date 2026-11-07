# Retained-client startup through the native offline SDK path

The unchanged Android 2.41.0 diagnostic installation now reaches the title and
multiplayer world using an explicit, isolated research fixture. Native login,
player details and world join return 200, with no fresh OneTrust or null-reference
exceptions in the capture. The client receives the scoped login cookie and sends
it on a native `/trading/config` request.

This is recovery of local testing through the client's existing offline path.
It does not restore OneTrust's online service, grant consent, prove all optional
SDKs default to denied, or establish native cancellation-button behavior.

## Cause and boundary

[Native analysis](onetrust-startup-contract.md) establishes that online startup
can continue after SDK initialization reports an error, then access missing
in-memory domain groups. Ordinary initialization does not hydrate the retained
server-data JSON. The existing file is valid and contains 48 groups; deleting
it would not fix that control-flow problem.

A host-side read-only request to the SDK endpoint with cached application
headers returned 403 HTML containing access-denied/Cloudflare markers. This is
not proof of the Android HTTP response. The exact cause of its online fetch
failure remains unresolved; the two earlier [failed captures](trade-cancellation-startup-blocker.json)
remain preserved.

The SDK's connectivity check is shared with asset/privacy code. An indefinitely
failed probe would break later startup too. The optional `offline-sdk-web`
service therefore returns one 503, followed by 204 for later probes. That selects
the existing offline SDK branch once while allowing the local asset/game path
to proceed. It writes only its own temporary probe counter. The normal research
service keeps returning 204 and never creates this counter.

The fixture is confined to the research image and localhost port 8091. Its
emulator-facing URLs remain `localhost:8087`; dedicated ADB reverse maps that
port to 8091. The APK and SDK code are unchanged. Radios and external SDK
destinations remain denied by the existing per-app IPv4/IPv6 firewall. That
isolation matters because native evidence does not establish universal optional
SDK denial. Stored consent is not edited or synthesized.

## Observed results

The [strict startup receipt](onetrust-startup-recovery-results.json) records
ACK-paired probes **503, 204, 204**, at 0.084, 9.256 and 50.984 seconds.
The extra later check is retained; its precise caller was not established.
Login, player details and world join follow at 51.901, 52.448 and 52.672 seconds,
all 200. The returned token and authenticated session match the immutable
fixture identity. Zero fresh OneTrust stacks or null references occur.

The [cookie receipt](onetrust-recovery-cookie-handoff.json) separately proves
actual native transmission of the cookie issued by login. It proves transport,
not successful cancellation. [Title](images/onetrust-recovered-title.png) and
[world](images/onetrust-recovered-world.png) screenshots show the recovered UI.

The retained SDK server-data and active-profile files are byte-for-byte
unchanged; before/after hashes are included in the startup receipt. The dedicated
persistent-save/history guard passes. Source and installed APK hashes match the
previous diagnostic build. No account, cache, consent file or installation was
reset. Raw captures, SDK data and account manifests remain ignored.

## Reproduce on a dedicated retained client

Use the existing isolated backend and the diagnostic devices from
[startup capture setup](android-shared-startup.md). Preserve an immutable account
fixture using its existing tools. Do not run global reseeding tests. This is a
single-client experiment: every client needs its own fresh fixture lifetime.
Do not share this one-shot service between simultaneous startups.

After verifying the dedicated identity, stop only that app before recreating the
optional service. Recreating it discards only this service's temporary counter,
not the database or Android data. A plain stop/start retains the used counter.

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
$adb = Join-Path $PWD '.research/emulator/sdk/platform-tools/adb.exe'
& $researchPython -X utf8 tools/research/startup_capture_device.py launch --role primary
& $researchPython -X utf8 tools/research/startup_capture_device.py status --role primary
& $adb -P 5038 -s emulator-5560 shell am force-stop com.turner.pocketmorties
docker compose -f compose.research.yaml --profile offline-sdk up -d --build --no-deps --force-recreate offline-sdk-web
& $researchPython -X utf8 tools/research/prepare_offline_sdk_device.py --role primary --output .research/emulator/offline-sdk-next/preparation
```

Never probe `/_research/online` before launching the client: a healthcheck or
another request can consume the first failure. Preparation checks `/time`
instead, refuses a used service and verifies the existing signed APKs without
reinstalling. It force-stops only the selected dedicated app, reapplies external
isolation, and sets the two reverse mappings. It does not launch the app or reset
an existing counter. Original devices 5556/5558 are outside its allowlist.

Start the capture in a separate terminal before launching the app. Use the
normal Multiplayer UI and retained login; do not manufacture a consent choice.

```powershell
& $researchPython -X utf8 tools/research/capture_shared_startup.py --role primary --duration 180 --screens 5 --output .research/emulator/offline-sdk-next/primary-capture
# In another terminal, after capture has started:
& $adb -P 5038 -s emulator-5560 shell monkey -p com.turner.pocketmorties -c android.intent.category.LAUNCHER 1
```

After capture completion, validate it against the immutable fixture, using a
fresh private output file. Review the sanitized output before publishing it.
The sanitizer accepts optional `--compare` inputs for copied SDK files.

```powershell
& $researchPython -X utf8 tools/research/sanitize_onetrust_startup.py --capture .research/emulator/offline-sdk-next/primary-capture --fixture .research/emulator/paired-selection-complete-20261106/fixture/startup-fixture.json --output .research/offline-sdk-next-results.json
& $researchPython -X utf8 tools/research/sanitize_trade_cookie_handoff.py --pcap .research/emulator/offline-sdk-next/primary-capture/primary-http.pcap --fixture .research/emulator/paired-selection-complete-20261106/fixture/startup-fixture.json --output .research/offline-sdk-next-cookie.json
```

Recheck save/history and original-account guards afterward. Stop the dedicated
AVD and `offline-sdk-web` when done, retaining their data/evidence. Do not clear
SDK data or reset the database. If the probe state is corrupt or unwritable,
the service fails with 503 rather than silently claiming online status.

## Verification and remaining work

Six probe tests pass, including disabled no-touch behavior, strict malformed
state, failed I/O and six concurrent calls yielding exactly one 503. They caught
an existing-empty-state issue, fixed by a companion lock before creating the
counter. Four startup-sanitizer and six cookie-sanitizer cases pass. A disposable
HTTP control using the new image with the flag unset returned 204 twice, empty
bodies and no state file. Preparation's used-counter refusal and successful
preparation against a fresh isolated service were both checked. The dedicated
save/history and SDK byte guards still passed afterward; both original-account
guards passed as well. Only the dedicated primary AVD and optional service were
stopped, retaining their data and evidence.

Native cancellation buttons, persistent trade-lock reconciliation, paired-client
startup fixtures and actual SDK online-fetch failure attribution remain open.
This opt-in fixture is not a production consent strategy or a game protocol
change. No deployment or merge is included.

Based on current main `9ff1a11`, explicitly fast-forwarding draft PR #49 at
`544a836`. The tested fixture implementation is commit `d939ca6`. The README
and all game PHP handlers remain unchanged relative to that prerequisite.

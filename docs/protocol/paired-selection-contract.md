# First shared ATTACK selection boundary

The bounded Android 2.41.0 ARM64 review and
[two-input native receipt](android-paired-selection-results.json) support storing
the first human ATTACK selection separately from resolving it. They do not recover
combat formulas, enable public acceptance, or establish a playable human battle.
The [shared startup policy](shared-battle-startup.md) and
[Android startup receipt](android-shared-startup.md) remain prerequisites.
Storage and rejection rules below are replacement-server policy.

## Native request, acknowledgement and waiting

`NetworkBattleAPI.SelectMove` (`0x17882bc`, 924 bounded bytes) sends JSON to
`/session/battle/move` with `session_id`, `battle_id`, enum-string `type`,
`owned_morty_id` and `move_id`. The reviewed request has no turn number,
selection nonce or phase identifier. Its five-field constructor is included
in the bounded export. Identical bodies therefore cannot safely identify
distinct later turns; this slice must never open a second selection phase.

Before dispatching HTTP, SelectMove invokes `MoveSelectedEvent`, clears its
local timer and marks the move sent. `MPBattleState.UIMoveSelectedHandler`
(`0x1576ea0`) forwards the menu selection. `NetBattleMoveSelectedHandler`
(`0x1578be8`) calls `MPBattleUI.MoveSelected` (`0x1574bec`) when the UI is
active, otherwise deferring the UI update. MoveSelected hides the menus and
sets dialogue to `MP_BATTLE_WAITING_FOR_ENEMY`. Waiting begins before the
HTTP acknowledgement, without a damage animation or local PP debit here.

The callback is `NetworkBattleAPI.<>c__DisplayClass80_0.<SelectMove>b__0`
at `0x1789eb4` (184 bytes). It calls
`NetworkDefs.ParseHTTPError<eBattleMoveSelectError>` then emits the separate
`MoveSelectFinishedEvent` enum. It does not deserialize a turn result,
acknowledgement ID, selection row, opponent selection or battle snapshot.
`ParseHTTPError<Int32Enum>` (`0x1b569d8`, 1032 bytes) returns the enum's NONE
member when `NetworkHTTPResponse.isSuccess` is true, without reading the
success JSON. NONE is 22 for this enum. Preserve the existing HTTP 200
`{"success":true}` envelope; optional internal receipt data is not native UI
state and cannot communicate that a pair is complete. A success body with
`success:false` would still follow the transport-success path in this parser.

Non-success HTTP reads `error.code` as a defined enum string. The existing
failure shape `{"success":false,"error":{"code":"FAILED"}}` remains
appropriate for this bounded replacement policy. The enum also contains
`NO_MOVE_PP`, `INVALID_MOVE` and other move-specific errors; this review does
not establish original status-code parity or user-facing recovery for each.

Turn consumption is independent: `BattleTurnResultHandler` (`0x1788dc4`)
and `MPBattleState.NetBattleTurnResultHandler` (`0x1578c1c`) process the
asynchronous result path. An HTTP acknowledgement can precede such a result.
A stored-only acknowledgement neither creates one nor advances the phase.
Both players can consequently remain waiting until the fixed startup expiry.

## HTTP transport and replay limits

`NetworkHTTP.Request` (`0x17b5a44`) serializes postData, selects POST for JSON,
adds `content_type: application/json` and `X_PMCLIENT`, and submits a Best.HTTP
request. The reviewed constructor path adds no idempotency or turn header.
`NetworkHTTPRequest..ctor` (`0x17b58d8`) sets a 60-second request timeout.
This is separate from the startup lease and native battle watchdog.

`RequestHandler` (`0x17bde00`) removes ordinary completed requests from its
pending list and invokes the callback. No response increments failedCount,
emits the request-error event and then follows that callback path. HTTP 503
increments failedCount; below three failures it retains the pending request
and writes retryCountdown zero, while the third failure disconnects with
reason 13. `CheckForRetryPendingRequests` (`0x17bd2d0`) resends only a positive
countdown that crosses zero. These bodies do not establish that 503 always
retries automatically, a retry delay, or a reliable retry count. Best.HTTP's
lower transport behavior was not exhaustively reviewed.

`RemoveDuplicateRequests` (`0x17bd580`) removes pending bookkeeping via a
path predicate before a new request. It does not establish server-side
deduplication or cancellation of an already received operation. Lost responses,
repeated manual/internal calls and delayed delivery must remain safe at the
server regardless of the client retry policy. Do not use HTTP connection,
room event cursor, X_PMCLIENT, current login session ID or arrival order as a
durable turn identity.

## Bounded first-selection policy

An internal first-selection operation accepts ATTACK after the submitting
participant's initial ready signal, under the same ordered participant/lifecycle
locks as startup. The first participant may select during STARTING while the
peer's intro is still running; a complete pair requires both ready signals and
READY state. Authenticate the current session and derive the participant
from persisted ownership. Revalidate the exact shared claims, intact startup,
private view and frozen party identities, live fixed startup deadline and
compatible BATTLE user state. Require the participant's current active Morty
from that party, an unambiguous owned attack matching move_id and positive
persisted PP. Foreign, missing, changed or ambiguous identities fail closed.

Persist one immutable normalized selection per battle and participant. A
valid same-selection replay returns the original acknowledgement and identity;
a different selection conflicts (409) without replacement. Match the
selection's semantic fields, not JSON whitespace or object ordering. Recheck
authentication, lifecycle integrity and lease even on replay; an expired
selection must not resurrect a retired startup. Both stored participants
make the pair complete internally; this is a derived bookkeeping fact and
must not change READY or start a new selection phase. Concurrent submissions
and retries must serialize to the same two immutable records.

Acknowledgement means committed selection storage only. Do not decrement PP,
change HP/items, compute damage or ordering, publish a turn result or timer,
award rewards, or infer the opponent's choice. No caller receives the other
participant's stored selection. Reaching the pair, retrying ready/select or
reading an acknowledgement never renews the deadline. Keep the startup lease
fixed and preserve existing cancellation/expiry cleanup for both users and
claims, retiring intents atomically while retaining selection history.

## Implemented replacement storage

Migration 013 adds `friend_battle_selections`, keyed by battle and participant
with a globally unique selection UUID, and `friend_battle_selection_pairs`,
keyed by battle with explicit sender/recipient selection IDs. Normalized JSON,
SHA-256, creation and retirement timestamps retain the first selection as history.
The nullable startup `selection_started_at` marker is written atomically with
the first selection. A null marker requires an empty ledger; a nonnull marker
requires one or two exact participants, with no pair for one row and one exact
pair for two rows. Stored owners must have their initial ready timestamps.
Missing rows, extra participants, invalid hashes/schema or contradictory markers
fail 409 without repairing or recapturing history.

`lib/friend_battle_selections.php` exposes the internal
`friend_battle_selection_submit(PDO, array, string)` operation. The request has
exactly the five native keys, all nonempty strings; missing/extra or malformed
fields fail 400, body/session disagreement fails 403, and unsupported move types
fail 501. Current session, participant ownership, fixed lease, startup/view/claim
integrity and exact current parties are checked on every submission and retry.
The chosen actor is the initial living active owned Morty; its selected attack
must be known, owned exactly once and have positive PP. No turn phase is opened.
The internal receipt is `{selection_id, paired}`; a matching retry retains its
ID, while a different valid selection fails 409. The second insert and pair
insert commit together under the existing ordered locks.

With `PM_RESEARCH_SHARED_BATTLE_STREAM=1`, `/session/battle/move` routes a known
shared battle ID through this operation and requires the existing bound live
streams and caller's start delivery attempt. HTTP success remains exactly
`{"success":true}`; it exposes neither receipt nor peer selection. The default
localhost:8087 service retains its legacy shared-ID 404 behavior. The research
localhost:8089 sidecar is opt-in. Public approval of a pending invitation remains
501 on both services; an already accepted invitation retains its existing 409.

Startup cancellation and expiry retire any selections and pair in the same
transaction as intents, both WORLD transitions and exact claim release. The
ordinary gate-off worker also retires research-created rows. A retirement error
rolls back the whole cleanup; old cancellation retries preserve newer claims.
No selection, retry or pair changes HP, PP, stock, saves, events or the lease.

Eighteen additive UUID fixture cases cover authentication, exact input shape,
own-ready selection before peer intro, both arrival orders, concurrent distinct
and duplicate submissions, invalid actors/attacks, live-party drift, valid
conflicting replay, ledger corruption, insertion/marker/retirement faults,
cancel/expiry, newer claims and gated HTTP behavior. Seventeen passed in the
265.086-second full run. The HTTP case initially expected pending-invitation 501
after acceptance; its corrected focused rerun passed in 9.411 seconds. All
eighteen cases were validated without reseeding retained accounts.

Run only the scoped suite serially against the isolated stack, with the research
sidecar running for its HTTP case:

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_friend_battle_selections.py -v
```

Existing regressions also passed serially: startup 19 (195.614 seconds),
transport 16 (117.316 seconds), and legacy wild lifecycle 24 (40.168 seconds).
The eight new receipt tests and ten existing parser/device guards passed. The
previous startup receipt reproduces identical JSON in default exporter mode.
PHP 8.3 lint passed all 64 changed/new files including prerequisites; protocol
validation and whitespace checks passed. Migration 013 applied twice to a
schema-only copy before the isolated database. Both original emulator account
guards passed, preserving saves, friends, battles, invitations and membership.
Only the two diagnostic AVDs were stopped, retaining their userdata and history.

The tested PHP implementation is commit `a11c222`, based on current main
`9ff1a11` with the explicit PR #46 prerequisite at `17dd3b3`. Default WSL REA
6.8.0 supplied artifact inspection for the bounded native pass.

## Android acceptance boundary

The earlier two-client startup receipt proves initial startup/ready followed by
startup expiry, `session:end {}`, clean EOF, automatic login and world rejoin.
It explicitly records zero move requests and remains separate evidence.

The completed paired-selection run on the same dedicated diagnostic clients
uses real ADB UI inputs: each selects its native initial Morty's `AttackOutburst`.
Both native move requests receive HTTP 200, with exactly two immutable selections
and one pair. Both clients show the waiting UI with HP 20/20; persistent HP, PP,
items and other guarded save data remain unchanged. No turn result is emitted.
At the fixed 120-second lease, startup reaches CANCELLED/STARTUP_TIMEOUT, both
users return WORLD, all claims are released, both intents and selections are
retired, and the one pair is retired. Both clients receive `session:end {}` and
clean EOF, then automatically log in and rejoin on new stream generations.
The [sanitized receipt](android-paired-selection-results.json) records the native
requests, acknowledgements, recovery and final database verification.

An earlier partial run stored only one native selection; it also expired and
retired correctly. It is not the two-input acceptance proof. The complete raw
capture remains ignored at
`.research/emulator/paired-selection-complete-20261106`, including separate
165-second primary/peer captures and guarded UI input screenshots. Duplicate and
conflicting submission behavior is covered by backend fixtures; this native
run does not claim those UI paths, broader parties or packet-loss compatibility.
Neither a fabricated result nor a new native cancel event is justified.
Public acceptance remains disabled pending its separate invitation-flow
review. Later turns require an explicit phase/replay design; this first
immutable pair cannot safely be generalized by deleting rows after a result.

## Native paired reproduction

Use the guarded diagnostic devices and opt-in sidecar from
[the startup reproduction](android-shared-startup.md#reproduction). Preserve their
registration parties and terminal history. For a later round, `snapshot --previous`
requires the prior terminal manifest, verifies its hash and save guards, and
creates a fresh output manifest without deleting accounts, friendships or history.
Use a fresh ignored directory and retain all earlier manifests.

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
$captureRoot = '.research/emulator/paired-selection-next'
& $researchPython -X utf8 tools/research/android_startup_fixture.py snapshot --output "$captureRoot/fixture" --previous .research/emulator/paired-selection-complete-20261106/fixture/startup-fixture.json
& $researchPython -X utf8 tools/research/android_startup_fixture.py prepare --output "$captureRoot/fixture"
```

Start both captures in separate terminals and the guarded chooser in a third.
The chooser waits for native READY, verifies the retained one-Morty Outburst
party and recognized 1280x720 menus, then taps Attack and Outburst once per role.
It sends no scripted HTTP move or ready request. Run activation promptly in
another terminal; `refresh-invite` replaces only the fixture's unreserved invite
if necessary and retains its previous record.

```powershell
& $researchPython -X utf8 tools/research/capture_shared_startup.py --role primary --duration 165 --screens 3 --output "$captureRoot/primary-capture"
& $researchPython -X utf8 tools/research/capture_shared_startup.py --role peer --duration 165 --screens 3 --output "$captureRoot/peer-capture"
& $researchPython -X utf8 tools/research/choose_startup_attack.py --fixture "$captureRoot/fixture/startup-fixture.json" --output "$captureRoot/input-proof" --wait 120
# Only if the unreserved invitation expired before activation:
# & $researchPython -X utf8 tools/research/android_startup_fixture.py refresh-invite --output "$captureRoot/fixture"
& $researchPython -X utf8 tools/research/android_startup_fixture.py reserve-activate --startup-seconds 120 --output "$captureRoot/fixture"
```

Keep the startup worker running separately as documented for the transport.
Wait for expiry and automatic native world recovery, then verify and export:

```powershell
& $researchPython -X utf8 tools/research/android_startup_fixture.py verify --expect-paired --output "$captureRoot/fixture"
& $researchPython -X utf8 tools/research/export_android_startup.py --expect-selections --capture-root $captureRoot --output docs/protocol/android-paired-selection-results.json
```

The selection exporter requires one successful native ATTACK from each local
initial actor, zero turn-result events, clean EOF/relogin/join, exactly one
retired pair and unchanged persistent data. It publishes sanitized role labels,
field names, statuses, relative timings and artifact hashes; raw captures and
credentials remain ignored. Never overwrite the published receipt with a failed
or incomplete round.

Reviewed waiting screenshots: [primary](images/android-paired-primary-waiting.png) and [peer](images/android-paired-peer-waiting.png). Both show only dedicated synthetic trainer names.

## Reproduction

Run `wsl bash tools/research/ghidra-paired-selection.sh`. It first uses default
WSL REA 6.8.0 artifact inspection, then targeted Ghidra 12.1.4 without whole
program analysis, then the explicit Windows Python executable
`C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe` for bounded
Capstone exports. Existing completion/timeout/startup outputs were reviewed
before this narrow pass. No backend, database or emulator was changed.

The ELF SHA-256 is
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`;
metadata version is 31, metadata SHA-256 is
`b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10`,
and existing script.json SHA-256 is
`a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb`.
The wrapper exports 15 Ghidra methods and 17 bounded ARM64 bodies including
the generic request constructors. REA establishes artifact identity only.
The generic error parser's Ghidra output over-follows exception fallthrough;
its actual ARM64 method bounds and normal return path constrain this report.

Ignored outputs are `rea-paired-selection-6.8.0-artifact.json`,
`ghidra-paired-selection.json`, `paired-selection-methods.json` and
`paired-selection-arm64.txt` under `.research/`. This run's last three
SHA-256 values respectively are
`ff7b84b3b03bf30166a181e871bad0f46fbb6eb17b0cfde7106c17da9e750cf9`,
`e04d6c3717dc96e4fb482d09adb983fd855e0a1966b1a7dc3aba217d552221f4`,
and `e30ad68a1ac5f2ca3deb093025ceeea59306107bb6de80fcf264dada5e5d0852`.
The manifest records individual signatures, bounds and body hashes. Ghidra
presentation hashes may vary across reproductions. Bash syntax validation passed
for the evidence wrapper. Storage implementation and scoped tests are recorded above.

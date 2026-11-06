# Android friend Battle missing-endpoint probe

On 2026-11-05 the Android 2.41.0 primary client sent an actual friend battle
invitation request and received Apache HTTP404. The native dialog read:
“The battle invite failed to send.” This is an observed failure against the
isolated replacement server, not evidence of original-server behavior or a
successfully accepted invitation or playable battle.

## Setup and observation

The already-running research clients were `PMResearch01` on `emulator-5556`
(`PocketMortys_API30`) and `PMResearch02` on `emulator-5558`
(`PocketMortys_API30_Peer`). Both were WORLD, with no active battle on either
side and no original relationship between them. The backend identity check
required `PM_DB_HOST=db` and `PM_PUBLIC_ORIGIN=http://localhost:8087`.

The helper saved the original account data and every touching friend row before
any mutation. It created a social friend request through
`/session/friend/request`, recorded the newly created row identity, then approved
through the recipient's `/session/friend/response` API. This is **synthetic API
setup**, not a native friend-request lifecycle check. No invite endpoint was
called synthetically and no battle, accepted invite or battle event was inserted.

The primary UI sequence was PDA → Friends → select ONLINE `PMResearch02` →
Battle. All taps used stationary 200ms swipes. The selected row exposed the
native Battle button; tapping it produced the failure dialog. The peer UI was
left unchanged.

A bounded 45-second root `tcpdump` on the primary captured TCP port8087. This
was needed because Apache's missing-route response bypasses the PHP request
capture middleware. The actual wire request was:

```http
POST /session/battle-invite/create HTTP/1.1
X-PMCLIENT: Android/2.41.0
User-Agent: UnityApp/2.41.0 (Android)
content-type: application/json
Host: localhost:8087
Content-Length: 133

{"session_id":"<redacted>","opponent_player_id":"<PMResearch02 player UUID>","battle_type":"PvF"}
```

The body contained exactly those three keys. The captured session matched
PMResearch01's current authenticated session; the opponent matched PMResearch02's
stored player ID. The route had no trailing slash. The same TCP stream returned
`HTTP/1.1 404 Not Found`, `Content-Type: text/html; charset=iso-8859-1` and
`Content-Length: 313`, with Apache's ordinary missing-URL page. The 133-byte request
length is the original wire body size; it does not describe the redacted example
body shown above. These fields are
observed wire values, not inferred solely from native metadata. The response is
not a supported invitation error DTO.

## Preservation and artifacts

Raw artifacts remain ignored under
`.research/emulator/friend-battle-probe-20261105/`. The complete PCAP SHA256 is
`4e8e43a5d1dbbee201596fc0a1a152e192d00117a59395634de7384dbf01e61e`.
`wire-observed.json` redacts the session; `primary-http-complete.pcap` and
`primary-http-complete-raw.txt` retain the private wire capture. Screenshots
`friends-primary.png`, `selected-primary.png` and `battle-failure-primary.png`
show the native sequence. The capture reported 124 packets and zero kernel
drops. An initial PowerShell-redirection screenshot `pda.png` is invalid binary;
the valid `pda-primary.png` was captured through Python binary subprocess output.

The complete guarded save comparison covers every nonvolatile user column, all
owned Morties, attacks, items and decks, plus all original touching friend rows.
Session ID, state, SSE cursor, last-seen and room-membership generation are
connection/state observations rather than restored save fields; each locked
snapshot requires both users WORLD. All battle rows mentioning either account
are compared separately and remained unchanged. These are the existing guarded
fixture's account tables, not a claim that every table in the database was copied.

The first setup request succeeded, then an exclusive-create manifest writer
refused its update. The original baseline remained intact. Recovery matched the
sole new pending row to exactly one successful post-baseline API capture using
canonical sender/recipient and creation timestamp. The response does not contain
the database row ID; the guarded row supplied it. That identity was persisted
before approval. Subsequent manifest updates atomically replace the manifest
while asserting its original snapshot and player identities are unchanged.
Other evidence files remain exclusive-create.

After the failure, the full guard passed. Cleanup verified the exact created row
ID and complete accepted row still matched before removing it using only
`/session/friend/remove`. Only the fresh tracked row was removed; no preexisting
friend row was deleted. The original account saves, original touching friend rows and
battle rows matched after cleanup. The primary app was then freshly reloaded;
the peer app was not restarted. `final-reloaded-primary.png` shows the primary
back in WORLD with normal controls, and `final-reloaded-verified.json` confirms
the complete guarded comparison again after reload and dismissal of the ordinary
startup running hint. The helper passed Python syntax compilation; no test suite
or test discovery ran.

## Reproduction boundary

Use the explicit Windows interpreter and a fresh ignored output directory:

```powershell
& 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe' -X utf8 tools/research/friend_battle_probe.py preflight --output .research/emulator/friend-battle-probe-NEW
& 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe' -X utf8 tools/research/friend_battle_probe.py prepare --output .research/emulator/friend-battle-probe-NEW
```

`prepare` changes only the new social relationship through the existing APIs.
Once the accepted friend is selected and its native Battle button is visible,
start capture with the following command. It performs no database or gameplay
mutation. Manually tap Battle within its 45-second window:

```powershell
& 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe' -X utf8 tools/research/capture_friend_battle_http.py --capture --duration 45 --output .research/emulator/friend-battle-wire-NEW
```

The tool checks the expected primary AVD and existing root shell, invokes bounded
`tcpdump` on TCP port8087, pulls the PCAP, and reconstructs TCP payloads. It checks
retransmitted overlap bytes, refuses incomplete messages and correlates the HTTP
response using the TCP acknowledgement of the complete request. It requires one
create request and one corresponding 404 response. Private captures and streams
stay under the ignored output directory; only the sanitized contract is printed.
It supports classic PCAP with Ethernet or Linux cooked links and unfragmented
IPv4 TCP, and fails closed for unsupported or ambiguous input. It does not alter
an emulator's root state, restart an app, or manufacture a Battle request.

To verify this probe again without touching either client or database, decode the
existing private PCAP to another fresh ignored directory:

```powershell
& 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe' -X utf8 tools/research/capture_friend_battle_http.py --pcap .research/emulator/friend-battle-probe-20261105/primary-http-complete.pcap --output .research/emulator/friend-battle-probe-20261105/decoded-NEW
```

The analysis-only invocation passed against the actual captured PCAP. Its
sanitized result is retained in [friend-battle-create-capture.json](friend-battle-create-capture.json);
that tracked artifact replaces both account identifiers with placeholders and
records original wire body size separately from the redacted JSON example.

Use `record --label NAME --screens`
before and after the tap, `cleanup` to remove only the tracked row after guards,
and `verify --label NAME --screens` after returning to WORLD. The helper refuses
an original pair or changed save data. `resume-setup` exists only for the recorded
post-request interruption case and demands matching API evidence; it must not
adopt an arbitrary relationship.

This helper assumes exclusive use of these two isolated research accounts during
the probe. The existing target-only remove API does not take a relationship row
ID, so the verified row check and API call cannot be one database transaction.
It deliberately refuses cleanup if the accepted row differs from its saved copy.
An interruption after successful approval but before saving that copy requires
manual evidence review; this helper does not weaken the equality guard to recover
that case automatically.

No runtime changes, deployment, reseed, test discovery, fake invitation response,
mocked start event or combat were part of this probe. Static contract recovery
and server implementation gaps are separate evidence.

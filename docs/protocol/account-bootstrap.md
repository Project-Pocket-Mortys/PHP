# Android account bootstrap and multiplayer entry

Android 2.41.0 registered a synthetic account, logged in, fetched player details,
friends and dimension configuration, and entered the world-1 multiplayer scene.
State updates and periodic HTTP pings reached the isolated server. This run uses
the explicitly instrumented multiplayer diagnostic profile below; it does not
prove normal campaign progression or two-player gameplay.

## Environment fixes

- `/user/login` previously allowed only two hard-coded secrets through its
  maintenance gate. A newly registered synthetic account received HTTP 400
  `MAINTENANCE`. `PM_LOGIN_MAINTENANCE=0` now explicitly disables that gate in
  Compose. Unset values retain the existing restriction, and database secret
  validation remains required.
- `PM_PUBLIC_ORIGIN=http://localhost:8087` directs both the returned SSE URL and
  the token's ping URL to the local server. The previous origin remains the
  default outside this configuration.
- The schema contains no populated world-1 room. The client sent `world_id:"1"`
  and received `NO_ROOM_FOUND`. `seed-client.php` adds a synthetic UUID room for
  world 1 without deleting accounts. Its zone `[1,1]` follows the existing test
  convention and remains an inferred fixture, not recovered original-server data.
- The empty `deck_config` table made `/decks/slots/config` return the non-JSON
  text `Deck config not found` with HTTP 200. The client threw in
  `NetworkPlayerAPI.<DeckSlotConfigs>b__36_0`. The seed uses the SQL schema's
  existing defaults: `MP`, 3 starting slots, 9 maximum slots, cost 10. These are
  replacement-server defaults, not independently recovered economy values.

The room advertises localhost UDP port 5055 as a reserved fixture. There is no
UDP listener, and remote movement/battle synchronization is not validated.

## Diagnostic profile and reproduction

The ordinary client completed its first single-player battle but still required
the campaign tutorial. To inspect multiplayer without claiming that tutorial was
completed, `--multiplayer-probe` overrides two ARM32 Boolean queries:

| Query | RVA/file offset | Original first 8 bytes |
|---|---|---|
| `SaveDataController.IsMultiplayerUnlocked` | `0xb05e9c` | `30482de9345090e5` |
| `SaveDataController.IsCampaignTutorialComplete` | `0xb05ed0` | `30482de994509fe5` |

Both become `0100a0e31eff2fe1` (`mov r0,#1; bx lr`). The unchanged input library
hash is guarded by the builder. ARM32 Dumper mappings and Capstone instructions
identify the entries; Ghidra independently shows multiplayer unlock consulting
campaign completion, which normally checks badges or a client debug flag.
The profile also includes the earlier localhost transport and startup patches.
Original archives remain unchanged. Pre-probe test saves are backed up under
`.research/emulator/pre-multiplayer-probe-save` and are not tracked.

```powershell
py tools/research/research_client.py --multiplayer-probe
wsl -- bash tools/research/sign-client.sh
docker compose -f compose.research.yaml up -d --build
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/seed-client.php
py tools/research/install_research_client.py --sdk-network
```

After Wi-Fi connects, launch using the ADB command in [research-client.md](research-client.md).
Choose Multiplayer and enter a unique synthetic name of 3–16 characters. The
recorded account used `PMResearch01`. Rebuilding with `--local-transport` omits
the two query overrides; do not mistake diagnostic access for natural progression.

**The general regression seed deletes synthetic accounts and rooms.** Run the
full suite before client registration, or back up the isolated database first.
Reapply `seed-client.php` afterward. `test_client_fixture.py` is additive and
checks that existing player/session rows survive repeated seed execution.

## Capture and validation

The research image loads `capture.php` with `auto_prepend_file`. It logs JSON
requests/responses to `/tmp/pocket-research-http.jsonl` inside the container,
redacting credentials and token-bearing session URLs. Query strings and headers
are omitted; non-JSON bodies retain only their size. SSE paths are excluded from
buffering. The capture does not change response bytes. Container recreation
discards these temporary logs, so export relevant captures before rebuilding.

```powershell
docker compose -f compose.research.yaml exec -T web cat /tmp/pocket-research-http.jsonl
```

Reviewed client exchanges are in [account-client-capture.json](account-client-capture.json).
Build hashes, test counts and stored account/session state are in
[account-bootstrap-results.json](account-bootstrap-results.json).
They are replacement-server evidence. They include the initial room failure and
the later successful flow, clearly separated from synthetic regression requests.
The client sends `player_avatar_ids:["AvatarRickDefault"]` at registration.

Validation: 20 backend tests (19 existing/account tests plus the additive fixture
test) and 5 patch tests passed. Account checks cover register/login persistence,
local SSE/ping URLs, invalid-secret rejection without mutation, and capture
redaction. Native query override checks constrain changed byte ranges.

Next: independently capture SSE event ordering/reconnection on this client,
recover and implement the UDP room service, and repeat room/private-event tests
with a second account. The registration UI advertises dash support but the PHP
username regex excludes dashes; investigate this captured discrepancy before
expanding the accepted-name contract.

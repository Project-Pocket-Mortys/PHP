# Live SSE session revocation

The replacement server's login handler assigns a new `users.session_id` on each
successful login (`user/login/index.php`). Before this repair, `/sse/` checked the
session once, then used only `player_id` while waiting for a room and streaming
events. A deleted account or replaced session could therefore retain a live
stream. Four synthetic-account tests reproduced the failure as a three-second
read timeout instead of EOF, covering rotation and deletion both inside a room
and while waiting for one.

The handler now checks the opening session and player together while waiting,
on each stream poll, and before processing individual snapshot and queued events.
If that pair no longer exists, it ends the stream. Existing authentication errors,
valid-session payloads, event names and cursor behavior are unchanged. This needs
no schema migration. Checks are polling-based (250 ms waiting, 300 ms streaming),
not an atomic guarantee against an event already being written during revocation.

Evidence confidence: the defect and repair are established by repository source
and replacement-server integration tests. They do not establish the original
server's revocation policy. The previously observed Android `ES_CLOSED` behavior
and manual login recovery are documented in [movement-and-reconnect.md](movement-and-reconnect.md);
revoking the emulator's session itself has not been tested in this change.

## Reproduce

With the isolated Compose web/database stack running:

```powershell
py -m unittest discover -s tests/protocol -p test_sse_sessions.py -v
py -m unittest discover -s tests/protocol -p test_sse_membership.py -v
docker compose -f compose.research.yaml exec -T web php -l /var/www/html/sse/index.php
py tools/research/validate.py
```

Four revocation tests and four existing membership tests pass. Revocation tests
queue a room event after invalidation, require EOF, and verify a replacement
session can connect. They create and remove random synthetic accounts and events;
the emulator account is preserved. PHP syntax and evidence validation also pass.

Room changes on a still-valid stream, generic event audience filtering, JWT
signature validation, reconnect cursors and stationary UDP registration remain
separate research/repair gaps. In particular, this repair does not rebind a live
stream to a newly joined room.

# Friend battle implementation handoff

The follow-up [invitation implementation](friend-battle-invitation-implementation.md)
now replaces the missing create/decline/revoke routes and delivers private
invitation events. Acceptance remains unavailable. The capture and research
below record the earlier missing-route baseline and the remaining shared
human battle work.

Android's Friends Battle action reaches a missing backend interface. The
[native probe](android-friend-battle-probe.md) captured an actual slashless
`POST /session/battle-invite/create` with `session_id`, `opponent_player_id`
and `battle_type:"PvF"`. Apache returned HTTP 404 HTML, and Android displayed
“The battle invite failed to send.” No battle was created.

This research supplies the contracts needed to implement the missing flow:

- [Invitations](friend-battle-invite-contract.md): create, response and revoke
  requests, typed create response, error enums, four events, tokens, local
  countdown and correlation behavior. A successful acceptance HTTP body is
  ignored; the accepted event alone does not start combat.
- [Battle start](friend-battle-start-contract.md): `PvF`, human opponent model,
  separate player/opponent perspectives, required cooldown dictionaries and
  active party IDs, animation-triggered readiness and timer consumption.
- [Server gaps](friend-battle-server-gaps.md): current one-player/wild assumptions,
  room-scoped SSE delivery, reconnect gaps, transaction invariants and a proposed
  dependency order with acceptance criteria.

The two native passes exported 74 and 50 bounded methods respectively; those
counts overlap and are not a count of distinct methods. REA 6.8.0, Ghidra and
actual ARM64 instructions establish the static findings. The native capture
verifies only create reachability and the replacement server's failure. No
original-server captures, token format, fixed invitation TTL, human turn order,
combat formulas, timeout adjudication or original server policy are claimed.

`contracts.json`, the OpenAPI discovery index, implementation inventory, managed
type index and parser mappings now account for these interfaces. Three HTTP
producers, the typed create callback, two error-only callbacks and four invitation
event consumers are mapped. Battle-start consumption is linked separately.
Implementation status remains absent for all three invitation endpoints.

## Next implementation

Start with durable invitation state and explicitly private delivery. Keep
friendship rows separate from battle invitation identity. Native replies carry
an opaque token and session, so authorize each action against the persisted
actor role; the client does not prove how the original server generated tokens.
Serialize send/respond/revoke/expiry and friendship-removal races with a common
ordered user-lock strategy, and preserve replay outcomes without duplicating
invites or notifications.

Playable acceptance additionally requires shared participation and world guards
for both users, two private start views, readiness, reconnect and terminal cleanup.
The existing `PvWM` handler assumes a wild spawn and generates AI retaliation;
feeding it a human opponent would leave the second user unguarded and cannot
provide the recovered two-client contract. Resolve the shared lifecycle before
enabling acceptance. Human move pairing and combat rules remain a subsequent
evidence/policy task, as detailed in the server gap review.

No gameplay PHP, schema or existing response format is changed by this pass.
The Android probe temporarily creates an accepted friendship through the existing
social APIs, records the exact new row, and removes only that row after guard
checks. That setup is synthetic and is not native invitation or original-server
evidence. The guarded capture helper and native export scripts are included;
raw account snapshots and wire captures remain ignored.
The primary app reloaded multiplayer WORLD after cleanup. Complete save/friend
guards, both-side battle-row comparison and the independent gameplay baseline
all passed; the integrator repeated the comparisons. The reusable decoder also
reproduced the sanitized fixture from the actual private PCAP without touching
either account. Shell syntax, Python syntax and protocol/source checks passed.

This branch starts from current main `9ff1a11`, with pending prerequisite PR #37
at `0512681` and its dependency history. It targets main without deployment,
migration or changes to README-completed feature status.

## Private start-view preparation

[Recipient-specific start views](private-battle-start-views.md) now freeze owner inventory/resources and public trainer profiles from existing immutable parties. Migration 010 stores both projections plus a capture marker; seven additional resource/profile writers serialize with shared participant claims. This is an internal preparation step: acceptance remains 501, with publication, readiness/reconnect, human turns and terminal cleanup still pending. Native evidence supports wire fields; no live client start or original combat formula is claimed.

[Shared startup](shared-battle-startup.md) adds atomic two-user activation,
recipient-only intent retrieval, initial readiness and paired cancellation/expiry
with migration 011. These are internal records without an SSE publisher or new
HTTP route. Public acceptance remains 501; native delivery/reconnect/abort
presentation, later readiness phases and human turns remain required.

[Research stream delivery](shared-battle-stream-delivery.md) supplies a separate
opt-in SSE/ready bridge, current-generation fencing and server-ended/EOF cleanup.
Its HTTP tests pass; the native client control path is statically established.
Actual Android startup/recovery capture and the remaining human battle lifecycle
still block public approval.

The [dedicated Android follow-up](android-shared-startup.md) now verifies
startup, initial ready and automatic fresh login/join on both clients. Native
approval was not successful or enabled, and no human moves were selected. The
remaining human selection/phase/combat/terminal implementation still blocks
public approval; broader delivery scenarios remain separate.

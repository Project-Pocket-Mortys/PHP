# Friend battle server gaps

This is a source review of the research branch based on main `9ff1a11` with
pending prerequisite changes, including the friend lifecycle work. It is not
evidence of a deployed database or successful two-client friend battle. No live
schema query, database write, emulator action, runtime change or migration was
performed for this review. Native invite and battle contracts are being recovered
separately; route names, invite fields, enum values and battle type strings must
come from that evidence before implementation.

## What exists

Accepted friendship is a usable prerequisite, not an invitation. In
`lib/friends.php`, `friend_lock_pair` authenticates an unambiguous account, locks
both users in sorted player-ID order, rechecks the session after waiting, then
reads the single relationship in either orientation. `pending='false'` is accepted;
duplicate or malformed pairs fail closed. The existing request/response/remove
writers share those locks. Reuse that discipline when an invitation depends on
friendship so removal and acceptance cannot observe incompatible relationship
states. The helper starts its own transaction, so it cannot simply be called
inside another transaction without refactoring or a separate lock-only primitive.

The following conflicts are observed directly in source:

| Area | Existing behavior | Consequence for two human accounts |
| --- | --- | --- |
| `pocket_mortys.sql`, `battles` | Initiator/opponent IDs, one active Morty and HP cache per side, terminal state, winner, streak fields, JSON `move_log`; no battle kind, room, invite, participant readiness or turn/selection identity | Two IDs alone do not describe a shared human battle. Do not infer kind from an ID matching a user. |
| Timeout migration `004-battle-move-deadline.sql` | Adds one nullable selection deadline and state/deadline index | This is a private-wild deadline, not evidence of two independently ready/selecting humans. The base SQL dump lacks the added column. |
| `session/battle-wild-morty/index.php` | Locks one user, reserves one wild snapshot, freezes the initiator deck, creates `PvWM`, marks one user and spawn `BATTLE`, emits one private start | Cannot start a friend battle by substituting the friend's ID for a wild ID. |
| `lib/battle_access.php` | Owner check permits only `battles.player_id` | Opponent is denied by the legacy access model. |
| `lib/battle_turn.php`, `battle_origin` | Requires exactly one explicitly private start for the initiator, current room match, `battle_type='PvWM'`, one player roster and one wild active ID | PvP needs its own durable origin/participant validation. Relaxing the type check would remove a safety boundary. |
| `session/battle/ready/index.php` | Initiator only; starts a 30-second deadline and private timer once | Does not wait for two players or record readiness. |
| `session/battle/move/index.php` | Initiator only; resolves immediately, uses opponent active ID as an `event_queue` wild spawn, deals fixed 20 damage and generates random AI retaliation | Cannot accept two human selections, await the other side, order actions, or update both owned parties correctly. |
| Turn result | One recipient; local `player_datas.player` contains updates while `opponent` is empty; outcome is local; terminal cleanup restores one user and removes/releases a wild spawn | Both views must be derived from one committed shared result, with correct local perspective and no wild cleanup. |
| `lib/world_action_guard.php` | Active lookup checks only `battles.player_id` | Opponent-side room/heal/absorb guards miss a human battle. Wild start also checks only initiator-side active battles. |
| `lib/battle_timeouts.php` | Locks one user then one battle; validates `PvWM` origin and spawn; restores one user and spawn on abandonment | Human battles require a separate shared terminal path and timeout interpretation. Do not feed them into this worker accidentally. |
| `session/state/index.php` | Echoes the supplied state without authentication or persistence | This endpoint cannot authorize or persist either participant entering/leaving a battle. |

The reviewed world guard callers include join-room, leave-room, heal,
use-shiny-potion and Morty absorption. An implementation must audit other roster,
deck, trade, inventory and session writers as well; this review does not establish
that every writer already observes the user lock or battle guard.

## Delivery and replay constraints

`lib/event_visibility.php` recognizes only start, turn-result and move-timer-started
as private battle events. An explicit `only_show_to_player_id` overrides legacy
targeting, and payload participant IDs grant no visibility. `publish_event` stores
one explicit recipient for each existing battle event; it serializes only the
known event payload columns. A new invite event cannot safely be introduced merely
by choosing a name: its recipient classification, serialization and SSE dispatch
must be implemented together from recovered evidence. Public subject `player_id`
does not make an unclassified event private.

The current SSE feed selects by the subscriber's room and then applies recipient
filtering. Its dispatcher emits the three known battle JSON columns. A fresh
connection snapshots room objects and advances to the room maximum event ID;
it does not reconstruct an active battle or pending invite. Therefore an event
alone is not sufficient durable state, and cross-room invitations cannot be
assumed to arrive through this feed. Establish from native evidence whether invites
are polled, delivered globally, or depend on room placement. Do not invent a
teleport or require co-location without evidence. If two private battle events
are needed, write one explicit recipient row per participant, addressed to their
supported delivery scope, in the same transaction as the shared state.

Private start payloads presently contain owner inventory and progression. Do not
blindly swap and broadcast the two complete owner objects. Derive each view from
the recovered local/opponent DTO contract and disclose only its required fields.

## Smallest safe dependency order

1. Complete native contract recovery first: invite send/list/respond/cancel or
   expiry operations actually present, recipient identification, errors, delivery
   and reconnect behavior, battle kind, start-side perspective, readiness and
   turn-result meaning. Record unknown combat mechanics explicitly. Social friend
   requests must remain separate from battle invitations.
2. Implement an invitation-only lifecycle behind the recovered routes. Persist
   invite identity, direction, lifecycle and replay result independently of
   `friend_list`; the precise schema is a later design change. Authenticate from
   session, validate accepted friendship and target eligibility under ordered
   user locks, and serialize send/respond/cancel/expiry/removal races. Do not set
   users to `BATTLE` or publish a start while no safe human battle lifecycle exists.
   If native approval necessarily starts combat, keep approval unavailable until
   the next slice is complete; do not report a successful playable battle.
3. Add explicit human-battle identity, durable participants/origin, immutable
   party snapshots, readiness/turn state and retry identity. The storage must
   enforce one live battle membership for either side and one battle per accepted
   invite. A participant reservation table with unique player membership is one
   candidate, not a native requirement or an approved migration. Make all start
   and world guard paths consult this invariant; preserve legacy PvWM behavior.
4. Connect atomic invite acceptance to one shared battle, two authoritative user
   transitions and two private start views. Add participant-specific ready handling,
   reconnect recovery and a safe shared cancellation/terminal path before enabling
   this slice. Test start/ready/cancel without applying combat damage or rewards.
5. Add two-human move selection and resolution only after the necessary rules are
   established. Persist selections and resolve once per authoritative turn; render
   both local results from that resolution. Define force-switch, simultaneous
   selection, timeout and surrender semantics from evidence or explicitly approved
   replacement policies. Existing fixed damage/AI values are documented replacement
   placeholders, not recovered original formulas and not a basis for claiming
   original PvP. Do not invent initiative, damage, status, reward or ranking rules.

Steps 1–2 are the smallest independent implementation slice. Step 4 is a viable
noncombat lifecycle milestone only when native contracts support that boundary;
it is not a completed friend battle feature. No step here authorizes deploying
runtime changes or modifying the shared database during research.

## Required transaction, security and retry properties

Use one lock order across invitation acceptance, friend removal, human ready/move,
terminal cleanup and workers: all involved user rows in deterministic order before
the shared battle/invite and deterministic roster/attack/inventory locks. Exact
ordering of later resources must be chosen consistently after schema design.
Revalidate session ownership and all eligibility after lock waits. Reject duplicate
player/session/Morty IDs, malformed rosters and contradictory historical state
without attempting speculative repair. A preliminary unlocked ID lookup is a hint,
not authorization. Never first lock only the caller and then wait for the opponent
while the opponent can do the symmetric operation.

Bind response/cancellation authority to the persisted invitation role. A third
account cannot learn invite/battle secrets by supplying another player's IDs.
Validate active party membership, owned attack and PP, inventory and selected
targets for the actual submitting side. An invitation is not permission for the
sender to choose or spend the recipient's moves or items.

Represent invitation expiry, readiness and turn transitions durably using the
database clock. Recheck a worker candidate after all locks, as the existing timeout
worker does, and make resolution compete atomically with cancellation/expiry.
Simultaneous acceptance and duplicate HTTP requests must reuse one persisted result,
not create another battle. A lost successful response must be retryable. A battle
ID and move fields alone cannot distinguish a retry from the same move on a later
turn; recover native request identity/acknowledgement behavior before choosing the
deduplication contract. Never silently treat a repeated attack as a new selection.

Commit participant state, roster/PP/inventory changes, immutable resolution and
both private deliveries together. A crash or insertion failure rolls everything
back. Terminal transition and cleanup run once for both participants; late moves,
ready requests and sweeps cannot reopen a terminal battle, reset a later deadline,
or apply rewards twice. Do not delete or mutate a wild spawn for a human opponent.
Do not repair human battles through legacy `PvWM` terminal reconciliation.

## Acceptance criteria for subsequent implementation

- Native invite UI sees the recovered response shapes and polling/events; accepted
  friendship alone never becomes an invite. Decline, cancellation and expiry do
  not change save, HP/AP, inventory or room membership.
- Two accepted friends can create at most one accepted battle from an invite;
  crossed invites, repeated approval, acceptance versus removal and acceptance
  versus wild start have deterministic persisted outcomes. Failed actions leave
  neither user partially reserved or in `BATTLE`.
- Both participants are guarded from incompatible world and roster mutations,
  whichever side occupies `player_id`. Third users and revoked sessions cannot
  ready, select moves, cancel as a participant or read private payloads.
- Both clients receive the same battle identity with correct local/opponent views;
  owner-only inventory/progression does not leak. Same-room third-account and
  cross-room delivery tests cover live SSE, resume cursor and fresh reconnect.
- Repeated ready does not extend a deadline. Duplicate, concurrent and reordered
  move requests resolve a turn once, consume PP/items once and emit consistent
  local outcomes. A legitimate identical move on a later turn still works.
- Disconnect, stale worker, timeout/move, cancel/move and simultaneous terminal
  races restore both users once without touching unrelated wild spawns. Injected
  failure during either event insert proves complete rollback and safe retry.
- Existing private-wild start/ready/move/switch/item/timeout/world-guard and friend
  lifecycle suites remain green. Two real Android accounts verify the recovered
  lifecycle before claiming playable friend battles; combat fidelity requires
  additional evidence beyond these server transaction tests.

These criteria are proposed checks, not tests executed by this source review.

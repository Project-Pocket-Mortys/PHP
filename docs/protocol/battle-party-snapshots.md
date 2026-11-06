# Internal friend battle party snapshots

This is an incremental server storage design for an internal `PREPARING` friend battle. It is not a recovered original-server schema, a native `battle:start` serializer, or a complete human battle implementation. Public invitation acceptance remains HTTP 501. No starts, accepted notifications, ready barrier, human turns, or reconnect flow are enabled by this work.

## Evidence and replacement design

[friend-battle-start-contract.md](friend-battle-start-contract.md) records the bounded Android 2.41.0 ARM64 native analysis using REA 6.8.0. The client consumes each participant's actual party and an `active_owned_morty` ID resolving inside it. Both parties need a living initial battler; synthesizing wild or bot stats does not supply a human party. The native evidence establishes model consumption, not a database layout, immutable snapshot algorithm, or initiative/stat formulas.

The replacement design stores raw database party and attack rows for both participants, preserving deck order, current HP, status, stats and AP. It chooses the first living Morty in deck order. Fainted members remain in the party; an entirely fainted party is invalid. Stored rows are internal data and must not be emitted directly to clients: database row IDs, owner columns and other internal fields need an explicit wire projection.

The internal entry point is `friend_battle_snapshot_parties(PDO, sessionId, battleId)`. It takes both users' locks in sorted player-ID order, rechecks current authentication after waiting, and validates the locked preparation, its live deadline, its invitation and accepted friendship, and exactly the two matching membership claims. A preparation is not an accepted wire invitation: its invitation remains `PENDING` while public accept is unavailable. Existing legacy ACTIVE battles must exclude preparation/snapshot admission.

Exactly one active deck must exist for each player; deck ID zero is valid. Its one to five distinct nonempty owned IDs must decode from a JSON list or the supported legacy escaped JSON representation. Missing, duplicate, foreign or globally ambiguous Morty IDs fail closed. This matters because `owned_attacks` has no player owner column, and legacy logical Morty IDs are not globally unique. Attack slot identity and current numeric fields must be validated rather than inferred from catalog formulas or silently repaired.

Species identity is checked against the 564 IDs in `config/multiplayer_morty_ids.json`, exported from the pinned multiplayer `MortyInfo` TextAsset through `tools/research/export_party_species.py`; the catalog records its provenance and hashes. It supplies identity membership only. The replacement server policy requires positive signed 32-bit level, maximum HP, attack/defence/speed and maximum AP, nonnegative current HP/AP within those maxima, and distinct attack slots 0 through 3. These are admission checks, not recovered formulas. Other raw fields, including XP and status/lock flags, remain preserved for a later explicitly validated native projection. A NULL legacy variant remains NULL in storage and is allowed under the established Normal fallback; no snapshot code rewrites it.

Migration `009` adds dedicated per-battle, per-player storage with a composite primary key and a SHA-256 digest of the stored JSON bytes. Both rows are created atomically. A replay validates the stored identities, shape, active-member consistency and integrity, and returns the committed pair rather than rereading changed gameplay stats. A missing half, extra participant, malformed payload or digest mismatch must fail closed. A digest detects accidental or partial changes; it is not an authentication mechanism against someone able to rewrite both the JSON and digest.

Preparation cancellation/expiry releases claims without restoring gameplay rows. Snapshots do not replace the shared membership guard, extend the preparation lease, or themselves advance its state to ACTIVE.

## Party writer coverage

The serialization rule is a user row lock followed by the shared-membership check, before party mutation. Reservation and snapshots use those same user locks. Merely checking `users.state='WORLD'` is insufficient because preparation intentionally leaves that state unchanged. Any membership claim blocks covered writers, including malformed or orphaned claims; only explicit preparation cleanup releases a proven claim pair.

| Writer | Party data affected | Coverage/boundary |
| --- | --- | --- |
| `session/deck/edit` | Deck membership/order; active deck | Transaction, authenticated user lock, membership guard before writes. |
| `session/deck/set-active` | Active deck selection | Same user serialization and membership guard. |
| `session/owned_morties/learn-attacks` | Replaces owned attack rows | User lock and membership guard; globally ambiguous IDs are skipped before attack deletion. |
| `session/gacha` | Creates Morties/attacks; may append to active deck | User lock and membership guard cover the whole transaction, including automatic party append. |
| `session/use-item` | Current HP, status, AP; item stock | User lock and membership guard before mutation. |
| `session/owned_morties/lock` | Morty lock flag | User lock and membership guard. |
| `session/owned_morties/release-multiple`, `attempt-release-multiple` via `lib/morty_release.php` | Deletes Morties/attacks; rewrites decks | User lock and membership guard; both aliases use the same implementation. |
| `session/owned_morties/absorb` via `lib/morty_absorb.php` | Removes donors/attacks; rewrites decks; target evolution points | Existing world-action guard includes shared memberships while holding user lock. |
| `session/heal` | Active party HP/AP | Existing world-action guard includes shared memberships while holding user lock; every referenced logical Morty ID is now globally locked and required to have exactly one row owned by the actor before HP/AP mutation. |
| `session/battle/move`, `lib/battle_items.php` | PvWM HP, status, AP; battle items | Existing battle transaction locks user first; friend admission excludes ACTIVE legacy battles. These are PvWM writers, not friend combat support. |
| `session/battle-wild-morty` | Claims a legacy battle and selects party | Existing user lock and shared-membership guard prevent new PvWM admission during preparation. |
| `trading/offer-response` via `lib/trade_membership_guard.php` | Changes Morty ownership; deletes offers | Locks every declared target and actual current owner in sorted order; rejects any membership, ambiguous identity or changed preflight row; exact row/owner updates and completion/deletion commit atomically. Trade authorization remains separate. |
| `user/register` | Initial user, deck, starter Morties/attacks | New-account initialization, outside an existing participant's preparation; not a universal admin/database-write guarantee. |

The trade guard is limited to protecting claimed participants' ownership. Preflight trade, offer, Morty and user reads happen outside its transaction. After all affected user locks are held, it locks and compares complete trade/offer/Morty rows with those hints, then makes its first nonlocking membership read. This prevents an old repeatable-read view from missing a reservation committed while it waited. Both declared destination owners and actual current owners are covered, since old trade rows can disagree with current ownership. Rejected and accepted responses both pass the guard before deleting an offer or changing ownership. Unreserved success keeps the existing `[null,null]` response.

This increment does **not** establish a universal party freeze or complete trade correctness. The legacy trade responder still lacks recovered authentication/authorization and offer-to-request binding policy. It does not reconcile deck references after an unreserved ownership swap, and it does not define a new general legacy-battle trade policy. Those gaps remain blockers for enabling public human starts; the limited guard must not be described as fixing the trade API as a whole.

Heal and learn-attacks now reject globally ambiguous Morty IDs before reaching ownerless attack updates. Heal also rejects a stale foreign or missing deck reference before either HP or AP changes. This closes a cross-owner bypass in which an unclaimed actor's malformed deck or duplicate logical ID could otherwise modify a claimed player's attacks. These checks reject malformed storage; they do not repair legacy decks or rewrite identities.

`trading/request-morty`, `offer-morty` and `cancel-trade` write trade metadata/currency, not party rows or lock flags. They can create or remove future trade references and remain part of the separate trade authorization/concurrency work. Read helpers such as `lib/active_deck.php`, player-details and state endpoints do not mutate parties. Research fixtures and direct operator SQL are outside HTTP writer coverage.

## Data deliberately outside this snapshot

The snapshot freezes party data only. It does not capture item inventory or a complete participant profile. Inventory changes and human trainer presentation still require a deliberate startup policy before native starts can be enabled.

| Writer area | Current mutation | Remaining startup decision |
| --- | --- | --- |
| `session/buy-item` | Item quantity | Legacy handler is outside the party guard; define authoritative stock reads and battle item policy. |
| `session/recipe/use` | Consumes ingredients and creates items | Locks user, checks WORLD; that alone does not block PREPARING. No inventory snapshot guarantee. |
| `session/collect-pickup` | Items/currency, pickup claims | Locks user and pickup, without a shared-membership check; no inventory frozen by party snapshots. |
| `session/use-shiny-potion` | Potion stock and expiry | Separate world-action guard; does not mutate an existing party's variant or stats. |
| `session/gacha`, `session/use-item`, `lib/battle_items.php` | Items/coupons alongside party mutations | Party guards cover their relevant paths, not all other stock writers. |
| `session/player-avatar/buy`, `set-active` | Active avatar and owned avatars | Profile can drift during preparation; choose a validated immutable public profile or atomic startup projection. |
| `session/decks/slots/buy` | `decks_owned` and coupons | Does not select a deck or edit party membership. |
| `user/login`, account/session endpoints | Session rotation and account data | Authentication must be revalidated under user locks; do not snapshot or expose session secrets. |

The future native wire serializer still needs separately validated trainer fields, perspective-specific `player`/`opponent` objects, `PvF`, the required `move_log` dictionaries, local authoritative inventory policy, and active IDs consistent with these stored parties. Shared readiness/timers, simultaneous human move resolution, disconnect/reconnect, completion and writeback policy remain separate work. Party capture alone does not make PvP ready.

## Verification boundary

`tests/protocol/test_friend_battle_party_snapshots.py` exercises additive UUID parties, exact raw stored values, replay after live changes, invalid ownership/decks/stats/attacks, authentication/claim/lease checks, corruption and paired-insert rollback. `test_party_writer_guards.py` covers guarded party writers and the duplicate-ID attack bypass. `test_trade_party_guard.py` covers all declared and actual owners, unreserved legacy accept/decline behavior, ambiguous identities, completion rollback and a claim committed while a trade waits for its user lock. These server tests do not establish native wire compatibility or successful human battle play; no emulator acceptance/start verification is implied.

`test_party_storage_guards.py` additionally checks both reserved actors' item,
lock and release/preview paths, cancellation reopening valid writes, and stale
foreign or globally ambiguous deck IDs failing healing without AP changes.

The focused runs passed: 12 snapshot cases in 129.398 seconds, six writer cases
in 39.727 seconds, six trade cases in 36.194 seconds and four storage cases in
23.856 seconds. These fixtures use fresh UUID accounts, catalog rows and fault
triggers and clean up only their own records; no real account purchases or
save reseeding are involved.

Migration 009 passed twice on a schema-only copy of the current research
database with its composite primary key checked, before application to the
isolated backend. Both party rows commit or roll back together. The affected
legacy PHP files use LF for reproducible source fingerprints; their behavior
changes are visible with end-of-line whitespace ignored. Duplicate local
`respond()` declarations in the two deck handlers were removed because they
conflicted with the shared bootstrap; unreserved success behavior is tested.

Reproduce the identity-only catalog and focused tests with the explicit installed
Windows interpreter (the Python Store aliases are unnecessary):

```powershell
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 tools/research/export_party_species.py
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_friend_battle_party_snapshots.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_party_writer_guards.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_party_storage_guards.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_trade_party_guard.py -v
```

Run database fixtures serially. The exporter uses UnityPy from the pinned local
toolchain and records the bundle and TextAsset hashes. It exports identities
only, without combining single-player data or replacing stored stats/AP.

The 62 existing item, release, lock, world-action, membership and preparation/
SSE cases also passed in 423.749 seconds: 90 distinct checked cases in total.
PHP 8.3 lint passed for all 52 changed/new PHP files including prerequisites;
protocol/source, Python and whitespace checks passed. Final fixture cleanup left
no party snapshots, preparation sessions or memberships. The original two-account
save/friend/battle/event/invitation guard and independent HP/AP/items/decks/
progression guard passed without reseeding, restoring or reserving real accounts.

This branch starts at main `9ff1a11` with pending prerequisite PR #41 at
`bbd9486` and its dependency history. README-completed features and attribution
are retained. Apply migration 009 before these internal capture helpers; no
deployment is included. Public acceptance remains unavailable.

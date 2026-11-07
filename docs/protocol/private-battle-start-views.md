# Private friend battle start views

This internal preparation format freezes two recipient-specific `PvF` start bodies. It does not publish `battle:start`, accepted notifications, timers, readiness, or turns. Public friend-battle acceptance remains disabled with 501. A valid private body does not establish a playable human battle implementation.

## Native compatibility evidence

Run `wsl bash tools/research/ghidra-private-start-context.sh` from the repository. This bounded pass uses default WSL, REA 6.8.0 artifact inspection, the pinned Ghidra toolchain, and `C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe`. Generated Ghidra JSON, Capstone disassembly, method bounds/hashes and artifact inspection stay under ignored `.research/` with the `private-start-context` prefix. No database, emulator, credentials, or event delivery is involved.

The pinned Android 2.41.0 ARM64 ELF SHA-256 is `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`. Metadata version is 31, metadata SHA-256 `b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10`, and script mapping SHA-256 `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb`.

| Method | Native RVA | Bounded bytes | Body SHA-256 |
| --- | --- | --- | --- |
| `MPOpponentData.SetFromDict` | `0x1589ab8` | 2552 | `b44327f90eb47a0c1df328c91d0b918ab80e3c7b28936027dfc5f95095d2f0cc` |
| `MPPlayerData.SetFromDict` | `0x15901b4` | 2308 | `f561864a5edd763dddd16f16d21c9d65375d1bae18967965d8f5f4b983b56303` |
| `MPUserData.SetFromDict` | `0x165f694` | 700 | `a114a3e184d6132451c92ba1e296483d37e0ac7121b84ad0c47435716812dc62` |
| `NetworkBattleAPI.BattleStartHandler` | `0x1788674` | 1676 | `9a4e196f10ecbe79e39f18c4d77d67ddc80c568e8393c127ba78d9ca1fca7030` |

Boundaries end at the next metadata method entry. Ghidra can follow exception fallthrough outside those bounds; conclusions here use normal paths and bounded Capstone evidence. REA establishes artifact identity, not semantics. Broader intro, active-Morty and cooldown evidence is recorded in [friend-battle-start-contract.md](friend-battle-start-contract.md).

`dump.cs:12429` declares `eMPOpponentType.USER = 2` and `PLAYER = 4`; `eMPOpponentState.BATTLE = 2` follows at line 12444. The local `player` projection must retain PLAYER (4), while the other human is USER (2). The base setter parses supplied `type` and `state` through enum parsing, including decimal numeric values. The human `PvF` branch additionally overwrites the enemy type with USER (2). It does not similarly overwrite the local player's supplied type.

`BattleStartHandler` applies `player` to the persistent local `MPPlayerData` with `clearMorties`, `clearItems` and `clearAvatars` all false. `MPPlayerData.SetFromDict` initializes deck storage, delegates to `MPUserData.SetFromDict`, then enumerates supplied keys. `MPUserData` delegates to `MPOpponentData` and handles `level`, `streak`, and avatar ID. Missing keys in those setters preserve existing state; they are not evidence that full account details are required by a start. Currency, XP, decks, owned avatars, Mortydex and other progression fields are optional update branches.

The directly required local key is `move_log`; its constructor directly reads `cooldown`, `cooldown_next`, and `count`. Empty inner JSON objects are valid zero-history containers. Supply the actual frozen party, active owned-Morty ID, trainer identity/avatar, level and streak needed by the intro and active selection. `active_owned_morty` is an owned-Morty ID string: the base setter converts its value to a string and stores the ID used by the selection predicates. An embedded Morty object does not meet that contract. The active ID must belong to that side's party.

The examined three setters and human start branch neither index nor parse `_meta.session_id`. The `PvF` branch constructs empty base battle metadata without reading the response's `meta`; the arena branch is different. There is no native justification for placing an authentication session in a start body. Serialize `meta` as an empty object and exclude sessions, tokens, recovery codes and arbitrary metadata throughout the wire projection. The later `/session/battle/ready` request independently uses the session held by the client.

Morty field spellings are declared at `dump.cs:12674`: `is_poisoned`, `is_paralysed`, `xp`, `xp_lower`, `xp_upper`, and `evolution_points`. Existing targeted `ghidra-use-item.json`, `ghidra-status-cure.json` and `ghidra-full-recover.json` exports include `MPOpponentMortyData.SetFromDict` (`0x158cb1c`): ailments convert to booleans; XP/bounds and evolution points convert to signed 32-bit integers. `evolution_points` is already a column in the raw `owned_morties` snapshot. Owner-only projection can normalize these values without altering that raw snapshot; the opponent projection excludes private XP and evolution progress. Item quantities convert to signed 16-bit integers, so nonnegative stock is bounded to 32767.

## Shipped identity catalog

`config/multiplayer_start_ids.json` contains `player_avatar_ids` (202), `item_ids` (51), and `default_player_avatar_id` (`AvatarRickDefault`). IDs are sorted, unique, nonempty strings. `sources` records bundle/asset hashes, asset names, path IDs, serialized-file identity and Unity version; `counts` records both list sizes. These are identifiers only, not item effect or stat formulas.

Reproduce with the explicit Python executable:

```powershell
& 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe' -X utf8 -B tools/research/export_start_identity_catalog.py
```

The script requires UnityPy 1.25.0 from `.research/python` and reads only `mpdata.assetbundle` through `export_item_effects.load_text`. Both assets come from `AssetBundles/AssetBundle-android_1011-ios_1011__7b175320/Android/mpdata.assetbundle`, bundle SHA-256 `f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413`, serialized file `CAB-e7dc2becff3f29e51ef6f3c597e695c4`, Unity `2022.3.62f1`.

| TextAsset | Path ID | Raw TextAsset SHA-256 |
| --- | --- | --- |
| `PlayerAvatarInfo` | `6817760569338222119` | `adc447fdbd2fcf89d56a6d63879da46ef2a2acda8be5121b6a86c4b049de426c` |
| `ItemInfo` | `8663868515058661470` | `ab713ae7e06f8b492628d10b73580d4016756d57072d04b5be43f271e7305a39` |

Do not combine these lists with single-player catalogs. Unknown avatar/item IDs fail closed during preparation; the catalog default is evidence that the existing shipped default is valid, not permission to silently replace an invalid stored profile.

## Persistence and privacy policy

Capture both current public trainer profiles and each owner's inventory/resources atomically once, under the same users-row locks used by reservation creation and preparation writers. A shared participant claim blocks changes to captured profile/resources and party state. Lock participants in deterministic order. Inventory capture must not start from an earlier consistent-read snapshot.

Store the frozen context and both recipient bodies with their JSON SHA-256 values in the private start-view storage. Replays compare frozen context with current profile and item rows and fail closed if either changed. They never recapture resources or replace a frozen view. Raw party snapshots remain unchanged; the wire projection is a separate explicit allowlist.

Migration 010 adds `friend_battle_start_views` and the nullable session marker
`start_views_created_at`. The two view rows and first-capture marker commit
together. A marked session with either or both rows missing fails closed, as
does a row pair without its marker. Capture does not renew the preparation
deadline or modify the session's gameplay state. Existing sessions begin with
a NULL marker; no existing save data is rewritten.

`active_owned_morty` is an ID string in both views. Inventory rows retain zero
quantities and sort by item ID; duplicate/unknown items and quantities outside
0..32767 fail. The upper bound follows native `SetItemsFromDicts`, which calls
`System.Convert.ToInt16`. Stored attack PP maxima remain unchanged; the attack
catalog is used for identity validation only. Owner XP/evolution, streak and
resources use nonnegative 32-bit integers; legacy NULL numeric values project
to zero. Required numeric source keys must exist, and level must be positive.
Legacy NULL flags project to false; malformed flags fail. These fallback rules
are replacement-server compatibility policy, not evidence of original formulas.

The internal `friend_battle_build_start_views` function returns both perspectives
to trusted server orchestration. It has no HTTP route. A future publisher must
select only the authenticated recipient's body; the combined return value must
never be returned to a client. Public acceptance still returns 501 `FAILED`.

For A's view, `player=A` has type PLAYER/BATTLE and contains only A's allowed owner resources; `opponent=B` has type USER/BATTLE and contains B's public trainer/party fields. Reverse those roles for B's view. Both bodies share the battle ID and `PvF` type. Never expose the opponent's currency, inventory, account progression or lock state. Project known names, IDs, numeric values and flags explicitly; never copy entire user/item/party database rows or authentication metadata into either body.

Resource/profile writers must lock the authenticated users row before checking the shared claim and before reading or changing resources. This includes item use and purchase, crafting, gacha, pickups, avatar changes, slot purchase and trading costs, alongside existing party/deck writers. This rule is a server preparation policy, not a recovered original-server protocol. Source review and isolated-backend integration tests cover these invariants; no live Android battle-start verification is implied.

## Reproduction and validation

Start the existing isolated Compose stack and apply its ordered, additive
migrations before these suites. The original SQL dump remains unchanged.

```powershell
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/migrate.php
$researchPython = Join-Path $env:LOCALAPPDATA 'Python\pythoncore-3.14-64\python.exe'
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_friend_battle_start_views.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_start_context_writer_guards.py -v
& $researchPython -X utf8 -m unittest discover -s tests/protocol -p test_crafting_pickup_preparation_guards.py -v
```

Run database suites serially. They create UUID accounts and narrowly scoped
fault triggers, then clean only their own records. Do not run unrestricted
discovery: older account/battle fixtures globally reseed saves. The explicit
suite list in `tools/research/check_gameplay_integration.py` includes these
three modules and checks migration 010 prerequisites.

The 12 start-view cases passed in 175.831 seconds. They cover typed owner/peer
projections, JSON object dictionaries, immutable party sourcing, profile/stock
drift, malformed records and hashes, both missing view rows, missing source
parties, auth/claims/lease revalidation, atomic second-insert rollback and
unchanged public acceptance. Migration 010 passed twice against a schema-only
copy of the current database, including composite-key and nullable-marker
checks, before application to the isolated backend.

The 13 writer regressions passed serially: eight profile/shop/trade cases in
62.249 seconds and five crafting/pickup cases in 26.711 seconds. Both participant
roles, orphan claims, cancellation reopening, post-lock claim/session changes,
legacy unclaimed responses/costs and injected second-write failures are covered.
No real purchases or save reseeding were performed.

The 74 existing party snapshot/writer/storage/trade, crafting, membership,
deadline, SSE preparation and shared-guard regressions passed in 443.805 seconds:
99 distinct checked cases in total. PHP 8.3 lint passed all 60 changed/new PHP
files including prerequisites; protocol/source fingerprints, Python syntax,
native boundary and whitespace checks passed. Both original account guards
passed: complete save/friend/battle/event/invitation state and independent
HP/AP/items/decks/progression/membership comparisons. Final UUID cleanup left
zero private views, party snapshots, preparation sessions and memberships.

This branch starts at `origin/main` `9ff1a11` with prerequisite PR #42 head
`ccfdfd1` and its dependency history fast-forwarded explicitly. README-completed
features and project attribution are preserved. Deployment, native event
publication and live human battle startup are outside this change.

## Next dependency

Implement shared startup/readiness and safe cancellation before exposing
acceptance. Activation must revalidate frozen context and atomically persist
both private publication identities, invitation transition and participant state.
The existing wild ready/timeout paths are owner/spawn-specific and cannot be
reused as human cleanup. Reconnect must recover the correct participant view
without relying on a historical room cursor. Shared terminal cleanup must
restore both users and release both claims once.

Native ready requests contain only session and battle IDs and recur after later
animations. Establish phase/barrier and retry behavior before publishing move
timers; delayed retries must not accidentally advance another phase. Human turns,
damage/rewards and ranking remain separate gaps. Accepted-before-start event
ordering is not established as a native requirement.

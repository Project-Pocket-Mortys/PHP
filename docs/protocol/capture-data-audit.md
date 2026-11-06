# Multiplayer capture data prerequisite audit

Audited 2026-11-04 against the Android 1011 bundles and current PHP/SQL sources. This is a read-only research result, not a balance implementation or official server response capture.

**Full authoritative MP capture is blocked by missing MP stat/XP generation and capture probability evidence.** Species identity, learnsets, attack definitions, and capture item flags are available. Existing local wild snapshots are explicit placeholders and cannot truthfully become captured owned records. This conclusion is limited to the inspected bundled tables and repository; it does not assert that original server logic can never be recovered elsewhere.

## Reproduction and source identity

Run `py -3.14 tools/research/audit_capture_data.py --check`. It imports `load_text` from `export_item_effects.py`, uses the ignored `.research/python` UnityPy **1.25.0** install (Windows cp314 extensions), reads Android bundles, compares all MP TextAsset payload hashes to `assets.json`, checks audited payload identities and learnset references, and prints JSON to stdout. It does not write runtime data, assets, or the database. `--check` checks evidence consistency; success does **not** mean capture is implementable.

Bundle root: `AssetBundles/AssetBundle-android_1011-ios_1011__7b175320/Android/`.

Actual `mpdata.assetbundle` SHA-256: `f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413`. Historical `docs/protocol/assets.json` bundle SHA-256: `4aaf41628752950012d0034624a3335964177ab723c91d979563eca144f821b5`. All **14 other TextAsset payloads match** the historical catalog; `ItemInfo` differs. Thus historical bundle identity must not be substituted for the inspected bundle, while unchanged individual payloads remain reusable evidence.

All three tables below are in serialized file `CAB-e7dc2becff3f29e51ef6f3c597e695c4`, Unity `2022.3.62f1`:

| MP TextAsset | Rows | Path ID | Payload SHA-256 |
| --- | ---: | ---: | --- |
| MortyInfo | 564 | -5656435499516812579 | `96072cc81591577cc31245c6f0ef7518d6ef1b5b5b47e261fd93163caba5ea99` |
| MortyAttacksInfo | 564 | 2865218101114482185 | `4b98487f06f6bdeb75eca0370ae736311741563fdc45327f1a9f591d91a79d7f` |
| AttackInfo | 690 | -2967366534230292340 | `ee1ce3bd8451e46a7cd29244eba26b275d4f564dc92b92b8c577bc00553d1d51` |

## What the MP tables establish

`MortyInfo` is a JSON list. Complete observed field types: `morty_id`, `asset_id`, `gender`, `height`, `weight` are strings; `number`, `division` are integers; `element` is string or null; `evolution_req` is integer or null. There are no HP, attack, defence, speed, XP, level growth, capture rate, or stat roll fields. Example `MortyDefault`: number 1, division 4, null element and evolution requirement. `MortyScruffy`: number 2, division 1, element `Rock`, evolution requirement 3.

`MortyAttacksInfo` is a list of `{morty_id: string, attacks: list}`. Each learnset entry is `{attack_id: string, level: integer}`. Its 564 species IDs equal the unique `MortyInfo` IDs, and every referenced attack exists in `AttackInfo` (`--check` passed). `MortyDefault` begins `AttackOutburst:1`, `AttackCry:6`, `AttackFlail:8`, `AttackBelch:10`. This establishes eligibility by level, not the original server's rule for choosing four initial attacks, positions, replacement behavior, or generated level.

`AttackInfo` entries have `attack_id: string`, `pp_stat: integer`, `element: string|null`, and `effects: list`. For example `AttackOutburst` has `pp_stat:12`, null element and Hit power 50, accuracy 0.95. `AttackStruggle` has `pp_stat:-1` and two Hit effects (power 25 and self power 20). These are real MP attack definitions, but do not supply Morty stats, growth, capture chance, or a complete damage formula.

The other MP TextAssets are `ItemCampaign`, `RecipeInfo`, `RaidEventInfo`, `RaidBossAttackInfo`, `ProductInfo`, `NPCInfo`, `RaidBossInfo`, `IAPInfo`, `ArenaEventInfo`, `PlayerAvatarInfo`, `ArenaRewardsInfo`, and `ItemInfo`. The exporter reports their complete top-level field/type inventories; none provides a normal MP species stat/XP or capture probability table. Raid boss data is not a wild Morty generator.

## Keep SP evidence separate

`appdata.assetbundle` has no `MortyInfo` TextAsset. The richer single-player table is **`spdata.assetbundle` / `MortyInfo`**, a dictionary of 564 records, payload SHA-256 `c90a68264d7b757858047b81e49fb1e95d3b61b8838fc6780ce7e5197eed36fa`, path ID `-193237568149106102`. Actual SP bundle SHA-256 is `8743a6c221497a99a38be4c8cc4d2a67cb566e63ca3c4beccf49d8b4e067c563`; historical catalog records a different bundle hash but the same MortyInfo payload.

SP `MortyDefault` contains string values `hpbase:"45"`, `attackbase:"45"`, `defencebase:"45"`, `speedbase:"40"`, `defeatedxp:"50"`, and a comma-separated learnset string. Their presence is **not evidence of MP balance or formulas**. Do not join these into an MP stat catalog merely because species IDs match.

## Current authoritative state and gaps

`lib/room_entities.php` seeds wild events with identity, position, state, random division, variant, potion flag, IDs and timestamps. `lib/room-spawner.php` also produces wild identity/placement/state/variant metadata. `lib/events.php` preserves those event values; it does not generate missing combat stats. The random division itself is not a species stat source.

`session/battle-wild-morty/index.php` explicitly sets level **999**, XP **1000000**, HP and maximum HP **1**. Its opponent record has no owned attacks, attack/defence/speed stats, or XP bounds. `battles.opponent_hp` and the private `battle:start` snapshot therefore authenticate the local battle state, but not original captured stats. `session/battle/move/index.php` currently rejects ITEM with HTTP 501 / `ITEM_UNUSABLE` before consuming an item; its ATTACK numbers remain documented placeholders.

`user/register/index.php` creates exactly one fixed starter record: `MortyDefault`, level 5, XP/lower 125, upper 216, HP/max 20, attack 11, defence/speed 10, `AttackOutburst` position 0 PP/max 12. This fixed local starter is not a level/species growth formula.

`session/gacha/index.php` creates records from DB promo stat ranges and promo attacks, randomly chooses their values, and sets XP to `round(level² * 28)` with both XP bounds equal to that XP. Neither the local SQL seed nor this local generator supplies provenance for original MP wild stats. Gacha rows cannot be reused as authoritative wild capture data. The `session/state` endpoint only echoes requested state.

`pocket_mortys.sql` defines:

| State | Current storage / implication |
| --- | --- |
| Owned record | `owned_morties`: owner/species/owned ID text; level, XP, current/max HP, attack, defence, speed, evolution points, lower/upper XP nullable bigint; variant and lock/fight-pit fields. New capture must populate a coherent record from verified source data. |
| Attacks | `owned_attacks`: owned ID, attack ID, position, current/max PP plus nullable effect columns. No player ownership column; current battle guards reject ambiguous owned IDs. |
| Deck | `decks`: player ID, deck ID, owned-Morty-ID text list; `users.active_deck_id` selects the deck. Storage insertion and automatic deck insertion are separate contract questions. |
| Seen/caught | `mortydex`: player ID, species ID, `caught` tinytext only. No explicit seen field. Existing row with false caught could represent seen; that transition needs client/original behavior evidence. Registration/gacha currently upsert true caught, and player-details emits a boolean. |
| Storage capacity | `/morty/slots/config` advertises starting 350, maximum 750, increments 100, cost 5. `users` has no `morty_slots` column or purchase state; player-details omits it. Do not enforce advertised maximum as the player's owned capacity. |
| Ailments | The original SQL dump has no persisted fields. Migration 003 now adds `is_poisoned` and `is_paralysed` to owned_morties for targeted cures (`status-cure-implementation.md`); battle application/ticks and capture status policy remain separate. Client fields alone do not authenticate an ailment. |

The ignored client stub `MPOpponentMortyData.cs` explicitly names string keys for owned ID/species, level, XP bounds, HP/max, attack/defence/speed, owned attacks, position, variant, locks, evolution points and ailments. Its numeric stats and XP are managed `int`, ailment flags are `bool`. These establish client metadata, not every field's mandatory presence or server generation algorithm. Existing SQL bigint declarations do not imply the client accepts arbitrarily large values.

Before enabling a successful capture, obtain original MP stat/XP generation or trustworthy complete per-spawn records, level/variant rules, initial attack choice and PP rules, capture chance/rounding/status modifiers, storage-capacity persistence and full-storage behavior, seen/caught transitions, deck placement, and exact success/failure event ordering. Existing lifecycle locks and snapshots can enforce ownership/replay protection once this behavior is evidenced. Do not invent balance or silently copy the level-999/HP-1 battle stub into ownership.

## Independent cure item evidence

Actual MP `ItemInfo` payload SHA-256: `ab713ae7e06f8b492628d10b73580d4016756d57072d04b5be43f271e7305a39`, path ID `8663868515058661470` (same MP serialized file/version above).

| Exact item ID | effect_type | effect_stat | attacker_animation |
| --- | --- | --- | --- |
| ItemPoisonCure | Cure | Poison | PoisonGun |
| ItemParalysisCure | Cure | Paralysis | ParalyseGun |
| ItemFullRecover | Cure | All | FullReviveGun |

All three have `use_world:true`, `use_battle:true`, `use_self:true`, `use_craft:true`, `use_account:false`. `CurePoison` and `CureParalyze` are not these bundled item IDs. The client `MPOpponentMortyData.cs` lines 36–37 gives `is_paralysed` and `is_poisoned`, with public bool fields `isParalysed` / `isPoisoned`. This supplies exact status names and avoids numeric balance inference. A correct implementation still needs authoritative status persistence and transactional decrement/mutation plus reviewed response behavior; flags must not come from caller-supplied status claims.

`ItemMortyChip` has `effect_type:"Capture"`, `effect_stat:null`, `use_battle:true`, `use_world:false`, `use_self:false`, `use_craft:true`, `use_account:false`, defender animation `CaptureGun`. No probability is encoded in that record.

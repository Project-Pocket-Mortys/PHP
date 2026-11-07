# Remaining item effect evidence

Read-only Android 2.41.0 audit, 2026-11-05. The next fixed numeric Morty
mutation is not established by the remaining world-item metadata. Account
Shiny Potion has an independently specified two-hour duration and a separate
endpoint; see the shiny-potion contract research.

## Sources

The current workspace MP bundle and English hashes, serialized files and
Unity version are recorded in [use-item-data.md](use-item-data.md). This audit
loaded both actual bundles with UnityPy, joining every MP `ItemInfo` record to
`EN.Item` by exact ID. MP has no `effect_value` column. The existing preserved
MP extraction differs only in price fields, as documented there.

`bash tools/research/ghidra-stat-items.sh` reproduces the bounded native
inspection through the pinned REA 6.8.0 toolchain and build-guarded Ghidra
wrapper, and exports all actual MP records plus English to ignored
`.research/stat-items-metadata.json`. Native ARM64 binary SHA-256 is
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`.

## Remaining world items

These are all world-usable records beyond the thirteen existing HP/full
revive/full AP/cure items. All six Morty items have `use_self=true`,
`use_account=false`. Only the two percentage items permit battle use.

| ID | MP effect/stat | English effect | Missing implementation evidence |
|---|---|---|---|
| `ItemHalzinger` | Revive | Restores a dazed Morty to 50% HP | Odd-HP rounding and minimum restoration |
| `ItemPlutonicRock` | RestorePP | Adds 50% of AP to all attacks | Fractional AP rounding |
| `ItemMegaSeedAttack` | StatIncrease / Attack | Increases Attack stat | Numeric MP gain, persisted training/stat transition and cap |
| `ItemMegaSeedDefence` | StatIncrease / Defence | Increases Defense stat | Numeric MP gain, persisted training/stat transition and cap |
| `ItemMegaSeedSpeed` | StatIncrease / Speed | Increases Speed stat | Numeric MP gain, persisted training/stat transition and cap |
| `ItemMegaSeedLevelUp` | StatIncrease / Level | Increases a Morty's level by 1 | XP bounds, growth, attack learning, HP/AP/status transition and maximum-level behavior |
| `ItemShinyPotion` | ShinyPotion / null | Increases chance to encounter Shiny Mortys for 2 hours | Separate account activation, expiry and encounter consumers; no probability in metadata |

Shiny Potion alone has `use_account=true`, `use_self=false`,
`use_battle=false`. No other account-usable record exists in this MP table.

## Native stat boundaries

`MPItemDefs.CanItemBeApplyedToMorty` (`0x176a44c`) explicitly validates HP,
cure, AP and revive conditions. Other effect types, including `StatIncrease`,
return true by default. It supplies no seed amount or cap and does not prove
server acceptance of every selected Morty.

`MPItemDefs.GetItemUsedResultText` (`0x176a6ec`) handles non-Level stat seeds
by checking the response `itemEffectValue > 0`. Positive values produce a
localized permanent-increase message containing the stat name but no amount;
zero/negative values use `MP_ITEM_APPLY_STAT_FAIL`. Level seeds use
`isSuccess` to select a maximum-level message or a level-result message.
This method consumes server results; it computes no stat transition.

The dumped `MortyDefs.kStatMax=256`, `kEVMax=65535`, and SP item values
10/10/5 are single-player evidence. `MPMortyDefs` provides no corresponding
numeric seed contract. These constants must not become MP server rules.

## General and battle-only items

There is no `currencyBox`/`ItemCurrencyBox` MP item record in these bundles.
`NetworkPlayerAPI.UseGeneralItem` (`0x17a48c0`) sends session/item identifiers
to `/session/use-general-item`; its callback (`0x17a6b30`) parses an opaque
object and publishes the result. The existence of this transport supplies no
currency reward or loot-table contract.

Crafting parts have null effects and `use_world=false`, `use_account=false`.
Dragon's Tear, Dragon's Sweat, Sentient Switchblade and Wrist-Mounted Scanner
also have all use flags false, including crafting. Their English flavor text
does not authorize inventory consumption or gameplay mutations.

Battle-only effects are Morty Manipulator Chip (`Capture`, low-health capture
description), Mr. Meeseeks Box (`DamageHP`, instant defeat description), Toxic
Bundle (`FDAItem` / Speed, no numeric description), and Vape Incinerating
Rocket (`DamageHP`, no numeric description). Mr. Meeseeks Box now has a separate [native contract](meeseeks-box-contract.md)
and [PvWM implementation](meeseeks-box-implementation.md): the current owned
actor uses one box to set the enemy HP to zero and complete WIN. Its numeric
`effect_value` convention reports prior enemy HP; the native damage animation
uses the defender snapshot. No damage formula is introduced. The remaining
battle-only items still require targeting, restrictions, result and terminal-state
contracts. None is an additional world-use candidate.

No runtime, account, database or asset mutation was performed for this audit.

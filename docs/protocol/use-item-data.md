# Item effect evidence

The shipped Android multiplayer item metadata and English descriptions establish
the item IDs and effects below. They do not establish every arithmetic detail of
the original multiplayer server. In particular, percentage rounding remains
unresolved. `RestorePP` is the internal name for AP restoration.

## Sources and reproduction

All bundles below belong to
`AssetBundles/AssetBundle-android_1011-ios_1011__7b175320/Android/`, used with the
Android 2.41.0 research client. These are Android sources; no iOS equivalence is
claimed. The Unity serialized files report `2022.3.62f1`.

| Source | SHA-256 |
|---|---|
| `mpdata.assetbundle` | `4aaf41628752950012d0034624a3335964177ab723c91d979563eca144f821b5` |
| Its `ItemInfo` TextAsset | `c7ddb7536ad2a4fa1f48bf3e109e520a706b9056e5d9c484b808ba222f3e5fcc` |
| `text.assetbundle` | `bbe4b3036a907354dd7cad8122c0f557491e3259b6f4f349eda27caa913bc7a8` |
| Its `EN` TextAsset | `841eed65c78a058635eef4993f07b0a5592e8906f77c95027604cc3c57d4e1c4` |

The MP hashes above identify the preserved extraction catalog in
`docs/protocol/assets.json` and ignored `.research/assets/4aaf416287529500/`.
The current workspace MP bundle instead hashes to
`f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413`, with
`ItemInfo` hash
`ab713ae7e06f8b492628d10b73580d4016756d57072d04b5be43f271e7305a39`.
Direct comparison with that preserved extraction found only eight price fields
changed: Shiny Potion premium price and Morty Chip, Serum, Great Serum, Poison
Cure, Paralyze Cure, Plutonic Rock, and Pure Plutonic Rock costs. Every item ID,
effect type, effect stat, and use flag agrees. The exporter reports the hashes
of the actual files it reads so this distinction remains visible.

`EN` has path ID `2069814988615685635` in serialized file
`CAB-39e13adce6685e5d14cbb0d06c247c93`. Its `Item` section maps the exact MP
`item_id` values to descriptions. The localization is shared client data, joined
to MP metadata by ID; it is not an MP numeric effect table. MP `ItemInfo` contains
`effect_type`, `effect_stat`, and use flags, but contains no `effect_value` field.

Reproduce the join directly from workspace bundles using the existing ignored
UnityPy installation:

```powershell
py tools/research/export_item_effects.py
```

The script reads bundles and prints JSON with source hashes, descriptions and
complete MP records. It does not change bundles or database state. Existing
`docs/protocol/assets.json` catalogs the MP metadata export; the English TextAsset
was separately inspected with UnityPy.

## HP, revival, and AP

Every item in this table has MP `use_world=true`, `use_battle=true`,
`use_self=true`, `use_account=false`.

| Exact item ID | MP effect type | Shipped English effect |
|---|---|---|
| `ItemSerum` | `RestoreHP` | Heals 20 HP |
| `ItemGreatSerum` | `RestoreHP` | Heals 50 HP |
| `ItemSensationalSerum` | `RestoreHP` | Heals 200 HP |
| `ItemPureSerum` | `RestoreHP` | Heals all HP |
| `ItemEasterEgg` | `RestoreHP` | Heals 30 HP |
| `ItemPumpkin` | `RestoreHP` | Heals 30 HP |
| `ItemSpicyBBQPizza` | `RestoreHP` | Heals 200 HP |
| `ItemBreakfastMedley` | `RestoreHP` | Restores 200 HP |
| `ItemHalzinger` | `Revive` | Restores a dazed Morty to 50% HP |
| `ItemPureHalzinger` | `Revive` | Restores a dazed Morty to 100% HP |
| `ItemPlutonicRock` | `RestorePP` | Adds 50% of AP to all attacks |
| `ItemPurePlutonicRock` | `RestorePP` | Restores full AP to all attacks |

The text does not specify floor/ceil/nearest rounding for half HP or half AP,
minimum restored HP, or fractional AP handling. Those details require native or
runtime evidence. The ordinary Plutonic Rock adds AP; it does not set remaining
AP to half. Full AP applies to all attacks, with each attack's own maximum.

The same `EN.TextDefs` includes failure messages for HP restoration on a dazed
Morty or one with full HP (`ITEM_APPLY_HP_FAILED_FAINTED`,
`ITEM_APPLY_HP_FAILED_FULL`), AP restoration on a dazed Morty or one with full AP
(`ITEM_APPLY_PP_FAILED_FAINTED`, `ITEM_APPLY_PP_FAILED_FULL`), and revival of a
Morty that is not dazed (`ITEM_APPLY_FAILED_ALIVE`). They support the intended UI
restrictions, without independently proving the original server's validation.

## Other world items

MP `ItemPoisonCure` is `Cure` / `Poison`, `ItemParalysisCure` is `Cure` /
`Paralysis`, and `ItemFullRecover` is `Cure` / `All`. Their English descriptions
respectively cure poison, cure paralysis, and heal all HP and cure all ailments.
Do not implement `ItemFullRecover` as AP restoration based on its name.

MP includes `ItemMegaSeedAttack`, `ItemMegaSeedDefence`, `ItemMegaSeedSpeed` and
`ItemMegaSeedLevelUp` as `StatIncrease` with corresponding `effect_stat` values
`Attack`, `Defence`, `Speed` and `Level`. They permit world use and forbid battle
use. Their numeric effects and stat/XP transitions need separate evidence.

## Single-player evidence boundary

Android `spdata.assetbundle` SHA-256
`dd1997d763c65eef8ad622f55c9b209a755ca534d1dce1c251cd409a31730f97`
has a different `ItemInfo` schema. Its TextAsset SHA-256 is
`d4658a265f0e0e04becb935e6931c3479012dbb25afd5331420d0a7e80005339`.
It supplies string `effectvalue` values: Serum 20, Great Serum 50, Sensational
Serum 200, Halzinger 50, Pure Halzinger 100, Plutonic Rock 50, Pure Plutonic Rock
100, attack seed 10, defense seed 10, speed seed 5, level seed 1. Pure Serum's
value is empty. These are SP metadata, not proof of MP arithmetic.

The client dump exposes SP `ItemDefs.ApplyRestoreHPItemToMorty`,
`ApplyPPItemToMorty`, and `ApplyReviveItemToMorty`. MP `MPItemDefs` instead
exposes `CanItemBeApplyedToMorty` and
`GetItemUsedResultText(..., int itemEffectValue, ...)`; it has no `EffectValue`
getter. Dumped signatures alone do not recover method behavior.

`ItemDefs.kPureHalzingerID` contains the spelling `ItemHalzingerPure`, but both
the MP and SP tables use `ItemPureHalzinger`. Implementations should use the
actual metadata ID and should not create a second item ID from that constant.

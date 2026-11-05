# Multiplayer crafting data

`config/crafting_recipes.json` contains all 22 recipes in the Android multiplayer
`RecipeInfo` TextAsset. It is keyed by the exact, case-sensitive recipe ID. Each
entry maps ingredient item IDs to their slot multiplicity and names the result
item with quantity 1. These are gameplay data identifiers, not display names.
The server must resolve the requested recipe against this catalog rather than
accepting ingredient or result IDs from the caller.

Regenerate or check the catalog with the local Python 3.14 research environment:

```powershell
py -3.14 tools/research/export_crafting_data.py
py -3.14 tools/research/export_crafting_data.py --check
```

Extraction used UnityPy 1.25.0, matching `tools/research/toolchain.lock.json`.
The exporter uses UnityPy from `.research/python` when present. It reads only
the Android `mpdata.assetbundle`; it never combines the 34 single-player recipes
with multiplayer recipes. It rejects unexpected TextAsset hashes, table sizes,
recipe fields, missing item IDs, and unsupported item types. Runtime operation
does not require Python, UnityPy, bundles, or the ignored research directory.

## Provenance

Bundle path:
`AssetBundles/AssetBundle-android_1011-ios_1011__7b175320/Android/mpdata.assetbundle`.
The actual checked-in bundle SHA-256 is
`f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413`.
This is the on-disk Android 1011 bundle; a manifest naming a different bundle
release does not establish the contents of that unavailable release.
UnityPy reports Unity `2022.3.62f1` and serialized file
`CAB-e7dc2becff3f29e51ef6f3c597e695c4`.

| TextAsset | Path ID | Raw UTF-8 SHA-256 | Rows |
| --- | --- | --- | --- |
| RecipeInfo | -8103420440329103237 | `e2a9a5dc4e33eb333d360ac7df2d0263afedadfb016b7ad6aa4df2331fd1c504` | 22 |
| ItemInfo | 8663868515058661470 | `ab713ae7e06f8b492628d10b73580d4016756d57072d04b5be43f271e7305a39` | 51 |

`docs/protocol/assets.json` preserves an earlier bundle catalog whose multiplayer
bundle hash is `4aaf41628752950012d0034624a3335964177ab723c91d979563eca144f821b5`.
Its RecipeInfo hash is identical. Its ItemInfo hash is
`c7ddb7536ad2a4fa1f48bf3e109e520a706b9056e5d9c484b808ba222f3e5fcc`.
A field-by-field comparison of all 51 rows confirms that the differences are
only these prices (preserved value → actual value):

| Item | Field | Change |
| --- | --- | --- |
| ItemShinyPotion | mp_premium_cost | 0 → 5 |
| ItemMortyChip | cost | 0 → 500 |
| ItemSerum | cost | 0 → 250 |
| ItemGreatSerum | cost | 0 → 500 |
| ItemPoisonCure | cost | 0 → 500 |
| ItemParalysisCure | cost | 0 → 500 |
| ItemPlutonicRock | cost | 0 → 200 |
| ItemPurePlutonicRock | cost | 0 → 800 |

The preserved catalog is intentionally left intact; the exporter pins the
actual bundle's TextAssets. Whole-bundle equality is not assumed.

## Recipe and item semantics

The raw recipe fields are `recipe_id`, `sortorder`, `item_id_1`, `item_id_2`,
`item_id_3`, and `item_id_result`. A null ingredient slot contributes nothing;
each non-null slot contributes one ingredient. No ingredient amount or output
amount is stored in RecipeInfo. The runtime representation aggregates repeated
slots and represents a single craft's result as quantity 1. No current recipe
has duplicate ingredient slots. Native/client contract evidence is needed to
establish how these quantities are applied by the crafting endpoint.

The MP ItemInfo table contains 24 `ITEM` and 27 `PART` rows. Every ingredient and
result resolves to one of those types. Every ingredient has `use_craft=true`.
`ItemBreakfastMedley`, `ItemSpicyBBQPizza`, and `ItemVapeIncineratingRocket` are
valid recipe results with `use_craft=false`, so that flag must not exclude a
result from the catalog. `ItemEasterEgg`, `ItemPumpkin`, and `ItemMrMeeseek` have
`use_craft=true` but appear in no multiplayer recipe; that flag alone does not
authorize a recipe.

There is no `limit`, maximum inventory, unlock, owned recipe, level gate, cost,
or required recipe ownership field in RecipeInfo. ItemInfo likewise has no
`limit` or maximum inventory field. Consequently no item-limit configuration
is generated from these tables. Absence of those fields does not establish
unlimited inventory or prove whether discovery/owned recipes gate requests;
those behaviors require native or observed endpoint evidence.

A minimal Android fixture is `RecipeSerum`: inventory containing
`ItemBattery: 1` and `ItemFleeb: 1`, with output `ItemSerum: 1`. The third raw
slot is null. The recipe ID is `RecipeSerum`, not `ItemSerum`.

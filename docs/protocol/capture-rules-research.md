# Capture rules research: Android 2.41.0 ARM64

The inspected multiplayer client does **not** establish the original server's wild generation, stat growth, XP bounds, IV/EV distribution, capture probability, or capture healing policy. Durable capture cannot be enabled from the current level-999/HP-1 wild placeholder without choosing replacement gameplay rules or obtaining another authoritative source. Singleplayer formulas are present but are not evidence that multiplayer uses them.

## Evidence and reproduction

Inspected 2026-11-04. `wsl bash tools/research/ghidra-capture-rules.sh` runs the existing bounded Ghidra fallback with whole-program analysis disabled, verifies the build's binary hash, and selects 23 methods. Output is `.research/ghidra-capture-rules.json`. Native RVAs below exclude Ghidra's `0x100000` image base. Managed signatures and layouts come from the dumper; actual function bodies come from the ARM64 ELF, not dummy assemblies. A separate Capstone 5.0.7 pass using the local `.research/python` dependency directory disassembled those same bounded bodies into `.research/capture-rules-arm64.txt`.

REA 6.8.0 `inspect-artifact --detail summary` supplies provenance only: `.research/rea-capture-6.8.0-artifact.json`, evidence `ev_cd267a868d996009a8eacddeb55941e7966a6db4daefbf531eea774917a37874`, linked inspected-artifact evidence `ev_90a8af00bf09f04e7f28d0f6c50e9e2d50a19317c036566cc4fd2654985424df`. Inventory coverage is root bytes only; no function-semantics claim follows from that inventory.

| Artifact | SHA-256 |
| --- | --- |
| ARM64 `libil2cpp.so` | `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326` |
| `dump.cs` | `8b659049aada5d5037f0c4d108d81e8ab9ff5e8127a11dd78f0a3954aeced27e` |
| `script.json` | `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb` |
| Ghidra capture output | `7d1a9891543a56e496ed24208ab8e51bd6a463de1ca66ed463df00a45411a7a8` |

The existing decompiler can absorb adjacent exception flows. Findings use normal paths, bounded ARM64 instructions, and known field offsets. In particular, `ResetBattleValues` exception-tail pseudocode is not a wild-generation routine.

## Multiplayer consumes server values

`NetworkBattleAPI.BattleStartHandler` (`0x1788674`) deserializes `BattleStartResponse`. The PvWM branch constructs `MPOpponentData` from the supplied opponent dictionary; it does not invoke singleplayer generation. `MPOpponentMortyData.SetFromDict` (`0x158cb1c`) copies supplied values directly to its fields, including level, XP, XP bounds, current HP and all four stats. There are no IV/EV fields or generation methods on this model. Missing numeric values are not calculated from species and level.

An exact durable captured record therefore needs these server values, with the same serialization consumed by the client:

| Dictionary fields | Requirement |
| --- | --- |
| `owned_morty_id`, `morty_id` | Durable new ownership identity and captured species |
| `level`, `xp`, `xp_lower`, `xp_upper` | Authoritative progression snapshot |
| `hp`, `hp_stat`, `attack_stat`, `defence_stat`, `speed_stat` | Authoritative current HP and stats |
| `owned_attacks` | Explicit slots, attack IDs and remaining PP |
| `variant`, `evolution_points` | Authoritative captured variant and evolution state |
| `is_poisoned`, `is_paralysed` | Explicit capture status policy/result |
| `is_locked`, `is_trading_locked`, `fight_pit_id`, `shiny_if_potion`, `custom_morty_name_localisation_id` | Preserve or explicitly initialize applicable ownership metadata |

These are consumer requirements, not proof that every field must be non-null or that the original server stores them in this form. Fresh models initialize attacks but do not synthesize stats. `SetFromDict` supports partial updates, so an absent field retaining a default is not evidence of a valid generation rule.

**Wild identity must change on capture:** `SetFromDict` sets `isWildMorty` by comparing `owned_morty_id` to `00000000-0000-0000-0000-000000000002` (writes model offset `0x58`). Returning that sentinel as the captured owned ID keeps the client model classified as wild. Allocate the durable ID once and use it consistently in the database, reward and optional deck insertion.

`SetAttacksFromDicts` (`0x1581ddc`) creates or updates attack slots when `position` is supplied. An entry without `position` searches an existing attack by `attack_id`; it cannot establish a fresh slot on an empty model. `MPAttackData.SetFromDict` (`0x1583dd4`) reads `attack_id` and `pp`. Consequently a fresh capture's `owned_attacks` must contain explicit `position`, `attack_id`, and `pp` entries. A species learnset alone does not establish its chosen four moves, slot order, or current PP.

The existing [battle completion contract](battle-completion-contract.md) establishes the reward path: successful ITEM act has `success:true`, terminal outcome is CAUGHT, and `player_datas.player.rewards` contains a MORTY reward with the exact `owned_morty` dictionary. Record insertion, item consumption, deck/seen/caught changes, battle completion and publication must describe one committed result. This research does not justify healing or regenerating captured attributes.

## Multiplayer metadata does not supply the missing rules

`MPMortyDefs.SetUp` (`0x176911c`) loads `MortyInfo` and `MortyAttacksInfo` using multiplayer asset scope 2. `MPItemDefs.SetUp` (`0x17692fc`) loads multiplayer `ItemInfo` with the same scope. Existing `docs/protocol/assets.json` identifies their extracted TextAssets in the Android 1011 `mpdata.assetbundle`:

| TextAsset | Content SHA-256 | Relevant contents |
| --- | --- | --- |
| MortyInfo | `96072cc81591577cc31245c6f0ef7518d6ef1b5b5b47e261fd93163caba5ea99` | species metadata, element, division, evolution requirement; no base stats or growth formula |
| MortyAttacksInfo | `4b98487f06f6bdeb75eca0370ae736311741563fdc45327f1a9f591d91a79d7f` | species with level/attack-ID learnset entries |
| ItemInfo | `c7ddb7536ad2a4fa1f48bf3e109e520a706b9056e5d9c484b808ba222f3e5fcc` | item metadata; no capture probability or effect-value field |

`MPMortyDefs.GetAttacksForMorty` (`0x176c514`) returns attack IDs from the matching species' learnset whose levels fall in the inclusive supplied minimum/maximum range. It does not select a wild's loadout or generate PP. `ItemMortyChip` has `effect_type:"Capture"`, `use_battle:true`, `use_self:false`, and defender animation `CaptureGun`; this is not a success chance.

`MPItemDefs.CanItemBeApplyedToMorty` (`0x176a44c`) checks restoration/cure/revive eligibility. Other effect types take its generic successful eligibility path; no capture roll is performed. `MPBattleUI.<UseItemCapture>d__96.MoveNext` (`0x159a718`) chooses CaptureSuccess or CaptureFailed from its supplied `isSuccess` boolean, then displays dialogue/animation. Neither method calculates capture probability.

## Singleplayer formulas are separately recoverable

These functions operate on `MortyData`, with IVs/EVs and singleplayer definition assets. They are intentionally not applied to multiplayer:

- `MortyData.SetLevel` (`0x166f974`) clamps level to 0..100, reads singleplayer species base stats and its IV/EV fields, and computes stats. Native `fsqrt`, `fmul 0.25`, `fcvtms`, integer multiply/division and field stores confirm actual calculation, unlike the multiplayer parser. It does not make level 999 a valid generated opponent.
- `GenerateIVs` (`0x1670384`) samples attack/defence/speed using `Random.Range(min,max+1)` and derives HP IV from their integer mean; MortyDefault takes the maximum branch. `GenerateEVs` (`0x1670468`) and `RandomizeAttacks` (`0x1670574`) are additional singleplayer generation code. Their presence does not establish multiplayer distributions or move selection.
- `MortyDefs.GetXPTarget` (`0x166f914`) calculates a cubic level target in the singleplayer code. No equivalent formula is called by the multiplayer owned-Morty parser.
- `ItemDefs.ApplyCaptureItemToMorty` (`0x166a0d0`) has a separate early guaranteed-success branch, then on its normal random branch calls integer `Random.Range(0,255)` and compares the result with `floor(hpStat * 1020 / (ItemDefs.EffectValue(itemID) * hp))`. ARM64 `0x166a170` calls Random.Range; `0x166a178`/`17c` load singleplayer offsets `0x40`/`0x2c`; `0x166a194` loads 1020; `0x166a1c8` divides; `0x166a1e8` converts rounding downward; `0x166a1f8`/`1fc` compare and return. The multiplayer ItemInfo lacks the EffectValue input, and multiplayer capture animation consumes the server's success flag. Porting this formula would be an unverified replacement rule.

## Selected native body hashes

Hashes cover bytes from each dumper method RVA to the next mapped method boundary, not pseudocode. They allow byte-level comparison of the principal evidence.

| Method | RVA | SHA-256 |
| --- | --- | --- |
| MPOpponentMortyData.SetFromDict | `0x158cb1c` | `78ff37dc1996edf98f03e3a72abdcc32600618cfcc40e4c3c3b990e7af5c2101` |
| MPOpponentMortyData.SetAttacksFromDicts | `0x1581ddc` | `28580610d1b03983db2e8d936f81627859d17d98c24b7b9b14c758338275f487` |
| MPAttackData.SetFromDict | `0x1583dd4` | `e50baaabb25834d264bcb3734242a1ba482a08eef90615fcb8e5af7a6a023390` |
| MPMortyDefs.GetAttacksForMorty | `0x176c514` | `380ce0d45bb47e4c1678d35d35d96462a862fafdbabb720b51e2552d8ad48197` |
| MPItemDefs.CanItemBeApplyedToMorty | `0x176a44c` | `12a6a2dbaba7c5990d1bbc1abcb02c63dd70bde5c5646df702aa66be7305d378` |
| MP capture animation MoveNext | `0x159a718` | `11229eb24f146bd45bdf24438e422ab05ca73d77d8c6673d7b8d288fbabb11ad` |
| SP ApplyCaptureItemToMorty | `0x166a0d0` | `6a0eef123bbd762d16174be7c19aa09abaad8e422454109b11f99667738d6389` |
| SP SetLevel | `0x166f974` | `346585a3bd0c151fe96be52746f09a8627716d970b5d5dc2c81506a349e639ed` |

## Decision boundary

Keep unsupported capture rejected while wild opponents have placeholder attributes. A future implementation needs an authoritative wild snapshot and an evidenced multiplayer capture decision source, or explicit authorization to define replacement rules. Once those exist, copy the authoritative captured state into a durable ownership record and return it through the recovered reward contract. This bounded negative result is not proof that no useful information exists anywhere else in the game or original server; it establishes that the inspected multiplayer consumer and bundled metadata do not supply the required mechanics.

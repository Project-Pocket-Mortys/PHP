# Multiplayer attack AP maxima

Android 2.41.0 ARM64 directly establishes that multiplayer maximum AP comes
from static attack metadata, selected by `attack_id`. It does not come from an
owned attack's response `pp_stat`. Internal PP means the AP shown in the UI.

## Native evidence

The inspected `libil2cpp.so` SHA-256 is
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`.
Addresses below are native RVAs, without Ghidra's `0x100000` image base.
Bounded ARM64 disassembly was checked directly against this ELF, with function
names and object offsets cross-checked against `.research/dumper/script.json`
and `dump.cs`.

| Method | RVA | Relevant normal-path instructions |
|---|---|---|
| `MPOpponentMortyData.GetTotalMaxPP` | `0x158ea14` | At `0x158eb68`, loads each attack's `id` from offset `0x10`; at `0x158eb70`, calls `MPAttackDefs.PP`; at `0x158eb74`, adds the result to the total. |
| `MPAttackData.RestorePPFull` | `0x1584004` | Loads its `id` at `0x158400c`, calls `MPAttackDefs.PP` at `0x1584014`, then stores the result into current `PP` at offset `0x18`. |
| `MPAttackDefs.PP` | `0x1765538` | Calls `GetNode(id)` at `0x1765568`, indexes the resulting JSON node using `pp_stat`, then reads its integer value. |

The last literal is verified through the ELF relocation: GOT address
`0x2f8e758` has `R_AARCH64_RELATIVE` addend `0x30cc138`, which `ScriptString`
identifies as `pp_stat`. `MPAttackDefs.GetNode` is at `0x1765284`.

The existing [use-item contract](use-item-contract.md) and ignored
`.research/ghidra-use-item.json` independently show that
`MPAttackData.SetFromDict` (`0x1583dd4`) reads only `attack_id` and current `pp`.
The managed object contains only `id` and `PP`. Supplying an owned attack's
`pp_stat` in a response therefore does not change the client's maximum AP.
Client item eligibility compares total remaining PP with this static total
maximum, after rejecting fainted Morties.

For optional targeted decompilation, without changing game or database state:

```powershell
wsl -- bash tools/research/ghidra-ap-maxima.sh
```

The wrapper uses the existing binary hash check and exports only the selected
AP methods to ignored `.research/ghidra-ap-maxima.json`. It was syntax checked;
the conclusions above were established by bounded disassembly without running
another Ghidra pass.

## Server data and restoration policy

MP `AttackInfo` has 690 records keyed by `attack_id`, each with `pp_stat`.
The preserved TextAsset SHA-256 in [the asset catalog](assets.json) is
`ee1ce3bd8451e46a7cd29244eba26b275d4f564dc92b92b8c577bc00553d1d51`.
The checked-in `config/attack_max_ap.json` and
`tools/research/export_attack_max_ap.py` provide the corresponding server lookup
and reproducible extraction. This is static client metadata evidence, not an
original multiplayer server capture.

Saved `owned_attacks.pp_stat` is not a reliable independent source of maximum
AP: the current learn-attacks endpoint initializes every attack to 8, while
the existing heal endpoint restores `pp` from that saved field. A full Plutonic
Rock should use the static lookup for every attack, set `pp` to that maximum,
and synchronize saved `pp_stat` to the same value so later healing preserves
the corrected maximum. Return updated `pp` with explicit attack `position`;
the response's `pp_stat` remains compatibility data ignored by this parser.

Unknown attack IDs cannot establish a correct maximum and should fail without
consumption. Full revival changes HP only and preserves attacks. Half-AP and
half-HP variants still require an explicit replacement-server rounding policy
or original multiplayer evidence; these maximum-AP findings do not settle
rounding or minimum restored HP.

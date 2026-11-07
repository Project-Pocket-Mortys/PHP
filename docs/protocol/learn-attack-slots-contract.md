# Learn-attacks empty slots

Android 2.41.0 ARM64 submits exactly four `attack_ids` entries for each Morty,
using JSON null for an empty attack slot. The replacement server previously
cast those nulls to empty strings and inserted invisible `owned_attacks` rows.
The repair skips strict null slots and retains the original array position for
each actual attack. An entry containing only null slots is skipped before
attack deletion, matching the existing empty-entry behavior.

The defect affects later gameplay: a full AP rock reads every stored attack,
and its effect planner rejects an empty attack ID because no static maximum
exists. Thus a native edit with empty slots can prevent restoration of valid
attacks even though the learn response hides the invalid rows.

## Evidence and reproduction

Fresh read-only receipts are in ignored
`.research/learn-attack-audit-20261107`: REA 6.8.0 version/artifact inspection,
two targeted Ghidra exports and logs, and metadata-bounded ARM64 instructions
and method hashes. The checked-in wrapper was also run successfully into
`.research/learn-attack-slots-20261107T055752Z`: 13 selected Ghidra methods,
all without `error`, and 14 bounded methods including the shared HTTP-success
accessor. No game, device or database mutation was used to establish
the native contract. ELF SHA-256 is
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`;
IL2CPP metadata is version 31. Addresses below are native RVAs, excluding
Ghidra's `0x100000` image base. Managed signatures and field offsets come from
the matching `.research/dumper/{dump.cs,script.json}`. Ghidra exception paths
that flow into adjacent functions are excluded from conclusions.

From the repository, reproduce a targeted export into a new ignored directory:

```powershell
wsl -- bash tools/research/ghidra-learn-attack-slots.sh
```

The wrapper checks REA 6.8.0, inspects the pinned ELF, runs Ghidra with
`-noanalysis` and a fixed method selection, and exports independently bounded
ARM64 instructions. It uses the explicit Python executable configured by
`POCKET_WINDOWS_PYTHON`, defaulting to
`C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe` through WSL.
It refuses to overwrite an existing evidence directory.

## Native action and request body

| Method | RVA | Established normal-path behavior |
|---|---|---|
| `MPMortyLabAttacksUI.SetUp` | `0x15bb014` | Copies the Morty's existing attack SortedList into `tempAttacks`. |
| `MPMortyLabAttacksUI.ForgetAttackAtIndex` | `0x15bd6e4` | Calls SortedList `Remove` for the selected position at `0x15bd794`, retaining other keys. |
| `MPMortyLabAttacksUI.AttackCellSelectedHandler` | `0x15bd920` | Passes the selected attack object into `TryLearnAttack`. |
| `MPMortyLabAttacksUI.TryLearnAttack` | `0x15bd84c` | Tests positions 0 through 3 and inserts at the first free index; `Add` is at `0x15bd904`. |
| `MPMortyLabAttacksState.DisplaySaveChangesPopup` | `0x15bad50` | Builds the selected Morty's request from `tempAttacks` and calls `EditMortyAttacks` with the labs flag true. |
| `MPMortyLabAttacksState.SaveChangesButtonClickedHandler` | `0x15bc418` | The save choice submits the same lab request. |
| `MPLearnAttacksState.UIFinishedEventHandler` | `0x15b4378` | Submits the level-up learn flow with the labs flag false. |
| `NetworkPlayerAPI.EditMortyAttacks` | `0x17a2f30` | Allocates four slots at `0x17a3130`; checks each SortedList key at `0x17a3188`; reads a present attack's ID at `0x17a31d4`; writes zero/null for an absent key at `0x17a31e8`–`0x17a31ec`. |

The API assigns `/session/owned_morties/learn-attacks` to the request path.
The anonymous body type has `session_id`, `owned_morties`, and `morty_labs`.
Each owned-Morty dictionary has `owned_morty_id` and `attack_ids`; no AP value
is transmitted. An illustrative native-shaped body is:

```json
{
  "session_id": "SESSION",
  "owned_morties": [{
    "owned_morty_id": "OWNED_MORTY",
    "attack_ids": ["AttackOutburst", null, "AttackSlam", null]
  }],
  "morty_labs": true
}
```

This illustrates slot placement, without asserting species/level eligibility
for the example combination. The actual attacks belong at positions 0 and 2.
Filtering out nulls and then renumbering attacks would change the native slots.

## Response and AP boundary

The callback at `0x17a7ff8` parses `PlayerEditAttacksResponse`, whose fields
are `coupons` (Int32 at `+0x10`) and `owned_morties` (dictionary array at
`+0x18`). On success `NONE=4`, it calls
`SetMortiesFromDicts(...,false,true)`, clearing old attacks before consuming
the response. It applies `coupons` only when `morty_labs` was true.
`MPOpponentMortyData.SetAttacksFromDicts` (`0x1581ddc`) inserts/updates attacks
by explicit integer `position`. `MPAttackData.SetFromDict` (`0x1583dd4`)
reads `attack_id` and current `pp`; it ignores response `pp_stat`.

The client locally initializes a newly learned attack to its static maximum:
the level-up confirm iterator calls `MPAttackDefs.PP` at `0x15b52f8` and
stores the result into current PP at `0x15b52fc`. Lab
`RefreshForgotAttacks` (`0x15bd20c`) likewise obtains that maximum at
`0x15bd3d4` and passes it to the attack constructor at `0x15bd3f4`.
These local values are not submitted; the response replaces the attack state.
They do not establish the original multiplayer server's new-attack AP or
whether unchanged attacks retain or reset their AP.

The [static maxima contract](ap-maxima-contract.md) and checked-in catalogue
establish, for example, `AttackOutburst=12`, `AttackSlam=12`, and
`AttackAntiMatterBomb=1`. The existing server's `pp=pp_stat=8` remains a known
placeholder. This slot repair preserves it. The server also continues its
legacy behavior of ignoring `morty_labs`; this repair adds no fee, coupon
charge, species/level eligibility formula, AP reset/preservation policy,
catalogue validation, or historical-row migration. Those require separate
scope and evidence.

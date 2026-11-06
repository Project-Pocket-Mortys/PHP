# Owned Morty absorption protection contract

Static Android 2.41.0 ARM64 evidence supports protecting consumed donors while
preserving the existing absorption point gain and response. This investigation
does not reconstruct evolution formulas or establish original-server validation.

## Reproduce

```powershell
wsl -- bash tools/research/ghidra-absorb-protection.sh
```

The bounded wrapper uses the default WSL distribution and the existing targeted
Ghidra driver. It first records fresh REA 6.8.0 artifact identity in ignored
`.research/rea-absorb-protection-6.8.0-artifact.json`; that identifies bytes,
not function semantics. The driver verifies `libil2cpp.so` SHA-256
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`.
The pass exported 35 functions without `error` properties to ignored
`.research/ghidra-absorb-protection.json`; independent Capstone disassembly of
each metadata-bounded body is in ignored `.research/absorb-protection-arm64.txt`.
The wrapper passes `bash -n`. Addresses below are native RVAs; Ghidra adds image
base `0x100000`. Managed types come from `.research/dumper/dump.cs` and
`.research/dumper/script.json`. Some Ghidra exception paths extend into adjacent
bodies: conclusions use normal paths checked against bounded instructions.

The wrapper also reproduces the independent Capstone 5.0.7 export from actual
ELF segments using the explicit Windows Python 3.14 interpreter. Another
installation can set `POCKET_WINDOWS_PYTHON` to its executable's WSL path;
Windows Store aliases are never needed. Native export SHA-256 is
`6e72e87c95c9cdd059249b27581175ee724a60014e32083ebfa98f8ceb557b3b`;
bounded ARM64 text SHA-256 is
`48e46424339f23c15d2715a9580ee3819687c6456f632deaaed1fdbbb5d0fe4c`.

## Request and response

`NetworkPlayerAPI.AbsorbMorties(string evolveMortyNetId,
List<string> absorbMortyNetIds, Action<eAbsorbMortysError,
MPOpponentMortyData,bool,List<string>> callback)` is RVA `0x17a55d0`.
It constructs AnonymousType46 and assigns it to request `postData`. The type
has exactly these fields (`dump.cs:4353`):

```json
{"session_id":"<session>","owned_morty_id":"<target instance ID>","absorb_owned_morty_ids":["<donor instance ID>"]}
```

The endpoint is `/session/owned_morties/absorb`. Target and donor values are
owned-instance IDs, not species IDs. The method resolves the target locally
before constructing the request; it passes the donor list directly. There is
no preview token or protected-ID field. Capstone confirms constructor arguments
at `0x17a5728` (session), `0x17a572c` (target), `0x17a5730` (donors), constructor
call at `0x17a5738`, and request `postData` assignment at `0x17a573c`.

The callback at `0x17aa294` specializes
`NetworkDefs.ParseHTTPResponse<eAbsorbMortysError,AbsorbMortiesResponse>`.
The managed response (`dump.cs:31525`) has:

| Field | Type | Offset |
|---|---|---|
| `removed` | `List<string>` | `0x10` |
| `modified` | `Dictionary<string,object>` | `0x18` |
| `created` | `Dictionary<string,object>` | `0x20` |
| `decks` | `Dictionary<string,object>[]` | `0x28` |

On `NONE=8` (comparison at `0x17aa364`), the callback selects `created` when
nonnull, otherwise `modified` (`0x17aa374` onward), wraps that dictionary into
a one-element array, and applies it through `SetMortiesFromDicts` at
`0x17aa3f8`. It removes exactly response `removed`, when nonnull, through
`RemoveMortys` at `0x17aa420`; applies response `decks` through `SetDecks` at
`0x17aa444`; invokes the player-change delegate; then resolves the returned
dictionary's `owned_morty_id` to forward the resulting Morty, created flag,
and removed list to the UI callback. It does not remove the original request
list automatically. This differs from release-multiple.

There is no `active_deck_id` response member or active-deck assignment here.
Return the complete actual deck state with `deck_id` and `owned_morty_ids`;
the shared `SetDecks` clears and rebuilds local memberships. Existing partial
`modified` point updates remain compatible; do not invent a `created` object
without implementing the corresponding evolution behavior.

## Native donor and target eligibility

`CreateAbsorbMortyCells` (`0x15ea900`) searches the player's entire owned list.
Its predicate (`0x15ebb94`) requires donor species ID (`MortyData.id`, offset
`0x10`) to equal target species ID, donor object to differ from the target,
and `MPMortyDefs.CanBeBlended(target.variant, donor.variant)` to succeed.
The donor cell is explicitly enabled only when `isLocked` (`0x6d`) is false:
`ldrb` at `0x15ead40`, comparison at `0x15ead48`, and virtual `SetEnabled`
call at `0x15ead54`. A locked donor can remain visible but cannot be selected.

`CanBeBlended` (`0x176b998`) checks variant compatibility, not an evolution
species relationship:

| Target variant | Allowed donor variants |
|---|---|
| Normal (`0`) | Normal, Shiny, Pulsing |
| Shiny (`1`) | Normal, Shiny |
| Pulsing (`2`) | Normal, Pulsing |

`CreateEvolveMortyCells` (`0x15e9a58`) removes species whose
`EvolutionRequirement` is less than one (predicate `0x15ebdb4`) and
trade-locked targets (`isTradeLocked` offset `0x6e`, predicate `0x15ebddc`).
It removes targets with fewer than two same-species, variant-compatible
objects in that candidate collection (predicates `0x15ebf2c`, `0x15ec048`).
It does not reject an ordinary locked target: that target survives and receives
the points. Do not apply a consumed-donor `is_locked` rejection to the target.

The inspected donor predicate and shared `MPMortyCell.SetUp` (`0x16a44a8`),
`Refresh` (`0x16a473c`), and selection handler (`0x15eb514`) contain no donor
trade-lock or fight-pit filter. `fight_pit_id` is managed field `0x70`.
Rejecting consumed trade-locked or pit-assigned donors is a conservative server
protection policy; it must not be described as an exact recovered native
`CanAbsorb` predicate. No such named method was found in this build.

## Deck and point constraints

Donor eligibility does not exclude active- or inactive-deck membership.
`TryAbsorb` (`0x15eaef0`) compares target evolution points plus selected donor
count with the species evolution requirement. At or above the requirement it
submits immediately. Below the requirement it obtains the active party using
virtual `GetAllPartyMortyDatas` (MPPlayerData override `0x1591418`), subtracts
the selected donors with `Enumerable.Except`, and requires both a nonempty
remainder and at least one nonfainted Morty (predicate `0x15ebebc`). Otherwise
it displays the empty-deck or fainted-deck dialogue and does not submit.

This permits partial point merges, active-deck donors when an adequate party
remains, and donors belonging to saved inactive decks. It does not support a
blanket ban on every saved-deck member. The threshold branch is observed client
behavior, not a reason for a server that only adds points to leave an empty
party. Preserving a living active party independently is conservative policy.
Clean consumed IDs from every affected owner deck and return those decks.

`RefreshAbsorbCellStates` (`0x15eb70c`) disables unselected cells when selected
count equals requirement minus current points. This supports an ordinary UI
selection limit, but does not establish original-server handling of malicious
oversized batches. Preserve the repository's existing gain and evolution
behavior in a protection-focused change.

## Errors and server-side boundary

The error enum (`dump.cs:30318`) is `UNKOWN=0` (client spelling),
`SESSION_ID_INVALID=1`, `OWNED_MORTY_ID_INVALID=2`,
`ABSORB_OWNED_MORTY_IDS_INVALID=3`, `ABSORB_NO_EVOLUTION=4`,
`ABSORB_TOO_MANY=5`, `ABSORB_INVALID_MORTY=6`, `FAILED=7`, `NONE=8`.
The shared HTTP parser consumes `error.code` as an enum-name string from a
non-success response, for example:

```json
{"error":{"code":"ABSORB_INVALID_MORTY"}}
```

The callback changes local Morties and decks only on `NONE`. No dedicated
lock/pit/deck error exists. Exact error assignment and HTTP status remain
replacement-server choices.

The client normally submits selected unique objects from its own owned list.
It supplies no evidence that duplicate IDs should earn duplicate points, that
foreign IDs are valid, or that malformed inputs should be coerced. Validate
list shape and IDs; resolve target and donors under the authenticated owner;
deduplicate accepted donors; protect against ambiguous instance IDs; recheck
protections in the mutation transaction; and scope Morty, attack, target-point,
and deck writes to the resolved owner/rows. The original server's duplicate,
unknown-ID, mixed-batch, transaction, and ownership behavior is not recoverable
from this client. Atomic rejection of a batch containing protected donors is
an explicit server policy that avoids unintended partial destructive actions.

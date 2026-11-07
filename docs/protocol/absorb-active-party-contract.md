# Absorption and the living active party

Android 2.41.0 ARM64 checks the surviving active party only when an absorption
falls below the evolution threshold. A replacement server that only adds
evolution points should preserve a living active party for every absorption.
That unconditional guard is deliberate replacement-server policy, not an exact
copy of the conditional native UI rule. The existing donor, response, and error
contract is in [absorb-protection-contract.md](absorb-protection-contract.md).

## Reproduce and evidence boundary

```powershell
wsl -- bash tools/research/ghidra-absorb-active-party.sh
```

The wrapper uses default WSL, REA 6.8.0 artifact inspection, the existing targeted
Ghidra driver, and the explicit Windows Python 3.14 executable with Capstone
5.0.7. It creates a unique ignored `.research/absorb-active-party-XXXXXX`
directory on every run, preserving previous outputs. It verifies the actual ELF
SHA-256 `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`
before decompilation and disassembly. The REA artifact inspection identifies
bytes; it supplies no function semantics. The Ghidra output supplies pseudocode
for 18 narrowly selected functions with no `error` fields. A separate ARM64
export uses ELF load segments and dumper method boundaries; it also includes
the fainted accessor that the existing Ghidra driver intentionally skips.

The verified run is `.research/absorb-active-party-ks50eO`, with:

| Artifact | SHA-256 |
|---|---|
| `methods.json` | `2155de7318d3b92eb26504abb0c59bb625c6c59541c3205e8640f15d316fb926` |
| `arm64.txt` | `1b70807a854d2e4503d8bc4cb42feb14d2fd6281df4a75ae00f6044db572e521` |

All addresses below are native RVAs; Ghidra adds image base `0x100000`.
Managed field/slot names come from `.research/dumper/dump.cs` and `script.json`.
Claims use normal paths checked against bounded instructions, rather than
decompiler-inferred exception fallthrough. The wrapper passes `bash -n`.

## Exact conditional check

`MPStorageCombineUI.TryAbsorb` (`0x15eaef0`) loads target
`evolutionPoints` (`+0x54`) and selected donor `List.Count` (`+0x18`), calls
`MPMortyDefs.EvolutionRequirement(target.id)` (`0x176b928`), then executes:

```text
0x15eafd8: add w8, w21, w20
0x15eafdc: cmp w8, w0
0x15eafe0: b.ge 0x15eb134
```

The native predicate is signed 32-bit
`target.evolutionPoints + selectedDonors.Count >= requirement`. Equality and
values above the requirement both bypass the party check and reach the submit
delegate. The addition itself is a 32-bit instruction; this is not evidence
that a server should reproduce integer overflow or accept oversized batches.
The count is selected objects, not their accumulated evolution points.

Below the threshold, the method calls virtual slot 6
`GetAllPartyMortyDatas` (`0x15eb030`/`0x15eb034`), copies that collection, then
materializes `Except(selectedDonors)` (`0x15eb07c`/`0x15eb08c`). It shows the
empty-deck dialogue when the result count is zero (`0x15eb09c`). Otherwise,
`FirstOrDefault` with predicate `0x15ebebc` must find a nonfainted Morty
(`0x15eb12c`); failure shows the fainted-deck dialogue. Neither failure submits.
The success delegate receives the target and donor owned-instance IDs, using
selector `0x15ebee4`, rather than a party preview or new species ID.

Only the selected donors are subtracted. An active-party target remains in the
remainder and can satisfy the living check if its current HP is positive.
There is no inferred healing or insertion of an off-party target in this check.

## Which party and which living predicate

`MPPlayerData.GetAllPartyMortyDatas` (`0x1591418`, override slot 6) constructs a
new list by looping from zero to `GetDeckCount(activeDeckIndex)` and calling
virtual slot 5 `GetPartyMortyData(index)`. `activeDeckIndex` is field `+0xd8`;
`decks` is `+0xd0`. `GetDeckCount` (`0x1591fc8`) reads the selected deck's ID
list count. This is the active saved deck, not every saved deck and not every
owned Morty. The base `MPOpponentData.GetAllPartyMortyDatas` (`0x158dc38`)
simply returns `morties`, but the player override is the relevant implementation.

`MPPlayerData.GetPartyMortyData` (`0x1591340`) searches this player's `morties`
(`+0x28`) with `FirstOrDefault`. Its predicate (`0x165d248`) compares candidate
`netId` (`+0x18`) to `decks[activeDeckIndex][index]` by string equality. Thus
party membership resolves active-deck owned-instance IDs against that player's
local owned objects. `IsMortyInParty` (`0x15916f4`) independently tests only
`decks[activeDeckIndex].Contains(morty.netId)`. `GetActiveDeck`
(`0x1591a1c`) and `GetActiveDeckIDs` (`0x1591cb0`) likewise select that index.

An unknown or foreign ID absent from the player's owned list resolves to null;
there is no global lookup granting foreign membership. The native list builder
does not discard null results, and the living predicate throws on null rather
than treating it as alive. Malformed memberships can therefore cause an
exception depending on predicate evaluation order. This is not an original
server validation contract. A replacement server must resolve memberships under
the authenticated owner and never count a dangling or foreign row as a survivor.
Duplicate deck entries also do not establish additional distinct living Morties.

`MPOpponentMortyData.get_isFainted` (`0x158e3d4`, 16 bytes) is exactly:

```text
ldr w8, [x0, #0x30]    // hp
cmp w8, #1
cset w0, lt
ret
```

It returns signed `hp < 1`, including zero and negative HP. The TryAbsorb
predicate (`0x15ebebc`) negates this boolean, so a valid living survivor has
`hp > 0`. Poison, paralysis, maximum HP, species, variant, lock, and fight-pit
assignment do not appear in this living predicate.

## Replacement-server guard

For the current point-only endpoint, evaluate the proposed result inside the
same transaction that validates and consumes the donors. Resolve the owner's
active deck and its members using owned-instance IDs scoped to that owner;
subtract the unique accepted donor rows. Require at least one resolved survivor
with `hp > 0`. Explicitly reject an empty remainder as well as a nonempty but
entirely fainted remainder. An inactive deck, foreign membership, dangling ID,
or off-party target cannot rescue the active party. An active target can count
using its unchanged current HP. Reject the batch before any mutation when the
guard fails; retain the existing point gain and ordinary response shape.

Apply this guard at and above the evolution threshold too. The native threshold
bypass occurs on the evolution-threshold path; its rationale is not established
by this method. This PHP
endpoint currently increments points and removes donors; it does not implement
the separate evolution replacement, healing, or deck-placement behavior. The
observed bypass supplies no evidence for those missing operations and cannot
justify deleting the last living party member in a point-only implementation.

This investigation does not recover original-server ownership enforcement,
HTTP status/error assignment, malformed membership handling, batch atomicity,
evolution formulas, or the party state resulting from full evolution. Those
remain separate contracts or explicit replacement-server policy. Donor cleanup
must still remove consumed IDs from all affected owner decks and return their
actual state as described in the existing absorption protection contract.

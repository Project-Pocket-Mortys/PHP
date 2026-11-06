# Owned Morty donor species and variant eligibility

Android 2.41.0 ARM64 requires a consumed donor to have the target's species ID
and a compatible variant. This contract isolates those checks; evolution
formulas, selection counts, locks, ownership, and party protections remain in
their existing contracts.

## Reproduce and evidence boundary

```powershell
wsl -- bash tools/research/absorb-eligibility-evidence.sh
```

The wrapper uses the default WSL distribution and `tools/research/rea.sh`
(REA 6.8.0). Artifact inspection records ignored
`.research/rea-absorb-eligibility-6.8.0-artifact.json`. It verifies native binary
SHA-256 `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`
and exports six bounded Capstone bodies to ignored
`.research/absorb-eligibility-arm64.txt`, SHA-256
`d00a1bc13d0d3d31718de8bd7eb594c9d780b4e91d514d9a1accb3a73f0b894c`.
The independent disassembly uses the explicit Windows Python executable;
`POCKET_WINDOWS_PYTHON` can override its WSL path. No emulator or database is
required. Artifact inspection establishes byte identity, not semantics.

Managed names, overloads, offsets, enum values, and body boundaries are from
`.research/dumper/dump.cs` and `script.json`. Existing bounded Ghidra exports
`.research/ghidra-absorb-protection.json` and
`.research/ghidra-capture-rules.json` supply readable predicate and dictionary
parser control flow; the new disassembly checks the relevant normal paths.
All addresses here are native RVAs; existing Ghidra exports add image base
`0x100000`.

## Species comparison and directed compatibility

`MPStorageCombineUI.<CreateAbsorbMortyCells>b__35_0`, RVA `0x15ebb94`,
loads donor and target species IDs from `NodeData.id` at offset `0x10`.
The call at `0x15ebbc0` invokes `String.Equals(string)` at `0x24b4e98`.
That overload compares lengths and then character bytes (`0x24b4ea4` through
`0x24b4ec4`); it performs no case folding or trimming. This is the species
string exposed as `morty_id`, not an owned-instance ID or evolution-family ID.
The target object itself is excluded by reference comparison at `0x15ebbcc`.
Related evolution species do not satisfy the equality requirement.

The predicate calls the target variant getter at `0x15ebbdc`, then donor
getter at `0x15ebbec`, and tail-calls `MPMortyDefs.CanBeBlended` at
`0x15ebc04`, preserving that argument order. `CanBeBlended`, RVA `0x176b998`,
implements this matrix:

| Target / donor | Normal | Shiny | Pulsing |
|---|---|---|---|
| Normal | allow | allow | allow |
| Shiny | allow | allow | reject |
| Pulsing | allow | reject | allow |

`MortyVariant` is `Normal=0`, `Shiny=1`, `Pulsing=2` (`dump.cs:12632`).
The Normal branch uses unsigned donor `< 3` at `0x176b9ac`; the Shiny
branch uses unsigned donor `< 2` at `0x176b9c0`; the Pulsing branch tests
all bits other than bit 1 at `0x176b9b4`. Other target values return false
at `0x176b9cc`. The matrix is directed: Normal targets accept Shiny and
Pulsing donors, while those two donor variants cannot mix with each other
under a Shiny or Pulsing target.

## Storage mapping and legacy boundary

Repository `owned_morties` stores `morty_id` and nullable text `variant`
(`pocket_mortys.sql:501`). It has no owned `is_shiny` or `is_pulsing` columns.
The player response serializes SQL NULL variant as the exact string `Normal`
(`session/player-details/index.php:138`); nonnull strings pass through.
Thus a compatibility check should use the stored `variant` text, with SQL
NULL mapped to Normal to match this established response behavior.

Native `MPOpponentMortyData.SetFromDict` (RVA `0x158cb1c`) recognizes the
`variant` dictionary key, converts its value to string, calls
`Enum.Parse(Type,string)` at `0x158cf8c`, and writes the result to `_variant`
offset `0x68` at `0x158cfbc`. The parser overload at `0x264d958` explicitly
sets `ignoreCase=false` at `0x264d9b4` before tail-calling the three-argument
overload. The canonical names and their case therefore matter. This is not
a pair of booleans.

`shiny_if_potion` is a separate native boolean at offset `0x6c`, assigned
at `0x158d028`. The getter at `0x158e478` checks potion activity and
`isWildMorty` offset `0x58`; for ordinary owned Morties it returns `_variant`
at `0x158e4f4`. The conditional flag can affect a Normal wild encounter,
but does not determine an owned donor's variant. See
[the Shiny Potion contract](shiny-potion-contract.md).

For destructive server validation, accept only the exact strings `Normal`,
`Shiny`, and `Pulsing`, plus the SQL NULL default above. Reject unknown,
empty, whitespace-padded, differently cased, numeric, or otherwise malformed
stored variants before consumption. Do not coerce arbitrary values to Normal.
Require nonempty species strings and compare them exactly. Rejecting malformed
legacy storage is a replacement-server policy; the client does not establish
the original server's repair or validation behavior. In particular, strict
canonical-name validation does not claim to reproduce every general
`Enum.Parse` input grammar, including numeric strings.

## Suggested verification

Exercise all nine directed variant pairs with matching species, and verify
that every rejected pair leaves donor rows, attacks, decks, and target points
unchanged. Verify a different species, a related evolution species, and a
case-only species difference all fail. Verify each SQL NULL/canonical variant
combination against the same matrix. Cover malformed target and donor variants
independently, including empty strings, case changes, padding, and numeric
text, as well as missing/empty species storage. Batch rejection and its exact
HTTP/error mapping are explicit server choices; `ABSORB_INVALID_MORTY` is an
available native enum name, not evidence of original-server status codes.

# Shiny Potion startup timestamp compatibility

Android 2.41.0 parses `player-details.play_shiny_potion[0].end_usage_time`
with `DateTime.Parse(string)` and then compares its raw ticks against
`DateTime.UtcNow`. A trailing `Z` makes that parser convert the value to the
device's local timezone. The comparison does not convert it back. Startup must
therefore supply UTC calendar fields without a timezone suffix, for example
`2026-11-05T22:36:24.963916`. The typed activation response retains its normal
UTC `Z` timestamp. Both representations refer to the same database deadline;
this compatibility rule changes neither the duration nor the stored expiry.

## Reproduce the source evidence

Run `bash tools/research/ghidra-shiny-datetime.sh` under WSL. It calls the pinned
REA 6.8.0 wrapper for root artifact identity, checks the actual ARM64 binary and
metadata version, and exports 16 bounded methods with Capstone 5.0.7. Each method
is selected by its actual dumper RVA, its name is asserted, and the exported
record contains its full ABI signature and byte hash. Bounds end at the next
actual dumper method entry and can include padding. The existing
`ghidra-shiny-potion.json` supplies supplementary decompilation for the player
data setter; ARM64 is decisive where Ghidra incorrectly falls through into a
following function after a throw helper.

| Source | SHA-256 |
|---|---|
| Actual `libil2cpp.so` | `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326` |
| Actual `global-metadata.dat`, version 31 | `b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10` |
| Dumper `script.json` | `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb` |
| Generated `shiny-datetime-methods.json` | `8f63da3ab82334bb188051ed0848cc9da99ee01d903845cf8a27e4e610499141` |
| Generated `shiny-datetime-arm64.txt` | `fc42aa808457c85ce79ce0b753483668cae1787c4458624de696c781ddd4ae20` |

All generated files remain under ignored `.research/`, including
`rea-shiny-datetime-6.8.0-artifact.json`. REA's root inspection proves artifact
identity and explicitly leaves format-specific analysis unexplored; it does
not itself prove method behavior. No game binary, metadata, device timezone,
device clock, account quantity, or database deadline is modified by this script.

## Startup ABI and parser branches

`MPPlayerData.SetFromDict` (`0x15901b4`) dispatches the exact
`play_shiny_potion` key through `ConvertExt.ToDictionaryArray` to
`MPShinyPotionData.SetupFromDict` (`0x165f148`). The latter takes
`Dictionary<string, object>[]`, uses the first dictionary's `end_usage_time`
string, and follows this sequence:

| Instruction RVA | Operation |
|---|---|
| `0x165f298`–`0x165f2a0` | Pass string in `x0`, null `MethodInfo*` in `x1`, call `DateTime.Parse` at `0x25fc9e4` |
| `0x165f2a4` | Store parsed DateTime at potion data offset `0x18` |
| `0x165f2ac` | Call `DateTime.get_UtcNow` at `0x25fc7c4` |
| `0x165f2b8` | Call `DateTime.op_LessThan` at `0x25fe1e0` with `(UtcNow, expiry)` |
| `0x165f2c0` | Store result in active bool at offset `0x10` |

The native signature at `0x25fc9e4` is
`System_DateTime_o System_DateTime__Parse(System_String_o* s, const MethodInfo* method)`.
The zero second argument is metadata, **not** a format provider or style flag.
Inside that wrapper, `0x25fca90` obtains `DateTimeFormatInfo.CurrentInfo`,
`0x25fcabc` explicitly sets `w3 = 0` (`DateTimeStyles.None`), and `0x25fcac4`
tailcalls `DateTimeParse.Parse`.

The shipped .NET parser implementation is present in this same native library:

* `ParseISO8601` (`0x260cd68`) recognizes `Z` at `0x260d06c` and sets
  `TimeZoneUsed = 0x100` and `TimeZoneUtc = 0x200` at `0x260d084` and
  `0x260d0ac`. A numeric offset, including `+00:00`, also sets `TimeZoneUsed`.
* `DetermineTimeZoneAdjustments` (`0x260d5f0`) tests `TimeZoneUsed` at
  `0x260d6a4`. With styles zero, it bypasses `RoundtripKind` and
  `AdjustToUniversal` and tailcalls `AdjustTimeZoneToLocal` at `0x260d7e8`.
* `AdjustTimeZoneToLocal` (`0x260db9c`) subtracts the supplied offset at
  `0x260dca0`, obtains the local offset using `TimeZoneInfo.GetUtcOffsetFromUtc`
  at `0x260dd04`, and adds it to the ticks at `0x260dd5c`.
* Without a suffix, `TimeZoneUsed` is absent. With styles zero,
  `0x260d6ac` branches to `0x260d770` and returns success without adjusting the
  calendar ticks or assigning a local/UTC kind. The result is Unspecified.

The enum names and values are independently present in the actual dumper's
`ParseFlags` and `DateTimeStyles` declarations. This conclusion comes from the
game's own parser, not an assumption about a desktop .NET runtime.

`DateTime.op_LessThan` masks both arguments with `0x3fffffffffffffff` at
`0x25fe22c`/`0x25fe230`, then compares them at `0x25fe23c`. This removes Kind
bits; it does not normalize timezones. `op_LessThanOrEqual` used by
`CheckIfShinyPotionDone` has the same tick semantics. `op_Subtraction` at
`0x25fe0a8` likewise masks the Kind bits and subtracts ticks at `0x25fe104`.

Consequently, for an expiry of 22:36 UTC and current time 20:39 UTC, a device
at UTC−05 parses a `Z` timestamp to 17:36 local ticks and marks it expired.
A device at UTC+09 would instead keep it active nine hours too long locally.
Removing the suffix leaves 22:36 calendar ticks on either device, so the
comparison and countdown agree with UTC. This is a compatibility encoding for
this particular consumer; adding `+00:00` does not solve it, and converting the
database deadline to device-local time would be incorrect.

## Startup has an existing HUD consumer

`MPWorldUI.SetUp` calls `ShinyPotionUI.Setup` at `0x164bcd4`. Then
`ShinyPotionUI.Update` (`0x162c9f0`) polls the current player's potion data:

* `0x162cb20` loads `MPPlayerData.shinyPotionData` at offset `0x108`, and
  `0x162cb28` reads its active bool at offset `0x10`.
* `0x162cb54` calls `CheckIfShinyPotionDone`.
* When active and not already displayed, `0x162cc04` calls `TweenIn`.
* `0x162cc58` reads expiry at offset `0x18`, and `0x162cc60` calls
  `TagGamesUtils.GetPrettyStringTimeLeftUntilDateTime` (`0x16bb060`). That
  helper compares against `UtcNow`; its remaining-time helper at `0x16c4df8`
  subtracts `UtcNow` using the raw-tick DateTime subtraction above.

Thus no activation callback or new HUD event is needed after rehydration.
The startup parser setting active false directly explains the missing HUD.
The activation path differs: `SetShinyPotion(bool, DateTime)` at `0x165f33c`
stores the supplied bool and typed date directly, bypassing this string parser.

## Evidence boundaries and runtime verification

This report establishes the shipped startup parser, comparison, and HUD paths
statically. Native A/B testing should keep the same persisted deadline and
inventory, reload player details once with `Z` and once without, and inspect
the outgoing JSON plus the HUD countdown. No second activation is needed.
See [android-shiny-potion.md](android-shiny-potion.md) for the separately
recorded native runtime observations and [shiny-potion-contract.md](shiny-potion-contract.md)
for the complete request/response contract.

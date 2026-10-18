# Fast-shoes dialogue blocker

The world-2 runtime attempt encountered a client dialogue blocker. Ignored
`.research/emulator/world2-logcat.txt` records `NullReferenceException` at
`DialogueUI.ContinuePressedHandler` at 2026-10-17 19:58:27.676 and 19:58:43.630
(device log timestamps). This observation does not identify the null reference
or establish that the destination fixture caused the exception.

[Bounded native evidence](fast-shoes-dialogue-evidence.json) records exact
artifact hashes and method RVAs. It uses the recovered Android 2.41.0 ARM64
binary and managed field declarations to interpret the native pseudocode; the
runtime diagnostic client is ARM32, so this is corresponding-build evidence,
not a direct fault-address analysis of its executing binary.

`PlayerDefs.CanShowFastShoesFtue` reads the inverse of
`PlayerSaveData.hasPlayerCompletedFastShoesFtue` (ARM64 field offset `0x13b`).
The declared persistent key is `HasPlayerCompletedFastShoesFtueKey`.
`MPWorldFtueController.AttemptToShowOnWorldEnteredFTUEs` can display
`FAST_SHOES_BRAZE`, whose recovered English label is “You can now run by holding
down the A button!” After normal dismissal,
`FastShoesReturningPlayerDialogueFinished` enables player input and registers
handlers for running and a 100-step counter. `FastShoesStepCounterReached` can
display the dialogue again. `FastShoesReturningPlayerRan` sets the completion
field, calls `SaveDataController.Save` with mask `0x10`, and removes those
handlers. This completion state belongs to client save data; it is not evidence
for a missing join-room response field.

The recovered `ContinuePressedHandler` has null checks for AudioController,
`_currentBox`, `_data` and `_data.entries` before continuing or finishing a box.
The captured stack cannot distinguish them. `DisplayAction` constructs and
stores dialogue data; its inspection alone does not establish which path failed.
No client or server patch is justified by these findings.

## Reproduce the bounded inspection

From the repository root in the default WSL distribution:

```bash
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-fastshoes.json" \
  'DialogueUI.*ContinuePressedHandler|.*CanShowFastShoesFtue'
bash tools/research/ghidra-targeted.sh "$PWD/.research/ghidra-fastshoes-detail.json" \
  'DialogueUI.*(DisplayAction|FinishCurrentBox|ContinueCurrentDialogue)|MPWorldFtueController.*(AttemptToShowOnWorldEnteredFTUEs|FastShoesReturningPlayerDialogueFinished|FastShoesReturningPlayerRan|FastShoesStepCounterReached)'
```

These are the effective method selections used for the investigation. The
existing helper verifies the build-specific ARM64 binary hash, imports a
disposable Ghidra project with `-noanalysis`, and decompiles the bounded methods;
it writes ignored research outputs and retains its disposable project. Its
pseudocode has inferred parameter types and build-specific null-throw/tail-call
annotations, so it must not be treated as original managed source.

Field and observation checks in PowerShell:

```powershell
rg -n -A 4 -B 2 'hasPlayerCompletedFastShoesFtue|HasPlayerCompletedFastShoesFtueKey' .research/dumper/dump.cs
rg -n -A 6 'NullReferenceException' .research/emulator/world2-logcat.txt
Get-FileHash .research/ghidra-fastshoes.json, .research/ghidra-fastshoes-detail.json, .research/emulator/world2-logcat.txt -Algorithm SHA256
```

This inspection changed no database records, runtime settings or client binaries.
The runtime attempt and fixture restoration are documented separately.

A subsequent controlled restart/retry completed world-2 entry without a binary
or server patch; see [runtime results](distinct-world-verification.md). The
exception is intermittent in these observations. Successful dismissal after
waiting between taps does not isolate the cause or establish a timing fix.

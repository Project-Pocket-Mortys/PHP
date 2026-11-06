# Android absorption protection acceptance

The guarded fixture uses the existing isolated research backend and Android
2.41.0 on `PocketMortys_API30`, ADB port 5038, `emulator-5556`, account
`PMResearch01`. The peer account `PMResearch02` is compared throughout; its
emulator is not touched. Raw account IDs, HTTP records and screenshots remain
inside ignored `.research`.

## Synthetic fixture boundary

`tools/research/absorb_protection_fixture.py` creates three fresh storage Morties:
a target, an ordinary locked donor and an unlocked donor. All use
`MortyScruffy`, with zero initial evolution points. Their complete stored stats
and attacks are copied from the original `MortyDefault`. These are explicitly
synthetic copied stats, not a recovered Scruffy stat-generation algorithm.
Original Morties, attacks, progression, stock and party membership are preserved.
Preparation refuses an existing original Scruffy, so no original can be selected
as a compatible donor. No deck change is made during preparation.

The helper extracts the actual MP `MortyInfo` table and pins its SHA-256 to
`96072cc81591577cc31245c6f0ef7518d6ef1b5b5b47e261fd93163caba5ea99`.
The source Android `mpdata.assetbundle` SHA-256 is
`f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413`;
the TextAsset path ID is `-5656435499516812579`. Scruffy has
`evolution_req=3`; original Morty has `evolution_req=null`. One donor produces
one point, below the full evolution threshold. This exercise does not validate
full species evolution, generated stats or learned attacks.

## Reproduction

Use the explicit Python executable below; local Python aliases can open Store.
Finish database integration tests before preparing the account fixture: existing
unindexed row-lock scans can conflict with concurrent fixture tests.

```powershell
$python = 'C:\Users\iantr\AppData\Local\Python\pythoncore-3.14-64\python.exe'
$capture = '.research/emulator/absorb-protection-<fresh-label>'
& $python -X utf8 tools/research/absorb_protection_fixture.py prepare --output $capture
```

If preparation committed but recording its snapshot was interrupted,
`finish-prepare` is read-only: it accepts exactly the manifest's three complete
clones and unchanged original accounts before writing `prepared.json`.

Restart the existing app and enter multiplayer to reload player details. Walk
west of the central portal to Morty Daycare, face an entrance arrow and press A.
Choose Evolve Mortys, select the synthetic Scruffy target and capture the
donor list. Verify the ordinary locked donor cannot be selected; select only the
unlocked synthetic donor and confirm the partial absorption using Android taps.
Do not unlock the protected donor or select any original Morty.

```powershell
& $python -X utf8 tools/research/absorb_protection_fixture.py record --output $capture --label native-result
& $python -X utf8 tools/research/absorb_protection_fixture.py cleanup --output $capture --absorbed
```

If no absorption occurred, omit `--absorbed`; cleanup then requires the exact
prepared snapshot. Cleanup accepts only the reconstructed point increment,
fresh unlocked donor/attack deletion and existing deck serialization. It refuses
any unexplained mutation. Both accounts are rechecked under transaction locks;
only surviving fresh clone rows and their attacks are deleted. Any changed raw
deck formatting is restored only after the entire expected state matches.
Original Morties and attacks are never rewritten to conceal an unexpected change.

Restart the app again and return to multiplayer WORLD, then verify independently:

```powershell
& $python -X utf8 tools/research/absorb_protection_fixture.py verify --output $capture --label reloaded
& $python -X utf8 .research/battle_item_account_guard.py compare
```

## Result — 2026-11-05

Android displayed the padlocked donor as a dimmed cell. Tapping it left the
blender empty and Blend disabled. Both account snapshots remained exactly equal
to the prepared snapshots, and no absorption HTTP request was captured.
Selecting the unlocked donor highlighted only that donor and enabled Blend.

One native slashless POST to `/session/owned_morties/absorb` returned HTTP 200:

```json
{"session_id":"<current session>","owned_morty_id":"<fresh target>","absorb_owned_morty_ids":["<fresh unlocked donor>"]}
```

The persisted target changed from zero to one evolution point. Android returned
to the target list with its EVO bar filled to one of three points, the unlocked
donor absent and the locked donor still visible. Only the fresh unlocked donor
and its attacks were removed; target stats, target attacks and locked donor rows
were unchanged. Every original Morty, original attack, item, party membership
and progression value matched baseline for both accounts. This confirms partial
absorption; full evolution was deliberately not exercised.

Cleanup matched the entire reconstructed two-account state under transaction
locks, removed the two surviving fresh clones and verified exact original
account rows. Raw evidence is under
`.research/emulator/absorb-protection-20261105/`: `locked-disabled.png`,
`locked-disabled-accounts.json`, `locked-disabled-http.json`,
`unlocked-selected.png`, `native-result.png`, `native-result-http.json`,
`native-result-accounts.json` and `cleanup.json`.

After a fresh app restart, Android reentered multiplayer WORLD. The helper's
`verify` action and the independent preexisting two-account baseline comparison
both passed. `final-world-stable.png` and `reloaded-verified.json` retain that evidence.
The peer emulator remained untouched.

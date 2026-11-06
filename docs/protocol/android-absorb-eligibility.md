# Android absorption eligibility acceptance

On 2026-11-05, Android 2.41.0 accepted a same-species Normal donor after the
[species and variant eligibility repair](absorb-eligibility-implementation.md).
This exercise verifies the compatible Normal-to-Normal partial path and the
existing locked-donor UI protection. The directional variant matrix and
incompatible-batch rejection are covered by the separate native/static evidence
and HTTP integration tests; they were not exercised through this Android UI.

The unchanged `tools/research/absorb_protection_fixture.py` ran against the
isolated research backend after all 29 eligibility/protection integration cases
completed. It used `PocketMortys_API30`, ADB port 5038, `emulator-5556`, and
`PMResearch01`; the `PMResearch02` emulator remained untouched. Reproduction and
the pinned source asset hashes are documented in
[the original protection acceptance](android-absorb-protection.md).

Three fresh Normal `MortyScruffy` storage clones were created: target, ordinary
locked donor, and unlocked donor. Complete stats and attacks were copied from
the original `MortyDefault`; these are synthetic copied stats, not recovered
Scruffy generation. The original accounts had no Scruffy, so no original Morty
could enter the compatible donor list. Scruffy requires three evolution points;
one donor deliberately exercises only partial absorption.

After restarting the primary app and entering multiplayer, native taps opened
Morty Daycare and Evolve Mortys. Tapping the dimmed padlocked donor left the
blender empty and Blend disabled. Both accounts exactly matched the prepared
snapshot, and no absorption request was captured. Selecting only the unlocked
donor enabled Blend. A native tap produced exactly one slashless POST to
`/session/owned_morties/absorb`, returning HTTP 200 with the fresh target and
only the fresh unlocked donor ID in the request.

Android returned to the target list with its EVO bar at one of three points,
the unlocked donor absent and the locked donor still visible. Cleanup accepted
the exact reconstructed two-account state: target evolution points changed
from zero to one, only the unlocked clone and its attacks were consumed, and
the target stats/attacks and locked clone were unchanged. It removed only the
two surviving fresh clones under row locks and restored any raw deck JSON
formatting. Both original account snapshots matched baseline exactly.

After a fresh primary app restart, multiplayer WORLD loaded with normal
controls. The helper's `verify` action and independent
`.research/battle_item_account_guard.py compare` both passed. The complete
`friend_lifecycle_fixture.py verify` guard also passed before preparation and
after cleanup/reload, proving both accounts' original save fields (including
NULL potion expiry and `worldID`) and every original friend row unchanged.
Its documented connection fields, including session IDs and membership
generation, are excluded and were never restored or decremented.
Its evidence labels are `absorb-eligibility-before` and
`absorb-eligibility-after-world-ready` under
`.research/emulator/friend-lifecycle-20261105/`.

Private raw evidence remains in ignored
`.research/emulator/absorb-eligibility-20261105/`: `fixture.json`, `prepared.json`,
`locked-disabled.png`, `locked-disabled-accounts.json`,
`locked-disabled-http.json`, `unlocked-selected.png`, `native-result.png`,
`native-result-http.json`, `native-result-accounts.json`, and `cleanup.json`.
`final-world-ready.png` and `world-ready-verified.json` retain final reload
evidence.
No full evolution, variant changes, reset, reinstall, or original Morty mutation
was performed.

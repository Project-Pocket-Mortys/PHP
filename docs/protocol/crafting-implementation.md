# Multiplayer crafting implementation

`POST /session/recipe/use` accepts `session_id` and `recipe_id` and crafts one
output from the pinned multiplayer recipe catalog. All 22 catalog entries are
supported. Ingredients and results are resolved on the server; callers cannot
choose prices, quantities, ingredients or rewards.

This feature branch starts at current upstream `main`, commit `9ff1a11`, rather
than the earlier stacked restoration branches. It does not depend on their
item-use, lock or release helpers. Those features remain separate work awaiting
integration into main. Existing completed gameplay features and attribution are
preserved. The branch also upgrades the research toolchain to
[REA 6.8.0](rea-6.8-upgrade.md).

## Inventory changes and response

An accepted request consumes one unit per occupied recipe slot and grants one
output. Repeated slots are aggregated. The account and touched inventory rows
are locked while validating and changing quantities. A successful transaction
persists all debits and the output together. Exhausted ingredient rows remain
at quantity zero so the response can explicitly remove them from the client.

Both `owned_items` and `result.quantity` carry **absolute final quantities**.
`result.type` is numeric `3` (item reward); `amount` and `amount_received` are
both one. Returning an increment as `result.quantity` would replace an existing
stack incorrectly. For example, crafting Serum while owning one returns Serum
quantity two, plus Battery/Fleeb remaining counts. See the recovered
[native contract](crafting-contract.md) and [data provenance](crafting-data.md).

The output cap is ten, following the literal multiplayer crafting UI check.
Missing ingredients, output overflow and malformed/ambiguous inventory fail
before any mutation. Counts outside the client's nonnegative signed-16-bit
inventory representation are rejected. The schema has no unique item/account
constraint; duplicate touched rows fail instead of guessing which to charge.
Only the authenticated owner's inventory changes. No currency, XP, Morty,
deck, purchase or challenge reward is introduced.

## Errors, policies and remaining limits

| Condition | HTTP status | `error.code` |
|---|---|---|
| Invalid/malformed input | 400 | `FAILED` |
| Invalid session | 401 | `FAILED` |
| Unknown recipe ID | 400 | `RECIPE_ID_INVALID` |
| Missing/insufficient ingredients | 409 | `RECIPE_ITEM_NOT_OWNED` |
| Output above ten | 409 | `RECIPE_ITEM_RESULT_LIMIT` |
| Non-WORLD state or ambiguous/invalid inventory | 409 | `FAILED` |
| Internal/catalog error | 500 | `FAILED` |

Enum names and UI behavior are client evidence; these exact HTTP statuses,
WORLD-state restriction and transaction policy are replacement-server choices.
One output per accepted request is supported by the one-result catalog and
single-request client flow, not a surviving original-server capture.

No recipe ownership/unlock data or event windows were recovered. All catalog
IDs, including four promotional recipes, are accepted when ingredients and
capacity permit; no invented event/discovery gate is enforced. Caller-supplied
unknown IDs never define new recipes. The input has no request identity:
repeated effective requests can craft again if stock remains. Concurrent
requests on the new route cannot overspend the last ingredients; older
inventory writers do not all share this account-lock protocol, so global
cross-route concurrency guarantees remain open.

No schema migration is required. Deploy `config/crafting_recipes.json` together
with the handler and slashless Apache rewrite. Python, UnityPy, binary dumps
and REA are research dependencies, not runtime server dependencies.

## Reproduction and tests

```powershell
py tools/research/export_crafting_data.py --check
py -3 -m unittest discover -s tests/protocol -p test_crafting.py -v
py tools/research/validate.py
```

The initial core test failed against the missing route. All 12 final integration
tests pass: two- and three-ingredient recipes; insertion and increment of an
existing output; zero depletion; owner and currency preservation; errors without
partial changes; caps; duplicate inventory; out-of-range counts; concurrent
last-stock requests; repeated effective requests; and the exact slashless client
POST without redirect. The handler passes PHP 8.3 syntax checks. Fixtures use
disposable UUID accounts and preserve the Android accounts.

The exporter checks pinned multiplayer TextAsset hashes and regenerates the
22-entry runtime catalog exactly. Main's preserved older asset inventory is
retained as historical evidence, with changed current bundle provenance explicit.

For the primary isolated Android account, prepare one Battery and Fleeb while
preserving its current Serum count:

```powershell
py tools/research/crafting_fixture.py prepare
# Reload Android and craft RecipeSerum at the multiplayer crafting table.
py tools/research/crafting_fixture.py restore
# Reload to discard restored fixture quantities from the local cache.
```

The helper requires the isolated backend, `PMResearch01` in WORLD, absent
ingredient stacks and Serum below its cap. Recovery state stays ignored under
`.research/emulator`. Restore verifies expected counts before removing fixture
ingredients and restoring the prior output quantity. It does not overwrite
unexpected inventory changes.


## Android acceptance

Android 2.41.0 entered world 1, walked to the crafting table near Morty Labs,
stood adjacent and facing it, and held A briefly to open the recipe list. The
Quick Craft button sent the exact slashless `RecipeSerum` request. The server
consumed Battery 1 -> 0 and Fleeb 1 -> 0 and changed the existing Serum stack
1 -> 2. The reward screen showed Serum x1, the returned recipe screen disabled
crafting for missing parts, and Your Items showed Serum 2/10. Client and server
therefore agreed on both the grant and final absolute quantity. Currency, XP,
level and active deck were unchanged. See [the sanitized capture](crafting-capture.json).

The temporary ingredient rows were removed and original Serum count restored
afterward, then the client restarted. Raw screenshots/logs and fixture account
identifiers remain ignored. Other recipes have catalog/native and automated
coverage; the live Android action recorded here is Serum only.

The long-idle primary emulator initially remained on splash while its DNS
resolver timed out. A primary-only cold start restored DNS and reached the menu
within about 50 seconds. Userdata, the research app UID, its existing application
firewall rules and ADB reverse were preserved; the peer emulator was untouched.
No app reinstall, save reset or additional client patch was used for crafting.

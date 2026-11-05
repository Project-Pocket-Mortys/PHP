# Android WORLD status cure acceptance

Android 2.41.0 on the isolated `PocketMortys_API30` AVD exercised both cures
through the multiplayer WORLD menu: Your Items, select cure, Use, select the
primary active Morty, Use Item. Both requests came from the Android client;
the fixture helper never sends an item-use request.

The target was the existing level-5 `MortyDefault`, with full HP 20/20 and
Outburst AP 12/12. A guarded database fixture supplied both ailments and one
temporary copy of each item. This proves consuming synthetic persisted ailments,
not acquiring ailments through battle. Battle ailment production remains outside
this acceptance. These are replacement-server results, not original-server proof.

| Native request (UTC, 2026-11-04) | Before poison/paralysis | After poison/paralysis | Stock | HTTP |
|---|---|---|---|---|
| 16:35:50 `ItemPoisonCure` | true / true | false / true | 1 → 0 | 200 |
| 16:36:40 `ItemParalysisCure` | false / true | false / false | 1 → 0 | 200 |

Both native paths were `/session/use-item` without a trailing slash. Responses
returned `is_success: true`, `effect_value: 0`, both boolean status fields and
the consumed inventory entry at quantity zero. HP, AP, maxima, Morty stats,
decks, player stats and unrelated inventory remained unchanged.

After the initial app reload, the Poison Cure target screen displayed both the
green poison droplet and purple paralysis symbol. After Poison Cure, its inventory
row disappeared and the next target screen retained only the paralysis symbol.
The Paralyze Cure dialogue read “You used the Paralyze Cure on Morty.” A screenshot
and screen recording retain that dialogue. The earlier Poison Cure dialogue was
not retained; its item removal, intermediate target display, HTTP response and
database snapshot were retained. The UI label is **Paralyze Cure**, while the
native inventory/request identifier is **`ItemParalysisCure`**.

A second app reload fetched native `/session/player-details` at 16:38:04 UTC
with both flags false. Your Mortys then showed neither ailment icon, HP 20/20,
and Stats showed Outburst AP 12/12. The initial native player-details capture at
16:34:43 had returned both flags true. The guarded restore subsequently matched
the complete original scoped account snapshot, removed both temporary inventory
rows and restored the original flags. The primary client was reloaded afterward;
its 16:40:39 native player-details response contained the original two inventory
entries only and both ailment flags false. Both research accounts' user, Morty,
attack, inventory and deck snapshots matched the pre-acceptance baseline exactly.

## Reproduction and cleanup

```powershell
py tools/research/status_cure_fixture.py prepare --output .research/emulator/<fresh-directory>
# Reload the primary Android app, enter Multiplayer, use both cures via Your Items.
py tools/research/status_cure_fixture.py record --label after-poison --output .research/emulator/<fresh-directory>
py tools/research/status_cure_fixture.py record --label after-paralysis --output .research/emulator/<fresh-directory>
# Reload and inspect persisted state, then restore the original account rows.
py tools/research/status_cure_fixture.py restore --poison-used --paralysis-used --output .research/emulator/<fresh-directory>
# Reload Android again to discard temporary fixture inventory.
```

The helper only accepts the isolated `db:http://localhost:8087` backend and the
primary research account in WORLD, checks for active battles, checks the active
target is living and at full HP, and preserves the original scoped account rows
before mutation. Temporary stock must remain within the native maximum of 10.
It locks and compares user, Morty, attack, inventory and deck rows in the same
transaction as each mutation. Restore requires the exact expected status and
quantity changes indicated by the two `--*-used` switches, then restores original
statuses and quantities or removes newly inserted item rows. Unexpected changes
abort cleanup instead of overwriting concurrent work. Omit the corresponding
switch when a UI attempt did not consume that cure.

Raw screenshots, the video, sanitized HTTP records, full row snapshots, cleanup
evidence, source revision and SHA-256 hashes are ignored under
`.research/emulator/status-cures/`. No account identifiers or credentials are
published here. The source baseline was `f8e1987` plus the status-cure working tree;
exact relevant file hashes accompany the ignored capture. The protocol and native
consumer evidence are described in [the status cure contract](status-cure-contract.md).

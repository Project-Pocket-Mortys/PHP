# Battle item data and transaction audit

Read-only audit of existing handlers and current Android MP metadata, 2026-11-05.
No upstream requests, purchases, runtime changes, or database changes were used.
This records the initial twelve-item audit. The subsequent [Pure Curum contract](full-recover-contract.md)
and [implementation](full-recover-implementation.md) enable ItemFullRecover as a thirteenth item;
the other six additional battle-enabled items below remain unsupported.
Wire request fields and animation shape require separate native evidence.

## Metadata boundary

Read `ItemInfo` with `tools/research/export_item_effects.py::load_text` using
UnityPy and the explicit Python 3.14 executable with `-B`. Current
`mpdata.assetbundle` SHA-256:
`f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413`;
`ItemInfo` SHA-256:
`ab713ae7e06f8b492628d10b73580d4016756d57072d04b5be43f271e7305a39`.
See `use-item-data.md` for the preserved catalog distinction and effect evidence.

All twelve currently supported world items explicitly permit MP battle use:

| IDs | Existing supported effect |
|---|---|
| `ItemSerum`, `ItemGreatSerum`, `ItemSensationalSerum`, `ItemPureSerum` | HP restoration |
| `ItemEasterEgg`, `ItemPumpkin`, `ItemSpicyBBQPizza`, `ItemBreakfastMedley` | HP restoration |
| `ItemPureHalzinger` | Full revival |
| `ItemPurePlutonicRock` | Full AP restoration |
| `ItemPoisonCure`, `ItemParalysisCure` | Corresponding status cure |

The complete metadata `use_battle=true` set additionally contains
`ItemHalzinger`, `ItemPlutonicRock`, `ItemFullRecover`, `ItemMortyChip`,
`ItemMrMeeseek`, `ItemToxicBundle`, and `ItemVapeIncineratingRocket` (19 total).
Metadata permission does not establish their arithmetic, target semantics, or
wire payloads. Keep these outside the initial implemented allowlist.
`ItemMegaSeedAttack`, `ItemMegaSeedDefence`, `ItemMegaSeedSpeed`, and
`ItemMegaSeedLevelUp` explicitly forbid battle use. No supported world item
conflicts with battle permission.

## Safe reuse

Reuse `lib/healing_items.php::morty_item_effect_plan` for the established twelve
effects after stricter battle validation. Preserve the world endpoint's existing
contract. Keep transaction ownership in `session/battle/move/index.php` and
follow its user, battle, origin, party, and spawn checks. Party membership comes
from the immutable private `battle:start` snapshot, never today's deck.
Retain the global Morty-ID ambiguity guard because attacks have no owner column.
Lock all initial party rows with `battle_lock_party`, and require the active
owned HP to equal `battles.player_hp` before applying anything.

Reject items while the active Morty is dazed and replacement is pending, and
reject nonpositive enemy HP. A normal effective item consumes the player action;
the existing placeholder AI damages the current active Morty even when the item
targets a bench Morty. Update the target row, in-memory party, active row/cache
when applicable, attacks, and inventory before building the turn. A revived
bench member must count as living if that AI attack dazes the active Morty.
Publish the private turn event and commit once; any validation or event failure
rolls back every mutation.

Lock exactly one owned inventory row, require positive integral stock, plan
before decrement, and consume one only for an effective plan. Full HP, alive
revive target, dazed heal/AP/cure target, absent corresponding status, and full AP
must be no-ops with no AI action, event, or consumption. A retry that is still
effective cannot be distinguished from a fresh action without a request nonce;
do not claim general replay protection.

## Attack snapshots and validation

`item_updated_morty` performs a fresh unlocked attack SELECT. The legacy
`session/owned_morties/learn-attacks` route does not take the user's lock and
deletes/reinserts attacks in autocommit operations. Therefore the user lock alone
does not guarantee a consistent DTO. When returning AP changes, lock the target's
complete attack rows with `FOR UPDATE` and build the DTO from those same rows
after applying the effect plan. Other effects can return partial HP/status
snapshots without reading attacks. Do not re-query attacks during serialization.

For full AP, the implemented validation accepts one to four rows as a bounded
replacement-data policy, with unique attack identities and unique nonnegative
Int32 positions. A native 0..3 position bound was not established; existing
sparse positions such as 2 and 7 remain valid and unchanged. Validate known
AttackInfo identities, integral nonnegative
current PP, and current PP no greater than the catalog maximum. An empty attack
set has no effective AP deficit. Do not silently rewrite positions. Use
`config/attack_max_ap.json`, never stored `pp_stat`, as the maximum. Existing
planner already repairs stale `pp_stat` while filling a real deficit; stale
`pp_stat` alone must not consume an item. Existing planner does not validate
attack identity or position uniqueness.

Validate stored HP with `battle_valid_hp`, including signed INT bounds and
`0 <= hp <= hp_stat`, `hp_stat > 0`; the shared world's nonnegative-integer
helper alone allows values too large for the battle cache.

## Meaningful regressions

- Active heal changes owned HP and battle cache before AI damage; bench heal
  changes only the target while AI damages the active Morty.
- Reviving the only bench survivor changes the next daze outcome to
  `FORCE_SWITCH`; current deck changes cannot add a target to the initial party.
- Status cures change only the corresponding flag, preserve the other flag,
  and do not work on dazed targets or missing status.
- Full AP uses unequal catalog maxima and repairs stale `pp_stat`; duplicate
  attacks/positions, unknown identities, negative PP, and over-max PP roll back.
- Duplicate inventory rows, ambiguous global Morty IDs, foreign/nonparty targets,
  invalid HP/cache, pending replacement, and unsupported items cannot mutate.
- No-op retries publish no turn and consume nothing; effective retries retain
  the explicit limitation above. A forced event-write failure rolls back HP,
  status, AP, stock, battle cache, and terminal state together.
- Preserve existing attack, switch, run, and world item route regressions.

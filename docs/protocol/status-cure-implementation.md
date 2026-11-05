# World poison and paralysis cures

`/session/use-item` now supports `ItemPoisonCure` and `ItemParalysisCure` for
an owned, living Morty with the corresponding ailment. Full HP is allowed.
The [multiplayer native contract](status-cure-contract.md) establishes these
eligibility rules, explicit false status updates and the fixed cure dialogue.

One successful request consumes one item and clears only its matching flag in
the same transaction. It preserves HP, AP, the other ailment, XP, stats, locks,
deck membership and unrelated inventory. The response uses the existing
unwrapped item DTO, includes both boolean status fields and the exact remaining
quantity, including zero. `effect_value:0` is a compatible replacement-server
convention: the native Cure UI does not use a numerical magnitude.

No ailment, a wrong cure, fainting, insufficient stock, invalid ownership or
an active battle rejects without mutation. A repeated cure after success is a
no-op and does not consume another item. Concurrent requests serialize on the
user/Morty/inventory locks. All item types now reject an owned ID shared with
another account before reading its attack rows; the schema does not enforce
global logical-ID uniqueness, and attacks have no player column.

## Persistence and upgrade order

Apply `tools/research/server/migrations/003-morty-ailments.sql` before loading
the updated handlers. It adds `is_poisoned` and `is_paralysed` as non-null
booleans with false defaults. It is additive and repeatable; it retains existing
Morty values and does not reset true flags on rerun. False for legacy records
follows the previously absent state and fresh client defaults, not a claim that
the original service had no afflicted Morties.

The migration was first tested against a disposable copy of the original SQL
schema, including existing record preservation, both defaults, repeated use,
retention of true flags and new inserts. It was then applied to the isolated
MariaDB 10.11 research database. The original SQL dump remains intact.

```powershell
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/migrate.php
py -3 -m unittest discover -s tests/protocol -p test_status_cure_items.py -v
py -3 -m unittest discover -s tests/protocol -p test_morty_ailment_snapshots.py -v
py -3.14 tools/research/audit_capture_data.py --check
```

Fresh player details, join/room snapshots, SSE user DTOs and battle-start player
snapshots now include the persisted booleans. Existing healing, AP/revival and
learn-attack responses preserve them. Those actions do not acquire an invented
cure-all side effect. Battles still use placeholder damage and do not implement
poison/paralysis application or damage ticks; the [battle item route](battle-item-implementation.md)
now supports the established cures. General items and `ItemFullRecover` are not enabled here.

## Evidence and validation

Both item IDs previously returned HTTP 400 in UUID-only baseline probes.
The new regression suites cover targeted flags at damaged/full HP, typed DTOs,
stock exhaustion, no-op retries, concurrent last-item use, invalid/ambiguous
ownership, battle guards, migration safety and preservation through fresh
HTTP/SSE/battle snapshots. Existing account fixtures are never globally reseeded.

Native/asset work also narrowed the capture blocker: the MP bundle supplies
564 species and learnsets but no base stats, XP generation or capture chance.
Single-player formulas exist and remain explicitly separate. See the
[data audit](capture-data-audit.md) and [bounded native research](capture-rules-research.md).
Capture remains unsupported until authoritative values or an explicit
replacement gameplay policy are supplied; no fake owned Morty is generated.

This feature starts from current main `9ff1a11` and explicitly incorporates the
pending integration prerequisite `f8e1987` (PR #28). The original completed
README features and attribution are retained. Only the local test database is
migrated; public deployment is outside this work.

## Acceptance on 2026-11-04

The targeted regression run passed all 66 tests in 392.808 seconds: existing
healing/revive/AP items, the migration/cures, authoritative ailment snapshots,
battle lifecycle, two-account SSE privacy and join ownership. PHP 8.3 lint
passed for all 24 changed/new PHP files including the integration prerequisite.
JSON/source-hash/native constructor checks, bounded script syntax and pinned
WSL tool verification passed. The data audit checked 15 MP TextAssets, with
14 payloads matching the historical catalog and no inconsistent learnsets.

[Android acceptance](android-status-cures.md) used synthetic stored ailments
and one temporary item of each type, followed by real Your Items UI requests.
Poison changed true/true to false/true; paralysis changed false/true to
false/false. Each item went from one to zero, while HP stayed 20/20 and AP 12/12.
An app reload confirmed no ailment icons and explicit false status fields.
Guarded cleanup restored both research accounts' gameplay snapshots exactly.
Natural battle ailment application is outside this acceptance.

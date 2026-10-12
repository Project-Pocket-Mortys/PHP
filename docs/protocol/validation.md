# Pocket Mortys validation scenarios

## Automated replacement server checks

Run `py -m unittest discover -s tests/protocol -v` after starting Compose. The suite uses synthetic accounts and reseeds only the isolated database. It checks readiness IDs, missing/malformed inputs, invalid sessions, foreign battles/Morties, inactive battles, single-document capture acknowledgements, active deck selection, private event recipients, two-account SSE filtering and capture redaction. Tests do not certify original-server parity.

## Working client scenarios

These scenarios are pending device access. For each, retain build hashes, server commit, sanitized HTTP exchanges, SSE sequence, database changes and reconnect results. Do not mark a scenario passed from source inspection.

| Baseline feature | Scenario | Expected invariant |
|---|---|---|
| Startup | Cold launch, status/manifest fetch, asset cache miss and cache hit, login | Correct content is loaded; no unintended original-host requests; same account reconnects. |
| Item spawning | Enter room, observe pickup, collect once, retry | Pickup disappears; inventory gains exactly one award. |
| Morty roaming | Enter room with two accounts; observe movement and room change | Positions and presence remain coherent; identify HTTP/SSE/UDP responsibilities. |
| Evolution | Absorb an eligible Morty, then reconnect | Evolution and consumed Morties persist; unrelated Morties unchanged. |
| Healing | Damage active deck, heal, repeat, reconnect | HP/PP and any cost match client expectations without duplicate charges. |
| Deck slots | Buy a slot with enough and insufficient funds; retry | Slot and currency mutate together exactly once. |
| Learn attacks | Replace a legal attack; submit invalid/foreign Morty; reconnect | Legal move/PP persists; invalid mutations do not occur. |
| Swap Stop | Confirm which shop flow the README label denotes with the working client; exercise its offers/purchases and reconnect | Existing completed shop behavior remains intact; prices and rewards persist. |
| Salesman Rick's | Purchase valid item, insufficient funds, rapid retry | Correct quantity/currency persistence and compatible error UI. |

## Unfinished feature probes

- Wild battle: ready, attack, switch, item, run, victory/defeat/capture, then reconnect. Compare player and opponent sides and inspect durable HP/PP/rewards.
- Trading: request, offer, reject, accept and cancel with two accounts; verify ownership, locks and no duplicated Morties.
- Duplicate/in-flight moves: simultaneous requests and retry after timeout; verify one authoritative turn. Currently a known gap, not a passing test.
- SSE: disconnect mid-battle, reconnect with and without cursor, change room, send private/public events, inspect event ordering and receiver isolation.
- UDP: capture movement, direction, teleport/snap, idle, sequence wrap and reconnect; compare bytes to native sender/receiver routines.
- Empty or inactive events: arena, raids, Moving Mortys and Fyre; establish valid empty schemas before configuring events.
- Inventory boundaries: zero items, full Morty storage, locked/trading Morties, invalid recipes, challenge reward replay.
- Purchase/account flows: inspect only with synthetic data; record third-party dependencies without real purchases or real account deletion.

## Fixture requirements

Each fixture must state whether it came from an original-server capture, the replacement server, or a synthetic test. Include operation, client/server versions, source evidence and expected database effects. Preserve JSON types, missing/null distinctions and event order. Redact credentials and review arbitrary strings before committing. Never promote a placeholder response to a compatibility fixture solely because PHP emitted it.

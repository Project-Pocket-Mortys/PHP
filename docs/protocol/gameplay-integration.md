# Gameplay integration and provenance

`hayward/gameplay-integration` starts at `origin/main` `9ff1a11` and combines
the previously delivered collection, transport, crafting and battle work.
ConspiracyRick's original completed features and attribution remain intact.

The GitHub merge audit on 2026-11-04 found that PRs #11 through #22 targeted
parent feature branches. Several children were merged after their parents had
already been merged further up the stack. A merged PR label therefore did not
establish that its code had reached main: main still had an empty use-item
handler and lacked the lock/release routes and later SSE/transport fixes.

| Source tip | Integrated work | Integration merge |
| --- | --- | --- |
| `5f0c82e` (`hayward/morty-release`) | 19 commits after main's shared ancestor: optional UDP transport/lifecycle, room ownership, SSE recipient/rejoin/snapshot fixes, lock, healing/revival/AP items, release | `f6efbd8` |
| `86ce51b` (`hayward/crafting`, PR #26) | REA 6.8.0/private Node prerequisite and 22 multiplayer recipes | `626a09b` |
| `ab89698` (`hayward/battle-completion`, PR #27) | Native result contract, durable attack/run/win/lose and Android acceptance | `4175e0c` |

History is merged rather than replacing handlers with reconstructed copies.
Conflicts retain all Apache endpoint rewrites, completed README entries,
reviewed contracts and endpoint inventory records. The SSE merge retains the
recipient, membership-generation and bounded-snapshot repairs alongside the
battle result recipient and wild-removal serialization. Source hashes are
refreshed after integration; the inventory remains a discovery index rather
than a claim of original-server compatibility.

## Cross-feature repairs

The integrated battle lifecycle exposed four existing world mutation paths
that could invalidate an ACTIVE battle. Healing changed the authoritative HP
behind its snapshot; absorption could delete its active Morty; join/leave could
move the user away from the stored origin so even RUN failed.

Heal, absorb, join and leave now lock the user and check ACTIVE battles in the
same transaction as their mutations. They return 409 without changing the
account, room, cursor, inventory, deck, HP/AP or queued events when a battle is
still active, including a legacy WORLD user. RUN remains available in the
original room. The shared guard first reconciles old ACTIVE rows only from
consistent private terminal evidence, reusing the battle repair; it does not
replay rewards or cancel an unknown battle. Proven completed legacy battles
therefore do not disable normal world healing.

`test_battle_world_guards.py` initially reproduced nine failing assertions.
Its three final cases check the four blocked actions in BATTLE and legacy
WORLD states, successful RUN afterward, ordinary world actions after victory,
and healing after a proven legacy terminal result. These HTTP status choices
are replacement-server safeguards; original error parity is not established.

Absorption's other legacy rules, universal lock enforcement, battle readiness
timer races and interrupted-battle restoration remain separate work. Capture,
switching, combat/stat/reward formulas and the other battle modes remain gaps;
this integration does not enable them.

## Reproduction

Keep the existing research database volume. Apply the ordered additive research
migrations before starting the restored membership-generation handlers:

```powershell
docker compose -f compose.research.yaml exec -T web php /var/www/html/tools/research/server/migrate.php
docker compose -f compose.research.yaml -f compose.research-udp-tunnel.yaml --profile udp up -d udp udp-tunnel
py -3 tools/research/check_gameplay_integration.py --udp
py -3 -m unittest discover -s tests/research -v
py -3 tools/research/validate.py
py -3.14 tools/research/export_attack_max_ap.py --check
py -3.14 tools/research/export_crafting_data.py --check
wsl -- bash tools/research/rea.sh --version
wsl -- python3 tools/research/verify_tools.py
```

The optional adapter also needs the Windows host client described in
[stable transport](udp-stable-transport.md); it binds localhost UDP 5055 and
connects to localhost TCP 5056. Without it, use the base Compose UDP profile or
omit `--udp` for the HTTP/SSE/gameplay suites. A new environment should follow
[the research setup](README.md) before these commands.

The explicit integration runner includes only reviewed additive fixtures and
checks the isolated backend configuration first. It excludes
`test_accounts.AccountBootstrapTests` and `test_http.BattleContractTests`, both
of which invoke the older global `seed.php`. Do not use unrestricted protocol
discovery while retaining emulator accounts. Migration checks use a disposable
schema/temporary table; one departure rollback test uses a temporary trigger
whose condition matches only its synthetic player. This is a local test stack.

Raw account-preservation snapshots and Android captures remain under ignored
`.research`; sanitized evidence and executable fixtures stay in source. Existing
Android acceptance for each component is linked from its contract. New combined
[Android smoke evidence](android-integration-smoke.md) records a fresh app/SSE
connection, private battle delivery, native RUN and WORLD return. Its first
fixture used explicitly labeled synthetic recovery; only the second supplied
native move acceptance.

## Integration validation on 2026-11-04

| Check | Result |
| --- | --- |
| Explicit HTTP/SSE/gameplay/UDP runner | 133 tests passed, 624.837 seconds |
| Research tools unit suite | 57 tests passed, 10.169 seconds |
| PHP 8.3 lint | All 21 changed/new PHP files passed |
| Protocol evidence validation | JSON, source hashes, constructors and native boundaries passed |
| Checked-in asset catalogs | 690 attack AP maxima and 22 multiplayer recipes matched pinned TextAssets |
| WSL toolchain | REA 6.8.0; all pinned archive/version/integrity checks passed |
| Android combined smoke | Fresh Multiplayer/SSE, native RUN with null move ID, WORLD return |
| Existing account preservation | Both research accounts' HP/AP, items, decks, progression and final room/state matched private before snapshots |

The catalog exporters used Python 3.14 because the existing ignored Windows
UnityPy dependencies contain CPython 3.14 extension modules. Other Python
versions cannot load that local dependency directory. Runtime PHP does not
depend on those extraction packages.

No real account was reseeded, no database volume was removed, and no public
deployment was performed. The current main ref remained `9ff1a11`; the recovered
source tips above are all ancestors of this integration branch. PRs #26 and #27
remain separate review records; this branch includes their complete changes.

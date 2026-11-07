# Missing gameplay features: implementation order

[Mr. Meeseeks Box](meeseeks-box-implementation.md) now supports one battle-only
PvWM item action: the current owned actor defeats the wild enemy, consumes one
box and completes WIN atomically without an AI counterattack. The
[native contract](meeseeks-box-contract.md) establishes actor identity and enemy
HP snapshots. All 17 new and 89 adjacent backend cases pass; XP/rewards remain
empty, and no new Android item capture is claimed. Other battle modes and
original combat/reward formulas remain separate.

[Morty mutation response flags](morty-mutation-flags.md) now retain durable
trade reservations in item/heal/learn-attacks dictionaries and fix string-false
conversion in learn-attacks. This serializer repair preserves existing item
effects and attack learning. Backend tests and the
[native merge audit](item-reservation-projection-contract.md) provide evidence;
no new Android gameplay capture was made.

[Counterpart cancellation updates](trade-cancellation-notifications.md) now
publish committed own-offer withdrawal and parent cancellation invalidations.
Fifteen new backend cases and 50 adjacent regressions pass. The
[three-capture native proof](trade-cancellation-refresh-results.json) verifies
both cancellation paths and counterpart trade/details refreshes on the Android
2.41.0 pair in one world. The peer deliberately cold logs in between capture
phases; no uninterrupted peer session is claimed. Immediate self-cancellation
unlock remains open under the
[fresh callback/save contract](trade-cancellation-refresh-contract.md); the
inspected paths supply no ordering-safe PHP acknowledgement.

[Counterpart trade updates](trade-refresh-implementation.md) now publish committed
offer/decision invalidations through the original refresh handlers. Immediate
self-cancellation lock visibility remains open; no cancellation actor echo was
added because it can race native saved-offer cleanup.

The [live Android pair](live-trade-refresh.md) now completes a native
request/offer/reject/offer/accept cycle with counterpart SSE-triggered trade and
owned-details refreshes, live post-rejection selector eligibility and an exact
two-spare transfer. The [receipt](live-trade-refresh-results.json) preserves the
previous completion and records one added completion. Cross-room, iOS and native
third-account audience checks remain; this does not close the self-cancel gap.

ConspiracyRick's playable backend and README-completed features remain the
baseline. An unverified feature is not automatically broken. Work now prioritizes
missing player actions; broad transport research is deferred unless a reproduced
failure blocks gameplay or exposes another player's data.

Latest trade repair: [durable reference protection](trade-reference-implementation.md)
keeps player-details locks visible and protects absorption; owners can withdraw
exact orphan offers. Native cookie transport is now observed. Trading-kiosk
entry is now [observed in the first dimension](trading-kiosk-reachability.md).
Native own-request creation/cancellation and lock refresh now
[pass on a disposable client](native-trade-cancellation.md), and GetTrades now
projects its stored cooldown correctly. [Native offer creation/reload/cancellation](native-trade-offers.md)
now passes with repaired display metadata. Immediate offer-cancel inventory
refresh, broader transfer variants and full-Morty serializers beyond the
item/heal/learn [repair](morty-mutation-flags.md) remain open;
the baseline claims below are preserved.

[Native incoming decisions](native-trade-decisions.md) now include captured Reject
and successful requester Accept, exact guarded spare transfer and normal inventory
refreshes matching the post-accept database for both actors. The same pending
rejection history proves the GetTrades `competed_trades` alias corrects a notification
error; existing `completed_trades` remains equal. The [navigation contract](native-trade-decision-navigation.md)
distinguishes the notification's Accept acknowledgement from an actual decision.

[Offer response authorization and binding](trade-response-implementation.md) are
now repaired with recovered native errors and atomic sibling-offer cleanup.
[Creation eligibility](trade-listing-protection.md) now protects active-party,
locked and already-reserved instances, with exact specific-offer criteria. The
selected native transfer and both inventory refreshes now pass, with intermediate
capture gaps disclosed. Later deck activation and acceptance-time active-party checks pass the
[party transition regressions](trade-party-transitions.md). These repairs do not
establish original economic policy.

| Order | Feature | Next deliverable and acceptance |
|---|---|---|
| 1 | Lock/unlock Morties | Toggle/persistence and release/absorption protection implemented (`absorb-protection-implementation.md`); same-species/variant absorption checks reject incompatible batches (`absorb-eligibility-implementation.md`). Point-only absorption preserves a living active party (`absorb-active-party-implementation.md`). Native own-request creation/cancellation and lock refresh pass (`native-trade-cancellation.md`); native friend offer creation/reload/cancellation also pass (`native-trade-offers.md`). Response authorization, protected creation and deck/acceptance transition guards now pass regression tests (`trade-response-implementation.md`, `trade-listing-protection.md`, `trade-party-transitions.md`). Native requester decisions and completed-key notification repair now have separate evidence (`native-trade-decisions.md`); selected native decisions, exact transfer and both inventory refreshes now pass with intermediate capture gaps disclosed. Offer-cancel refresh, broader transfer variants and legacy flag provenance remain separate. |
| 2 | Use items | Eight HP items, full revival/AP restoration and targeted poison/paralysis cures work in world and battle (`battle-item-implementation.md`); Pure Curum combined HP/ailment recovery is implemented (`full-recover-implementation.md`). Account Shiny Potion activation/expiry is implemented (`shiny-potion-implementation.md`). Battle-only Mr. Meeseeks Box now completes a PvWM WIN (`meeseeks-box-implementation.md`). Finish percentage variants, stat/other damage/general items and authentic timing; remaining numeric evidence gaps are in `remaining-item-evidence.md`. |
| 3 | Release Morties | World preview/confirmation implemented; Android Stats cancel/release verified. Batch contracts, locks, trade and party guards pass tests (`morty-release-implementation.md`). |
| 4 | Crafting | 22 multiplayer recipes implemented atomically; Android Serum Quick Craft and inventory verified (`crafting-implementation.md`). |
| 5 | Wild battles and catching | Durable attack/run/victory/defeat, party switching/forced replacement and safe selection expiry implemented (`battle-timeout-implementation.md`). Recover trustworthy stats/attacks, capture consumption/owned records and rewards; original combat rules and reconnect remain. |
| 6 | Bot/friend battles | Invitations, membership, frozen parties/views and shared startup now work (migrations009–011). Research SSE/ready delivery (migration012) now passes two native Android startup/automatic-recovery captures (`android-shared-startup.md`). Research-gated first ATTACK storage and immutable pairing now pass 18 backend cases (migration013, `paired-selection-contract.md`); [two native inputs, waiting and expiry recovery](android-paired-selection-results.json) are verified on the dedicated registration parties. Public acceptance remains unavailable pending later-phase readiness, replay identity and combat/terminal behavior. Full native send/approval and broader interruption cases remain; bot modes are separate. |
| 7 | Challenges, raids and events | Implement claims and event battles after their underlying battle/reward flows work; no invented success responses. |

This order favors independently usable additions and their dependencies; it is
not a claim that battles are less valuable. A reproducible player-blocking battle
defect can take priority. Remaining protocol research is listed in
[backlog.md](backlog.md).

## Lock/unlock delivered

`POST /session/owned_morties/lock` now accepts `session_id`, `owned_morty_id` and
a JSON boolean `is_locked`. It authenticates and locks the account/Morty rows,
persists only that owned Morty's flag, and returns the complete existing decks
and active deck ID. Repeated requests set the requested state again without
changing inventory, HP, trading lock or deck membership. Slashless client POSTs
use an internal Apache rewrite. No schema migration is required.

Five additive tests cover lock/unlock/retries, player-details persistence,
cross-player and missing IDs, invalid sessions, strict booleans, slashless POSTs,
and empty/legacy-escaped decks:

```powershell
py -m unittest discover -s tests/protocol -p test_morty_lock.py -v
```

The initial four cases failed against the absent route. All five final tests
pass. [Native evidence](morty-lock-contract.md) establishes the success fields
and error envelope; exact original HTTP error codes remain unknown.

Android 2.41.0 on the primary research emulator was exercised through the normal
menu: Your Mortys, select Morty, Stats, Lock, then Unlock. The padlock appeared,
Release became disabled, and the button changed to Unlock; unlocking reversed
those changes. Both slashless requests returned HTTP 200. The database changed
from legacy `false` to `1` to `0`, restoring the logical unlocked state while
normalizing its storage. HP stayed 20 and active deck stayed 0. The account was
returned to the world without a save reset. See the sanitized
[capture](morty-lock-capture.json); raw screenshots/captures remain ignored.

This delivers the toggle and persistence, not universal server enforcement of
protection: [absorption now protects consumed donors](absorb-protection-implementation.md), and
release enforces both lock flags (`morty-release-implementation.md`). Other destructive
interfaces remain separate; this is not universal protection. No original-server capture,
production deployment or client relaunch persistence test is claimed.

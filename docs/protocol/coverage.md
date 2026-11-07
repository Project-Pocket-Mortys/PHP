# Protocol coverage

[Mr. Meeseeks Box](meeseeks-box-implementation.md) now supports one battle-only
PvWM item action: the current owned actor defeats the wild enemy, consumes one
box and completes WIN atomically without an AI counterattack. The
[native contract](meeseeks-box-contract.md) establishes actor identity and enemy
HP snapshots. All 17 new and 89 adjacent backend cases pass; XP/rewards remain
empty. [Android acceptance](android-meeseeks-box.md) now verifies native item
use, the Meeseeks animation, WIN, depletion to zero and exact fixture cleanup.
Encounter setup is synthetic; other battle modes and original combat/reward
formulas remain separate.

[Item, heal and learn-attacks flags](morty-mutation-flags.md) now use canonical
legacy booleans and preserve durable reservations in full-Morty responses.
The [bounded native merge audit](item-reservation-projection-contract.md) and
additive HTTP/database tests establish this repair; no new Android capture.

[Cancellation invalidations](trade-cancellation-notifications.md) now target
counterparts only, atomically with listing removal. All 15 new backend cases,
50 adjacent cases and nine pure observer cases pass. Native cancellation
consumption is now [verified on the Android 2.41.0 pair](trade-cancellation-refresh-results.json)
for both cancellation paths and counterpart trade/details refreshes. Three
captures retain the deliberate peer cold-login/session boundary. The [bounded actor callback/save
audit](trade-cancellation-refresh-contract.md) preserves the immediate
self-cancellation refresh gap.

[Trade refresh delivery](trade-refresh-implementation.md) now notifies counterparts
after committed new offers and decisions. Bounded REA establishes the handlers;
synthetic HTTP/DB/SSE tests cover privacy, rollback, startup and reconnect.
Original audiences and immediate self-cancellation unlock remain separate.

The [live native follow-up](live-trade-refresh.md) and
[receipt](live-trade-refresh-results.json) now verify a parent, rejected first
offer and accepted second offer with both clients continuously connected in one
world session. Two offer-submit frames reach the requester; rejected and accepted
frames reach the offerer. Every frame is followed by successful native
GetTradeData and exact GetDetails(`0x78`) requests. The rejection also restores
live selector eligibility without restart. The guarded final state swaps exactly
two spares, retains the prior completion and adds one (two total), with no
remaining parent/offers. Native third-account privacy, cross-room and iOS remain
separate from this two-account proof.

[Native trade decisions](native-trade-decisions.md) now cover requester Reject
and successful requester Accept, exact guarded spare transfer and both actors'
normal owned-inventory refreshes. A controlled reload of the same pending
offer history proves that GetTrades needs `competed_trades`; the server retains
`completed_trades` as an equal legacy alias. [Navigation and notification logic](native-trade-decision-navigation.md)
distinguishes the decision from the notification's Accept acknowledgement.
Both refreshed inventories match the guarded post-accept database; active parties,
resources and boolean lock fields are preserved. This verifies selected captures,
with intermediate capture gaps disclosed.

[Party transitions and acceptance](trade-party-transitions.md) now preserve
trade reservations across current deck/edit, set-active and accepted transfers.
Bounded native evidence distinguishes UI lock predicates from replacement
activation/transfer integrity policy. Synthetic HTTP/DB races pass; no new
Android deck capture is claimed by that regression work; native decisions are separate above.

[Request/offer creation eligibility](trade-listing-protection.md) now enforces
the recovered native selector at insertion, including active-deck/lock exclusion
and offer species/variant criteria. Evidence combines bounded REA6.8 traces and
synthetic HTTP/DB tests; later deck transitions and native decisions have separate follow-ups.

[Trade offer responses](trade-response-implementation.md) now enforce authenticated
requester decisions and exact request/offer binding, with native error codes and
atomic competing-offer cleanup. Evidence is bounded client analysis plus
synthetic HTTP/database regression tests. Native decision presentation and
protected listing creation now have separate evidence; complete party safety
and original economic policy remain broader obligations.

The retained Android client now passes [isolated offline SDK startup](onetrust-startup-recovery.md)
and [native trading cookie transmission](onetrust-recovery-cookie-handoff.json).
This closes the prior cookie-transport observation gap. Native own-request
creation/cancellation is now [verified](native-trade-cancellation.md); offer
cancellation now also [passes on the disposable pair](native-trade-offers.md).
Immediate inventory unlock after offer cancellation remains a refresh gap.
Player details and absorption now honor
[durable trade references](trade-reference-implementation.md). Item, heal and
learn-attacks serializers now have the [same projection](morty-mutation-flags.md);
legacy true-flag reconciliation remains separate.

[Native kiosk entry](trading-kiosk-reachability.md), Trade slots and Browse's empty
state are now observed. A separate disposable client created and cancelled its
own listing, with lock refreshes and corrected stored-cooldown projection.
Nonempty offer creation/reload/cancellation is now observed, with corrected
display metadata. Requester decisions, exact transfer and both-actor
post-accept refreshes now have the follow-up above; broader transfer variants remain separate.

Generated by `tools/research/inventory.py`. Status is provisional source triage, not client certification.

The partial `/session/battle/move` status includes research-gated first human
ATTACK storage and immutable pairing (migration 013), in addition to the existing
private-wild behavior. The submitting participant must be initially ready; the
pair requires both ready signals. The native HTTP acknowledgement remains
`{"success":true}`. No combat resolution, resource spend, timer/result publication,
later selection phase or public approval is enabled. Eighteen scoped backend
cases are validated; [two native inputs, waiting and automatic expiry recovery](android-paired-selection-results.json)
are verified on the dedicated registration parties. See
[the selection contract and implementation](paired-selection-contract.md).

| Path | Status | Client constant | Server source |
|---|---|---|---|
| `/` | stub | not found | index.php |
| `/arena/battle/bot` | stub | yes | arena/battle/bot/index.php |
| `/arena/energy/fetch` | stub | yes | arena/energy/fetch/index.php |
| `/arena/events/list` | partial | yes | arena/events/list/index.php |
| `/arena/rewards/claim` | absent | yes | absent |
| `/arena/rewards/list` | partial | yes | arena/rewards/list/index.php |
| `/arena/rewards/pending/list` | stub | yes | arena/rewards/pending/list/index.php |
| `/arena/scores/list` | partial | yes | arena/scores/list/index.php |
| `/consent` | absent | yes | absent |
| `/decks/slots/config` | partial | yes | decks/slots/config/index.php |
| `/event/brackets` | partial | yes | event/brackets/index.php |
| `/event/check` | partial | yes | event/check/index.php |
| `/event/claimRewards` | absent | yes | absent |
| `/event/pendingRewards` | partial | not found | event/pendingRewards/index.php |
| `/iap` | absent | yes | absent |
| `/iap/display/list` | partial | yes | iap/display/list/index.php |
| `/inappdeletion/get-account-data-storage-time` | stub | yes | inappdeletion/get-account-data-storage-time/index.php |
| `/inappdeletion/request-account-deletion` | stub | yes | inappdeletion/request-account-deletion/index.php |
| `/is-gdpr` | stub | yes | is-gdpr/index.php |
| `/linkaccount` | partial | not found | linkaccount/index.php |
| `/lte/fyre/battle/summer` | absent | yes | absent |
| `/lte/fyre/events/list` | stub | yes | lte/fyre/events/list/index.php |
| `/lte/fyre/events/playerinfo` | absent | yes | absent |
| `/lte/fyre/purchase/item` | absent | yes | absent |
| `/lte/fyre/purchase/pack` | absent | yes | absent |
| `/morty/slots/config` | stub | yes | morty/slots/config/index.php |
| `/moving-mortys/battle` | absent | yes | absent |
| `/moving-mortys/events/list` | stub | yes | moving-mortys/events/list/index.php |
| `/moving-mortys/purchase-pass` | absent | yes | absent |
| `/promos/active` | stub | yes | promos/active/index.php |
| `/reward/multiplayer` | absent | yes | absent |
| `/reward/single-player` | absent | yes | absent |
| `/session/battle-boss` | stub | yes | session/battle-boss/index.php |
| `/session/battle-bot` | stub | yes | session/battle-bot/index.php |
| `/session/battle-custom-battle` | absent | yes | absent |
| `/session/battle-invite/create` | absent | yes | absent |
| `/session/battle-invite/response` | absent | yes | absent |
| `/session/battle-invite/revoke` | absent | yes | absent |
| `/session/battle-wild-morty` | partial | yes | session/battle-wild-morty/index.php |
| `/session/battle/move` | partial | yes | session/battle/move/index.php |
| `/session/battle/ready` | partial | yes | session/battle/ready/index.php |
| `/session/buy-item` | implemented | yes | session/buy-item/index.php |
| `/session/challenge/claim-reward` | absent | yes | absent |
| `/session/challenge/list` | partial | yes | session/challenge/list/index.php |
| `/session/collect-pickup` | implemented | yes | session/collect-pickup/index.php |
| `/session/deck/edit` | partial | yes | session/deck/edit/index.php |
| `/session/deck/set-active` | partial | yes | session/deck/set-active/index.php |
| `/session/decks/slots/buy` | implemented | yes | session/decks/slots/buy/index.php |
| `/session/dimensions/buy` | absent | yes | absent |
| `/session/dimensions/check-if-dimension-ftue-rewards-dispensed` | absent | yes | absent |
| `/session/dimensions/dispense-dimension-ftue-rewards` | stub | yes | session/dimensions/dispense-dimension-ftue-rewards/index.php |
| `/session/dimensions/query` | stub | yes | session/dimensions/query/index.php |
| `/session/dispense-item` | absent | yes | absent |
| `/session/emote/p2p` | absent | yes | absent |
| `/session/emote/room` | partial | yes | session/emote/room/index.php |
| `/session/friend/donate-morty` | absent | yes | absent |
| `/session/friend/list` | partial | yes | session/friend/list/index.php |
| `/session/friend/remove` | partial | yes | session/friend/remove/index.php |
| `/session/friend/request` | partial | yes | session/friend/request/index.php |
| `/session/friend/request-morty` | absent | yes | absent |
| `/session/friend/response` | partial | yes | session/friend/response/index.php |
| `/session/friend/search` | partial | yes | session/friend/search/index.php |
| `/session/gacha` | partial | yes | session/gacha/index.php |
| `/session/gacha-info` | partial | yes | session/gacha-info/index.php |
| `/session/heal` | implemented | yes | session/heal/index.php |
| `/session/incentive/reject` | absent | yes | absent |
| `/session/join-room` | partial | yes | session/join-room/index.php |
| `/session/leave-room` | partial | yes | session/leave-room/index.php |
| `/session/morty/slots/buy` | absent | yes | absent |
| `/session/morty/slots/ftue` | absent | yes | absent |
| `/session/owned_morties/absorb` | implemented | yes | session/owned_morties/absorb/index.php |
| `/session/owned_morties/attempt-release-multiple` | absent | yes | absent |
| `/session/owned_morties/learn-attacks` | implemented | yes | session/owned_morties/learn-attacks/index.php |
| `/session/owned_morties/lock` | absent | yes | absent |
| `/session/owned_morties/release-multiple` | absent | yes | absent |
| `/session/ping-dynamic` | stub | not found | session/ping-dynamic/index.php |
| `/session/player-avatar/buy` | partial | yes | session/player-avatar/buy/index.php |
| `/session/player-avatar/migrate` | stub | yes | session/player-avatar/migrate/index.php |
| `/session/player-avatar/set-active` | partial | yes | session/player-avatar/set-active/index.php |
| `/session/player-details` | partial | yes | session/player-details/index.php |
| `/session/player-flag` | absent | yes | absent |
| `/session/recipe/use` | absent | yes | absent |
| `/session/room-details` | partial | yes | session/room-details/index.php |
| `/session/state` | stub | yes | session/state/index.php |
| `/session/use-general-item` | absent | yes | absent |
| `/session/use-item` | stub | yes | session/use-item/index.php |
| `/session/use-shiny-potion` | absent | yes | absent |
| `/shard/health` | absent | yes | absent |
| `/shard/scores` | partial | yes | shard/scores/index.php |
| `/sp/gacha-info` | partial | yes | sp/gacha-info/index.php |
| `/sse` | partial | not found | sse/index.php |
| `/support` | partial | not found | support/index.php |
| `/support/dashboard` | partial | not found | support/dashboard/index.php |
| `/time` | stub | not found | time/index.php |
| `/trading/cancel-trade` | partial | yes | trading/cancel-trade/index.php |
| `/trading/cancel-trade-offer` | partial | yes | trading/cancel-trade-offer/index.php |
| `/trading/config` | stub | yes | trading/config/index.php |
| `/trading/get-trades` | partial | yes | trading/get-trades/index.php |
| `/trading/offer-morty` | partial | yes | trading/offer-morty/index.php |
| `/trading/offer-response` | partial | yes | trading/offer-response/index.php |
| `/trading/request-morty` | partial | yes | trading/request-morty/index.php |
| `/user/login` | partial | yes | user/login/index.php |
| `/user/register` | partial | yes | user/register/index.php |

Absorption now preserves a living owner-resolved active party before point-only
donor deletion; see [native evidence](absorb-active-party-contract.md) and the
[repair boundary](absorb-active-party-implementation.md). Full transformation
remains separate, and README-completed feature status is retained.

Owner-scoped trade and offer cancellation now preserve native one-ID bodies and
use current cookie/Bearer sessions; see [contracts and limits](trade-cancellation-implementation.md).
Native outgoing-cookie transmission is verified by the linked recovery receipt;
native Android 2.41.0 cancellation and counterpart refresh are now observed.
Immediate own-offer cached unlock, iOS and stock online startup remain separate.
Exact owner withdrawal of orphan
offers is supported, with no transfer, refund or raw-lock rewrite.

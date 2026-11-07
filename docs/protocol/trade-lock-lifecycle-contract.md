# Android 2.41.0 trading-lock lifecycle contract

Recovered 2026-11-06 from the ARM64 client before implementing persisted lock changes. This is static client evidence, not a recording of the original service or proof of its database, concurrency, or authorization policy. See also [trade cancellation](trade-cancellation-contract.md).

## Reproduction and evidence boundary

From the repository in PowerShell, using the default WSL distribution:

```powershell
wsl.exe -- bash tools/research/ghidra-trade-lock-lifecycle.sh
```

The wrapper requires REA 6.8.0, records artifact inspection, runs targeted Ghidra 12.1.4 analysis in a disposable project, and uses `C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe -X utf8 -B` for metadata-bounded ARM64 disassembly. Every run creates a fresh ignored output directory and refuses an existing destination. The helper's optional regex adds explicitly selected accessors to the bounded disassembly; it does not alter the Ghidra result.

Final receipt: `.research/trade-lock-lifecycle-20261106T193701Z/{rea-version.txt,artifact.json,ghidra.json,ghidra.log,methods.json,arm64.txt}`. Earlier distinct receipts ending `193525Z` and `193631Z` were retained. The final receipt contains 30 bounded methods, including one supplemental own-trades accessor and the existing HTTP success accessor. ELF SHA-256: `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`; IL2CPP metadata version 31. No device, database, PHP endpoint, or server state was modified for this analysis.

RVAs below are relative to the original ELF, not Ghidra's displayed image base. Managed parameter types are not imported into Ghidra. Only instructions inside the bounds recorded in `methods.json` establish behavior; generic exception paths and decompiler return types must not be taken literally.

## Two independent owned-Morty flags

`MPOpponentMortyData` represents an owned Morty, including `netId` at `+0x18`. Its `SetFromDict` method (`0x158cb1c`) handles these keys independently:

| Player-details key | Native field | Bounded instruction |
| --- | --- | --- |
| `is_locked` | `isLocked`, `+0x6d` | `0x158d394: strb w8, [x19, #0x6d]` |
| `is_trading_locked` | `isTradeLocked`, `+0x6e` | `0x158d4b4: strb w8, [x19, #0x6e]` |

Each value is converted using `System.Convert.ToBoolean`. The trading lock is separate from the manual/favorite lock. Creation and cancellation lock writes recovered below target only `+0x6e`.

## Creation reserves both own requests and own offers locally

The endpoint labels RequestTrade and OfferMorty correspond to native `RequestMortyTrade` (`0x1790f04`) and `SubmitMortyTradeOffer` (`0x1791170`). Their success callbacks both reserve an owned Morty:

| Operation | Callback and success enum | Owned-Morty selection | Lock write |
| --- | --- | --- | --- |
| Create own request | `<RequestMortyTrade>b__0`, `0x1793c00`, `NONE=4` | `ownedMorty.netId == response.trade.morty_trade_id` | `0x1793e44`: byte `+0x6e = 1` |
| Create own offer | `<SubmitMortyTradeOffer>b__0`, `0x1794924`, `NONE=6` | `ownedMorty.netId == response.offer.morty_offer_id` | `0x1794b68`: byte `+0x6e = 1` |

The request selectors at `0x17948a4` and `0x17948e0`, and offer selector at `0x1794d3c`, compare the owned Morty's `netId` at `+0x18` with the corresponding response object's field at `+0x20`. These are instance IDs, not Morty species IDs.

Request success appends `response.trade` to `ownTrades`, creates the trade-Morty cache entry, stores response cooldown and conditionally response coupons, calls `CheckUpdateTradeOffers`, then calls `NetworkPlayerAPI.GetDetails(0x78)` at `0x1794010`. Offer success appends `response.offer` to `ownTradeOffers`, creates its trade-Morty cache entry, adds the offer to saved `trade_offer_made_ids`, calls `GetDetails(0x78)` at `0x1794c9c`, saves multiplayer data with mask `0x80`, and calls `CheckUpdateTradeOffers`. These creation side effects occur in the success branch; a rejected creation does not execute these reservation writes.

Mask `0x78` requests `MORTIES | MORTY_ATTACKS | DECKS | MORTYDEX`. Consequently a local success write is insufficient for persistence: a subsequent player-details Morty dictionary supplies `is_trading_locked` again. A server returning a stale false value can overwrite the local true when that dictionary is applied. This last consequence is an inference from the explicit refresh and `SetFromDict` writes, not a device observation of response ordering.

## GetTradeData and own-trades assignment do not derive locks

`GetTradeData` success callback (`0x1794d80`, `NONE=2`) partitions response lists using the supplied player ID:

| Cache | Source and predicate |
| --- | --- |
| `ownTradeOffers`, `+0x90` | `trade_offers` with `offer.player_id == playerID`, predicate `0x1795294` |
| `friendOffersOnOwnTrades`, `+0x98` | `trade_offers` with `offer.player_id != playerID`, predicate `0x17952b8` |
| `friendTrades`, `+0x80` | `trade_requests` with `trade.player_id != playerID`, predicate `0x17952dc` |
| `ownTrades`, `+0x88` | `trade_requests` with `trade.player_id == playerID`, predicate `0x1795300` |

It replaces `tradeMortys`, attaches the returned attacks, stores completed trades/cooldown, calls `CheckUpdateTradeOffers`, and emits trade-data/request/offer/cooldown events. Its bounded body does not scan owned Morties or write either lock byte. Returned trade-Morty presentation records are not a substitute for the owned-Morty inventory dictionary.

The metadata contains no method named `SetOwnTrades`. The actual generated `NetworkFriendAPI.set_ownTrades` is exactly eight bytes at `0x178eaf4..0x178eafc`: `str x1, [x0, #0x88]; ret`. Assigning that list has no hidden reservation or release side effect. `GetTradeData` itself writes the backing field directly.

## Cancellation asymmetry and refresh limits

`CancelTrade` callback (`0x1795cf8`) requests `GetDetails(0x78)` before checking the success result, including on failure. On success it finds the own request, removes its displayed incoming offers, clears the request Morty's `isTradeLocked` (`0x1795fbc: strb wzr, [x0, #0x6e]`), removes the own request, checks offer updates, and refreshes trade data. It does not test for another active request/offer before its local clear. This local single-row behavior is not proof that the original backend allowed overlapping reservations.

`CancelTradeOffer` callback (`0x1796134`) removes the successful own offer and its saved offer-ID cache entry, saves multiplayer data with mask `0x80`, and checks offer updates. Its bounded body does **not** directly clear `isTradeLocked`, request player details, or call `GetTradeData`. The offer-cancellation UI result handler (`0x1600b4c`) calls `UIBackHandler` on `NONE=3`; it has no direct inventory mutation or details refresh. This does not rule out later state transitions or ordinary future refreshes. It does rule out assuming that this callback itself releases the owned-Morty byte.

`CheckUpdateTradeOffers` classifies disappeared saved offer records and may show completion/decline updates. The recovered bounded helper does not reconcile owned-Morty locks. Neither cancellation callback changes `isLocked`. Static evidence does not establish an immediate native refresh after offer cancellation, nor guarantee when a server-side release becomes visible in an already loaded client.

## Replacement-server policy and limits

Both successful creation callbacks set a trading lock locally. The implemented
repair derives the player-details flag from durable references and preserves
the existing stored flag. This is replacement-server policy, not recovered SQL:

```text
effective is_trading_locked =
    existing legacy flag conversion
    OR exists trades reference to this owned_morty_id
    OR exists trade_offers reference to this owned_morty_id
```

References count globally by the instance ID, including orphan offers and rows
whose declared owner is stale. This conservative choice matches the existing
release guard. Native code does not establish original-server handling of
orphan or conflicting rows. Do not infer that the original service accepted
overlapping reservations or used this legacy table layout.

No stored flag is rewritten. Removing the last reference releases only the
derived contribution; an existing true flag remains true. Manual `is_locked`,
ownership, decks, refunds and cooldowns are unchanged. An authenticated owner
can withdraw its exact orphan offer so that reference can be removed without
deleting another player's data or reversing a completed transfer.

Absorption checks the same durable references with explicit current locking
reads before modifying the recipient or consuming actual eligible donors.
Other full-Morty response paths still serialize stored flags and are not covered
by this player-details repair. Immediate native refresh after offer cancellation,
legacy true-flag reconciliation and wider trade authorization remain separate.

# Android 2.41.0 native trade creation contract

Recovered 2026-11-06 from the ARM64 client. This is bounded static evidence, not an observed successful native creation/cancellation or proof of original-service policy. See [cancellation](trade-cancellation-contract.md), [trading locks](trade-lock-lifecycle-contract.md), and [kiosk entry](trading-kiosk-native-contract.md).

## Reproduction and evidence boundary

From PowerShell, using the default WSL distribution:

```powershell
wsl.exe -- bash tools/research/ghidra-trade-creation.sh
```

The combined wrapper requires exactly REA 6.8.0, records artifact inspection, runs targeted Ghidra 12.1.4 analysis in a disposable project, and exports metadata-bounded ARM64 instructions with `C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe -X utf8 -B`. It refuses an existing output directory. Its optional second argument supplements the bounded export with a full-match method regex. It reuses `trade-cancellation-bounded.py`; the exporter's default HTTP-success accessor does not imply that every selected method uses HTTP.

The combined wrapper was syntax-checked without repeating Ghidra. Findings came from these fresh, retained ignored receipts under `.research/`, each containing `rea-version.txt`, `artifact.json`, `ghidra.json`, `ghidra.log`, `methods.json`, and `arm64.txt`:

| Receipt | Scope |
| --- | --- |
| `trade-creation-native-20261106T210059Z` | Request constructors/callbacks, eligibility, selection UI and creation confirmation; 41 bounded methods. |
| `trade-creation-gates-20261106T210204Z` | Selection predicates, active-deck accessor, entry, timer and premium-dialogue paths; 13 bounded methods. |
| `trade-creation-gates-20261106T210228Z` | Own-trade slot setup/selection and supporting gates; 17 bounded methods. |

ELF SHA-256 is `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`; metadata version is 31. RVAs below refer to that original ELF; Ghidra adds image base `0x100000`. Managed parameter types are not imported. Only instructions within `methods.json` bounds establish behavior; decompiler exception-path overrun and inferred return types do not.

## First-party creation bodies

`NetworkFriendAPI.RequestMortyTrade` (`0x1790f04`) constructs AnonymousType18 with exactly six fields:

```json
{
  "session_id": "<session>",
  "player_id": "<player>",
  "owned_morty_id": "<owned instance ID>",
  "requested_morty_id": "any",
  "request_variant": "Normal",
  "is_free_trade": true
}
```

The endpoint is `/trading/request-morty`. `request_variant` comes from `MortyVariant.ToString()`: `Normal=0`, `Shiny=1`, or `Pulsing=2`, serialized as its name string. `SubmitRequest` (`0x160522c`) passes `yours.net_id` as the owned instance ID and `theirs.morty_id` as the desired species ID. `MPTradeRequestCreateUI.SetUp` (`0x1604150`) creates a default desired record with `morty_id="any"` and default `Normal` variant when none is supplied. The method's `couponCost` argument is callback closure state, not a request-body field.

`NetworkFriendAPI.SubmitMortyTradeOffer` (`0x1791170`) constructs AnonymousType19 for `/trading/offer-morty`:

```json
{
  "session_id": "<session>",
  "player_id": "<player>",
  "offered_morty_id": "<owned instance ID>",
  "trade_request_id": "<existing trade ID>"
}
```

The offer confirmation handler (`0x16006a4`) supplies the selected Morty's `net_id` and existing request's `trade_id`. Creation bodies differ from the ID-only cancellation bodies; do not add creation fields to native cancellation requests.

## Owned-Morty eligibility

`MPTradeMortySelectState.GetTradeableMortys` (`0x15f98d0..0x15f9ae0`) filters the current owned inventory to records satisfying `!isLocked && !isTradeLocked`, then removes each object returned by `MPPlayerData.GetActiveDeck`. The predicate at `0x15fc240` independently reads bytes `+0x6d` and `+0x6e`. `GetActiveDeck` (`0x1591a1c`) forwards to `GetDeckMortyDatas` with the current active-deck index.

This excludes the **active deck**, not demonstrably every saved deck. No Morty-level, trainer-level, species, HP, attack-count or inventory-count threshold occurs in this bounded eligibility helper. `MPTradeManageState.UISelectHandler` (`0x15f95c4..0x15f98c8`) checks this list before opening a new empty request; an empty list invokes `HandleNoTradeableMortys` instead of transitioning.

For a specific desired species, `MPTradeOfferCreateState.UISelectHandler` (`0x16004f4`) supplies `trade.morty_request` and `trade.request_variant` as selection restrictions. Owned-list `SetCell` removes species mismatches and variant mismatches using predicates `0x15fe0c4` and `0x15fe0f0`. The literal `any` bypasses setting those restrictions.

No numeric player/Morty level prerequisite was proven in the bounded kiosk-entry, creation, slot-selection or inventory-selection paths. `MPWorldState.AttemptToOpenTrade` (`0x163f96c`) performs a state transition without a level check. These narrow observations do not establish every startup, progression, resource or server-side gate.

## Free slot, premium slots and cooldown inputs

`MPTradeManageUI.SetUp` (`0x15f8850..0x15f9054`) creates the number of slots supplied by `TradeConfig.max_trades`, putting an existing `is_free_trade` request in the first slot. `TradeCellSelectedHandler` (`0x15fa838..0x15fab44`) sets create-state `isFreeTrade = selectedIndex == 0`. An empty first slot is selectable only when `NetworkFriendAPI.isFreeTradeInCooldown` is false; setup also compares the supplied cooldown timestamp against server-adjusted time. Other empty slots follow the premium purchase flow and display `TradeConfig.premium_trade_cost`.

The config declares `premium_trade_cost`, `max_trades`, and `trade_cooldown_minutes`; these are server-supplied values, while availability of the free slot is also enforced by native UI. This trace does not establish the original backend's charge, deduction, refund or cooldown-generation formula. Choose the first free slot when available for an acceptance trace to avoid depending on unknown premium payment behavior.

## Responses and errors

Both creation callbacks first call `ParseHTTPError`; success then deserializes `TradeRequestCreateResponse {trade,cooldown,coupons}` or `TradeOfferCreateResponse {offer}`. Thus cancellation's body-agnostic success behavior does not apply to creation. Success appends the returned record and reserves its owned Morty locally, followed by the inventory refresh described in the trading-lock contract.

| Endpoint enum | Recognized values |
| --- | --- |
| `eSubmitTradeRequestError` | `UNKNOWN=0`, `FAILED=1`, `TRADE_MORTY_LOCKED=2`, `TRADE_REQUEST_MORTY_DOES_NOT_BELONG_TO_PLAYER=3`, `NONE=4` |
| `eSubmitTradeOfferError` | `UNKNOWN=0`, `FAILED=1`, `TRADE_NO_TRADE_EXISTS=2`, `TRADE_NO_SUCH_MORTY=3`, `TRADE_MORTY_NOT_MATCH_CRITERIA=4`, `TRADE_OFFER_MORTY_DOES_NOT_BELONG_TO_OFFERING_PLAYER=5`, `NONE=6` |

On a non-success HTTP response, the parser consumes the exact enum-name string in `error.code`, as documented for cancellation. These names do not prove original backend validation order, authorization rules or status mappings.

## Disposable fixture and proposed acceptance sequence

A replacement-server fixture should provide a valid normal active party and at least one additional owned Morty outside the active deck with both locks false. That is an operational test arrangement inferred from the native filter, not recovered original-service fixture policy. Exact minimum active-party size and numeric progression thresholds remain unproven. Ensure its displayed free slot is available using the server's actual config/cooldown contract; do not invent a premium price or timestamp formula.

The shortest proposed native sequence requires one authenticated client: enter the kiosk, open own trades, select an available empty first/free slot, choose the spare owned Morty, retain the default desired `any`, and confirm. Then verify the returned request and inventory trading lock, reopen that own request and cancel, and verify the cancellation request plus resulting inventory refresh. This is a proposed acceptance procedure; successful native creation or cancellation has **not** been established by these static receipts. Native cancellation has its own cookie-authentication and refresh evidence requirements.

An offer-create/cancel trace additionally requires a visible existing request and an eligible spare matching its criteria. Immediate owned-inventory refresh after offer cancellation remains unproven. No second player, incoming offer, premium purchase or ownership transfer is needed for the proposed own-request create/cancel sequence.

# Android 2.41.0 trading-kiosk native contract

Recovered 2026-11-06 from the ARM64 client. This is bounded static client evidence about world loading and interaction selection, not a device observation of successful trading or evidence of original-service behavior. See [trading-lock lifecycle](trade-lock-lifecycle-contract.md) for inventory reservations and cancellation behavior.

## Reproduction and receipts

From PowerShell in the repository, using the default WSL distribution:

```powershell
wsl.exe -- bash tools/research/ghidra-trading-kiosk.sh
```

The combined wrapper requires REA 6.8.0, records artifact inspection, runs targeted Ghidra 12.1.4 analysis, and exports metadata-bounded ARM64 instructions using `C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe -X utf8 -B`. It creates a fresh ignored output directory and refuses an existing destination. An optional second argument adds a full-match method regex to the supplementary ARM64 selection. Existing navigation methods are included by default. The shared bounded exporter also includes `Best.HTTP.HTTPResponse.get_IsSuccess`; its presence does not imply an HTTP dependency in kiosk selection.

The findings below came from these retained receipts; the combined wrapper was subsequently added for reproduction and was syntax-checked without another Ghidra run:

| Receipt directory under `.research/` | Contents and scope |
| --- | --- |
| `trade-navigation-wzfQcv` | Earlier targeted `ghidra.json` and log: world interaction handler, trading entry, and trading menu methods. |
| `trade-kiosk-native-B0vyPR` | `rea-version.txt` (`6.8.0`), artifact inspection, targeted Ghidra JSON/log, `methods.json`, `arm64.txt`; world/node loading and kiosk methods. |
| `trade-kiosk-gates-MysSM2` | Bounded ARM64 export for controller setup, base-node setup/constructor/interactability, and resource-ID formatting; inspection copied from the preceding receipt. |
| `trade-kiosk-coords-xqFwGv` | Bounded ARM64 export for node coordinates, coordinate conversion, and A-button forwarding; same inspected artifact. |
| `trade-kiosk-input-GlgNtT` | Bounded ARM64 export for input handling and interaction raycast; same inspected artifact. |

Original ELF SHA-256: `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`. IL2CPP metadata version: 31. Metadata SHA-256: `b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10`. ARM64 mapping is `.research/dumper/script.json`, SHA-256 `a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb`.

All addresses below are native ELF RVAs. Ghidra displays an additional image base of `0x100000`. Managed types are not imported into its decompiler. In particular, the `CreateWorld` decompilation follows an exception path into the next method; only instructions within the `methods.json` bounds support the claims here. Supplemental receipts have empty Ghidra selections and were produced by the bounded exporter, not additional decompiler runs.

## World resources and client nodes

`MPWorldController.SetUp` (`0x1610678..0x16107fc`) stores the supplied world ID at `+0x48`. It calls `CreateWorld` at `0x161078c`, `SetUpClientNodes` at `0x1610794`, then `SetUpRoomNodes` at `0x161079c`.

`CreateWorld` (`0x16107fc..0x1610998`) calls `MPWorldDefs.GetResourceId` at `0x16108ac`, formats `World/Multiplayer/Dimensions/{0}`, calls `Resources.Load` at `0x16108c8`, then instantiates the resource at `0x16108ec`. The bounded `GetResourceId` body (`0x1778318..0x1778364`) is string formatting; the loader does not select a kiosk by a separate trade endpoint in this body. Metadata declares world-ID constants `1` through `7`; those declarations alone do not establish kiosk placement or unlock conditions for a particular world.

`SetUpClientNodes` (`0x1610998..0x1610b00`) finds the instantiated world's `Nodes` child, calls `GetComponentsInChildren<MPNode>()` at `0x1610a1c`, and invokes each returned node's virtual `SetUp` at `0x1610a64`. The two subsequent type checks populate the storage-Rick and dimensions-Rick controller fields. They do not selectively instantiate the kiosk.

`SetUpRoomNodes` (`0x1610b00..0x16110d8`) dispatches creation of room users/player, bots, wild Morties, pickups, raid bosses, LTE nodes and moving Morty nodes. Its bounded body has no kiosk-specific creation dispatch. This supports examining the world resource's client-node hierarchy for kiosk placement; it does not prove every possible creation or activation path has been recovered.

`CreateNode` (`0x1612618..0x16128a4`) is a generic resource-pool instantiation helper. It parents the new node under the controller's node container, applies coordinate/ground placement, and optionally registers a network ID. Its existence does not establish that a server should manufacture a kiosk record.

## Kiosk setup and interaction gate

`MPTradeKioskNode.SetUp` is exactly four bytes at `0x1617778..0x161777c`: a tail branch to `MPNode.SetUp` (`0x1616054`). Its constructor similarly branches to the base constructor. Neither kiosk body sets `interactionType`; metadata declares `eMPNodeInteractionType.TRADE_KIOSK = 18`, while the instantiated component's serialized state must be inspected separately.

Base `MPNode.SetUp` (`0x1616054..0x16160b8`) finds the transform child `InteractionPoint` and stores it in `_interactionPoint` at `+0x40`. Base `IsInteractable` (`0x1619190..0x1619224`) returns false for a missing interaction-point transform; otherwise it returns that child game object's `activeSelf` through the tail call at `0x161921c`.

These bounded kiosk/base bodies contain no player-level or trading-feature check. That narrow observation does not exclude gates elsewhere, inactive parent hierarchies, collider configuration, resource variants, or later state behavior.

## A-button selection uses a world-space collider

`MPWorldController.FaceBtnAPressedInteract` (`0x16125e0..0x1612600`) forwards through the player node's input module to `MPNodePlayerInputModule.FaceBtnInteract` (`0x161c434..0x161c514`). That method requires an interaction subscriber, obtains the player's transform **world position** at `0x161c47c`, reads facing direction from the movement module's `+0x3c`, and calls `MPNodeUtils.GetCollidingWithInteractionPoint` at `0x161c498`. It invokes the selected node's virtual `IsInteractable` at `0x161c4d8` before emitting the interaction event.

`GetCollidingWithInteractionPoint` (`0x1622dc8..0x1622f34`) converts facing direction to a ray direction, adds a vertical offset to the supplied player position, then calls `Physics.Raycast` at `0x1622ea8` with distance `1.0` and layer mask `0x100` (layer 8). The receipt does not decode the vertical-offset constant. It rejects a hit whose collider `isTrigger` is true (`0x1622ed8`). For a valid hit it obtains the hit transform's **parent** game object and calls `GetComponent<MPNode>` at `0x1622f10`.

Consequently an approach trace must locate the actual interaction collider in world space, its parent node, layer and trigger settings, active hierarchy, and the player's facing. The kiosk's visible model center alone is insufficient to establish a valid A-button approach.

## Node coordinates are a separate calculation

`MPNode.GetCoord` (`0x16156a8..0x161582c`) first uses the movement module's stored coordinate when that module exists (`node +0x28`, module coordinate at `+0x34`). Without it, the method reads the node transform's **local position**, floors X and Z (`fcvtms` at `0x1615784` and `0x16157e8`), and constructs `Coord` at `0x1615808`. `Coord.ToVector3` (`0x16be3d8..0x16be3ec`) converts integer X/Z to `(x, 0, z)`.

A node local position `(15.83, 1.03, 62.44)` therefore implies `Coord(15, 62)` only in the no-movement-module branch and for that immediate-parent coordinate frame. It does not give the interaction collider's world position or identify which adjacent standing position/facing passes the raycast.

## Evidence boundary and next trace

The earlier navigation receipt identifies the world interaction switch for type 18 and `AttemptToOpenTrade` (`0x163f96c`), which transitions toward trading state. Static entry code does not establish that a device has reached the kiosk or that an offer-cancellation refresh has occurred.

The smallest remaining reachability trace is to resolve the selected world resource's kiosk `InteractionPoint` collider and parent transforms, then observe the client facing that collider within the recovered one-unit ray distance. Correlate a successful interaction with the trading-state transition and relevant requests. This research changed no emulator, database, PHP endpoint or server state. Asset placement and observed UI acceptance belong to separate evidence.

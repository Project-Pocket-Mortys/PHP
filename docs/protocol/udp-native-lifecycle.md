# Native UDP sender lifecycle

The inspected Android 2.41.0 ARM64 paths preserve the sender sequence across room leave/join and UDP socket close/open. A fresh sender with the same session identifier and sequence zero remains a synthetic edge case: this review did not establish a client path that produces it. This is bounded evidence, not proof that arbitrary scene or controller recreation cannot retain a session identifier.

The binary, method RVAs, evidence hashes, instruction addresses, and confidence limits are recorded in [udp-native-lifecycle.json](udp-native-lifecycle.json). Reproduce the twenty selected method decompilations from the repository root using:

```sh
wsl -d Ubuntu -- bash tools/research/ghidra-udp-lifecycle.sh
```

The runner uses the existing targeted Ghidra importer with `-noanalysis`, verifies the build-specific binary hash, and writes `.research/ghidra-udp-lifecycle.json`. Its selection is bounded to twenty methods; it does not run whole-program analysis. Pseudocode is interpreted alongside existing ARM64 instruction dumps because exception edges can otherwise include unrelated code.

## Sequence writes

`UdpNodeSender` has five declared methods: `SendPosition`, `UpdatePositionHistory`, two debug methods, and its constructor. It declares no `Init`, `Start`, `Stop`, dispose, or sequence-reset method. Its `_seqNum` is a `ushort` at object offset `0x28`.

At RVA `0x17c0684`, `SendPosition` reads the low sequence byte for outbound packet byte sixteen. Instructions `0x17c0750` through `0x17c0768` read the ushort, compare it with 254, select increment or zero, and store it. This implements the ordinary 255-to-zero wrap. The snap branch clears position history at `0x17c05dc` and `0x17c05e0`; it does not reset the sequence.

The constructor at RVA `0x17c0ec4` allocates a two-byte history array, stores it at `0x17c0f04`, and tails to the MonoBehaviour constructor at `0x17c0f18`. It contains no explicit sequence-zero store. A newly allocated sender beginning with zero is an inference from managed default field initialization, not an assignment observed in this constructor.

## Object and socket lifetimes

`NetworkRoomAPI.Awake` creates the UDP channel, sender, and receiver. Its sender AddComponent call at `0x17ad588` is followed by the sender reference store at `0x17ad58c` and channel wiring at `0x17ad59c`. The sender identity is supported by the returned object being stored into the typed `nodeSender` backing field at room offset `0x140`; the call target alone is shared by generic instantiations.

`NetworkController.Awake` creates a session component and a room component during controller initialization. The session creation call is at `0x17bfc1c`; room creation is at `0x17bfc88`. This places the observed sender creation within controller initialization, but does not prove that every possible controller recreation must obtain a new session identifier.

Room setup calls `OpenComs`, which clears the receiver's last-sequence dictionary and opens the existing channel. Clearing that dictionary is receiver bookkeeping; it is not a sender sequence reset. `NetworkRoomAPI.Disconnected` calls `Leave`; leave closes communications and clears room collections. These inspected paths neither replace the sender nor store zero into its sequence.

`UdpChannel.Open` and `Close` recreate or close the socket and read thread. Channel offset `0x28` is its own open/closed state; it must not be confused with sender offset `0x28`. The channel does not reference the sender sequence. Channel `OnDestroy` tails to `Close`. The controller disconnect callback dispatches `INetworkDisconnected` to components, and controller `OnDestroy` removes its event subscriptions.

## Scope and uncertainty

This review establishes behavior only for the selected functions in the recorded binary. It does not establish an exhaustive write-reference graph, all Unity scene transitions, serialized object restoration, reflection, or arbitrary native writes. No client runtime experiment was performed for this artifact. A full process or controller restart can allocate a new sender, but retaining the exact prior session identifier through that recreation has not been demonstrated here.

These findings do not define a backend expiry interval, acceptance window, origin policy, or gameplay contract. A backend change intended specifically to accommodate same-session sender sequence resets needs additional evidence that such a client path occurs.

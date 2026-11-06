# Shared battle stream and native abort boundary

The [dedicated Android follow-up](android-shared-startup.md) now verifies this
startup/ready/end/fresh-login/join path on two diagnostic clients. The bounded
native analysis below remains the static evidence for the control flow.

This bounded Android 2.41.0 ARM64 review supplements the [startup contract](shared-battle-startup-contract.md). It establishes a native session termination and fresh sign-in path. It does not establish playable human battles, reliable SSE delivery, or a battle resume protocol. Server policy recommendations below are replacement-server choices.

## Reproduction

Run `wsl bash tools/research/ghidra-shared-battle-stream.sh` from the repository using default WSL. The wrapper uses REA 6.8.0 artifact inspection, Ghidra 12.1.4 with no whole-program analysis, and the explicit Windows Python executable `C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe` with `-X utf8`. It makes no database, emulator, credential, or server runtime calls.

The pinned ELF SHA-256 is `ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`; metadata is version 31. Generated evidence remains ignored under `.research/`: `rea-shared-battle-stream-6.8.0-artifact.json`, `ghidra-shared-battle-stream.json`, `shared-battle-stream-methods.json`, `shared-battle-stream-arm64.txt`, and `shared-battle-stream-relocations.json`. The manifest includes binary, metadata, mapping and bounded method hashes. REA establishes artifact identity only. Native method bounds use the next actual metadata method entry; the normal paths and bounded ARM64 disassembly constrain decompiler fallthrough.

The wrapper also resolves twelve specific `R_AARCH64_RELATIVE` relocation addends into dumper metadata. Raw pointer slots are zero in the file. This resolution proves the delegate and generic state types referenced by the decompiler's unnamed data pointers, including `NetworkEventSource.OnRetryHandler`, `NetworkSessionAPI.ESEndedHandler`, `StateController.Get<MPUserSignInState>`, `StateController.Set<MPServerMessageState>`, and `StateController.Set<MPWorldState>`.

The completed pass exported 36 bounded methods. Output SHA-256 values are `107aa26b825174b6badad2fe51c28a2d6d9a51246b85dced6ef13e9338591f22` for Ghidra JSON, `1cacba3bc94c02ef0302a817d6aa9ca5a83fd63935b9660deaba82cd4ac92875` for the method manifest, `a0278e50a098161149da2c0220f2925881ad224a4479d79969b0e5ffbd6198ef` for bounded disassembly, and `eedcda8223288f9311aacdb45d7e932e9f3ac2d6a4866f50a6047f5be86be1fd` for relocation evidence. Ghidra presentation hashes may vary across toolchain environments.

## Native findings

| Method | Native RVA | Bounded bytes | Relevant behavior |
| --- | --- | --- | --- |
| `NetworkEventSource.OnRetryHandler` | `0x17b9fb8` | 80 | Returns false. |
| `Best.ServerSentEvents.EventSource.Retry` | `0x1a48450` | 252 | False retry callback calls `SetClosed`; the retry heartbeat path is not entered. |
| `Best.ServerSentEvents.EventSource.OnRequestFinished` | `0x1a4854c` | 1200 | Finished HTTP 200 `text/event-stream` closes; transport failures can enter `Retry`. |
| `NetworkSessionAPI.ESEndedHandler` | `0x17b6b48` | 12 | Stores `SERVER_ENDED` (5) only. |
| `NetworkSessionAPI.ESClosedHandler` | `0x17b6a88` | 192 | Removes handlers, stops coroutines, emits disconnected; substitutes `ES_CLOSED` (7) if reason was NONE. |
| `App.NetSessionDisconnectedHandler` | `0x1482190` | 692 | In multiplayer, routes ordinary disconnect reasons through server-message state to sign-in state. |
| `MPUserSignInState.Activate` | `0x1608e84` | 376 | SERVER_ENDED (5) and NONE (0) set `_autoConnect`; resets stored disconnect reason. |
| `MPUserSignInState.TransitionInComplete` | `0x1609754` | 132 | `_autoConnect` invokes sign-in handler. |
| `MPUserSignInState.UISignInBtnHandler` | `0x16097d8` | 296 | Calls fresh `NetworkSessionAPI.Connect` with account/consent identity. |
| `MPUserSignInState.<UISignInBtnHandler>b__16_0` | `0x1609f30` | 476 | Successful connection proceeds to `JoinRoom`. |
| `MPUserSignInState.<JoinRoom>b__15_0` | `0x1609d38` | 504 | Successful room join creates `MPWorldInfo`, marks multiplayer, and sets `MPWorldState`. |

### Same-source reconnection

The Best SSE library contains a generic retry mechanism, a reconnection time, and `Last-Event-ID` support. Those fields alone do not prove this game's behavior. `NetworkEventSource.Open` creates a Best EventSource, calls `AddEvents`, and opens it. `AddEvents` installs the game's `OnRetryHandler`. That callback returns false unconditionally. Best `CallOnRetry` returns the callback result; `Retry` closes when it is false. Thus this pinned game's installed wrapper disables automatic retry on the same EventSource. A clean successful HTTP SSE completion closes directly anyway. Source errors also call session `Disconnect(ES_ERROR=6)`.

`NetworkEventSource.OnClosedHandler` removes the source delegates, clears its current source reference when matching, and emits its closed event. Session close broadcasts disconnect. `NetworkController.NetSessionDisconnectedHandler` dispatches `INetworkDisconnected` across its network components; the battle API's `Disconnected` calls `Leave`, clearing battle identity and battle subscriptions as documented in the startup contract. This is a local battle reset, not a forfeit or a server terminal battle result.

### Exact wire termination sequence

`NetworkSessionAPI.AddEventSourceEvents` registers the literal `session:end` to `ESEndedHandler`. That handler only writes reason 5. It does not call `Close`, `Disconnect`, `Leave`, or change UI. The server must end the response as well to trigger session closure. A compatible research sequence is:

```text
event: session:end
data: {}

```

Flush that complete event and then end the HTTP SSE response normally. The nonempty data is necessary: Best `OnMessageReceived` returns before delivering message delegates when `Message.Data` is null or empty. The ended handler does not parse the data, so `{}` suffices. An empty `data:` or event-name-only frame does not establish SERVER_ENDED. `session:end` is a session control event, not a battle cancellation event.

On subsequent close, the session retains reason 5. While App is in multiplayer, its disconnect handler clears the multiplayer flag, records the reason in `MPUserSignInState`, and creates `MPServerMessageInfo` with next state `MPUserSignInState`; it transitions to `MPServerMessageState`. That state's next-state flow uses the supplied sign-in type. Sign-in `Activate` treats SERVER_ENDED specially, sets `_autoConnect`, and `TransitionInComplete` invokes the normal sign-in action. This calls a fresh session `Connect`, and successful connect and room join lead to `MPWorldState`. There is no automatic same-source battle continuation in this path.

Bare successful EOF still closes and resets local battle state, but normally supplies reason 7 and generic sign-in error presentation. It does not set `_autoConnect` in `Activate`; a separate client configuration condition also exists in `TransitionInComplete`, so this review does not promise bare EOF always requires a user click. To intentionally select the recovered fresh-connect path, deliver `session:end` with nonempty data before EOF.

## Replacement-server policy and remaining limits

A research-only, default-off shared start bridge may abort its shared startup transactionally, retire both recipient intents, restore/release the exact original claims, and terminate each involved authenticated session with the sequence above. Do not replay a previously attempted `battle:start` on reconnect: fresh sign-in and world join are the native recovery direction, and repeated intro safety remains unproven. Authenticate stream identity; one durable send-attempt per recipient intent is a server policy to bound duplicate starts, not proof that a native client received or acknowledged an event.

Abort both participants and make terminal server state visible before allowing fresh session connect/world actions. A late ready or pending start intent must not resurrect the cancelled startup. Scope termination to the authenticated session associated with the attempt; avoid ending an unrelated newer session. Existing close/session rotation and room cleanup must preserve the shared membership locking rules.

Native analysis supports a deliberate full session disconnect followed by fresh sign-in. It does not guarantee event receipt before a network failure, immediate UI transition timing, successful reconnect, credentials/backend availability, or playable recovery after any battle intro stage. The server-message/sign-in flow can show intermediate UI. Runtime verification on the pinned client remains necessary before public startup. Do not describe this as seamless world restoration, invent `battle:cancelled`, or fabricate win/loss/reward events. Public acceptance and gameplay remain separately gated.

# OneTrust startup contract and retained-cache limitation

The November 6, 2026 pre-login spinner is consistent with a failed OneTrust
initialization whose result the game's integration does not inspect. The repeated
`get_domainData_Groups` exceptions identify absent in-memory SDK data; they do not
by themselves identify the failed network request, prove corrupt on-disk data, or
establish a consent choice. No recovery or successful subsequent login is claimed
by this static analysis.

This supplements [research-client.md](research-client.md),
[local-transport.md](local-transport.md), and the two retained boot receipts in
[trade-cancellation-startup-blocker.json](trade-cancellation-startup-blocker.json).
It describes the shipped Android 2.41.0 IL2CPP v31 ARM64 library, SHA-256
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`.
The working research runtime is ARM32; ARM64 static findings are cross-build
integration evidence, not a claim that ARM64 runs successfully.

## Initialization and completion gates

| Native method | RVA | Observed behavior |
|---|---|---|
| `OneTrustController.Awake` | `0x148fba8` | Online path inserts false `BannerData` and `PreferenceCenterData` gates, loads platform configuration, calls `StartSDK`, attaches a main-thread continuation, then subscribes to SDK events. |
| `OneTrustController.<Awake>b__14_0` | `0x14946d0` | Starts `CopySDKFiles(config.files)` without inspecting the task, result payload, `hasException`, or exception. |
| `CopyFileFromStreamingToPersistentDirectory.MoveNext` | `0x14959f4` | Copies one bundled resource, sets its permissions, and calls `UpdateSDKs`. |
| `CopySDKFiles.MoveNext` | `0x1495c04` | Copies resources sequentially, then sets `_initialised=true`. |
| `OneTrustController.Initialized` | `0x148fa98` | Requires `_initialised` and every `_dataLoaded` dictionary value to be true. |
| `ConsentState.<ActivateComplete>b__3_0` | `0x16575ac` | Wait predicate reads `OneTrustController.Initialized`. |

`UpdateSDKs` (`0x1493db4`) queues its action on `UnityMainThreadDispatcher`.
The action (`0x1494980`) immediately reads `CMPSDK.domainData_Groups`.
A bounded direct B/BL scan of executable segments found its caller at
`0x1495b74` in the single-resource copy coroutine. Consequently, a fixed number
of exceptions can represent resource-copy completions; seven errors are not
evidence of seven network retries. Matching the count to the configured file
list remains a separate check.

SDK event `cmp_bannerDataAvail` (15) supplies banner and preference-center data;
their write-completion callbacks set the corresponding `_dataLoaded` gates.
The controller also handles event 19 (`cmp_SDKConsentValuesChanged`), vendor
data event 12, and receipt event 10. The inspected switch has no handler for
event 11 (`cmp_unrecoverableError`) or event 13 (`cmp_gotErrorButWillRetry`).
SDK internal logging appends timestamped strings to `sessionLogs`; the inspected
`OTSDK_logger` does not write them to Unity logcat.

After initialization, the consent state calls `ShowBanner(false)`. That reads
the SDK's `shouldShowBanner` and, when required, enters the WebView state with
the local banner URL. When a banner is not required it advances to the next
state. This is downstream of the initialization gate.

## Fetch and cache shape

The game's `Awake` supplies `domainIdentifier`, `storageLocation`, `apiVersion`,
`languageCode`, and its identifier to `StartSDK`. The SDK's ordinary initial
fetch uses `WebClient.DownloadStringTaskAsync` and the default URL
`https://mobile-data.onetrust.io/bannersdk/v2/applicationdata`.
An SDK parameter named `domaindata_url` can override this URL, but the inspected
game initialization does not supply that parameter.

The SDK clears the WebClient header collection before adding:

| Header | Value source |
|---|---|
| `lang` | Language code |
| `Location` | Configured storage location |
| `application` | Configured domain identifier |
| `sdkVersion` | SDK version field, set from `apiVersion` |
| `Content-Type` | `application/json` |
| `cache-control` | `no-cache` |
| `Accept` | `*/*` |

Two-character country/region overrides add `OT_Country_Code` and
`OT_Region_Code`. Profile synchronization headers require additional SDK
parameters absent from the game's inspected call. The ordinary request is a
GET; there is no JSON request body at this call site. Preserve identifiers and
raw response/profile data in ignored evidence rather than documentation.

Successful download parses the complete response as `m_serverData`, updates
groups, processes synchronization rules, constructs banner/preference data,
and writes the SDK data file. The accessor chain is case-sensitive:

```text
m_serverData (JObject)
  culture (JObject)
    DomainData (JObject)
      Groups (JArray)
```

`get_DomainData` (`0x17deec0`) lazily populates field `0x158` from
`m_serverData` (`0x38`). `get_domainData_Groups` (`0x17dfc98`) lazily populates
`0x170` from `DomainData.Groups`. Native instructions explicitly branch to the
null-throw thunk when DomainData or its Groups token is absent. An absent
`m_serverData` also leads to that path. These errors do not distinguish missing
download, failed parsing, absent nested keys, or other initialization failures.

The historical retained SDK JSON has top-level `status`, `info`, `domain`,
`culture`, and `profile`; its `culture` contains `DomainData`, `CommonData`,
`NtfyConfig`, `OTTData`, and `MobileData`. Its DomainData has 48 groups. This is
a historical observed shape, not an invented fallback response or a guarantee
that every later response is compatible.

## Why an existing SDK data file may not recover startup

`CMPSDK`'s static constructor sets the SDK data path to:

```text
Application.persistentDataPath/ONETRUST_SDK/SERVER_DATA/OneTrustOTTData.json
```

It constructs paths and directories without hydrating `m_serverData` from this
file. `loadCache` (`0x17dff18`) loads saved consent keys/preferences and vendor
selection files; its bounded body does not read `OneTrustOTTData.json` or assign
`m_serverData`.

In the inspected initialization state machine (`0x1812700`), reading the SDK
data file occurs in the branch where `allowedToDownload` is false. That predicate
(`0x17e1c98`) is normally true; its false branch requires profile switching and
the multi-profile `downloadDataAfterSwitch` rule. The ordinary initial online
path attempts a download directly. The offline branch checks existing
**in-memory** `m_serverData`; when absent, it returns a payload with
`hasException=true` and `Internet not reachable, and no cache available.`
No version, language, or domain rejection of the disk file was found in these
bounded paths. This is a limited statement about these methods, not proof that
all profile/cache paths have been exhausted.

`StartSDK.MoveNext` checks the initialization payload's `hasException` before
its success processing. The controller continuation ignores that payload and
starts resource copies regardless. An initial fetch failure can therefore leave
the disk JSON intact while copy-completion callbacks access absent in-memory
groups and the banner/preference gates remain false. This mechanism explains
the observed stack without proving the live fetch's failure cause.

## Recovery constraints and next evidence

Preserve account, save, asset, SDK configuration, and consent/profile files.
Do not clear storage, reinstall, restore an old consent receipt, fabricate SDK
success, force `Initialized`, or synthesize group consent values. The inspected
SDK-to-game callback grants an SDK consent only when the category result equals
`1`; unavailable/other values must not be converted to a grant.

The safe operational candidate is to establish working Wi-Fi/DNS and the
existing restricted SDK HTTPS route before a fresh app process initializes,
then observe the native request, parsed-data event, completion gates, and login.
Do not add a configuration-mentioned hostname to the allowlist solely because
it occurs in SDK data. A live failed connection/request must establish any
additional destination requirement. A valid disk JSON file alone does not prove
the current process hydrated it; host GET success alone does not prove a native
SDK request succeeded.

### Built-in offline branch and shared connectivity probe

A follow-up bounded pass confirms that the constructor creates an empty
`_dataLoaded` dictionary. If `Awake`'s connectivity check returns false, it skips
SDK initialization and the two false data gates, sets `_initialised=true`, and
returns. `Initialized` then evaluates `All` over the empty dictionary as true.
`shouldShowBanner` safely returns false when `DomainData` is absent, with the
internal message `shouldShowBanner == false (sdk not loaded)`. Thus this shipped
branch can naturally advance the consent state without manufacturing an SDK
success or consent callback. This is a static path finding; no successful
offline launch is claimed here.

The connectivity predicate is **not** Android radio state or Unity internet
reachability. `AssetBundleState.CheckForInternetConnection` (`0x1655694`) uses a
synchronous `WebClient.OpenRead` of the `clients3.google.com/generate_204`
literal. The research client redirects that literal to
`http://localhost:8087/_research/online`. Disabling Wi-Fi/mobile data while
leaving that local endpoint reachable can therefore still choose the online
SDK path.

The probe is shared. The executable's direct callers are:

| Caller | Call RVA |
|---|---|
| `OneTrustController.Awake` | `0x148fd44` |
| `AssetBundleState.AssetBundleControllerLoadingFinishedHandler` | `0x1654900` |
| `PrivacyState.UITargetedContentPressedHandler` | `0x1679c8c` |

The selected literal-pointer ADRP/LDR cross-reference scan found uses only in
that shared predicate. Its callers use the same method and request construction;
the static evidence supplies no header or user-agent distinction between them.
Permanently failing the research probe could affect asset startup and privacy
UI as well. Any research-only temporal probe experiment must account for these
later callers and must not be described as restoring actual SDK availability.

The offline branch creates no new OneTrust consent decision, but this does not
prove that every optional SDK starts denied. `BrazeController.Awake` calls
`AppboyBinding.EnableSDK()` unconditionally; its inspected consent-change
handler compares the identifier and returns without enabling/disabling the SDK.
`FirebaseController.Awake` starts dependency initialization; its consent-change
handler forwards the matched callback boolean to analytics collection.
`IronSourceController.Awake` clears initialization flags. Keep the existing
external network isolation in place and do not infer optional-SDK privacy state
from merely passing the consent-state gate.

## Evidence and bounded reproduction

Fresh ignored evidence is in `.research/onetrust-native-20261106a`, `...b`, and
`...c`: REA version/inspection receipts, disposable Ghidra driver and run script,
selected pseudocode, metadata-bounded ARM64 disassembly and body hashes.
REA 6.8.0 ran in the default WSL distribution. Artifact inspection evidence ID:
`ev_90a8af00bf09f04e7f28d0f6c50e9e2d50a19317c036566cc4fd2654985424df`.
The three targeted passes selected 22 OneTrust/Consent methods. Their
disassembly exporter also includes an unrelated shared HTTP accessor; it is
not evidence for this contract.

Follow-up offline/probe and optional-SDK initialization evidence is retained in
the unique directories `.research/onetrust-native-20261106d` and `...e` (six
and seven selected methods respectively), including direct-call/literal scans.

The driver derives function ends from the next Il2CppDumper method/address,
labels mapped methods/strings, imports with `-noanalysis`, and permits selected
property accessors. Unlike the standard driver, it must retain accessors to
inspect `Initialized`, `DomainData`, and `domainData_Groups`. It uses the existing
build-specific no-return annotation for null throwing at RVA `0x1354d7c`.
Critical accessor branches, copy-to-update call, and completion gates were
checked against bounded ARM64 instructions; decompiler exception cleanup and
generic collection expansion remain less reliable than those direct branches.

The tracked reproduction wrapper uses the existing `PocketProtocols.java`
driver with the explicit `include-accessors` option and an exact allowlist of
36 methods (the five follow-up passes plus the consent-state coroutine):

```powershell
wsl -- bash tools/research/ghidra-onetrust-recovery.sh
```

The optional first argument names a fresh directory within `.research`; the
default adds a UTC timestamp. Existing directories and paths outside `.research`
are rejected. The wrapper verifies REA 6.8.0, the binary hash above, metadata
SHA-256 `b7f21def19043ce7698f520668611ab75882cc836de3f9bb05ea6964641b4a10`,
and dumper mapping SHA-256
`a3b7736ec67f28448818bf3de5295e405bcede5f1fc27fefdaa5c209d9d15ffb`.
These mapping hashes intentionally reject regenerated/different dumper output
until separately reviewed. It retains the disposable Ghidra project path,
artifact receipt, selected pseudocode, bounded instructions/body hashes, and
direct B/BL callers of the two fixed startup/probe methods. It does not run
whole-program analysis or establish indirect-call coverage.

`onetrust-recovery-bounded.py` exports exactly those 36 selected methods, with no
unrelated HTTP accessor. It preserves decompiler errors in `methods.json` while
still exporting bounded instructions. The retained `updateGroupsArray`
decompilation timed out; its invocation in the initialization path and bounded
instructions are available, but no contract here relies on its missing
pseudocode. Wrapper verification reused the retained five passes and existing
consent coroutine in `.research/onetrust-wrapper-check-20261106`: 36 bounded
methods, four direct calls to the two selected targets, one retained decompiler
timeout. Shell syntax, input guards, overwrite refusal, and whitespace checks
passed; the combined 36-method Ghidra invocation has not been rerun.

The wrapper invokes Windows Python explicitly as
`C:/Users/iantr/AppData/Local/Python/pythoncore-3.14-64/python.exe -X utf8`
and uses the existing `.research/python` Capstone dependency.
No PHP, client binary, device, database, account, or consent state was modified
for this static investigation.

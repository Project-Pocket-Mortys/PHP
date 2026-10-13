# Pocket Mortys protocol research handoff

This workspace reconciles Android 2.41.0 against the existing PHP server. The root README's completed features remain the baseline. The inventory distinguishes existing implementation from client compatibility; it does not certify that every route works.

## Current evidence

- [Supplied asset copies](asset-copies.md): all 155 version 1011 bundles match the repository; the saved manifest differs only by asset origin.

- Archive and extracted input hashes, Unity version and repository baseline: [artifacts.json](artifacts.json).
- REA/JADX package inspection: [android-package.json](android-package.json). Package version 2.41.0, code 602; min SDK 28, target SDK 36. Signature verification was not performed.
- Cpp2IL parsed metadata header 31 as its internal variant **31.1**, recovered 85,926 method mappings, and found registration addresses `0x2e15e68` and `0x2ee8b28`. Il2CppDumper independently found the same addresses. Its generic protection warning did not prevent successful output; it is not proof of protection.
- [coverage.md](coverage.md) and [inventory.json](inventory.json) reconcile PHP index routes, client endpoint constants, native request candidates and event names. Static-response size classification is provisional; an empty list can be a valid response.
- [native-transport.json](native-transport.json) links 1,252 disassembled ARM64 transport functions to literal loads, calls and generic metadata. Linear reference tracking produces candidates, not control-flow proofs. Full disassembly stays in `.research/disassembly`.
- [parser-mapping.json](parser-mapping.json) contains 89 request-constructor candidates, 119 response-parser references and entries for all 51 discovered event names. Unresolved associations remain explicit. [client-types.json](client-types.json) records managed field types; these alone do not establish wire optionality or serializer behavior.
- [contracts.json](contracts.json) contains reviewed battle request fields, transport findings and initial SSE/UDP descriptions. [openapi.json](openapi.json) intentionally leaves unverified methods as extension-only path entries instead of inventing operations.
- [assets.json](assets.json) catalogs the existing data bundles and extracted TextAssets. They report Unity **2022.3.62f1**, while the supplied client reports **2022.3.62f2**. This is a provenance difference, not proof of incompatibility. Do not merge SP and MP tables: their schemas differ.
- [static-content.json](static-content.json) records served data files separately. `Status/rat.json` is empty; its client behavior is unresolved. The manifest's colon-delimited bundle path is now rewritten to the existing underscore-delimited directory and checked by a byte-hash regression test.
- [external-services.json](external-services.json) separates known backend hostnames from external/SDK/documentation candidates found in string literals. Presence in the binary does not establish traffic or a startup dependency.

There are no original-server captures in this handoff. Automated HTTP/SSE tests exercise the replacement server. Physical-client startup, redirection, completed-feature smoke tests, native UDP exchange and iOS compatibility remain unverified.

[Validation results](validation-results.json) record 15 passing automated tests and the remaining acceptance gates. This is a research and repair handoff, not a claim of full restoration or complete runtime compatibility.

## Reproduce on Windows and default WSL Ubuntu

Prerequisites: Windows Python (`py`), Docker Desktop with Linux containers, default WSL Ubuntu with Python 3/curl/tar, and the supplied APKM in the repository root. Research tools stay under `.research` or the WSL user's `.local/share/pocket-research`; no global Codex configuration is needed for REA CLI use.

From PowerShell in the repository root:

```powershell
py tools/research/extract.py com.turner.pocketmorties_2.41.0.apkm
./tools/research/cpp2il.ps1
./tools/research/dumper.ps1
py -m pip install --target .research/python UnityPy==1.25.0 capstone==5.0.7
wsl -d Ubuntu -- bash tools/research/bootstrap.sh
wsl -d Ubuntu -- python3 tools/research/verify_tools.py
py tools/research/native_refs.py
py tools/research/inventory.py
py tools/research/contracts.py
py tools/research/assets.py
```

The verifier expects the downloaded Node and Ghidra archives in the WSL tool directory. Compare hashes before executing downloaded binaries; `toolchain.lock.json` records the inspected artifacts. REA is pinned to npm 6.4.0; tool downloads come from the upstream projects. Generated research data is not runnable server code.

```powershell
wsl -d Ubuntu -- bash tools/research/rea.sh doctor --provider ghidra --format json
wsl -d Ubuntu -- bash tools/research/rea.sh analyze /bin/true --provider ghidra --format json
wsl -d Ubuntu -- bash tools/research/rea.sh inspect-android-package .research/android/base.apk --format json
wsl -d Ubuntu -- bash tools/research/rea.sh analyze .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --provider ghidra --snapshot /tmp/pocket-il2cpp-rea.json --format json
```

Use the snapshot for subsequent `rea decompile` calls. Confirm Ghidra's image base before translating the RVAs in `native-methods.json`. Preserve raw REA evidence locally; checked-in findings should retain its evidence ID and artifact hash.

The full REA/Ghidra automatic pass was cancelled after prolonged function-boundary repair; it did not complete a whole-binary inventory. The bounded fallback is `wsl -d Ubuntu -- bash tools/research/ghidra-targeted.sh`. It imports a disposable project, labels IL2CPP methods, and decompiles nine selected transport methods without whole-program analysis. Ghidra rebases this ELF at `0x100000`; the script records both that image base and the original RVA. It annotates external tail branches and a non-returning null-throw thunk to prevent decompilation flowing into adjacent methods. These annotations are build-specific and the runner checks the binary hash. Review pseudocode against the independent ARM64 disassembly, especially when types or control flow are uncertain. [native-analysis.json](native-analysis.json) records the results and limitations; `py tools/research/summarize.py` regenerates it from saved REA and Ghidra output.

## Isolated server and regression tests

```powershell
docker compose -f compose.research.yaml up -d --build
py -m unittest discover -s tests/protocol -v
docker compose -f compose.research.yaml logs web
docker compose -f compose.research.yaml down
```

The server binds only `127.0.0.1:8087`. The test suite reseeds the dedicated Compose database; never point it at a shared server. Its named database volume survives `down`. Credentials are synthetic and restricted to this local stack. `PM_DB_HOST`, `PM_DB_NAME`, `PM_DB_USER`, and `PM_DB_PASS` configure the shared PHP connection. Existing manually configured fallback strings can still be used outside Compose.

Repairs preserve routes and success envelopes: readiness uses the actual battle ID; ready/move reject another initiator and inactive/missing battles; attacks reject another player's or inactive Morty; capture emits one JSON acknowledgement; SSE deck payloads use the active owned deck; shared bootstrap logs PHP errors without printing them into responses. No schema migration is needed. Error HTTP statuses are tested replacement-server behavior, not a claim of original-server parity.

## Runtime capture and remaining validation

An Android phone is not required. See [Windows emulator setup](emulator.md) for
the dedicated research device and reproducible installation commands.
The [local research client](research-client.md) documents startup patches,
confirmed loopback requests, and the remaining consent/WebView gate.

Use a separate test installation/account. Record its installed version, split APK hashes, redirection method, device/ADB identity and server commit before comparing captures. The original APK contains hostname/certificate validation in `NetworkHTTP`; a working modified client may behave differently.

For HTTP JSON capture, install mitmproxy in a separate environment and run:

```text
mitmdump -s tools/research/capture.py --set pocket_capture=.research/captures/http.jsonl
```

The addon redacts known credential fields and omits non-JSON bodies; inspect captures before sharing because arbitrary text can still contain personal data. SSE is streamed without buffering and requires a separate event capture. Proxy setup and TLS trust must match the working client. No requests to original service hosts or real purchases are needed.

For each manual scenario in [validation.md](validation.md), record request/response, SSE order, database before/after, and whether reconnect/retry duplicates a mutation. Store raw material under `.research/captures`; only reviewed sanitized fixtures belong in tests. Resolve the evidence gaps in [backlog.md](backlog.md) before describing the milestone as complete.

Tool references: [REA](https://github.com/morluto/rea), [Cpp2IL](https://github.com/SamboyCoding/Cpp2IL), [Il2CppDumper](https://github.com/Perfare/Il2CppDumper), [UnityPy](https://github.com/K0lb3/UnityPy).

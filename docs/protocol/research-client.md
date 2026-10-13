# Local Android startup research client

The author-authorized research copy of Android 2.41.0 now initializes Unity,
renders correctly, and sends `/time` requests to the isolated PHP server.
It has **not** reached the main menu or a validated multiplayer session.

## Reproduce

Start Docker Compose and the [dedicated emulator](emulator.md), then run from
the repository root. The default WSL distribution supplies Java and signing.

```powershell
docker compose -f compose.research.yaml up -d --build
./tools/research/emulator.ps1
py tools/research/research_client.py --local-server
wsl -- bash tools/research/sign-client.sh
py tools/research/install_research_client.py --sdk-network
```

On the first replacement of the original-signed test installation, add
`--replace-original` to the installer. That option removes this test app and its
data because the research signature differs. Subsequent installs preserve saves.
The installer rejects any AVD name other than `PocketMortys_API30`.

Wait until Wi-Fi reports connected, then launch:

```powershell
$adb = "$PWD/.research/emulator/sdk/platform-tools/adb.exe"
& $adb -P 5038 -s emulator-5556 shell cmd wifi status
& $adb -P 5038 -s emulator-5556 shell monkey -p com.turner.pocketmorties 1
```

The setup keeps downloaded tools, signed APKs, logs and the device outside tracked
source, under `.research`. The original APKM/APKs remain unchanged. The signer is
uber-apk-signer 1.3.0, pinned by SHA-256 in `sign-client.sh`; its embedded debug key
is used only for this local test build. The script verifies alignment/signatures.

## Reviewed changes

`research_client.py` rejects every base APK except SHA-256
`b44f255bdd58b3196d73ff811c3e645d68edcbd76366a39f5c4489bc538ebf74`.

| Change | Evidence and scope |
|---|---|
| Return from `LicenseClient.initializeLicenseCheck()` | Original log opened PairIP `LicenseActivity` and exited. REA/JADX established the entry method; one complete DEX instruction becomes `return-void; nop`. This is a local bootstrap experiment, not a Play license. |
| Null guard in `GoogleIABPlugin.queryInventory(String[])` | Runtime threw on a null billing client. Guard emits the existing `queryInventoryFailed` callback with the existing unavailable-service message. Initialized billing behavior is retained apart from entry logging. No products or purchase success are fabricated. REA/JADX independently decompiled the patched method. |
| Six IL2CPP URL literals | Startup game origin, asset alias/status, consent check, time, and connectivity probe point to loopback. Literal offsets are preserved; lengths and padding are adjusted. Other endpoints may still need research redirection. |
| `PlayerSettings.insecureHttpOption: 0 -> 2` | UnityPy 1.25.0 identified one changed byte at asset offset 209724 in `globalgamemanagers`. This enables local HTTP in UnityWebRequest; the Android manifest already allows cleartext. See [Unity's setting](https://docs.unity3d.com/ja/2022.3/ScriptReference/PlayerSettings-insecureHttpOption.html). |
| Refresh Unity's extracted metadata | Updating an APK with `-r` retained the original metadata under the app's `files/il2cpp` directory. The installer removes only that regenerable runtime cache, allowing Unity to extract it with correct ownership. Direct root `adb push` caused a misleading storage-space error through SELinux denial and is not used. |

Native executable method bodies are unchanged. `.research/emulator/research-client/patch.json`
records exact DEX offsets/bytes and original/replacement URLs. Three tests check
the allowed byte ranges, DEX checksums, metadata layout and HTTP setting.

## Local backend and SDK isolation

ADB port 5038 avoids the WSL relay occupying 5037. `adb reverse tcp:8087 tcp:8087`
makes the Compose backend reachable at `http://127.0.0.1:8087` inside Android.

The research Apache configuration adds an empty HTTP 204 connectivity probe at
`/_research/online`, and substitutes the local origin into **manifest responses**
under `/Aliases/<tag>/<platform>/manifest.json`. Source manifests, bundle bytes,
and public PHP routes are unchanged. Tests verify substitution changes only the
origin and that bundle hashes remain correct. This configuration is confined to
the research Docker image.

The installer uses the app UID and a `PMRESEARCH` firewall chain. By default it
permits loopback only and disables radios. `--sdk-network` permits TCP 443 to the
current IPv4 addresses of `cdn.cookielaw.org` and `mobile-data.onetrust.io`, plus
the emulator DNS resolver, and enables Wi-Fi. These are IP restrictions, not TLS
hostname enforcement; CDN addresses may be shared. Rules are transient and must
be reapplied after emulator reboot. No Google account or real purchase is used.

## Observed results and next gate

- Original ARM64 exited with signal 11; its cause remains unresolved. ARM32 is
  the current runtime target. No ARM64 success is claimed.
- Licensing no longer closes the research client. The billing null-reference
  exception is gone and startup advances beyond the former loading stall.
- Host GLES 3.1 renders the splash and game loading/error UI correctly.
- Confirmed game requests reach `/_research/online` and `/time` with HTTP 204/200.
- OneTrust configuration, logos, banner HTML and preference-center data were
  downloaded. They are current third-party responses, not original game-server
  contracts or proof of permission choices.
- Current startup stops at a consent/loading spinner. The Android UI hierarchy
  shows the Unity surface, without a visible consent WebView. Before successful
  SDK fetch, `OneTrust.CMPSDK.get_domainData_Groups` threw null-reference errors.
  The current wait requires WebView/state-transition tracing; its cause is not
  established solely by those earlier errors.
- Manifest and appdata HTTP 200s from automated tests **must not be counted as
  game-driven asset downloads**. No game-driven manifest request, registration,
  title-screen completion or multiplayer session has yet been verified.

Next: trace `ConsentState.<ActivateComplete>d__3`,
`OneTrustController.Initialized`, `ShowBanner`, and the WebView lifecycle, then
capture a client-originated manifest download and reconcile its parser. Preserve
default denied optional SDK consent; do not substitute invented consent success.

Raw evidence is under `.research/emulator`; hashes and selected REA evidence IDs
are in [startup-results.json](startup-results.json). Additional Ghidra outputs
(`ghidra-startup.sh`, `ghidra-assets.sh`) are research candidates: exception paths
can produce misleading pseudocode outside the intended function. Verify native
instructions before promoting those candidates into contracts or patches.

An audit of decompressed APK entries confirms that the native libraries are
unchanged. Re-signing also changes signature metadata and `stamp-cert-sha256`;
these signing changes are included separately from the four patched base payloads.

```powershell
py -m unittest discover -s tests/research -v
py -m unittest discover -s tests/protocol -v
```

Result: 3 research patch tests and 17 isolated backend tests passed. This extends
the earlier handoff; the full runtime acceptance milestone remains incomplete.

# Windows Android test device

The dedicated `PocketMortys_API30` AVD uses Android 11 Google APIs x86_64
revision 16, Android Emulator 37.2.12 and platform-tools 37.0.1. The Google
APIs Android 11 image includes ARM64 translation for the supplied game's ARM
libraries ([Google release notes](https://developer.android.com/studio/releases/emulator#30.0.0)).
Translation support alone does not establish game compatibility.

All downloads, device data, screenshots and logs stay in ignored
`.research/emulator`. Original APKs remain unchanged. No Google account is
required. Windows runs the emulator directly; default WSL Ubuntu remains the
native-analysis environment. WHPX acceleration passed on the setup machine.

From the repository root in PowerShell:

```powershell
py tools/research/emulator_setup.py
./tools/research/emulator.ps1 -InstallGame
```

Downloads are pinned in `tools/research/emulator.lock.json`, with Google's
repository SHA-1 checksums and locally recorded SHA-256 checksums. The installer
verifies both. It installs the base APK and ARM32 split by default. Use
`-Abi arm64-v8a` to reproduce the ARM64 experiment.
The launcher uses software graphics with Vulkan disabled after an initial
automatic-graphics boot failed to expose ADB. `-Headless` suppresses the device
window for automation. The launcher does not reset an existing device.

```powershell
$adb = "$PWD/.research/emulator/sdk/platform-tools/adb.exe"
$env:ANDROID_ADB_SERVER_PORT = '5038'
& $adb -s emulator-5556 devices
& $adb -s emulator-5556 shell getprop ro.product.cpu.abilist
& $adb -s emulator-5556 shell monkey -p com.turner.pocketmorties 1
& $adb -s emulator-5556 logcat -d > .research/emulator/logcat.txt
& $adb -s emulator-5556 emu kill
```

ADB reverse exposes the isolated Compose service on Android at
`http://127.0.0.1:8087`. This makes the backend reachable; it does **not** rewrite
the game's original URLs or bypass its TLS checks. Game redirection and runtime
protocol validation are separate follow-up work. Avoid signing into personal
accounts or making purchases on this research device.

The dedicated ADB server listens on port 5038 because port 5037 was occupied by
a WSL relay on the setup machine. Pass `-P 5038` when invoking ADB outside the
launcher environment. The Android device serial is `emulator-5556`.

## First runtime results

Machine-readable results and raw-log hashes: [emulator-results.json](emulator-results.json).

- Android boots and ADB connects. Advertised ABIs include both ARM variants.
- The supplied base and splits install as version 2.41.0, versionCode 602.
- A request from the Android shell through ADB reverse returns HTTP 200 for
  `/Aliases/rat/Android/manifest.json` on the isolated PHP backend.
- ARM64 launch exited with signal 11 before confirmed Unity initialization.
  The cause is unresolved; ARM translation is a candidate, not an established cause.
- ARM32 launch logged Unity 2022.3.62f2 IL2CPP initialization. PairIP reported
  `Local install check failed due to wrong installer` and a licensing-service
  error, opened `LicenseActivity`, then the process sent itself SIGKILL.
- Launches were offline (emulator Wi-Fi and mobile data disabled). No personal
  Google account or original-server response was used. This does not establish
  that offline mode is the only cause of the licensing failure.

Raw logs: `.research/emulator/game-launch.log` (ARM64) and
`.research/emulator/game-launch-arm32.log`. A functioning game session remains
unverified. Next isolate the licensing/bootstrap dependency using the authorized
research build, then resolve game URL/TLS redirection and complete startup tests.

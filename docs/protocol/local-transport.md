# Local transport and successful asset loading

On October 12, 2026, the Android 2.41.0 ARM32 research client requested the local
manifest, downloaded all 155 bundles with HTTP 200, and reached the opening
single-player Rick-and-Morty scene. Multiplayer is not yet validated.

The missing files hypothesis was ruled out for the isolated environment: the
supplied copies match the repository. Two local setup problems prevented loading:

1. `NetworkHTTP.Request` validates requests before sending them. Its constructor
   enables HTTPS-only and hostname validation, with `*.bps-pmnet.com` allowed.
   URL validation also rejects `127.0.0.1`, while explicitly exempting `localhost`
   from that pattern rejection. The earlier HTTP loopback redirects failed these
   checks before Apache could see a manifest request.
2. With the corrected profile, syscall tracing showed port 8087 connections to
   `10.0.2.15` and `10.0.2.16`, the emulator's own addresses, which the research
   firewall rejected. Allowing only TCP 8087 to addresses reported by `ip addr`
   made the existing ADB reverse listener reachable. Other external destinations
   remain subject to the existing SDK restrictions.

## Reproduce

Use the setup in [research-client.md](research-client.md), with:

```powershell
py tools/research/research_client.py --local-transport
wsl -- bash tools/research/sign-client.sh
docker compose -f compose.research.yaml up -d --build
py tools/research/install_research_client.py --sdk-network
```

Wait for Wi-Fi connectivity, then launch using the documented ADB command. The
dedicated test installation now retains its downloaded asset cache and save.
First launch shows a terms/privacy acknowledgement before the opening scene.

## Exact patch scope

The profile changes the six URL literals to `http://localhost:8087` and replaces
the hostname allowlist literal with exact `localhost`. Hostname validation stays
enabled. Certificate checks are unchanged; this local first-party route uses HTTP.
The research Apache manifest substitution uses the same origin.

The ARM32 `NetworkHTTP` constructor begins at RVA/file offset `0xee9ec4`.
At `0xeea0cc`, `movw r1,#0x101` becomes `movw r1,#0x100`:
`011100e3` -> `001100e3`. The following `strh r1,[r4,#0x28]` writes the two
Boolean fields: HTTPS-only becomes false, hostname validation remains true.
Only one byte of the library changes. SHA-256 guards reject other input builds.
The ARM64 library remains unchanged and is not a supported runtime for this profile.

Il2CppDumper's ARM32 mapping and Capstone ARM disassembly established the patch
location; ARM64 Ghidra output independently describes the validation logic.
Reproduce that candidate analysis with `wsl -- bash tools/research/ghidra-security.sh`.
The original ARM32 library SHA-256 is
`d51c2884f6a3045febfa1434ffdc83e4775ebaa8790fe4153fa1a1660b3742e7`.

Reproduce the ARM32 mapping with the pinned secondary exporter:

```powershell
New-Item -ItemType Directory -Force .research/dumper-arm32 | Out-Null
& .research/tools/dumper/Il2CppDumper.exe .research/android/split_config.armeabi_v7a/lib/armeabi-v7a/libil2cpp.so .research/android/base/assets/bin/Data/Managed/Metadata/global-metadata.dat .research/dumper-arm32
```

For a bounded transport trace on the running dedicated emulator:

```powershell
$adb = "$PWD/.research/emulator/sdk/platform-tools/adb.exe"
& $adb -P 5038 -s emulator-5556 root
& $adb -P 5038 -s emulator-5556 shell 'timeout 40 strace -f -p $(pidof com.turner.pocketmorties) -s 160 -e trace=network -o /data/local/tmp/transport-strace.log'
& $adb -P 5038 -s emulator-5556 pull /data/local/tmp/transport-strace.log .research/emulator/transport-strace.log
```

Trigger retry in the emulator while the trace runs. This system strace warns that
some 32-bit structures are not fully decoded; the IPv4 connect destinations above
are decoded. Keep raw traces ignored because they can contain identifiers.

## Evidence and checks

[local-transport-results.json](local-transport-results.json) records client-originated
paths/statuses, patch details, and artifact hashes. Raw logs, syscall traces and
screenshots remain ignored under `.research/emulator`. The capture interval
excludes test requests by Apache request-start time, including earlier SSE tests
whose access-log lines were emitted later when their streams closed.

Four patch checks and 17 backend regression tests passed. The opening scene
visually verifies asset loading; it does not establish battle, account or
multiplayer compatibility. These are replacement-server observations, not
original-server captures. Next: exercise onboarding and multiplayer registration
with synthetic accounts and capture their contracts and persistent effects.

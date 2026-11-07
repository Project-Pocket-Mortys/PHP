# REA 6.8.0 in the default WSL installation

On 2026-11-02 the private research installation was upgraded from
`rea-agents@6.4.0` to exactly `rea-agents@6.8.0`, using the official npm package
identified by the [upstream repository](https://github.com/morluto/rea).
No agent registration or global application configuration was changed.

The package requires Node `^22.23.4 || ^24.22.1 || >=26.12.1`. The previous
private Node 24.20.0 was below that range, so the research runtime was updated to
24.22.1. The Linux x64 archive SHA-256 matched the entry downloaded from
[Node's release checksums](https://nodejs.org/dist/v24.22.1/SHASUMS256.txt):
`6c172a9ab6718f7b801fb5a7bd486af2ee5e32758086a04b84fcce2aa77095e6`.
The old runtime/archive were retained. Ghidra, Java and JADX were not upgraded.

`tools/research/toolchain.lock.json` records the new versions and npm integrity.
Bootstrap and the REA wrapper now read the Node/REA versions from that lock.
The verifier checks the versioned Node archive and the installed REA version
and package-lock integrity, alongside the existing research archive checks.
It does not claim to attest every installed/transitive package file.

```powershell
wsl -- bash tools/research/bootstrap.sh
wsl -- python3 tools/research/verify_tools.py
wsl -- bash tools/research/rea.sh --version
wsl -- bash tools/research/rea.sh doctor --provider ghidra --format json --filter-output healthy,scope_checks
```

Bootstrap completed on the supported runtime. Every archive check and REA
version/integrity check passed; version returned `6.8.0`. Scoped doctor reported
healthy Node 24.22.1 and Ghidra 12.1.4 with Java 21.0.12.1. Optional providers
were not installed as part of this update.

The Android ARM64 library was inspected again using the new CLI:

```powershell
wsl -- bash tools/research/rea.sh inspect-artifact .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --format json --detail summary --evidence_output .research/rea-crafting-6.8.0-artifact.json
```

Evidence export never overwrites an existing bundle; choose a fresh output name
when reproducing. The bundle SHA-256 is
`466f07590ce0ceebd3294e4f91c617e74676bacd8409cce27134035b4a268ef2`.
Parent artifact evidence is
`ev_90a8af00bf09f04e7f28d0f6c50e9e2d50a19317c036566cc4fd2654985424df`;
the summary view is
`ev_cd267a868d996009a8eacddeb55941e7966a6db4daefbf531eea774917a37874`.
The authenticated library remains SHA-256
`ff773be7d3718ee307f6342358268748e8fa2487460e7b3857715478cb8e4326`.
This inspection establishes artifact provenance, not recovered executable
method semantics. The earlier crafting method bodies came from the targeted
Ghidra pass described in [crafting-contract.md](crafting-contract.md); the
initial REA 6.4.0 observations there remain labeled historical evidence.

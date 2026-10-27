$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root
New-Item -ItemType Directory -Force .research/tools | Out-Null
$exe = Join-Path $root '.research/tools/Cpp2IL.exe'
if (-not (Test-Path $exe)) {
    Invoke-WebRequest 'https://github.com/SamboyCoding/Cpp2IL/releases/download/2022.1.0-pre-release.21/Cpp2IL-2022.1.0-pre-release.21-Windows.exe' -OutFile $exe
}
$lock = Get-Content tools/research/toolchain.lock.json -Raw | ConvertFrom-Json
if ((Get-FileHash $exe -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.cpp2il.sha256) { throw 'Cpp2IL hash mismatch' }
& $exe --force-binary-path .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so --force-metadata-path .research/android/base/assets/bin/Data/Managed/Metadata/global-metadata.dat --force-unity-version 2022.3.62f2 --output-as diffable-cs --output-to .research/cpp2il
if ($LASTEXITCODE -ne 0) { throw 'Cpp2IL failed' }

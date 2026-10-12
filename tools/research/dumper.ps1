$ErrorActionPreference = 'Stop'
$root = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
Set-Location $root
New-Item -ItemType Directory -Force .research/tools, .research/dumper | Out-Null
if (-not (Test-Path .research/tools/dumper/Il2CppDumper.exe)) {
    Invoke-WebRequest 'https://github.com/Perfare/Il2CppDumper/releases/download/v6.7.46/Il2CppDumper-win-v6.7.46.zip' -OutFile .research/tools/dumper.zip
    Expand-Archive .research/tools/dumper.zip .research/tools/dumper
}
$lock = Get-Content tools/research/toolchain.lock.json -Raw | ConvertFrom-Json
if ((Get-FileHash .research/tools/dumper.zip -Algorithm SHA256).Hash.ToLowerInvariant() -ne $lock.il2cppdumper.sha256) { throw 'Il2CppDumper archive hash mismatch' }
$config = Get-Content .research/tools/dumper/config.json -Raw | ConvertFrom-Json
$config.RequireAnyKey = $false
$config | ConvertTo-Json | Set-Content .research/tools/dumper/config.json
& .research/tools/dumper/Il2CppDumper.exe .research/android/split_config.arm64_v8a/lib/arm64-v8a/libil2cpp.so .research/android/base/assets/bin/Data/Managed/Metadata/global-metadata.dat .research/dumper
if ($LASTEXITCODE -ne 0 -or -not (Test-Path .research/dumper/script.json)) { throw 'Dumper failed' }

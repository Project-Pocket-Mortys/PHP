param([switch]$Headless, [switch]$InstallGame,
    [ValidateSet('armeabi-v7a', 'arm64-v8a')][string]$Abi = 'armeabi-v7a',
    [ValidateSet('host', 'swiftshader')][string]$Gpu = 'host')
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$work = Join-Path $root '.research/emulator'
$env:ANDROID_HOME = Join-Path $work 'sdk'
$env:ANDROID_AVD_HOME = Join-Path $work 'avd'
$env:ANDROID_ADB_SERVER_PORT = '5038'
$adb = Join-Path $env:ANDROID_HOME 'platform-tools/adb.exe'
$emulator = Join-Path $env:ANDROID_HOME 'emulator/emulator.exe'
if (!(Test-Path $emulator)) { throw 'Run py tools/research/emulator_setup.py first.' }
& $adb start-server
$emulatorArgs = @('-avd', 'PocketMortys_API30', '-port', '5556', '-no-snapshot', '-no-boot-anim', '-no-metrics', '-gpu', $Gpu, '-feature', '-Vulkan,GLESDynamicVersion')
if ($Headless) { $emulatorArgs += '-no-window' }
if (!((& $adb devices) -match 'emulator-5556\s+device')) {
    $windowStyle = if ($Headless) { 'Hidden' } else { 'Normal' }
    Start-Process -FilePath $emulator -ArgumentList $emulatorArgs -WindowStyle $windowStyle -RedirectStandardOutput (Join-Path $work 'stdout.log') -RedirectStandardError (Join-Path $work 'stderr.log') | Out-Null
}
$deadline = (Get-Date).AddMinutes(4)
do {
    Start-Sleep -Seconds 2
    $ErrorActionPreference = 'Continue'
    $booted = & $adb -s emulator-5556 shell getprop sys.boot_completed 2>$null
    $ErrorActionPreference = 'Stop'
    if ((Get-Date) -gt $deadline) { throw "Emulator did not boot; inspect $work logs." }
} until ($booted -eq '1')
& $adb -s emulator-5556 reverse tcp:8087 tcp:8087
if ($LASTEXITCODE -ne 0) { throw 'Could not expose the local backend through ADB reverse.' }
if ($InstallGame) {
    $split = if ($Abi -eq 'armeabi-v7a') { 'split_config.armeabi_v7a.apk' } else { 'split_config.arm64_v8a.apk' }
    & $adb -s emulator-5556 install-multiple -r --abi $Abi (Join-Path $root '.research/android/base.apk') (Join-Path $root ".research/android/$split")
    if ($LASTEXITCODE -ne 0) { throw 'Game installation failed.' }
}
Write-Output 'Ready: emulator-5556. Local backend: http://127.0.0.1:8087 (ADB reverse). Game URLs still require redirection.'

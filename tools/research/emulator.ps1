param([switch]$Headless, [switch]$InstallGame,
    [ValidateSet('PocketMortys_API30', 'PocketMortys_API30_Peer')][string]$Avd = 'PocketMortys_API30',
    [ValidateSet(5556, 5558)][int]$Port,
    [ValidateSet('armeabi-v7a', 'arm64-v8a')][string]$Abi = 'armeabi-v7a',
    [ValidateSet('host', 'swiftshader')][string]$Gpu = 'host')
$ErrorActionPreference = 'Stop'
$expectedPort = if ($Avd -eq 'PocketMortys_API30_Peer') { 5558 } else { 5556 }
if ($PSBoundParameters.ContainsKey('Port') -and $Port -ne $expectedPort) {
    throw "AVD $Avd is restricted to emulator port $expectedPort."
}
$Port = $expectedPort
$serial = "emulator-$Port"
$root = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$work = Join-Path $root '.research/emulator'
$env:ANDROID_HOME = Join-Path $work 'sdk'
$env:ANDROID_AVD_HOME = Join-Path $work 'avd'
$env:ANDROID_ADB_SERVER_PORT = '5038'
$adb = Join-Path $env:ANDROID_HOME 'platform-tools/adb.exe'
$emulator = Join-Path $env:ANDROID_HOME 'emulator/emulator.exe'
if (!(Test-Path $emulator)) { throw 'Run py tools/research/emulator_setup.py first.' }
$avdPath = Join-Path $env:ANDROID_AVD_HOME "$Avd.avd"
if (!(Test-Path (Join-Path $avdPath 'config.ini'))) { throw "Run py tools/research/emulator_setup.py --avd $Avd first." }
$locator = Join-Path $env:ANDROID_AVD_HOME "$Avd.ini"
$locatorPath = Get-Content -LiteralPath $locator | Where-Object { $_ -match '^path=' }
if (!$locatorPath -or $locatorPath.Count -gt 1 -or [IO.Path]::GetFullPath($locatorPath.Substring(5)) -ne [IO.Path]::GetFullPath($avdPath)) {
    throw "AVD $Avd must use its dedicated userdata directory $avdPath."
}
if ((Get-Item -LiteralPath $avdPath).Attributes -band [IO.FileAttributes]::ReparsePoint) {
    throw "AVD $Avd must not redirect to another userdata directory."
}
& $adb -P 5038 start-server
if ($LASTEXITCODE -ne 0) { throw 'Could not start the dedicated ADB server.' }
$emulatorArgs = @('-avd', $Avd, '-port', "$Port", '-no-snapshot', '-no-boot-anim', '-no-metrics', '-gpu', $Gpu, '-feature', '-Vulkan,GLESDynamicVersion')
if ($Headless) { $emulatorArgs += '-no-window' }
$deviceList = & $adb -P 5038 devices
if ($LASTEXITCODE -ne 0) { throw 'Could not enumerate the dedicated ADB server devices.' }
$existing = $deviceList | Where-Object { $_ -match "^$serial\s+" }
if ($existing) {
    if ($existing -notmatch "^$serial\s+device\s*$") { throw "$serial is occupied but unavailable; inspect it before launching." }
    $existingName = @(& $adb -P 5038 -s $serial emu avd name)
    if ($LASTEXITCODE -ne 0 -or !$existingName -or $existingName[0].Trim() -ne $Avd) { throw "$serial is not the expected AVD $Avd." }
} else {
    $windowStyle = if ($Headless) { 'Hidden' } else { 'Normal' }
    $logPath = if ($Avd -eq 'PocketMortys_API30') { $work } else { $avdPath }
    Start-Process -FilePath $emulator -ArgumentList $emulatorArgs -WindowStyle $windowStyle -RedirectStandardOutput (Join-Path $logPath 'stdout.log') -RedirectStandardError (Join-Path $logPath 'stderr.log') | Out-Null
}
$deadline = (Get-Date).AddMinutes(4)
do {
    Start-Sleep -Seconds 2
    $ErrorActionPreference = 'Continue'
    $booted = & $adb -P 5038 -s $serial shell getprop sys.boot_completed 2>$null
    $ErrorActionPreference = 'Stop'
    if ((Get-Date) -gt $deadline) { throw "Emulator did not boot; inspect $work logs." }
} until ($booted -eq '1')
$bootedName = @(& $adb -P 5038 -s $serial emu avd name)
if ($LASTEXITCODE -ne 0 -or !$bootedName -or $bootedName[0].Trim() -ne $Avd) { throw "$serial is not the expected AVD $Avd." }
& $adb -P 5038 -s $serial reverse tcp:8087 tcp:8087
if ($LASTEXITCODE -ne 0) { throw 'Could not expose the local backend through ADB reverse.' }
if ($InstallGame) {
    $split = if ($Abi -eq 'armeabi-v7a') { 'split_config.armeabi_v7a.apk' } else { 'split_config.arm64_v8a.apk' }
    & $adb -P 5038 -s $serial install-multiple -r --abi $Abi (Join-Path $root '.research/android/base.apk') (Join-Path $root ".research/android/$split")
    if ($LASTEXITCODE -ne 0) { throw 'Game installation failed.' }
}
Write-Output "Ready: $serial ($Avd). Local backend: http://127.0.0.1:8087 (ADB reverse). Game URLs still require redirection."

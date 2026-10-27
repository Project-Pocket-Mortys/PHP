# Android multiplayer data cache repair

The merged upstream `mpdata.assetbundle` changes the `ItemInfo` TextAsset but
retains manifest cache version 1050. The running Android 2.41.0 client reused its
old cached multiplayer data after receiving manifest 1012. Its decoded TextAssets
matched the pre-merge bundle, not the merged bundle. Single-player data already
had a new cache version and was downloaded successfully.

The Android manifest now uses overall version 1013 and `mpdata` version 1051.
Bundle bytes, URL paths, iOS metadata, and declared CRC values are unchanged by
this repair. Version numbers here are replacement-server release metadata, not
claims about an original official release.

## Evidence

[asset-update-audit.json](asset-update-audit.json) records old/new bundle hashes and
versions against commit `7576d6b`. [asset-cache-results.json](asset-cache-results.json)
records the emulator cache comparison and the successful new bundle download.

Before the repair, the only multiplayer cache key was
`0000000000000000000000001a040000`. After the repair, the client fetched the
1,258,844-byte bundle and created `0000000000000000000000001b040000`. Every decoded
TextAsset in the new cache entry matches the current repository bundle. Unity
recompresses cached containers, so comparisons use decoded TextAsset hashes rather
than assuming identical container bytes. The saved manifest now records 1013/1051.

The diagnostic multiplayer client reached the world scene with zero Unity error
logs after download. This establishes download/cache/startup acceptance; it does
not validate shop charges, purchases, item effects, natural onboarding or UDP.
The upstream ItemInfo changes include item prices and are not original-server
formula evidence. Saves, account records and old cache entries were preserved.

## Reproduce

```powershell
py tools/research/audit_asset_update.py --baseline 7576d6b
py -m unittest discover -s tests/research -v
py -m unittest discover -s tests/protocol -p test_emulator_environment.py -v
```

The cache-invalidation regression failed on the merged 1012 manifest and passes
with 1013. All six research tests and two emulator-environment tests pass.
The audit compares all existing Android bundle hashes and returns nonzero if a
changed payload retains its prior cache version. Use a different baseline commit
when auditing a later release. This does not calculate or verify Unity CRCs.

To repeat runtime verification on the dedicated research installation, restart
the game without clearing its saves, select Multiplayer, and inspect the local
Apache asset requests. Pull the cache for read-only UnityPy inspection:

```powershell
& .research/emulator/sdk/platform-tools/adb.exe -P 5038 -s emulator-5556 pull /sdcard/Android/data/com.turner.pocketmorties/files/UnityCache/Shared/mpdata .research/emulator/mpdata-cache
```

Decode each `__data` file with the pinned UnityPy installation under
`.research/python`, and compare each TextAsset's name and SHA-256 of `m_Script`
with the tracked Android `mpdata.assetbundle`. Raw caches and saves remain ignored.
The existing supplied-copy comparison tool now also accepts the upstream GitHub
URL prefix when locating repository assets; old published comparisons remain
historical version-1011 evidence.

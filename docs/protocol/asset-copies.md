# Supplied asset copies

All 155 bundles under the user's `Pocket Mortys/dat/2.41.0v1011` directory have
identical SHA-256 hashes to the repository payloads and cover every bundle in the
version 1011 Android manifest. No replacement copies are needed.

The `bundles/2.41.0v1011/AssetBundle.dat` save also contains embedded manifest JSON
identical to `Aliases/rat/Android/manifest.json` after changing only the origin
from `https://assets.bps-pmnet.com` to `https://assets.conspiracyrick.com`.
The script extracts JSON without deserializing the surrounding binary save.
These are user-supplied saved artifacts; their capture history is not established.

| Directory | Files | Findings |
|---|---:|---|
| `2.41.0v1011` | 155 | Complete manifest coverage; all payloads match repository |
| `2.39.0v1003` | 154 | No byte-identical matches to current payloads; lacks `psh027.assetbundle` |
| `archive` | 11,523 | Historical copies, approximately 7.15 GB; counted, not content-hashed |
| `bundles` | 105 | Save files; current and previous embedded manifests extracted |

Byte differences do not establish gameplay differences. Historical versions must
remain separate until their serialized content and provenance are compared.
SHA-256 comparison does not verify Unity's manifest CRC calculation.

## Reproduction

```powershell
py tools/research/compare_asset_copies.py 'C:\Users\iantr\OneDrive\Projects\Pocket Mortys\dat'
wsl -- bash tools/research/ghidra-manifest.sh
```

The comparison is read-only for the supplied directory. Results and file hashes
are in [asset-copy-comparison.json](asset-copy-comparison.json). Extracted manifests
and candidate native pseudocode remain in the ignored `.research` directory.

## Runtime diagnosis

The user's subsequent screenshot shows `Error: Outdated Assets`, superseding the
earlier spinner as the latest reported screen. This message alone does not prove
that bundles are missing at the original host. The patched research client is
configured to use loopback asset URLs; no game-originated manifest request has
yet appeared in the isolated Apache access log.

Candidate ARM64 decompilation traces `AssetBundleDefs.GetServerPath` to the alias
URL format string and `NetworkGeneralAPI.GetServerAssetBundleManifest` to a
`NetworkHTTPRequest` with the directory endpoint and `manifest.json` path.
The loading coroutine distinguishes request failure before loading bundles.
These candidates still require independent native-boundary validation and runtime
confirmation; do not use them alone to change wire contracts or version checks.

Next: capture the constructed manifest URI and transport failure, then verify a
client-originated manifest request and bundle download. Current ownership and
service configuration of `bps-pmnet.com` have not been independently verified here
and are not required for the isolated local setup.

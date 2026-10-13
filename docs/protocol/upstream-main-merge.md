# Upstream main integration

Merged `origin/main` at `3a579debace39badeb9e3dd1dfc526cf760a256e`
(also the fetched `TORCommunity/main`) into the restoration branch. The two
previously missing upstream commits are `76d4349` and `3a579de`.

The merge retains upstream GPLv3 licensing and team attribution, the individual
ConspiracyRick credit, the research handoff link, and the completed-feature list.
Upstream executable-mode changes are retained. Existing PHP handler contents do
not change through this merge; the restoration fixes remain in place.

## Asset provenance changes

- Adds 155 iOS bundles and an iOS manifest; an IPA is still unavailable.
- Android manifest version changes from 1011 to 1012, and bundle URLs now use
  the GitHub-hosted Project-Pocket-Mortys/.github asset path.
- Android `spdata` version changes from 1045 to 1046 and its declared CRC changes
  from 56704220 to 56704221. Both `spdata` and `mpdata` binary contents change;
  other existing Android bundle blobs are identical.
- Current Android SHA-256 values:
  - `mpdata`: `f9101d6012defb85545913db6a0f3fa0d1eb06014d604a6f341937a61887b413`
  - `spdata`: `8743a6c221497a99a38be4c8cc4d2a67cb566e63ca3c4beccf49d8b4e067c563`

The earlier asset-copy comparison, gameplay catalog, and emulator startup results
describe the pre-merge version-1011 assets. They are retained as historical evidence,
not regenerated or presented as verification of the changed data. Client CRC/cache
acceptance and gameplay semantics of the upstream replacements remain unverified.

## Integration validation

The isolated Apache configuration now rewrites the upstream GitHub asset prefix to
localhost as well as the older asset origin. Public manifests remain as supplied
upstream. Manifest tests cover both platforms and verify local bundle URLs.

Seven focused tests pass: two emulator environment tests, one Android asset-serving
test, and four additive SSE membership tests. Evidence validation passes. UnityPy
loads all six Android/iOS appdata, mpdata and spdata bundles successfully; this is a
structural check, not an iOS runtime or gameplay compatibility claim. Existing
emulator accounts are preserved; the destructive global seed was not run.

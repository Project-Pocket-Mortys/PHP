# World-2 fixture provenance

Static inspection supports selecting `world_id: "2"` for Plumbubo Prime 51b in
the recovered Android 2.41.0 research client. The exact APK, entry hashes and
object fields are recorded in [the evidence JSON](world2-fixture-evidence.json).
This establishes asset provenance and consistent naming; runtime loading and
original-server behavior require separate evidence.

`MPWorldDefs.kWorld2Id` is `"2"` in `.research/dumper/dump.cs`. The APK's `EN`
TextAsset contains `TextDefs.MP_WORLD_TITLE_2.label = "Plumbubo Prime 51b"`.
Its ResourceManager maps `world/multiplayer/dimensions/mpdimension2` to file
`1280`, object `412`. The external table's zero-based index `1279` resolves to
`09090185f9294494db8fed68cd00257b`; object `412` in that APK entry is the active
GameObject `MPDimension2`. The matching numeric suffixes support the destination
identification; this inspection does not establish the implementation of native
`MPWorldDefs.GetResourceId`.

The recovered `RoomJoinedResponse` and `RoomDetailsResponse` declare no
`zone_id`. The replacement schema requires `room_ids.zone_id` as non-null text,
and `session/join-room/index.php` selects by `world_id`, then returns `zone_id`
unchanged. A minimal additive destination fixture can use a unique room ID,
`world_id = "2"`, the working transport host/port, empty entity collections and
`zone_id = "[1,1]"`. That zone value is an opaque schema fixture copied from the
established world-1 seed, not a recovered world-2 zone or spawn coordinate.

`lib/worlds.json` also defines world 2, with its first player level band `[10,19]`.
Those server level bands do not establish a Unity zone-coordinate format.

## Reproduce without exporting or changing assets

From the repository root in PowerShell, with the existing `.research/python`
UnityPy dependency directory:

```powershell
@'
import hashlib, json, sys, zipfile
sys.path.insert(0, '.research/python')
import UnityPy

apk = '.research/android/base.apk'
print('APK SHA256:', hashlib.file_digest(open(apk, 'rb'), 'sha256').hexdigest())
with zipfile.ZipFile(apk) as z:
    def load(entry):
        raw = z.read('assets/bin/Data/' + entry)
        print(entry, 'SHA256:', hashlib.sha256(raw).hexdigest())
        return UnityPy.load(raw)

    env = load('globalgamemanagers')
    manager = next(o for o in env.objects if o.type.name == 'ResourceManager')
    key = 'world/multiplayer/dimensions/mpdimension2'
    pointer = next(v for k, v in manager.read_typetree()['m_Container'] if k == key)
    external = manager.assets_file.externals[pointer['m_FileID'] - 1].path
    print('Resource:', key, pointer, 'external:', external)
    destination = load(external)
    obj = next(o for o in destination.objects if o.path_id == pointer['m_PathID'])
    tree = obj.read_typetree()
    print('Destination:', obj.path_id, obj.type.name,
          {k: tree[k] for k in ('m_Name', 'm_IsActive')})

    english = load('5eaa370fb472742fd9c0f40448eb1f08')
    text = next(o for o in english.objects if o.type.name == 'TextAsset').read()
    print('TextAsset:', text.m_Name)
    print('Text SHA256:', hashlib.sha256(text.m_Script.encode('utf-8')).hexdigest())
    print('Title:', json.loads(text.m_Script)['TextDefs']['MP_WORLD_TITLE_2'])
'@ | py -

rg -n -A 22 'public class RoomJoinedResponse|public class RoomDetailsResponse' .research/dumper/dump.cs
rg -n 'kWorld2Id' .research/dumper/dump.cs
rg -n -A 8 'CREATE TABLE `room_ids`' pocket_mortys.sql
rg -n 'WHERE world_id|zone_id' session/join-room/index.php
```

`tools/research/assets.py` and `docs/protocol/assets.json` catalog downloaded
data bundles, but do not catalog these individual embedded APK resources. The
commands above read the embedded entries directly. No database changes, tests,
emulator actions or restarts were performed for this static inspection.

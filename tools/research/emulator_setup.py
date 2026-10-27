"""Install pinned Windows emulator tools and a dedicated research AVD locally."""
import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.research' / 'emulator'
SDK = WORK / 'sdk'
AVDS = ('PocketMortys_API30', 'PocketMortys_API30_Peer')


def install(item):
    archive = WORK / item['url'].rsplit('/', 1)[1]
    if not archive.exists():
        print('Downloading ' + item['package'], flush=True)
        temporary = archive.with_suffix('.partial')
        urllib.request.urlretrieve(item['url'], temporary)
        temporary.replace(archive)
    assert archive.stat().st_size == item['size'], archive
    with archive.open('rb') as stream:
        assert hashlib.file_digest(stream, 'sha1').hexdigest() == item['sha1'], archive
    if item.get('sha256'):
        with archive.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == item['sha256'], archive
    target = SDK
    if item['package'].startswith('system-images;'):
        target = SDK / 'system-images' / 'android-30' / 'google_apis'
    marker = WORK / (archive.stem + '.installed')
    if not marker.exists():
        print('Extracting ' + item['package'], flush=True)
        with zipfile.ZipFile(archive) as zipped:
            for member in zipped.infolist():
                if not (target / member.filename).resolve().is_relative_to(target.resolve()):
                    raise ValueError('Unsafe archive path')
            zipped.extractall(target)
        marker.write_text(item['sha1'])
    with archive.open('rb') as stream:
        return dict(item, sha256=hashlib.file_digest(stream, 'sha256').hexdigest())


def provision_avd(name):
    if name not in AVDS:
        raise ValueError('Unsupported research AVD')
    avd = WORK / 'avd' / (name + '.avd')
    if avd.resolve() != avd.absolute():
        raise ValueError('Research AVD directory must not redirect to shared userdata')
    avd.mkdir(parents=True, exist_ok=True)
    locator = avd.parent / (name + '.ini')
    if locator.exists():
        entries = dict(line.split('=', 1) for line in locator.read_text().splitlines() if '=' in line)
        if Path(entries.get('path', '')).resolve() != avd.resolve():
            raise ValueError('Existing AVD locator points outside its dedicated directory')
    else:
        locator.write_text(f'avd.ini.encoding=UTF-8\npath={avd}\ntarget=android-30\n')
    config = avd / 'config.ini'
    if not config.exists():
        display_name = 'Pocket Mortys Research' + (' Peer' if name.endswith('_Peer') else '')
        config.write_text(f'''avd.ini.encoding=UTF-8
AvdId={name}
avd.ini.displayname={display_name}
abi.type=x86_64
hw.cpu.arch=x86_64
hw.cpu.ncore=4
hw.ramSize=4096
hw.lcd.width=720
hw.lcd.height=1280
hw.lcd.density=320
hw.gpu.enabled=yes
hw.gpu.mode=auto
hw.keyboard=yes
hw.audioInput=no
hw.camera.back=none
hw.camera.front=none
disk.dataPartition.size=6G
image.sysdir.1=system-images/android-30/google_apis/x86_64/
tag.id=google_apis
tag.display=Google APIs
PlayStore.enabled=false
showDeviceFrame=no
fastboot.forceColdBoot=yes
''')
    return avd


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avd', choices=AVDS, default=AVDS[0],
                        help='Dedicated AVD to create; existing device data is retained')
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    packages = json.loads((ROOT / 'tools/research/emulator.lock.json').read_text())
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        records = list(pool.map(install, packages))
    (WORK / 'installed.json').write_text(json.dumps(records, indent=2) + '\n')
    provision_avd(args.avd)
    print(f'Installed. Start with tools/research/emulator.ps1 -Avd {args.avd}')

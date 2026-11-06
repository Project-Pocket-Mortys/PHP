"""Route one retained diagnostic client through a fresh offline-SDK fixture.

Never reinstalls, clears app data, edits consent, or resets a used probe counter.
Launch/capture the client separately after this preparation.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request

from startup_capture_device import Device, ROOT, PACKAGE, DEVICES


def prepare(role, output):
    private = (ROOT / '.research').resolve()
    output = output.absolute()
    if output.resolve() != output or not output.is_relative_to(private) or output == private:
        raise ValueError('Fresh unredirected output under .research required')
    if output.exists():
        raise ValueError('Output already exists; preserve earlier evidence')
    command = ['docker', 'compose', '-f', str(ROOT / 'compose.research.yaml'),
               'exec', '-T', 'offline-sdk-web', 'test', '!', '-e',
               '/tmp/pocket-research-offline-sdk-once.json']
    if subprocess.run(command, cwd=ROOT, capture_output=True).returncode:
        raise RuntimeError('Fresh offline-sdk-web required; used/unavailable service was not reset')
    with urllib.request.urlopen('http://localhost:8091/time', timeout=10) as reply:
        if reply.status != 200:
            raise RuntimeError('Dedicated local backend is not healthy')
    device = Device(role)
    device.verify()
    if not device.adb('shell', 'pm', 'path', PACKAGE).stdout.startswith(b'package:'):
        raise ValueError('Retained installed diagnostic package required; no installation performed')
    device.install()  # Already installed: verify both signed APK hashes only.
    device.adb('shell', 'am', 'force-stop', PACKAGE)
    device.network(False)  # No external SDK destinations; no consent is granted.
    for port in ('8087', '8089'):
        device.adb('reverse', 'tcp:' + port, 'tcp:8091')
    output.mkdir(parents=True, exist_ok=False)
    for name, args in {'ipv4': ('shell', 'iptables', '-S'),
                       'ipv6': ('shell', 'ip6tables', '-S'),
                       'wifi': ('shell', 'cmd', 'wifi', 'status')}.items():
        (output / (name + '-private.txt')).write_bytes(device.adb(*args).stdout)
    record = dict(role=role, avd=device.name, serial=device.serial,
                  routing='device 8087/8089 -> host 8091; emulator-facing origin localhost:8087',
                  mode='One first probe 503, then 204; external traffic denied',
                  package_reinstalled=False, app_data_cleared=False, consent_edited=False,
                  probe_state_reset=False,
                  handler_sha256=hashlib.sha256((ROOT / 'tools/research/server/online.php').read_bytes()).hexdigest())
    (output / 'preparation.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Retained diagnostic identity verified; offline SDK fixture prepared. Capture before launching.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=DEVICES, default='primary')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.role, args.output)

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


def prepare(role, output, instance='primary'):
    if instance not in ('primary', 'peer'):
        raise ValueError('Unknown offline SDK instance')
    if instance == 'peer' and role != 'trade-peer':
        raise ValueError('Peer offline SDK instance is reserved for trade-peer')
    service = 'offline-sdk-peer' if instance == 'peer' else 'offline-sdk-web'
    host_port = 8093 if instance == 'peer' else 8091
    private = (ROOT / '.research').resolve()
    output = output.absolute()
    if output.resolve() != output or not output.is_relative_to(private) or output == private:
        raise ValueError('Fresh unredirected output under .research required')
    if output.exists():
        raise ValueError('Output already exists; preserve earlier evidence')
    command = ['docker', 'compose', '-f', str(ROOT / 'compose.research.yaml')]
    if instance == 'peer':
        command.extend(['-f', str(ROOT / 'compose.research-trade-pair.yaml')])
    command.extend(['exec', '-T', service, 'test', '!', '-e',
                    '/tmp/pocket-research-offline-sdk-once.json'])
    if subprocess.run(command, cwd=ROOT, capture_output=True).returncode:
        raise RuntimeError(f'Fresh {service} required; used/unavailable service was not reset')
    with urllib.request.urlopen(f'http://localhost:{host_port}/time', timeout=10) as reply:
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
        device.adb('reverse', 'tcp:' + port, f'tcp:{host_port}')
    output.mkdir(parents=True, exist_ok=False)
    for name, args in {'ipv4': ('shell', 'iptables', '-S'),
                       'ipv6': ('shell', 'ip6tables', '-S'),
                       'wifi': ('shell', 'cmd', 'wifi', 'status')}.items():
        (output / (name + '-private.txt')).write_bytes(device.adb(*args).stdout)
    record = dict(role=role, avd=device.name, serial=device.serial,
                  instance=instance, service=service, host_port=host_port,
                  routing=f'device 8087/8089 -> host {host_port}; emulator-facing origin localhost:8087',
                  mode='One first probe 503, then 204; external traffic denied',
                  package_reinstalled=False, app_data_cleared=False, consent_edited=False,
                  probe_state_reset=False,
                  handler_sha256=hashlib.sha256((ROOT / 'tools/research/server/online.php').read_bytes()).hexdigest())
    (output / 'preparation.json').write_text(json.dumps(record, indent=2) + '\n')
    print('Retained diagnostic identity verified; offline SDK fixture prepared. Capture before launching.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=DEVICES, default='primary')
    parser.add_argument('--instance', choices=('primary', 'peer'), default='primary',
                        help='peer uses independent port 8093 and requires --role trade-peer')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    prepare(args.role, args.output, args.instance)

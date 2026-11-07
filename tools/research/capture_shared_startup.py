"""Bounded private native HTTP/screens capture on verified research AVDs only."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import threading
import time
import uuid

from startup_capture_device import Device, ROOT, SDK, DEVICES


def utc():
    return datetime.now(timezone.utc).isoformat()


def capture(role, duration, output, screens=None):
    if not 30 <= duration <= 900 or screens is not None and not 3 <= screens <= 10:
        raise ValueError('Require duration 30..900 and optional screenshot interval 3..10 seconds')
    output = Path(output).absolute()
    private = (ROOT / '.research').resolve()
    if output.resolve() != output or not output.is_relative_to(private) or output == private:
        raise ValueError('Output must be a fresh, unredirected directory inside .research')
    device = Device(role)
    device.verify()
    if device.adb('shell', 'id', '-u').stdout.strip() != b'0':
        raise ValueError('Fresh capture AVD must already have root adbd')
    device.adb('shell', 'test', '-x', '/system/bin/tcpdump')
    installation = json.loads((device.path / 'startup-install.json').read_text())
    if installation['avd'] != device.name or installation['serial'] != device.serial:
        raise ValueError('Installation metadata identity mismatch')
    output.mkdir(parents=True, exist_ok=False)
    manifest = dict(role=role, avd=device.name, serial=device.serial, duration_seconds=duration,
                    apk={key: installation[key] for key in ('version', 'source_apk_sha256', 'installed_apk_sha256')},
                    screenshots=[], started_utc=utc(), started_monotonic=time.monotonic())
    stop = threading.Event()
    remote = '/data/local/tmp/pm-startup-' + uuid.uuid4().hex + '.pcap'
    manifest['remote_pcap'] = remote
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)

    def run(*args, timeout=10, check=True):
        return subprocess.run([str(SDK / 'platform-tools/adb.exe'), '-P', '5038',
                               '-s', device.serial, *args], capture_output=True,
                              timeout=timeout, check=check, creationflags=flags)

    def screenshots():
        due = 0
        while not stop.is_set():
            delay = manifest['started_monotonic'] + due - time.monotonic()
            if stop.wait(max(0, delay)) or due >= duration:
                break
            sample = dict(elapsed_seconds=time.monotonic() - manifest['started_monotonic'], utc=utc())
            try:
                result = run('exec-out', 'screencap', '-p')
                if not result.stdout.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('Invalid screenshot')
                path = output / f'{role}-{due:03d}.png'
                path.write_bytes(result.stdout)
                sample.update(file=path.name, sha256=hashlib.sha256(result.stdout).hexdigest())
            except Exception as error:
                sample['error_type'] = type(error).__name__
            manifest['screenshots'].append(sample)
            due += screens

    worker = None
    failure = None
    try:
        if screens:
            worker = threading.Thread(target=screenshots, daemon=True)
            worker.start()
        try:
            result = run('shell', 'timeout', '-s', 'INT', str(duration), '/system/bin/tcpdump',
                         '-i', 'any', '-nn', '-s', '0', '-U', '-w', remote,
                         'tcp', 'port', '8087', 'or', 'tcp', 'port', '8089',
                         timeout=duration + 10, check=False)
            (output / 'tcpdump-stdout-private.txt').write_bytes(result.stdout)
            (output / 'tcpdump-stderr-private.txt').write_bytes(result.stderr)
            manifest['tcpdump_exit_code'] = result.returncode
            if result.returncode not in (0, 124, 130):
                failure = 'Unexpected tcpdump exit; inspect private status files'
        except subprocess.TimeoutExpired as error:
            (output / 'tcpdump-stdout-private.txt').write_bytes(error.stdout or b'')
            (output / 'tcpdump-stderr-private.txt').write_bytes(error.stderr or b'')
            failure = 'ADB capture exceeded bounded timeout; remote timeout remains authoritative'
        finally:
            manifest.update(capture_ended_utc=utc(), capture_ended_monotonic=time.monotonic())
            stop.set()
            if worker:
                worker.join(timeout=12)
        result = run('pull', remote, str(output / f'{role}-http.pcap'), timeout=20, check=False)
        (output / 'pull-status-private.txt').write_bytes(result.stdout + result.stderr)
        manifest['pull_exit_code'] = result.returncode
        log = run('logcat', '-d', '-v', 'epoch', '-t', '5000', timeout=20, check=False)
        (output / 'logcat-private.txt').write_bytes(log.stdout)
        (output / 'logcat-stderr-private.txt').write_bytes(log.stderr)
        manifest['logcat_exit_code'] = log.returncode
        pcap = output / f'{role}-http.pcap'
        if pcap.is_file():
            manifest['pcap_sha256'] = hashlib.sha256(pcap.read_bytes()).hexdigest()
            manifest['pcap_size_bytes'] = pcap.stat().st_size
        if result.returncode or not pcap.is_file():
            failure = failure or 'PCAP pull failed; inspect private status files'
    except Exception as error:
        failure = 'Capture failed: ' + type(error).__name__
    finally:
        stop.set()
        if worker:
            worker.join(timeout=12)
        manifest.update(finished_utc=utc(), finished_monotonic=time.monotonic(), failure=failure)
        (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    if failure:
        raise RuntimeError(failure)
    print(f'Private {role} capture saved: {output / "manifest.json"}', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--role', choices=DEVICES, required=True)
    parser.add_argument('--duration', type=int, default=60)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--screens', type=int, help='Screenshot interval, 3..10 seconds')
    args = parser.parse_args()
    capture(args.role, args.duration, args.output, args.screens)

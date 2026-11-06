"""Prepare isolated startup-capture AVDs; never reuse original research userdata."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / '.research/emulator'
SDK = WORK / 'sdk'
AVDS = WORK / 'avd'
DEVICES = {'primary': ('PocketMortys_API30_Startup', 5560),
           'peer': ('PocketMortys_API30_Startup_Peer', 5562)}
PACKAGE = 'com.turner.pocketmorties'


def dedicated_path(name):
    if name not in {value[0] for value in DEVICES.values()}:
        raise ValueError('Only fresh startup-capture AVD names are allowed')
    path = AVDS / (name + '.avd')
    for candidate in (AVDS, path, AVDS / (name + '.ini')):
        if candidate.is_symlink() or candidate.is_junction():
            raise ValueError('Redirected AVD paths are forbidden')
        if candidate.resolve() != candidate.absolute():
            raise ValueError('AVD path must resolve exactly to its dedicated location')
    return path


def entries(path):
    return dict(line.split('=', 1) for line in path.read_text().splitlines() if '=' in line)


def validate_config(path, name):
    config = path / 'config.ini'
    if config.is_symlink() or config.is_junction():
        raise ValueError('Redirected configuration is forbidden')
    values = entries(config)
    if values.get('AvdId') != name:
        raise ValueError('Unexpected AVD identity')
    for key in values:
        if ('path' in key.lower() or key.startswith('disk.') and 'init' in key.lower()):
            raise ValueError('Explicit disk/data paths are forbidden')
    if values.get('image.sysdir.1') != 'system-images/android-30/google_apis/x86_64/':
        raise ValueError('Unexpected system image')


class Device:
    def __init__(self, role):
        self.name, self.port = DEVICES[role]
        self.serial = f'emulator-{self.port}'
        self.path = dedicated_path(self.name)

    def adb(self, *args, check=True, timeout=8):
        return subprocess.run([str(SDK / 'platform-tools/adb.exe'), '-P', '5038',
                               '-s', self.serial, *args], capture_output=True,
                              check=check, timeout=timeout)

    def verify(self):
        locator = AVDS / (self.name + '.ini')
        if Path(entries(locator).get('path', '')).absolute() != self.path.absolute():
            raise ValueError('Locator must point exactly at dedicated userdata')
        validate_config(self.path, self.name)
        result = self.adb('emu', 'avd', 'name').stdout.decode().splitlines()
        if not result or result[0].strip() != self.name:
            raise ValueError('Serial is occupied by an unexpected AVD')

    def provision(self):
        if not (SDK / 'emulator/emulator.exe').is_file():
            raise ValueError('Pinned SDK must already be installed')
        locator = AVDS / (self.name + '.ini')
        if self.path.exists() or locator.exists():
            if not self.path.is_dir() or not locator.is_file():
                raise ValueError('Incomplete existing AVD; refusing to overwrite')
            if Path(entries(locator).get('path', '')).absolute() != self.path.absolute():
                raise ValueError('Existing locator redirects userdata')
            validate_config(self.path, self.name)
            return
        baseline = AVDS / 'PocketMortys_API30.avd/config.ini'
        text = baseline.read_text()
        text = re.sub(r'^AvdId=.*$', 'AvdId=' + self.name, text, flags=re.M)
        text = re.sub(r'^avd.ini.displayname=.*$', 'avd.ini.displayname=' + self.name, text, flags=re.M)
        self.path.mkdir()
        (self.path / 'config.ini').write_text(text)
        validate_config(self.path, self.name)
        locator.write_text(f'avd.ini.encoding=UTF-8\npath={self.path}\ntarget=android-30\n')

    def launch(self):
        self.provision()
        devices = self.adb('devices').stdout.decode().splitlines()
        occupied = [line for line in devices if line.startswith(self.serial + '\t')]
        if occupied:
            if occupied != [self.serial + '\tdevice']:
                raise ValueError('Dedicated serial is occupied but unavailable')
            self.verify()
            return
        env = dict(os.environ, ANDROID_HOME=str(SDK), ANDROID_AVD_HOME=str(AVDS),
                   ANDROID_ADB_SERVER_PORT='5038', ADB_SERVER_PORT='5038')
        with (self.path / 'startup-stdout.log').open('ab') as out, (self.path / 'startup-stderr.log').open('ab') as err:
            subprocess.Popen([str(SDK / 'emulator/emulator.exe'), '-avd', self.name,
                              '-port', str(self.port), '-no-window', '-no-snapshot',
                              '-no-boot-anim', '-no-metrics', '-gpu', 'host',
                              '-feature', '-Vulkan,GLESDynamicVersion'], env=env,
                             stdout=out, stderr=err, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline:
            if self.adb('shell', 'getprop', 'sys.boot_completed', check=False).stdout.strip() == b'1':
                self.verify()
                return
            time.sleep(1)
        print('Launch requested; boot still pending. Run status later.')

    def install(self):
        self.verify()
        signed = WORK / 'research-signed'
        apks = [signed / 'base-aligned-debugSigned.apk', signed / 'split_config.armeabi_v7a-aligned-debugSigned.apk']
        hashes = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in apks}
        installed = self.adb('shell', 'pm', 'path', PACKAGE, check=False).stdout.strip()
        if not installed:
            self.adb('install-multiple', '--abi', 'armeabi-v7a', *map(str, apks), timeout=45)
        paths = self.adb('shell', 'pm', 'path', PACKAGE).stdout.decode().splitlines()
        actual_hashes = {}
        for line in paths:
            if not re.fullmatch(r'package:/data/app/[A-Za-z0-9_./=+~-]+\.apk', line):
                raise ValueError('Unexpected installed APK path; preserving package')
            path = line.removeprefix('package:')
            digest = self.adb('shell', 'sha256sum', path).stdout.decode().split()[0]
            if not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ValueError('Invalid installed APK hash; preserving package')
            actual_hashes[path] = digest
        if len(actual_hashes) != len(hashes) or set(actual_hashes.values()) != set(hashes.values()):
            raise ValueError('Installed APK identity differs from diagnostic inputs; preserving package')
        details = self.adb('shell', 'dumpsys', 'package', PACKAGE).stdout.decode()
        version = re.search(r'versionName=([^\s]+)', details)
        if not version or version[1] != '2.41.0':
            raise ValueError('Expected installed version 2.41.0; preserving package')
        metadata = dict(avd=self.name, serial=self.serial, version=version[1],
                        already_installed=bool(installed), source_apk_sha256=hashes,
                        installed_apk_sha256=actual_hashes)
        (self.path / 'startup-install.json').write_text(json.dumps(metadata, indent=2) + '\n')
        print('Verified version 2.41.0; existing app data preserved.' if installed else 'Installed fresh diagnostic client.')

    def network(self, sdk_network):
        self.verify()
        self.adb('root')
        self.adb('wait-for-device')
        self.verify()
        details = self.adb('shell', 'dumpsys', 'package', PACKAGE).stdout.decode()
        uid = re.search(r'userId=(\d+)', details)
        if not uid:
            raise ValueError('Package must be installed first')
        addresses = re.findall(r'\binet (\d+\.\d+\.\d+\.\d+)/', self.adb('shell', 'ip', '-o', '-4', 'addr', 'show').stdout.decode())
        providers = set()
        if sdk_network:
            for host in ('cdn.cookielaw.org', 'mobile-data.onetrust.io'):
                providers.update(item[4][0] for item in socket.getaddrinfo(host, 443, socket.AF_INET))
        for tool in ('iptables', 'ip6tables'):
            def rule(*args, check=True):
                return self.adb('shell', tool, *args, check=check)
            rule('-N', 'PMSTARTUP', check=False)
            rule('-F', 'PMSTARTUP')
            if tool == 'iptables':
                rule('-A', 'PMSTARTUP', '-d', '127.0.0.0/8', '-j', 'ACCEPT')
                for address in sorted(set(addresses)):
                    for port in ('8087', '8089'):
                        rule('-A', 'PMSTARTUP', '-d', address, '-p', 'tcp', '--dport', port, '-j', 'ACCEPT')
                for address in sorted(providers):
                    rule('-A', 'PMSTARTUP', '-d', address, '-p', 'tcp', '--dport', '443', '-j', 'ACCEPT')
                if sdk_network:
                    rule('-A', 'PMSTARTUP', '-d', '10.0.2.3', '-p', 'udp', '--dport', '53', '-j', 'ACCEPT')
            rule('-A', 'PMSTARTUP', '-j', 'REJECT')
            owner = ['-m', 'owner', '--uid-owner', uid[1], '-j', 'PMSTARTUP']
            if rule('-C', 'OUTPUT', *owner, check=False).returncode:
                rule('-I', 'OUTPUT', '1', *owner)
        for port in ('8087', '8089'):
            self.adb('reverse', 'tcp:' + port, 'tcp:8089')
        self.adb('shell', 'svc', 'data', 'disable')
        self.adb('shell', 'svc', 'wifi', 'enable' if sdk_network else 'disable')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('provision', 'launch', 'install', 'network', 'status'))
    parser.add_argument('--role', choices=DEVICES, default='primary')
    parser.add_argument('--sdk-network', action='store_true')
    args = parser.parse_args()
    device = Device(args.role)
    if args.action == 'network':
        device.network(args.sdk_network)
    elif args.action == 'status':
        device.verify()
        print(f'{device.name}: {device.serial}, dedicated userdata verified')
    else:
        getattr(device, args.action)()

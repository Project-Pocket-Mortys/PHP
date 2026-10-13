"""Install and isolate the research APK on the dedicated AVD; retain game saves."""
import argparse
from pathlib import Path
import re
import socket
import subprocess

ROOT = Path(__file__).resolve().parents[2]
ADB = ROOT/'.research/emulator/sdk/platform-tools/adb.exe'
PACKAGE = 'com.turner.pocketmorties'


def adb(*args, check=True):
    return subprocess.run([str(ADB), '-P', '5038', '-s', 'emulator-5556', *args],
                          capture_output=True, text=True, check=check)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--replace-original', action='store_true',
                        help='Remove the original-signed test installation and its data first')
    parser.add_argument('--sdk-network', action='store_true',
                        help='Allow current OneTrust provider IPv4 addresses to fetch consent configuration')
    args = parser.parse_args()
    if adb('emu', 'avd', 'name').stdout.splitlines()[0] != 'PocketMortys_API30':
        raise RuntimeError('This installer is restricted to the dedicated research AVD')
    signed = ROOT/'.research/emulator/research-signed'
    inputs = [signed/'base-aligned-debugSigned.apk', signed/'split_config.armeabi_v7a-aligned-debugSigned.apk']
    if not all(p.is_file() for p in inputs):
        raise RuntimeError('Build and sign the research APKs first')
    adb('shell', 'am', 'force-stop', PACKAGE)
    if args.replace_original:
        print(adb('uninstall', PACKAGE).stdout)
    print(adb('install-multiple', '-r', '--abi', 'armeabi-v7a', *map(str, inputs)).stdout)
    adb('root')
    adb('wait-for-device')
    uid = re.search(r'userId=(\d+)', adb('shell', 'dumpsys', 'package', PACKAGE).stdout).group(1)
    # These app-owned, extracted runtime files are recreated from the new APK.
    # Removing only this cache avoids both stale metadata and root-owned pushed files.
    cache = '/sdcard/Android/data/' + PACKAGE + '/files/il2cpp'
    adb('shell', 'rm', '-rf', cache)
    allowed = set()
    local_addresses = set(re.findall(r'\binet (\d+\.\d+\.\d+\.\d+)/',
                                    adb('shell', 'ip', '-o', '-4', 'addr', 'show').stdout))
    if args.sdk_network:
        for hostname in ('cdn.cookielaw.org', 'mobile-data.onetrust.io'):
            allowed.update(item[4][0] for item in socket.getaddrinfo(hostname,443,socket.AF_INET))
    for tool in ('iptables', 'ip6tables'):
        chain = 'PMRESEARCH'
        adb('shell', tool, '-N', chain, check=False)
        adb('shell', tool, '-F', chain)
        if tool == 'iptables':
            adb('shell', tool, '-A', chain, '-d','127.0.0.0/8','-j','ACCEPT')
            # Mono can resolve localhost to this emulator's interface addresses.
            # ADB reverse listens on these too; allow only the research backend port.
            for address in sorted(local_addresses):
                adb('shell', tool, '-A', chain, '-d',address,'-p','tcp','--dport','8087','-j','ACCEPT')
            for address in sorted(allowed):
                adb('shell', tool, '-A', chain, '-d',address,'-p','tcp','--dport','443','-j','ACCEPT')
            if args.sdk_network:
                adb('shell', tool, '-A', chain, '-d','10.0.2.3','-p','udp','--dport','53','-j','ACCEPT')
        adb('shell', tool, '-A', chain, '-j', 'REJECT')
        rule = ['-m','owner','--uid-owner',uid,'-j',chain]
        if adb('shell', tool, '-C', 'OUTPUT', *rule, check=False).returncode:
            adb('shell', tool, '-I', 'OUTPUT', '1', *rule)
    adb('reverse', 'tcp:8087', 'tcp:8087')
    # Localhost stays reachable with radios disabled. SDK traffic is additionally
    # blocked for this package if Wi-Fi is enabled later. Rules expire on reboot.
    adb('shell', 'svc', 'wifi', 'enable' if args.sdk_network else 'disable')
    adb('shell', 'svc', 'data', 'disable')
    print('Installed ARM32 research client; runtime cache refreshed; network rules configured.')
    if allowed:
        print('OneTrust IPv4 exceptions:', ', '.join(sorted(allowed)))

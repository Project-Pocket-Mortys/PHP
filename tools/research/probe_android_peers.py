"""Bounded capture of two already-running Android WORLD clients; raw output stays ignored."""
import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
ADB = ROOT / '.research/emulator/sdk/platform-tools/adb.exe'
DEVICES = {'primary': ('emulator-5556', 'PocketMortys_API30'),
           'peer': ('emulator-5558', 'PocketMortys_API30_Peer')}
PACKAGE = 'com.turner.pocketmorties'
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
REMOTE_PCAP = '/data/local/tmp/peer-probe-pcap.pcap'
REMOTE_SYSCALLS = '/data/local/tmp/peer-probe-syscalls.log'


def adb_args(role, *args):
    return [str(ADB), '-P', '5038', '-s', DEVICES[role][0], *args]


def adb(role, *args, binary=False, timeout=15):
    return subprocess.run(adb_args(role, *args), capture_output=True, text=not binary,
                          check=True, timeout=timeout, creationflags=FLAGS).stdout


def socket_identity(role):
    pid = adb(role, 'shell', 'pidof', PACKAGE).strip()
    if not re.fullmatch(r'[1-9][0-9]*', pid):
        raise RuntimeError(f'{role}: expected exactly one running game PID')
    table = adb(role, 'shell', 'cat', f'/proc/{pid}/net/udp')
    inodes = set()
    for line in table.splitlines()[1:]:
        fields = line.split()
        if len(fields) > 9 and fields[2].upper() == '0202000A:13BF':
            if not fields[9].isdigit():
                raise RuntimeError(f'{role}: invalid UDP socket inode')
            inodes.add(fields[9])
    links = adb(role, 'shell', 'ls', '-l', f'/proc/{pid}/fd')
    matches = []
    for line in links.splitlines():
        match = re.search(r'\s(\d+)\s+->\s+socket:\[(\d+)\]\s*$', line)
        if match and match[2] in inodes:
            matches.append({'pid': int(pid), 'fd': int(match[1]), 'inode': int(match[2])})
    if len(matches) != 1:
        raise RuntimeError(f'{role}: expected one owned UDP relay socket, found {len(matches)}')
    return matches[0]


def heartbeat_reader():
    # Importing this test module does not run/reseed tests. Reuse its SQL quoting,
    # with a bounded subprocess adapter so a stalled Docker call cannot hang us.
    spec = importlib.util.spec_from_file_location('peer_probe_test_http', ROOT / 'tests/protocol/test_http.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def php(code):
        return subprocess.run(module.COMPOSE + ['exec', '-T', 'web', 'php', '-r', code],
                              cwd=ROOT, capture_output=True, text=True, check=True,
                              timeout=15, creationflags=FLAGS).stdout

    module.php = php
    query = """SELECT u.username, (u.state='WORLD') AS in_world,
        TIMESTAMPDIFF(SECOND,h.received_at,CURRENT_TIMESTAMP) AS heartbeat_age_seconds,
        COALESCE(h.session_id=u.session_id,0) AS session_matches,
        COALESCE(h.room_id=u.room_id,0) AS room_matches,
        EXISTS(SELECT 1 FROM users v WHERE v.username IN ('PMResearch01','PMResearch02')
            AND v.id<>u.id AND v.room_id=u.room_id) AS same_room
        FROM users u LEFT JOIN research_client_heartbeats h ON h.user_id=u.id
        WHERE u.username IN ('PMResearch01','PMResearch02') ORDER BY u.username"""
    return lambda: module.sql(query)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--duration', type=int, default=170, help='Capture seconds, 165 through 300')
    parser.add_argument('--output-dir', type=Path, default=ROOT / '.research/emulator/peer-probe')
    args = parser.parse_args(argv)
    if not 165 <= args.duration <= 300:
        parser.error('--duration must be between 165 and 300 seconds')
    output = args.output_dir.resolve()
    if not output.is_relative_to((ROOT / '.research').resolve()):
        parser.error('--output-dir must be inside this repository .research directory')
    if output.exists() and any(output.iterdir()):
        parser.error('--output-dir must be empty to preserve existing captures')
    output.mkdir(parents=True, exist_ok=True)
    metadata = {'started_utc': datetime.now(timezone.utc).isoformat(),
                'duration_seconds': args.duration, 'devices': {}, 'events': [],
                'heartbeats': {}, 'artifacts': {}, 'complete': False}
    children, streams, futures = [], [], []
    pool = concurrent.futures.ThreadPoolExecutor(max_workers=2)
    origin = None

    def save_metadata():
        (output / 'metadata.json').write_text(json.dumps(metadata, indent=2) + '\n', encoding='utf-8')

    def elapsed():
        return None if origin is None else round(time.monotonic() - origin, 3)

    def event(label, planned=None):
        entry = {'event': label, 'elapsed_seconds': elapsed()}
        if planned is not None:
            entry['planned_seconds'] = planned
        metadata['events'].append(entry)
        print(json.dumps(entry), flush=True)

    def spawn(role, label, command, binary_output=None):
        stdout = (output / binary_output).open('wb') if binary_output else (output / f'{role}-{label}.stdout.log').open('wb')
        stderr = (output / f'{role}-{label}.stderr.log').open('wb')
        streams.extend((stdout, stderr))
        child = subprocess.Popen(adb_args(role, *command), stdout=stdout, stderr=stderr,
                                 creationflags=FLAGS)
        children.append((role, label, child))

    def sample(label):
        started = elapsed()
        rows = read_heartbeats()
        return label, {'elapsed_seconds': started, 'completed_elapsed_seconds': elapsed(), 'rows': rows}

    try:
        for role, (serial, name) in DEVICES.items():
            names = adb(role, 'emu', 'avd', 'name').splitlines()
            if not names or names[0].strip() != name:
                raise RuntimeError(f'{role}: {serial} must be {name}')
            if adb(role, 'shell', 'id', '-u').strip() != '0':
                raise RuntimeError(f'{role}: ADB shell must already be root; runner does not restart adbd')
            for tool in ('tcpdump', 'strace'):
                adb(role, 'shell', 'test', '-x', '/system/bin/' + tool)
            image = adb(role, 'exec-out', 'screencap', '-p', binary=True)
            if image[:8] != b'\x89PNG\r\n\x1a\n' or len(image) < 24 or struct.unpack('>II', image[16:24]) != (1280, 720):
                raise RuntimeError(f'{role}: expected landscape 1280x720 screenshot')
            (output / f'{role}-initial.png').write_bytes(image)
            metadata['devices'][role] = {'serial': serial, 'avd': name,
                                         'socket_before': socket_identity(role)}
        read_heartbeats = heartbeat_reader()
        label, initial = sample('start')
        metadata['heartbeats'][label] = initial
        rows = initial['rows']
        if {row['username'] for row in rows} != {'PMResearch01', 'PMResearch02'} or not all(
                int(row['in_world']) and int(row['same_room']) and
                int(row['session_matches']) and int(row['room_matches']) and
                row['heartbeat_age_seconds'] is not None and
                0 <= int(row['heartbeat_age_seconds']) <= 60 for row in rows):
            raise RuntimeError('Both research accounts must be WORLD in the same room with current-session/current-room heartbeats aged 0 through 60 seconds')
        origin = time.monotonic()
        metadata['heartbeats']['start']['elapsed_seconds'] = 0
        for role in DEVICES:
            pid = metadata['devices'][role]['socket_before']['pid']
            spawn(role, 'pcap', ['shell', 'timeout', '-s', 'INT', str(args.duration),
                               '/system/bin/tcpdump', '-i', 'any', '-s', '0', '-U', '-w', REMOTE_PCAP,
                               'udp', 'port', '5055'])
            spawn(role, 'syscalls', ['shell', 'timeout', '-s', 'INT', str(args.duration),
                                   '/system/bin/strace', '-f', '-q', '-ttt',
                                   '-e', 'trace=recvfrom,recvmsg,recvmmsg,sendto,sendmsg',
                                   '-e', 'raw=all', '-p', str(pid), '-o', REMOTE_SYSCALLS])
        event('captures_started', 0)
        timeline = [(3, 'register_both'), (12, 'peer_left'), (139, 'before_idle_delivery'),
                    (140, 'peer_right'), (144, 'after_idle_delivery'), (150, 'primary_left'),
                    (155, 'heartbeat_155')]
        for planned, action in timeline:
            while time.monotonic() - origin < planned:
                for role, label, child in children:
                    if label in ('pcap', 'syscalls') and child.poll() is not None:
                        raise RuntimeError(f'{role} {label} ended before the capture deadline; inspect ignored logs')
                time.sleep(min(0.25, max(0, planned - (time.monotonic() - origin))))
            event(action, planned)
            if action in ('before_idle_delivery', 'after_idle_delivery'):
                for role in DEVICES:
                    label = f'screenshot-{planned}'
                    spawn(role, label, ['exec-out', 'screencap', '-p'], f'{role}-{planned}.png')
            if action in ('before_idle_delivery', 'heartbeat_155'):
                futures.append(pool.submit(sample, str(planned)))
            moves = [('primary', 307), ('peer', 307)] if action == 'register_both' else {
                'peer_left': [('peer', 140)], 'peer_right': [('peer', 307)],
                'primary_left': [('primary', 140)]}.get(action, [])
            for role, x in moves:
                spawn(role, f'move-{planned}', ['shell', 'input', 'touchscreen', 'swipe',
                                               str(x), '533', str(x), '533', '600'])
        deadline = origin + args.duration + 12
        while True:
            for role, label, child in children:
                if label in ('pcap', 'syscalls') and child.poll() is not None and elapsed() < args.duration - 1:
                    raise RuntimeError(f'{role} {label} ended before the capture deadline; inspect ignored logs')
            if all(child.poll() is not None for _, _, child in children):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('Capture children exceeded the bounded capture deadline')
            time.sleep(0.25)
        for role, label, child in children:
            # Android timeout expiration may return 1, 124, or signal status.
            permitted = (0, 1, 124, 130, 137, 143) if label in ('pcap', 'syscalls') else (0,)
            metadata['events'].append({'event': 'child_exit', 'role': role, 'kind': label,
                                       'returncode': child.returncode, 'elapsed_seconds': elapsed()})
            if child.returncode not in permitted:
                raise RuntimeError(f'{role} {label} failed; inspect ignored logs')
        for future in futures:
            label, result = future.result(timeout=20)
            metadata['heartbeats'][label] = result
        for role in DEVICES:
            for remote, extension in ((REMOTE_PCAP, 'pcap'), (REMOTE_SYSCALLS, 'syscalls.log')):
                adb(role, 'pull', remote, str(output / f'{role}.{extension}'), timeout=30)
        unchanged = True
        for role in DEVICES:
            device = metadata['devices'][role]
            try:
                after = socket_identity(role)
                device['socket_after'] = after
                device['socket_unchanged'] = after == device['socket_before']
            except (RuntimeError, subprocess.SubprocessError) as error:
                device['socket_after_error'] = type(error).__name__
                device['socket_unchanged'] = False
            unchanged = unchanged and device['socket_unchanged']
        if not unchanged:
            raise RuntimeError('PID, UDP socket inode, or exact FD changed during capture')
        if any((output / f'{role}.pcap').stat().st_size <= 24 or
               (output / f'{role}.syscalls.log').stat().st_size == 0 for role in DEVICES):
            raise RuntimeError('Expected nonempty packet and syscall captures on both devices')
        metadata['complete'] = True
        event('capture_complete', args.duration)
    except BaseException as error:
        # Error strings are intentionally omitted: subprocess exceptions can
        # contain full SQL/PHP or raw command output. Detail remains in logs.
        metadata['failure_type'] = type(error).__name__
        raise
    finally:
        for _, _, child in children:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
        pool.shutdown(wait=True, cancel_futures=True)
        for stream in streams:
            stream.close()
        for path in output.iterdir():
            if path.is_file() and path.name != 'metadata.json':
                with path.open('rb') as stream:
                    metadata['artifacts'][path.name] = {'bytes': path.stat().st_size,
                                                       'sha256': hashlib.file_digest(stream, 'sha256').hexdigest()}
        save_metadata()


if __name__ == '__main__':
    main()

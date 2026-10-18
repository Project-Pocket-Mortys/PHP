"""Bounded two-emulator movement capture in already selected same/different rooms.

Does not select worlds, change accounts, restart clients or seed fixtures.
Raw captures stay ignored; exported results omit identities and endpoints.
"""
import argparse
import hashlib
import json
import struct
import subprocess
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/protocol'))
from test_http import sql, php
from probe_android_peers import adb, adb_args, socket_identity, FLAGS
from compare_udp_hops import _read_udp
from summarize_udp_pcap import summarize

ROLES = ('primary', 'peer')


def accounts():
    return sql("SELECT username,player_id,session_id,room_id,state, (SELECT world_id FROM room_ids r WHERE r.room_id=users.room_id LIMIT 1) AS world_id FROM users "
               "WHERE username IN ('PMResearch01','PMResearch02') ORDER BY username")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expect', choices=('same', 'different'), required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if not output.is_relative_to((ROOT / '.research').resolve()):
        parser.error('Output must be within repository .research')
    if php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');") != 'db:http://localhost:8087':
        raise RuntimeError('Isolated backend required')
    before = accounts()
    if len(before) != 2 or any(r['state'] != 'WORLD' or not r['room_id'] for r in before):
        raise RuntimeError('Both accounts must be in WORLD rooms')
    same = before[0]['room_id'] == before[1]['room_id']
    if same != (args.expect == 'same'):
        raise RuntimeError('Room membership does not match expected scenario')
    for role, name in zip(ROLES, ('PocketMortys_API30', 'PocketMortys_API30_Peer')):
        if adb(role, 'emu', 'avd', 'name').splitlines()[0] != name:
            raise RuntimeError('Unexpected emulator identity')
        if adb(role, 'shell', 'id', '-u').strip() != '0':
            raise RuntimeError('ADB must already be root')
        adb(role, 'shell', 'test', '-x', '/system/bin/tcpdump')
    identities = {r: socket_identity(r) for r in ROLES}
    output.mkdir(parents=True, exist_ok=False)
    report = {'started_utc': datetime.now(timezone.utc).isoformat(),
              'expect': args.expect, 'worlds': {r: before[i]['world_id'] for i, r in enumerate(ROLES)}, 'actions': [], 'capture_complete': False,
              'acceptance_passed': False}
    children, logs = [], []

    def screens(label):
        for role in ROLES:
            png = adb(role, 'exec-out', 'screencap', '-p', binary=True)
            if png[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', png[16:24]) != (1280, 720):
                raise RuntimeError('Expected landscape 1280x720')
            (output / f'{role}-{label}.png').write_bytes(png)

    try:
        screens('before')
        start = time.monotonic()
        for role in ROLES:
            log = (output / f'{role}-capture.log').open('wb')
            logs.append(log)
            children.append(subprocess.Popen(adb_args(role, 'shell', 'timeout', '-s', 'INT', '16',
                'tcpdump', '-i', 'any', '-s', '0', '-U', '-w', '/data/local/tmp/world-rooms.pcap',
                'udp', 'port', '5055'), stdout=log, stderr=log, creationflags=FLAGS))
        for target, role, x in ((2, 'primary', 307), (4, 'peer', 307), (8, 'primary', 140), (10, 'peer', 140)):
            time.sleep(max(0, target - (time.monotonic() - start)))
            if any(c.poll() is not None for c in children):
                raise RuntimeError('Capture ended prematurely')
            report['actions'].append({'role': role, 'direction': 'right' if x == 307 else 'left',
                                      'elapsed_seconds': round(time.monotonic() - start, 3)})
            adb(role, 'shell', 'input', 'touchscreen', 'swipe', str(x), '533', str(x), '533', '600')
        for child in children:
            if child.wait(timeout=12) not in (0, 1, 124, 130, 137, 143):
                raise RuntimeError('Capture failed; inspect ignored logs')
        for log in logs:
            log.flush()
        screens('after')
        after = accounts()
        report['membership_and_sessions_unchanged'] = before == after
        report['socket_unchanged'] = {r: socket_identity(r) == identities[r] for r in ROLES}
        report['packets'], report['matches'], report['capture_logs'] = {}, {}, {}
        captures = {}
        for role in ROLES:
            adb(role, 'pull', '/data/local/tmp/world-rooms.pcap', str(output / f'{role}.pcap'))
            report['packets'][role] = summarize(output / f'{role}.pcap')
            captures[role] = _read_udp(output / f'{role}.pcap')[2]
            report['capture_logs'][role] = (output / f'{role}-capture.log').read_text(encoding='utf-8')
        for i, role in enumerate(ROLES):
            other = ROLES[1-i]
            player = uuid.UUID(before[i]['player_id']).bytes
            incoming = [p['payload'] for p in captures[other] if p['source'][1] == 5055]
            outgoing = [p['payload'] for p in captures[role] if p['destination'][1] == 5055]
            report['matches'][role] = [{'sequence': p[16], 'received_by_other': player + p[16:] in incoming}
                                       for p in outgoing if len(p) == 24]
        report['capture_complete'] = True
        matched = all(any(p['received_by_other'] for p in report['matches'][r]) for r in ROLES)
        isolated = all(not report['packets'][r]['directions']['inbound']['packet_count'] for r in ROLES)
        active = all(report['matches'][r] for r in ROLES)
        no_drops = all('0 packets dropped by kernel' in report['capture_logs'][r] for r in ROLES)
        report['acceptance_passed'] = bool(active and no_drops and report['membership_and_sessions_unchanged']
            and all(report['socket_unchanged'].values()) and (matched if same else isolated))
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
        for log in logs:
            log.close()
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        report['artifacts'] = {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()}
                               for p in output.iterdir() if p.is_file()}
        (output / 'results.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'capture_complete': report['capture_complete'], 'acceptance_passed': report['acceptance_passed']}))
    if not report['acceptance_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()

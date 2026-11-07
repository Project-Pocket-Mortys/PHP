"""Capture a 60-second Android portal leave/rejoin scenario in the isolated backend.

Precondition: both named research clients are in world 1, primary faces the portal
with no dialog open, and both displays are 1280x720. Fixed taps require visual
review afterward; completion means acquisition, not gameplay acceptance. Raw
PCAPs contain sessions and stay ignored. Do not run alongside another capture.
See docs/protocol/android-portal-transition.md for setup and limitations.
"""
import sys, subprocess, time, json, hashlib, struct
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/research'))
sys.path.insert(0, str(ROOT / 'tests/protocol'))
from probe_android_peers import adb, adb_args, socket_identity, FLAGS
from test_http import sql

def main():
    import argparse, os
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    if not out.is_relative_to((ROOT / '.research').resolve()):
        parser.error('Output must be a new directory within repository .research')
    os.chdir(ROOT)
    out.mkdir(parents=True, exist_ok=False)
    roles = ('primary', 'peer')
    meta = {'started_utc': datetime.now(timezone.utc).isoformat(), 'events': [], 'samples': {}, 'complete': False}
    initial = sql("SELECT username,session_id,room_id FROM users WHERE username IN ('PMResearch01','PMResearch02') ORDER BY username")
    if not (len(initial) == 2 and initial[0]['room_id'] == initial[1]['room_id'] and initial[0]['room_id']):
        raise RuntimeError('Both research accounts must share a room')
    if not all((adb(r, 'emu', 'avd', 'name').splitlines()[0] == n for r, n in [('primary', 'PocketMortys_API30'), ('peer', 'PocketMortys_API30_Peer')])):
        raise RuntimeError('Unexpected emulator identity')
    for r in roles:
        if adb(r, 'shell', 'id', '-u').strip() != '0':
            raise RuntimeError('ADB must already be root')
        for tool in ('tcpdump', 'strace'):
            adb(r, 'shell', 'test', '-x', '/system/bin/' + tool)
        png = adb(r, 'exec-out', 'screencap', '-p', binary=True)
        if png[:8] != b'\x89PNG\r\n\x1a\n' or struct.unpack('>II', png[16:24]) != (1280, 720):
            raise RuntimeError('Expected 1280x720 landscape')
    meta['socket_before'] = {r: socket_identity(r) for r in roles}

    def sample(label):
        rows = sql("SELECT username,session_id,room_id,state FROM users WHERE username IN ('PMResearch01','PMResearch02') ORDER BY username")
        meta['samples'][label] = [{'role': roles[i], 'same_session': row['session_id'] == initial[i]['session_id'], 'original_room': row['room_id'] == initial[i]['room_id'], 'outside_room': row['room_id'] is None, 'state': row['state']} for i, row in enumerate(rows)]
        for r in roles:
            (out / f'{r}-{label}.png').write_bytes(adb(r, 'exec-out', 'screencap', '-p', binary=True))
    sample('before')
    start = time.monotonic()
    children = []
    logs = []
    try:
        for r in roles:
            for kind, args in [('pcap', ['tcpdump', '-i', 'any', '-s', '0', '-U', '-w', '/data/local/tmp/roundtrip.pcap', 'udp', 'port', '5055']), ('trace', ['strace', '-f', '-q', '-ttt', '-e', 'trace=recvfrom,sendto', '-e', 'raw=all', '-p', str(meta['socket_before'][r]['pid']), '-o', '/data/local/tmp/roundtrip.trace'])]:
                log = (out / f'{r}-{kind}.log').open('wb')
                logs.append(log)
                children.append(subprocess.Popen(adb_args(r, 'shell', 'timeout', '-s', 'INT', '60', *args), stdout=log, stderr=log, creationflags=FLAGS))
        actions = [(3, 'open_portal'), (8, 'outside'), (11, 'peer_left'), (15, 'select_mortyland'), (19, 'teleport'), (29, 'returned'), (32, 'dismiss_popup'), (35, 'dismiss_tutorial'), (39, 'primary_left'), (43, 'peer_right'), (49, 'after')]
        for target, action in actions:
            time.sleep(max(0, target - (time.monotonic() - start)))
            meta['events'].append({'action': action, 'elapsed': round(time.monotonic() - start, 3), 'utc': datetime.now(timezone.utc).isoformat()})
            if action in ('outside', 'returned', 'after'):
                sample(action)
            elif action in ('peer_left', 'primary_left', 'peer_right'):
                r = 'primary' if action.startswith('primary') else 'peer'
                x = '307' if 'right' in action else '140'
                adb(r, 'shell', 'input', 'touchscreen', 'swipe', x, '533', x, '533', '600')
            else:
                x, y = {'open_portal': (1054, 535), 'select_mortyland': (160, 242), 'teleport': (559, 576), 'dismiss_popup': (640, 504), 'dismiss_tutorial': (1144, 600)}[action]
                adb('primary', 'shell', 'input', 'tap', str(x), str(y))
        for child in children:
            status = child.wait(timeout=20)
            if status not in (0, 1, 124, 130, 137, 143):
                raise RuntimeError('Capture child failed; inspect ignored logs')
        for r in roles:
            for ext in ('pcap', 'trace'):
                adb(r, 'pull', f'/data/local/tmp/roundtrip.{ext}', str(out / f'{r}.{ext}'))
        meta['socket_after'] = {r: socket_identity(r) for r in roles}
        meta['complete'] = True
    finally:
        for child in children:
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
        for log in logs:
            log.close()
        meta['finished_utc'] = datetime.now(timezone.utc).isoformat()
        meta['artifacts'] = {p.name: {'bytes': p.stat().st_size, 'sha256': hashlib.sha256(p.read_bytes()).hexdigest()} for p in out.iterdir() if p.is_file()}
        (out / 'metadata.json').write_text(json.dumps(meta, indent=2) + '\n', encoding='utf-8')
    print('Portal roundtrip capture complete')
if __name__ == '__main__':
    main()

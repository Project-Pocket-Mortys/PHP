"""Bounded synthetic peer for the dedicated emulator room; removes its account on exit."""
import argparse
import json
from pathlib import Path
import socket
import struct
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tests/protocol'))
from test_http import php, sql
from udp_codec import decode_datagram


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=60)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.seconds <= 120:
        parser.error('Use a bounded duration of 1..120 seconds')
    if php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');") != 'db:http://localhost:8087':
        raise RuntimeError('Isolated backend required')
    room = '00000000-0000-4000-8000-000000000001'
    player, session = str(uuid.uuid4()), str(uuid.uuid4())
    report = {'kind': 'One emulator plus synthetic UDP peer; not two Android clients',
              'sent': 0, 'received': 0, 'received_positions': [], 'identifiers_exported': False}
    def publish(event):
        php("require '/var/www/html/pocket_f4894h398r8h9w9er8he98he.php'; require '/var/www/html/lib/events.php'; "
            f"publish_event($pdo, '{room}', '{event}', ['room_id'=>'{room}', 'player_id'=>'{player}', 'state'=>'WORLD']);")
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('127.0.0.1', 0)); sock.settimeout(0.1)
    try:
        sql(f"INSERT INTO users (secret, player_id, session_id, username, room_id, player_avatar_id, level, state, tags) "
            f"VALUES ('{session}', '{player}', '{session}', 'UDPProbe', '{room}', 'AvatarRickDefault', 2, 'WORLD', '[]')")
        publish('room:user-added')
        deadline, next_send = time.monotonic() + args.seconds, 0
        print('Synthetic UDPProbe player active in research room', flush=True)
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= next_send:
                index = report['sent']
                x = 32 + index % 2
                packet = uuid.UUID(session).bytes + struct.pack('>BHH', index % 256, x, 35) + b'\x00\x00' + bytes([1 if index % 2 else 2])
                sock.sendto(packet, ('127.0.0.1', 5055))
                report['sent'] += 1
                next_send = now + 0.5
            try:
                packet, _ = sock.recvfrom(65535)
            except socket.timeout:
                continue
            for record in decode_datagram(packet):
                report['received'] += 1
                report['received_positions'].append({key:value for key,value in record.items() if key != 'net_id'})
    finally:
        sock.close()
        try:
            publish('room:user-removed')
        finally:
            sql(f"DELETE FROM users WHERE player_id='{player}'")
            # Retain the removal tombstone until SSE readers consume it.
            sql(f"DELETE FROM event_queue WHERE room_id='{room}' AND player_id='{player}' AND event_name <> 'room:user-removed'")
            args.output.write_text(json.dumps(report, indent=2)+'\n', newline='\n')
        print(f"Probe removed: {report['sent']} sent, {report['received']} received", flush=True)


if __name__ == '__main__':
    main()

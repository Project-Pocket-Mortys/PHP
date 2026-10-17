"""Synthetic Windows localhost UDP mapping probe; never seeds or controls Android.

Start an independent relay PCAP before running. Raw captures are private: outbound
UDP identifiers are session credentials. This report exports no identifiers,
addresses, ports, or payloads. Correlate packets by role coordinates (role 0:
x=29, role 1: x=35; both y=35), sequence, and recorded relative send times.
"""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
FLAGS = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0


def http_helpers():
    # Importing helpers does not invoke unittest or its destructive seed fixture.
    spec = importlib.util.spec_from_file_location('quiet_probe_http', ROOT / 'tests/protocol/test_http.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def php(code):
        return subprocess.run(module.COMPOSE + ['exec', '-T', 'web', 'php', '-r', code],
                              cwd=ROOT, capture_output=True, text=True, check=True,
                              timeout=10, creationflags=FLAGS).stdout

    module.php = php
    return module


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds', type=int, default=125, help='UDP quiet seconds, 125 through 180')
    parser.add_argument('--output', type=Path, default=ROOT / '.research/quiet-udp-report.json')
    args = parser.parse_args(argv)
    if not 125 <= args.seconds <= 180:
        parser.error('--seconds must be between 125 and 180')
    output = args.output.resolve()
    if not output.is_relative_to((ROOT / '.research').resolve()) or output.suffix != '.json':
        parser.error('--output must be a JSON file inside this repository .research directory')
    if output.exists():
        parser.error('--output must not overwrite an existing report')
    output.parent.mkdir(parents=True, exist_ok=True)

    report = {'probe': 'synthetic_localhost_two_peers',
              'started_utc': datetime.now(timezone.utc).isoformat(),
              'requested_quiet_seconds': args.seconds,
              'receive_timeout_seconds': 0.7, 'heartbeat_interval_seconds': 20,
              'events': [], 'heartbeats': [], 'heartbeat_persistence_checks': [], 'deliveries': [],
              'complete': False, 'cleanup_complete': False}
    helpers = http_helpers()
    room = str(uuid.uuid4())
    players = [str(uuid.uuid4()) for _ in range(2)]
    sessions = [str(uuid.uuid4()) for _ in range(2)]
    sockets, original_tuples = [], []
    started = time.monotonic()
    fixtures_started = False
    quiet_start = None

    def elapsed():
        return round(time.monotonic() - started, 3)

    def event(name, **fields):
        entry = {'event': name, 'elapsed_seconds': elapsed(), **fields}
        report['events'].append(entry)
        print(json.dumps(entry), flush=True)

    def packet(role, sequence):
        return (uuid.UUID(sessions[role]).bytes +
                struct.pack('>BHH', sequence, (29, 35)[role], 35) + b'\x00\x00\x01')

    def delivery(sender, sequence, label):
        receiver = 1 - sender
        entry = {'label': label, 'sender_role': sender, 'receiver_role': receiver,
                 'sequence': sequence, 'sent_elapsed_seconds': elapsed()}
        sockets[sender].sendto(packet(sender, sequence), ('127.0.0.1', 5055))
        try:
            raw = sockets[receiver].recv(65535)
            entry['received'] = True
            entry['expected_translation'] = raw == uuid.UUID(players[sender]).bytes + packet(sender, sequence)[16:]
        except socket.timeout:
            entry['received'] = False
            entry['expected_translation'] = False
        entry['checked_elapsed_seconds'] = elapsed()
        report['deliveries'].append(entry)
        event(label, received=entry['received'], expected_translation=entry['expected_translation'])
        return entry

    def heartbeat():
        for role in range(2):
            before = elapsed()
            status, body = helpers.post('/session/ping-dynamic',
                                        {'session_id': sessions[role], 'type': 'DEFAULT'})
            ok = status == 200 and body == {'success': True}
            report['heartbeats'].append({'role': role, 'started_elapsed_seconds': before,
                                         'completed_elapsed_seconds': elapsed(), 'success': ok})
            event('http_heartbeat', role=role, success=ok)
            if not ok:
                raise RuntimeError('Synthetic HTTP heartbeat failed')

    def check_persisted_heartbeats(label):
        # A successful HTTP response alone is insufficient: ping also acknowledges
        # invalid sessions. Scope each database read to this fixture's current
        # player, session and room, and export only derived facts.
        entries = []
        for role in range(2):
            rows = helpers.sql(
                "SELECT TIMESTAMPDIFF(SECOND,h.received_at,CURRENT_TIMESTAMP) AS age_seconds "
                "FROM users u JOIN research_client_heartbeats h ON h.user_id=u.id "
                f"WHERE u.player_id='{players[role]}' AND u.session_id='{sessions[role]}' "
                f"AND u.room_id='{room}' AND u.state='WORLD' "
                f"AND h.session_id='{sessions[role]}' AND h.room_id='{room}'")
            age = int(rows[0]['age_seconds']) if len(rows) == 1 else None
            entry = {'label': label, 'role': role, 'elapsed_seconds': elapsed(),
                     'age_seconds': age, 'current_and_fresh': age is not None and 0 <= age <= 30}
            report['heartbeat_persistence_checks'].append(entry)
            entries.append(entry)
            event('heartbeat_persistence_checked', role=role, label=label,
                  age_seconds=age, success=entry['current_and_fresh'])
        if not all(entry['current_and_fresh'] for entry in entries):
            raise RuntimeError('Synthetic heartbeat missing, mismatched or stale in database')

    try:
        event('started')
        if helpers.php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');") != 'db:http://localhost:8087':
            raise RuntimeError('Local research Compose environment required')
        # Every value interpolated into SQL below is a generated UUID or constant.
        fixtures_started = True
        helpers.sql(f"INSERT INTO room_ids (room_id,world_id,zone_id) VALUES ('{room}','quiet-udp-probe','[1,1]')")
        for role in range(2):
            helpers.sql("INSERT INTO users (secret,player_id,session_id,username,room_id,state,tags) "
                        f"VALUES ('{sessions[role]}','{players[role]}','{sessions[role]}',"
                        f"'QuietUDPProbe','{room}','WORLD','[]')")
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sockets.append(sock)
            sock.bind(('127.0.0.1', 0))
            sock.settimeout(0.7)
            original_tuples.append(sock.getsockname())
        heartbeat()
        check_persisted_heartbeats('before_quiet')
        sockets[0].sendto(packet(0, 0), ('127.0.0.1', 5055))
        # A brief bounded pause lets registration 0 precede registration 1.
        time.sleep(0.1)
        registration = delivery(1, 0, 'registration_confirmed')
        if not registration['expected_translation']:
            raise RuntimeError('Both initial UDP registrations were not confirmed')
        # Detect any pre-quiet queued packet; none may contaminate the post-idle check.
        for sock in sockets:
            sock.setblocking(False)
            try:
                sock.recv(65535)
            except BlockingIOError:
                pass
            else:
                raise RuntimeError('Unexpected queued UDP during registration')
            finally:
                sock.settimeout(0.7)
        quiet_start = time.monotonic()
        event('quiet_started')
        next_ping = quiet_start + 20
        deadline = quiet_start + args.seconds
        while time.monotonic() < deadline:
            time.sleep(min(0.25, max(0, min(next_ping, deadline) - time.monotonic())))
            if time.monotonic() >= next_ping and time.monotonic() < deadline:
                heartbeat()
                event('quiet_http_heartbeat', quiet_elapsed_seconds=round(time.monotonic() - quiet_start, 3))
                next_ping += 20
        check_persisted_heartbeats('after_quiet')
        report['actual_quiet_seconds'] = round(time.monotonic() - quiet_start, 3)
        event('quiet_ended')
        delivery(1, 1, 'peer_to_quiet_recipient')
        resumed = delivery(0, 1, 'recipient_sends_again')
        refreshed = delivery(1, 2, 'peer_to_refreshed_recipient')
        report['local_socket_tuple_unchanged'] = [
            sock.getsockname() == original for sock, original in zip(sockets, original_tuples)]
        if not resumed['expected_translation'] or not refreshed['expected_translation']:
            raise RuntimeError('UDP delivery did not recover after both endpoints sent again')
        if not all(report['local_socket_tuple_unchanged']):
            raise RuntimeError('Local UDP socket tuple changed')
        report['complete'] = True
        event('probe_finished')
    except (Exception, KeyboardInterrupt) as error:
        # Exception text/tracebacks can contain subprocess arguments and credentials.
        report['error_type'] = type(error).__name__
        event('probe_failed', error_type=type(error).__name__)
    finally:
        for sock in sockets:
            sock.close()
        cleanup_errors = []
        if fixtures_started:
            # Continue cleanup after individual failures. User deletion cascades
            # research_client_heartbeats; event and room rows need explicit removal.
            queries = [f"DELETE FROM event_queue WHERE room_id='{room}'"]
            for player in players:
                queries.extend([f"DELETE FROM event_queue WHERE player_id='{player}'",
                                f"DELETE FROM users WHERE player_id='{player}'"])
            queries.append(f"DELETE FROM room_ids WHERE room_id='{room}'")
            for query in queries:
                try:
                    helpers.sql(query)
                except Exception as error:
                    cleanup_errors.append(type(error).__name__)
        report['cleanup_complete'] = not cleanup_errors
        if cleanup_errors:
            report['cleanup_error_types'] = cleanup_errors
        event('cleanup_finished', success=report['cleanup_complete'])
        report['finished_utc'] = datetime.now(timezone.utc).isoformat()
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    return 0 if report['complete'] and report['cleanup_complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())

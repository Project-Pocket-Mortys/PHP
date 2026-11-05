"""Live PHP/optional TCP adapter lifecycle tests; no reseed or service restart.

The adapter at localhost:5056 must already target the PHP relay at localhost:5055.
Opt in with PM_RUN_UDP_TUNNEL=1 when invoking this file through unittest.
These short checks exercise retained endpoints, not the actual 120-second TTL.
Retired adapter sockets remain quarantined until a coordinated service restart.
"""
import os
import select
import socket
import struct
import time
import unittest
import uuid

from test_http import php, sql


@unittest.skipUnless(os.environ.get('PM_RUN_UDP_TUNNEL') == '1',
                     'set PM_RUN_UDP_TUNNEL=1 with the optional TCP adapter running')
class UdpTunnelLifecycleTests(unittest.TestCase):
    TIMEOUT = 1.0

    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.rooms = [str(uuid.uuid4()) for _ in range(2)]
        self.players = [str(uuid.uuid4()) for _ in range(4)]
        self.sessions = [str(uuid.uuid4()) for _ in range(4)]
        self.clients = []
        self.addCleanup(self.cleanup)
        for room in self.rooms:
            sql(f"INSERT INTO room_ids (room_id, world_id, zone_id) VALUES ('{room}', 'udp-tunnel-test', '[1,1]')")
        for index, player in enumerate(self.players):
            session, room = self.sessions[index], self.rooms[index // 2]
            sql(f"INSERT INTO users (secret, player_id, session_id, username, room_id, state, tags) "
                f"VALUES ('{session}', '{player}', '{session}', 'TunnelTest', '{room}', 'WORLD', '[]')")
        self.original = self.connect()
        self.observer = self.connect()
        self.register_pair(self.original, 0, self.observer, 1)

    def cleanup(self):
        for client in self.clients:
            client.close()
        for player in self.players:
            sql(f"DELETE FROM event_queue WHERE player_id='{player}'")
            sql(f"DELETE FROM users WHERE player_id='{player}'")
        for room in self.rooms:
            sql(f"DELETE FROM room_ids WHERE room_id='{room}'")

    def connect(self):
        client = socket.create_connection(('127.0.0.1', 5056), timeout=self.TIMEOUT)
        client.settimeout(self.TIMEOUT)
        self.clients.append(client)
        return client

    def packet(self, index, sequence, session=None):
        return (uuid.UUID(session or self.sessions[index]).bytes
                + struct.pack('>BHH', sequence, 29 + index, 35) + b'\x00\x00\x01')

    def send(self, client, index, sequence, session=None):
        payload = self.packet(index, sequence, session)
        client.sendall(struct.pack('>H', len(payload)) + payload)

    def read_exact(self, client, length, deadline):
        result = bytearray()
        try:
            while len(result) < length:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise socket.timeout('frame read deadline exceeded')
                client.settimeout(remaining)
                chunk = client.recv(length - len(result))
                if not chunk:
                    self.fail('unexpected TCP EOF during framed reply')
                result.extend(chunk)
        finally:
            client.settimeout(self.TIMEOUT)
        return bytes(result)

    def receive(self, client):
        deadline = time.monotonic() + self.TIMEOUT
        length, = struct.unpack('>H', self.read_exact(client, 2, deadline))
        self.assertEqual(length, 24)
        return self.read_exact(client, length, deadline)

    def expect(self, client, sender, sequence):
        self.assertEqual(self.receive(client),
                         uuid.UUID(self.players[sender]).bytes + self.packet(sender, sequence)[16:])

    def silent(self, client):
        with self.assertRaises(socket.timeout):
            # Any byte (including a partial frame) or EOF is a failure.
            received = client.recv(1)
            self.fail(f'unexpected TCP data or EOF: {received!r}')

    def register_pair(self, first, first_index, second, second_index):
        self.send(first, first_index, 0)
        self.send(second, second_index, 0)
        # Separate connections can be scheduled in either order by the adapter.
        ready, _, _ = select.select([first, second], [], [], self.TIMEOUT)
        self.assertTrue(ready, 'framed registrations did not reach PHP')
        for client in ready:
            self.expect(client, second_index if client is first else first_index, 0)
        # Once either translation arrives both endpoints have been learned.
        for client in (first, second):
            if client not in ready:
                self.silent(client)

    def close_with_eof(self, client):
        # A write half-close lets us observe the adapter accepting TCP EOF and
        # closing its side before testing a replacement connection.
        client.shutdown(socket.SHUT_WR)
        self.assertEqual(client.recv(1), b'')
        client.close()

    def test_increasing_sequence_reconnect_and_other_room_port_isolation(self):
        self.send(self.original, 0, 100)
        self.expect(self.observer, 0, 100)
        self.close_with_eof(self.original)

        outsider, outsider_peer = self.connect(), self.connect()
        self.register_pair(outsider, 2, outsider_peer, 3)
        # PHP still retains the disconnected endpoint. These updates must be
        # drained by its quarantined UDP socket, never given to the outsider.
        self.send(self.observer, 1, 1)
        self.silent(outsider)
        self.silent(outsider_peer)

        replacement = self.connect()
        self.send(replacement, 0, 101)
        self.expect(self.observer, 0, 101)
        self.send(self.observer, 1, 2)
        self.expect(replacement, 1, 2)
        self.silent(outsider)
        self.silent(outsider_peer)

    def test_reset_sequence_requires_session_rotation_while_peer_is_retained(self):
        self.send(self.original, 0, 100)
        self.expect(self.observer, 0, 100)
        self.close_with_eof(self.original)
        replacement = self.connect()

        # Known limitation: resetting to zero after 100 is stale while PHP
        # retains this session. A new TCP endpoint alone cannot reset sequence.
        self.send(replacement, 0, 0)
        self.silent(self.observer)
        self.send(self.observer, 1, 1)
        self.silent(replacement)

        old_session = self.sessions[0]
        self.sessions[0] = str(uuid.uuid4())
        sql(f"UPDATE users SET session_id='{self.sessions[0]}' WHERE player_id='{self.players[0]}'")
        self.send(replacement, 0, 0)
        self.expect(self.observer, 0, 0)
        self.send(self.observer, 1, 2)
        self.expect(replacement, 1, 2)

        self.send(replacement, 0, 101, session=old_session)
        self.silent(self.observer)
        self.send(replacement, 0, 1)
        self.expect(self.observer, 0, 1)


if __name__ == '__main__':
    unittest.main()

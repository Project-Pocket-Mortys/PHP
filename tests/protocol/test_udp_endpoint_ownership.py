"""Additive live-PHP endpoint ownership checks against localhost UDP:5055.

Only an accepted movement packet may replace the session owning a UDP endpoint.
Each test creates isolated UUID accounts and rooms; no fixture reseed or restart.
"""
import select
import socket
import struct
import unittest
import uuid

from test_http import php, sql


class UdpEndpointOwnershipTests(unittest.TestCase):
    TIMEOUT = 0.5

    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.rooms = [str(uuid.uuid4()) for _ in range(2)]
        # A and C share room 1; B and D share room 2.
        self.players = {name: str(uuid.uuid4()) for name in 'ABCD'}
        self.sessions = {name: str(uuid.uuid4()) for name in 'ABCD'}
        self.sockets = {}
        self.addCleanup(self.cleanup)
        for room in self.rooms:
            sql(f"INSERT INTO room_ids (room_id, world_id, zone_id) VALUES ('{room}', 'udp-owner-test', '[1,1]')")
        for name in 'ABCD':
            room = self.rooms[0 if name in 'AC' else 1]
            sql(f"INSERT INTO users (secret, player_id, session_id, username, room_id, state, tags) "
                f"VALUES ('{self.sessions[name]}', '{self.players[name]}', '{self.sessions[name]}', "
                f"'EndpointTest', '{room}', 'WORLD', '[]')")
            client = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.sockets[name] = client
            client.bind(('127.0.0.1', 0))
            client.settimeout(self.TIMEOUT)
        self.register_pair('A', 'C')
        self.register_pair('B', 'D')
        self.send('B', 'B', 100)
        self.expect('D', 'B', 100)

    def cleanup(self):
        for client in self.sockets.values():
            client.close()
        for player in self.players.values():
            sql(f"DELETE FROM event_queue WHERE player_id='{player}'")
            sql(f"DELETE FROM users WHERE player_id='{player}'")
        for room in self.rooms:
            sql(f"DELETE FROM room_ids WHERE room_id='{room}'")

    def packet(self, name, sequence):
        return (uuid.UUID(self.sessions[name]).bytes
                + struct.pack('>BHH', sequence, 29 + 'ABCD'.index(name), 35)
                + b'\x00\x00\x01')

    def send(self, endpoint, name, sequence):
        self.sockets[endpoint].sendto(self.packet(name, sequence), ('127.0.0.1', 5055))

    def expect(self, endpoint, sender, sequence):
        expected = uuid.UUID(self.players[sender]).bytes + self.packet(sender, sequence)[16:]
        self.assertEqual(self.sockets[endpoint].recv(128), expected)

    def silent(self, endpoint):
        with self.assertRaises(socket.timeout):
            received = self.sockets[endpoint].recv(128)
            self.fail(f'endpoint {endpoint} received unexpected payload ({len(received)} bytes)')

    def register_pair(self, first, second):
        self.send(first, first, 0)
        self.send(second, second, 0)
        clients = [self.sockets[first], self.sockets[second]]
        ready, _, _ = select.select(clients, [], [], self.TIMEOUT)
        self.assertTrue(ready, 'same-room UDP registrations did not complete')
        for client in ready:
            self.expect(first if client is clients[0] else second,
                        second if client is clients[0] else first, 0)

    def rejected_attempt_preserves_a(self, packet):
        self.sockets['A'].sendto(packet, ('127.0.0.1', 5055))
        # Waiting for silence also gives PHP time to process the rejected
        # ownership attempt before C sends its room update independently.
        self.silent('D')
        self.send('C', 'C', 1)
        self.expect('A', 'C', 1)

    def test_accepted_session_replaces_endpoint_owner_without_old_room_delivery(self):
        # The very same source socket changes identity from valid A to valid B.
        self.send('A', 'B', 101)
        self.expect('D', 'B', 101)
        self.send('D', 'D', 1)
        self.expect('A', 'D', 1)
        self.send('C', 'C', 1)
        self.silent('A')

    def test_malformed_packet_does_not_evict_current_owner(self):
        self.rejected_attempt_preserves_a(self.packet('B', 101)[:-1])

    def test_unknown_session_does_not_evict_current_owner(self):
        self.rejected_attempt_preserves_a(uuid.uuid4().bytes + self.packet('B', 101)[16:])

    def test_non_world_session_does_not_evict_current_owner(self):
        sql(f"UPDATE users SET state='BATTLE' WHERE player_id='{self.players['B']}'")
        self.rejected_attempt_preserves_a(self.packet('B', 101))

    def test_stale_sequence_does_not_evict_current_owner(self):
        self.rejected_attempt_preserves_a(self.packet('B', 0))


if __name__ == '__main__':
    unittest.main()

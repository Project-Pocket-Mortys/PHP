"""Additive socket/DB tests for the optional, localhost-only UDP profile."""
import socket
import struct
import unittest
import uuid

from test_http import php, post, sql


class UdpRelayTests(unittest.TestCase):
    def setUp(self):
        self.assertEqual(php("echo getenv('PM_DB_HOST').':'.getenv('PM_PUBLIC_ORIGIN');"),
                         'db:http://localhost:8087')
        self.room, self.other_room = str(uuid.uuid4()), str(uuid.uuid4())
        self.players = [str(uuid.uuid4()) for _ in range(3)]
        self.sessions = [str(uuid.uuid4()) for _ in range(3)]
        self.sockets = []
        self.addCleanup(self.cleanup)
        for room in (self.room, self.other_room):
            sql(f"INSERT INTO room_ids (room_id, world_id, zone_id) VALUES ('{room}', 'udp-test', '[1,1]')")
        for index in range(3):
            room = self.room if index < 2 else self.other_room
            sql(f"INSERT INTO users (secret, player_id, session_id, username, room_id, state, tags) "
                f"VALUES ('{self.sessions[index]}', '{self.players[index]}', '{self.sessions[index]}', 'UDPTest', '{room}', 'WORLD', '[]')")
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.bind(('127.0.0.1', 0)); sock.settimeout(0.4)
            self.sockets.append(sock)
        self.send(0, 0)
        self.send(1, 0)
        # Observing B's packet at A establishes that both registrations were processed.
        self.assertEqual(self.sockets[0].recv(128)[:16], uuid.UUID(self.players[1]).bytes)
        self.send(2, 0)

    def cleanup(self):
        for sock in self.sockets:
            sock.close()
        for player in self.players:
            sql(f"DELETE FROM event_queue WHERE player_id='{player}'")
            sql(f"DELETE FROM users WHERE player_id='{player}'")
        for room in (self.room, self.other_room):
            sql(f"DELETE FROM room_ids WHERE room_id='{room}'")

    def packet(self, index, seq):
        return uuid.UUID(self.sessions[index]).bytes + struct.pack('>BHH', seq, 29, 35) + b'\x00\x00\x01'

    def send(self, index, seq):
        self.sockets[index].sendto(self.packet(index, seq), ('127.0.0.1', 5055))

    def silent(self, index):
        with self.assertRaises(socket.timeout):
            self.sockets[index].recv(128)

    def test_same_room_receives_player_guid_never_session_guid(self):
        self.send(0, 1)
        expected = uuid.UUID(self.players[0]).bytes + self.packet(0, 1)[16:]
        self.assertEqual(self.sockets[1].recv(128), expected)
        self.silent(0)
        self.silent(2)

    def test_duplicates_and_old_sequences_are_not_forwarded(self):
        self.send(0, 1); self.sockets[1].recv(128)
        self.send(0, 1); self.send(0, 0)
        self.silent(1)

    def test_unknown_session_and_malformed_packets_are_ignored(self):
        raw = self.packet(0, 1)
        for packet in (b'', raw[:-1], raw + b'\x00', uuid.uuid4().bytes + raw[16:],
                       raw[:23] + b'\xff', raw[:22] + b'\xf0' + raw[23:]):
            self.sockets[0].sendto(packet, ('127.0.0.1', 5055))
        self.silent(1)

    def test_rotated_sender_session_is_rejected(self):
        sql(f"UPDATE users SET session_id='{uuid.uuid4()}' WHERE player_id='{self.players[0]}'")
        self.send(0, 1)
        self.silent(1)

    def test_rotated_recipient_session_stops_delivery(self):
        sql(f"UPDATE users SET session_id='{uuid.uuid4()}' WHERE player_id='{self.players[1]}'")
        self.send(0, 1)
        self.silent(1)

    def test_recipient_room_change_stops_delivery_without_udp_update(self):
        sql(f"UPDATE users SET room_id='{self.other_room}' WHERE player_id='{self.players[1]}'")
        self.send(0, 1)
        self.silent(1)

    def test_non_world_sender_cannot_move(self):
        sql(f"UPDATE users SET state='BATTLE' WHERE player_id='{self.players[0]}'")
        self.send(0, 1)
        self.silent(1)

    def test_non_world_recipient_does_not_receive(self):
        sql(f"UPDATE users SET state='BATTLE' WHERE player_id='{self.players[1]}'")
        self.send(0, 1)
        self.silent(1)

    def test_deleted_recipient_does_not_receive(self):
        sql(f"DELETE FROM users WHERE player_id='{self.players[1]}'")
        self.send(0, 1)
        self.silent(1)

    def test_http_leave_stops_recipient_delivery(self):
        self.assertEqual(post('/session/leave-room', {'session_id':self.sessions[1]}), (200, {'success':True}))
        self.send(0, 1)
        self.silent(1)

    def test_sequence_wrap_is_forwarded(self):
        for seq in (100, 200, 255, 0):
            self.send(0, seq)
            self.assertEqual(self.sockets[1].recv(128)[16], seq)


if __name__ == '__main__':
    unittest.main()

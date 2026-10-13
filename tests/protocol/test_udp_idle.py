"""Opt-in real-time expiry test; never reseeds emulator data."""
import os
import socket
import time
import unittest
import uuid

from test_http import post, sql
import test_udp_relay


@unittest.skipUnless(os.getenv('PM_RUN_SLOW_UDP') == '1', '125-second UDP idle test is opt-in')
class UdpIdleTests(unittest.TestCase):
    setUp = test_udp_relay.UdpRelayTests.setUp
    cleanup = test_udp_relay.UdpRelayTests.cleanup
    packet = test_udp_relay.UdpRelayTests.packet
    send = test_udp_relay.UdpRelayTests.send
    silent = test_udp_relay.UdpRelayTests.silent

    def test_http_heartbeat_keeps_stationary_peer_but_not_disconnected_peer(self):
        sql(f"UPDATE users SET room_id='{self.room}' WHERE player_id='{self.players[2]}'")
        self.send(2, 1)
        self.sockets[0].recv(128)
        self.sockets[1].recv(128)
        deadline = time.monotonic() + 125
        seq = 1
        while time.monotonic() < deadline:
            self.assertEqual(post('/session/ping-dynamic', {'session_id': self.sessions[1], 'type': 'DEFAULT'}),
                             (200, {'success': True}))
            self.send(0, seq)
            # Drain both recipients so the final assertions cannot read old packets.
            for index in (1, 2):
                try:
                    self.sockets[index].recv(128)
                except socket.timeout:
                    pass
            seq += 1
            time.sleep(min(20, max(0, deadline - time.monotonic())))
        self.send(0, seq)
        self.assertEqual(self.sockets[1].recv(128),
                         uuid.UUID(self.players[0]).bytes + self.packet(0, seq)[16:])
        self.silent(2)
        # A late HTTP ping cannot establish/revive an endpoint without UDP.
        post('/session/ping-dynamic', {'session_id': self.sessions[2], 'type': 'DEFAULT'})
        self.send(0, seq + 1)
        self.sockets[1].recv(128)
        self.silent(2)
        self.send(2, 2)
        self.sockets[0].recv(128)
        self.sockets[1].recv(128)
        self.send(0, seq + 2)
        self.assertEqual(self.sockets[2].recv(128)[16], seq + 2)


if __name__ == '__main__':
    unittest.main()

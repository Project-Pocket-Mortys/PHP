from pathlib import Path
import socket
import struct
import sys
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/research'))
from udp_transport_tunnel import HostTunnel, ServerTunnel, MAX_BUFFER


class TransportTunnelTests(unittest.TestCase):
    def setUp(self):
        self.sockets = []
        self.tunnels = []
        self.relay = self.udp()
        self.server = ServerTunnel(bind=('127.0.0.1', 0), target=self.relay.getsockname())
        self.tunnels.append(self.server)

    def tearDown(self):
        for tunnel in self.tunnels:
            tunnel.close()
        for sock in self.sockets:
            sock.close()

    def udp(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('127.0.0.1', 0))
        sock.setblocking(False)
        self.sockets.append(sock)
        return sock

    def tcp(self):
        sock = socket.create_connection(self.server.address, timeout=1)
        sock.setblocking(False)
        self.sockets.append(sock)
        self.pump(lambda: bool(self.server.peers))
        return sock

    def pump(self, predicate, timeout=2):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            for tunnel in self.tunnels:
                tunnel.step(0)
            if predicate():
                return
            time.sleep(0.001)
        self.fail('local tunnel did not reach expected state')

    def receive(self, sock):
        rows = []

        def read():
            try:
                rows.append(sock.recvfrom(4096))
                return True
            except BlockingIOError:
                return False

        self.pump(read)
        return rows[0]

    def test_distinct_sources_preserve_payload_and_return_paths_after_quiet(self):
        host = HostTunnel(bind=('127.0.0.1', 0), target=self.server.address)
        self.tunnels.append(host)
        first, second = self.udp(), self.udp()
        payloads = [bytes(range(24)), bytes(reversed(range(24)))]
        relay_paths = []
        for client, payload in zip((first, second), payloads):
            client.sendto(payload, host.address)
            observed, source = self.receive(self.relay)
            self.assertEqual(observed, payload)
            relay_paths.append(source)
        self.assertNotEqual(relay_paths[0], relay_paths[1])
        # No host traffic is necessary for either persistent return path.
        for path, payload in zip(relay_paths, reversed(payloads)):
            self.relay.sendto(payload, path)
        self.assertEqual(self.receive(first)[0], payloads[1])
        self.assertEqual(self.receive(second)[0], payloads[0])
        first.sendto(payloads[1], host.address)
        self.assertEqual(self.receive(self.relay), (payloads[1], relay_paths[0]))
        self.assertEqual(len(host.peers), 2)

    def test_fragmented_and_coalesced_tcp_frames_are_exact(self):
        tcp = self.tcp()
        payload = bytes(range(24))
        framed = struct.pack('!H', 24) + payload
        for fragment in (framed[:1], framed[1:9], framed[9:]):
            tcp.sendall(fragment)
            self.server.step(0.01)
        self.assertEqual(self.receive(self.relay)[0], payload)
        tcp.sendall(framed + framed)
        self.assertEqual(self.receive(self.relay)[0], payload)
        self.assertEqual(self.receive(self.relay)[0], payload)
        self.assertEqual(self.server.counts['tcp_packets_received'], 3)

    def test_return_traffic_refreshes_both_idle_deadlines(self):
        host = HostTunnel(bind=('127.0.0.1', 0), target=self.server.address,
                          idle_seconds=10)
        self.tunnels.append(host)
        self.server.idle_seconds = 10
        client = self.udp()
        client.sendto(bytes(24), host.address)
        _, relay_path = self.receive(self.relay)
        host_peer = next(iter(host.peers))
        server_peer = next(iter(self.server.peers))

        # Advance a controlled clock past both original deadlines. Only relay
        # return traffic, with no new host datagram, can keep these peers alive.
        host_peer.active = server_peer.active = 90.0
        reply = bytes(range(24))
        with patch('udp_transport_tunnel.time.monotonic', return_value=100.0) as clock:
            self.relay.sendto(reply, relay_path)
            self.server.step(0.1)  # UDP return queues the frame and refreshes server.
            self.assertEqual(server_peer.active, 100.0)
            self.server.step(0.1)  # Flush the frame on the existing TCP connection.
            host.step(0.1)  # TCP return refreshes host and delivers the UDP reply.
            self.assertEqual(host_peer.active, 100.0)
            self.assertEqual(client.recv(128), reply)
            clock.return_value = 109.0
            self.server.step(0)
            host.step(0)
            self.assertIn(server_peer, self.server.peers)
            self.assertIn(host_peer, host.peers)
            self.assertEqual(self.server.counts['idle_expired'], 0)
            self.assertEqual(host.counts['idle_expired'], 0)

    def test_malformed_length_closes_only_its_peer(self):
        bad = self.tcp()
        good = socket.create_connection(self.server.address, timeout=1)
        self.sockets.append(good)
        self.pump(lambda: len(self.server.peers) == 2)
        bad.sendall(b'\xff\xff')
        self.pump(lambda: self.server.counts['invalid_frame'] == 1)
        self.assertEqual(len(self.server.peers), 1)
        good.sendall(b'\x00\x18' + bytes(24))
        self.assertEqual(self.receive(self.relay)[0], bytes(24))
        self.assertEqual(self.server.counts['tcp_packets_received'], 1)

    def test_short_tcp_writes_preserve_complete_frame(self):
        tcp = self.tcp()
        peer = next(iter(self.server.peers))
        original = peer.tcp

        class ShortWrites:
            def fileno(self):
                return original.fileno()

            def send(self, payload):
                return original.send(payload[:3])

            def __getattr__(self, name):
                return getattr(original, name)

        peer.tcp = ShortWrites()
        self.server._queue(peer, bytes(range(24)))
        self.pump(lambda: not peer.outgoing)
        received = bytearray()

        def read_frame():
            try:
                received.extend(tcp.recv(4096))
            except BlockingIOError:
                pass
            return len(received) == 26

        self.pump(read_frame)
        self.assertEqual(received, b'\x00\x18' + bytes(range(24)))

    def test_truncated_frame_and_eof_quarantine_udp_socket(self):
        tcp = self.tcp()
        peer = next(iter(self.server.peers))
        tcp.sendall(b'\x00\x18partial')
        tcp.shutdown(socket.SHUT_WR)
        self.pump(lambda: not self.server.peers)
        self.assertEqual(self.server.counts['truncated_frame'], 1)
        self.assertNotEqual(peer.udp.fileno(), -1)
        self.assertIn(peer.udp, self.server.retired)
        self.assertEqual(len(self.server.selector.get_map()), 2)

    def test_host_releases_source_on_server_disconnect(self):
        host = HostTunnel(bind=('127.0.0.1', 0), target=self.server.address)
        self.tunnels.append(host)
        client = self.udp()
        client.sendto(bytes(24), host.address)
        self.receive(self.relay)
        self.server._close_peer(next(iter(self.server.peers)), 'test_disconnect')
        self.pump(lambda: not host.peers)
        self.assertFalse(host.sources)
        client.sendto(bytes(range(24)), host.address)
        self.assertEqual(self.receive(self.relay)[0], bytes(range(24)))

    def test_queue_limit_closes_peer_without_replay(self):
        self.tcp()
        peer = next(iter(self.server.peers))
        for _ in range(MAX_BUFFER // 26 + 1):
            self.server._queue(peer, bytes(24))
        self.assertTrue(peer.closed)
        self.assertEqual(self.server.counts['buffer_limit'], 1)
        self.assertLessEqual(len(peer.outgoing), MAX_BUFFER)
        self.assertEqual(self.server.counts['tcp_packets_received'], 0)

    def test_invalid_udp_is_dropped_before_peer_creation(self):
        host = HostTunnel(bind=('127.0.0.1', 0), target=self.server.address)
        self.tunnels.append(host)
        client = self.udp()
        for size in (0, 23, 25, 100):
            client.sendto(bytes(size), host.address)
        self.pump(lambda: host.counts['invalid_udp'] == 4)
        self.assertFalse(host.peers)
        self.assertFalse(self.server.peers)

    def test_peer_limit_and_idle_cleanup_are_bounded(self):
        limited = ServerTunnel(bind=('127.0.0.1', 0), target=self.relay.getsockname(),
                               max_peers=1, idle_seconds=0.05)
        self.tunnels.append(limited)
        for _ in range(2):
            self.sockets.append(socket.create_connection(limited.address, timeout=1))
        self.pump(lambda: limited.counts['peer_limit'] == 1)
        self.assertEqual(len(limited.peers), 1)
        self.pump(lambda: not limited.peers)
        self.assertEqual(limited.counts['idle_expired'], 1)
        self.sockets.append(socket.create_connection(limited.address, timeout=1))
        self.pump(lambda: limited.counts['peer_limit'] == 2)
        self.assertEqual(len(limited.retired), 1)

    def test_disconnected_endpoint_cannot_deliver_to_replacement_peer(self):
        previous = self.tcp()
        previous.sendall(b'\x00\x18' + bytes(24))
        _, old_path = self.receive(self.relay)
        previous.shutdown(socket.SHUT_RDWR)
        previous.close()
        self.pump(lambda: not self.server.peers)
        replacement = self.tcp()
        replacement.sendall(b'\x00\x18' + bytes(range(24)))
        _, new_path = self.receive(self.relay)
        self.assertNotEqual(old_path, new_path)
        self.relay.sendto(bytes(24), old_path)
        self.pump(lambda: self.server.counts['quarantined_packets_dropped'] == 1)
        with self.assertRaises(BlockingIOError):
            replacement.recv(4096)
        self.relay.sendto(bytes(range(24)), new_path)
        self.assertEqual(self.receive(replacement)[0], b'\x00\x18' + bytes(range(24)))

    def test_transient_accept_error_keeps_listener_and_existing_peer_alive(self):
        existing = self.tcp()
        pending = socket.create_connection(self.server.address, timeout=1)
        self.sockets.append(pending)

        class FailedAccept:
            def accept(self):
                raise OSError('injected transient accept failure')

        with patch.object(self.server, 'listener', FailedAccept()):
            self.server._accept()
        self.assertEqual(self.server.counts['accept_error'], 1)
        self.assertEqual(len(self.server.peers), 1)
        self.assertEqual(len(self.server.selector.get_map()), 3)
        existing.sendall(b'\x00\x18' + bytes(range(24)))
        self.assertEqual(self.receive(self.relay)[0], bytes(range(24)))
        self.pump(lambda: len(self.server.peers) == 2)

    def test_failed_peer_setup_releases_partial_resources_without_using_capacity(self):
        existing = self.tcp()
        self.server.max_peers = 2
        original_socket = socket.socket
        original_listener = self.server.listener
        original_register = self.server.selector.register
        stages = ('tcp_nonblocking', 'udp_allocation', 'udp_bind', 'udp_connect',
                  'udp_nonblocking', 'tcp_register', 'udp_register')

        for failure_index, stage in enumerate(stages, 1):
            with self.subTest(stage=stage):
                pending = socket.create_connection(self.server.address, timeout=1)
                self.sockets.append(pending)
                allocated = []
                accepted = []

                class FaultSocket:
                    def __init__(self, wrapped, prefix):
                        self.wrapped, self.prefix = wrapped, prefix

                    def __getattr__(self, name):
                        if stage == self.prefix + '_' + name:
                            def fail(*args, **kwargs):
                                raise OSError('injected setup failure')
                            return fail
                        if name == 'setblocking' and stage == self.prefix + '_nonblocking':
                            def fail(*args, **kwargs):
                                raise OSError('injected nonblocking failure')
                            return fail
                        return getattr(self.wrapped, name)

                class AcceptWrapper:
                    def accept(self):
                        tcp, address = original_listener.accept()
                        accepted.append(tcp)
                        return FaultSocket(tcp, 'tcp'), address

                def allocate(*args, **kwargs):
                    is_udp = len(args) > 1 and args[1] == socket.SOCK_DGRAM
                    if is_udp and stage == 'udp_allocation':
                        raise OSError('injected UDP allocation failure')
                    sock = original_socket(*args, **kwargs)
                    if is_udp:
                        allocated.append(sock)
                        return FaultSocket(sock, 'udp')
                    return sock

                def register(sock, events, data):
                    result = original_register(sock, events, data)
                    # Fail after registration to also exercise rollback of a
                    # selector entry that was installed before setup failed.
                    if stage == sock.prefix + '_register':
                        raise OSError('injected selector failure')
                    return result

                with patch.object(self.server, 'listener', AcceptWrapper()), \
                        patch('udp_transport_tunnel.socket.socket', side_effect=allocate), \
                        patch.object(self.server.selector, 'register', side_effect=register):
                    self.server._accept()

                self.assertEqual(self.server.counts['accept_error'], failure_index)
                self.assertEqual(self.server.counts['peers_opened'], 1)
                self.assertEqual(len(self.server.peers), 1)
                self.assertFalse(self.server.retired)
                self.assertEqual(len(self.server.selector.get_map()), 3)
                self.assertEqual(len(accepted), 1)
                self.assertTrue(all(sock.fileno() == -1 for sock in accepted + allocated))
                existing.sendall(b'\x00\x18' + bytes([failure_index]) * 24)
                self.assertEqual(self.receive(self.relay)[0], bytes([failure_index]) * 24)

        # Failed attempts consume no lifetime allocation slots; a healthy new
        # peer can still use the second slot after every injected failure.
        pending = socket.create_connection(self.server.address, timeout=1)
        self.sockets.append(pending)
        self.pump(lambda: len(self.server.peers) == 2)
        pending.sendall(b'\x00\x18' + bytes(range(24)))
        self.assertEqual(self.receive(self.relay)[0], bytes(range(24)))


if __name__ == '__main__':
    unittest.main()

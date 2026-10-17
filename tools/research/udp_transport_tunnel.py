#!/usr/bin/env python3
"""Research-only, payload-transparent UDP/TCP adapter for the 24-byte relay.

Run ``host`` on the emulator host and ``server`` beside the PHP UDP relay.
One TCP connection and one server UDP socket are retained per host UDP source.
There are no keepalives, retries, authentication packets, or packet replays.
The CLI endpoints are deliberately fixed; constructor addresses support local tests.
Server UDP ports stay quarantined until shutdown, including after TCP disconnect.
Restart the PHP relay together with the server to clear its learned endpoints.
"""

import argparse
import errno
import json
import selectors
import signal
import socket
import struct
import time
from collections import Counter
from dataclasses import dataclass, field


PACKET_SIZE = 24
FRAME_SIZE = PACKET_SIZE + 2
MAX_BUFFER = FRAME_SIZE * 256
MAX_PEERS = 256
IDLE_SECONDS = 600.0


@dataclass(eq=False)
class Peer:
    tcp: socket.socket
    source: tuple | None = None
    udp: socket.socket | None = None
    connecting: bool = False
    incoming: bytearray = field(default_factory=bytearray)
    outgoing: bytearray = field(default_factory=bytearray)
    active: float = field(default_factory=time.monotonic)
    closed: bool = False


class Tunnel:
    def __init__(self, *, max_peers=MAX_PEERS, idle_seconds=IDLE_SECONDS):
        if not 1 <= max_peers <= MAX_PEERS or idle_seconds <= 0:
            raise ValueError("invalid peer limit or idle timeout")
        self.selector = selectors.DefaultSelector()
        self.peers = set()
        self.max_peers = max_peers
        self.idle_seconds = idle_seconds
        self.counts = Counter()
        self.stopped = False
        self.closed = False

    def _watch_tcp(self, peer):
        events = selectors.EVENT_READ
        if peer.connecting or peer.outgoing:
            events |= selectors.EVENT_WRITE
        self.selector.modify(peer.tcp, events, ("tcp", peer))

    def _close_peer(self, peer, reason):
        if peer.closed:
            return
        peer.closed = True
        self.peers.discard(peer)
        for sock in (peer.tcp, peer.udp):
            if sock is not None:
                try:
                    self.selector.unregister(sock)
                except KeyError:
                    pass
                sock.close()
        self.counts[reason] += 1

    def _queue(self, peer, payload):
        if len(payload) != PACKET_SIZE:
            self.counts["invalid_udp"] += 1
            return
        if len(peer.outgoing) + FRAME_SIZE > MAX_BUFFER:
            self._close_peer(peer, "buffer_limit")
            return
        peer.outgoing.extend(struct.pack("!H", len(payload)))
        peer.outgoing.extend(payload)
        peer.active = time.monotonic()
        self._watch_tcp(peer)

    def _tcp_event(self, peer, mask):
        try:
            if peer.connecting and mask & selectors.EVENT_WRITE:
                if peer.tcp.getsockopt(socket.SOL_SOCKET, socket.SO_ERROR):
                    self._close_peer(peer, "connect_error")
                    return
                peer.connecting = False
            if mask & selectors.EVENT_READ and not peer.connecting:
                chunk = peer.tcp.recv(4096)
                if not chunk:
                    self._close_peer(peer, "truncated_frame" if peer.incoming else "eof")
                    return
                peer.incoming.extend(chunk)
                while len(peer.incoming) >= 2:
                    length = struct.unpack_from("!H", peer.incoming)[0]
                    if length != PACKET_SIZE:
                        self._close_peer(peer, "invalid_frame")
                        return
                    if len(peer.incoming) < FRAME_SIZE:
                        break
                    payload = bytes(peer.incoming[2:FRAME_SIZE])
                    del peer.incoming[:FRAME_SIZE]
                    peer.active = time.monotonic()
                    self._deliver(peer, payload)
                    self.counts["tcp_packets_received"] += 1
            if mask & selectors.EVENT_WRITE and not peer.connecting and peer.outgoing:
                sent = peer.tcp.send(peer.outgoing)
                if not sent:
                    self._close_peer(peer, "socket_error")
                    return
                del peer.outgoing[:sent]
            self._watch_tcp(peer)
        except BlockingIOError:
            pass
        except OSError:
            self._close_peer(peer, "socket_error")

    def _send_udp(self, sock, payload, target=None):
        try:
            sent = sock.sendto(payload, target) if target else sock.send(payload)
            self.counts["udp_packets_sent" if sent == len(payload) else "udp_dropped"] += 1
        except (BlockingIOError, OSError):
            self.counts["udp_dropped"] += 1

    def step(self, timeout=0.1):
        for key, mask in self.selector.select(timeout):
            kind, peer = key.data
            if peer is not None and peer.closed:
                continue
            if kind == "tcp":
                self._tcp_event(peer, mask)
            elif kind == "listener":
                self._accept()
            elif kind == "retired":
                self._drain_retired(key.fileobj)
            else:
                self._receive_udp(peer)
        now = time.monotonic()
        for peer in list(self.peers):
            if now - peer.active >= self.idle_seconds:
                self._close_peer(peer, "idle_expired")

    def run(self, seconds=None):
        deadline = None if seconds is None else time.monotonic() + seconds
        while not self.stopped:
            remaining = None if deadline is None else deadline - time.monotonic()
            if remaining is not None and remaining <= 0:
                break
            self.step(min(0.1, remaining) if remaining is not None else 0.1)

    def close(self):
        if self.closed:
            return
        self.closed = True
        for peer in list(self.peers):
            self._close_peer(peer, "shutdown")
        for key in list(self.selector.get_map().values()):
            self.selector.unregister(key.fileobj)
            key.fileobj.close()
        self.selector.close()


class HostTunnel(Tunnel):
    def __init__(self, bind=("127.0.0.1", 5055), target=("127.0.0.1", 5056), **kwargs):
        super().__init__(**kwargs)
        self.target = target
        self.sources = {}
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.udp.bind(bind)
        self.udp.setblocking(False)
        self.address = self.udp.getsockname()
        self.selector.register(self.udp, selectors.EVENT_READ, ("udp", None))

    def _close_peer(self, peer, reason):
        if self.sources.get(peer.source) is peer:
            del self.sources[peer.source]
        super()._close_peer(peer, reason)

    def _receive_udp(self, unused):
        for _ in range(32):
            try:
                payload, source = self.udp.recvfrom(65535)
            except BlockingIOError:
                break
            except OSError:
                self.counts["udp_dropped"] += 1
                break
            if len(payload) != PACKET_SIZE:
                self.counts["invalid_udp"] += 1
                continue
            peer = self.sources.get(source)
            if peer is None:
                if len(self.peers) >= self.max_peers:
                    self.counts["peer_limit"] += 1
                    continue
                tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                tcp.setblocking(False)
                result = tcp.connect_ex(self.target)
                if result not in (0, errno.EINPROGRESS, errno.EWOULDBLOCK, errno.EALREADY, 10035, 10036):
                    tcp.close()
                    self.counts["connect_error"] += 1
                    continue
                peer = Peer(tcp=tcp, source=source, connecting=result != 0)
                self.sources[source] = peer
                self.peers.add(peer)
                self.selector.register(tcp, selectors.EVENT_READ | selectors.EVENT_WRITE, ("tcp", peer))
                self.counts["peers_opened"] += 1
            self._queue(peer, payload)
            self.counts["udp_packets_received"] += 1

    def _deliver(self, peer, payload):
        self._send_udp(self.udp, payload, peer.source)


class ServerTunnel(Tunnel):
    def __init__(self, bind=("0.0.0.0", 5056), target=("127.0.0.1", 5055), **kwargs):
        super().__init__(**kwargs)
        self.retired = set()
        self.target = target
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.listener.bind(bind)
        self.listener.listen(32)
        self.listener.setblocking(False)
        self.address = self.listener.getsockname()
        self.selector.register(self.listener, selectors.EVENT_READ, ("listener", None))

    def _accept(self):
        for _ in range(32):
            try:
                tcp, _ = self.listener.accept()
            except BlockingIOError:
                break
            except OSError:
                self.counts["accept_error"] += 1
                break
            if len(self.peers) + len(self.retired) >= self.max_peers:
                tcp.close()
                self.counts["peer_limit"] += 1
                continue
            udp = None
            try:
                tcp.setblocking(False)
                udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                udp.bind(("127.0.0.1", 0))
                udp.connect(self.target)
                udp.setblocking(False)
                peer = Peer(tcp=tcp, udp=udp)
                self.selector.register(tcp, selectors.EVENT_READ, ("tcp", peer))
                self.selector.register(udp, selectors.EVENT_READ, ("udp", peer))
            except OSError:
                # Neither socket has processed payload yet, so PHP cannot know
                # this UDP endpoint. It is safe to release this failed setup.
                for sock in (tcp, udp):
                    if sock is None:
                        continue
                    try:
                        self.selector.unregister(sock)
                    except (KeyError, ValueError, OSError):
                        pass
                    try:
                        sock.close()
                    except OSError:
                        pass
                self.counts["accept_error"] += 1
                continue
            self.peers.add(peer)
            self.counts["peers_opened"] += 1

    def _close_peer(self, peer, reason):
        if peer.closed:
            return
        # PHP can retain this endpoint after TCP disconnect (HTTP room heartbeat).
        # Never let another TCP identity inherit its port during this process.
        udp = peer.udp
        peer.udp = None
        super()._close_peer(peer, reason)
        peer.udp = udp
        self.retired.add(udp)
        self.selector.modify(udp, selectors.EVENT_READ, ("retired", None))
        self.counts["udp_sockets_quarantined"] += 1

    def _drain_retired(self, udp):
        for _ in range(32):
            try:
                udp.recv(65535)
                self.counts["quarantined_packets_dropped"] += 1
            except BlockingIOError:
                break
            except OSError:
                break

    def _receive_udp(self, peer):
        for _ in range(32):
            try:
                payload = peer.udp.recv(65535)
            except BlockingIOError:
                break
            except OSError:
                self.counts["udp_dropped"] += 1
                break
            self._queue(peer, payload)
            self.counts["udp_packets_received"] += 1
            if peer.closed:
                break

    def _deliver(self, peer, payload):
        self._send_udp(peer.udp, payload)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("host", "server"))
    parser.add_argument("--seconds", type=float, help="stop after this many seconds")
    args = parser.parse_args()
    if args.seconds is not None and not (0 < args.seconds < float("inf")):
        parser.error("--seconds must be positive and finite")
    tunnel = HostTunnel() if args.mode == "host" else ServerTunnel()

    def stop(signum, frame):
        tunnel.stopped = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    print(json.dumps({"mode": args.mode, "state": "started"}), flush=True)
    try:
        tunnel.run(args.seconds)
    finally:
        tunnel.close()
        print(json.dumps({"mode": args.mode, "state": "stopped", "counts": dict(tunnel.counts)}), flush=True)


if __name__ == "__main__":
    main()

import socket
import threading
import time
import secrets


class Discovery:
    """LAN peer discovery using the existing MYMSG/1 UDP protocol.

    The public interface and wire format remain compatible with older
    MYMSG clients. Peers are retained until their last response expires,
    rather than being erased at the start of every discovery sweep.
    """

    PORT = 5001
    BROADCAST = "255.255.255.255"

    REQUEST = b"MYMSG/1 DISCOVER "
    RESPONSE = b"MYMSG/1 HERE "

    def __init__(self, interval=5, window=2, peer_timeout=30):
        self.interval = interval
        self.window = window
        self.peer_timeout = max(float(peer_timeout), float(interval + window))

        # host -> monotonic timestamp of the most recent valid response
        self._peers = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._socket = None
        self._local_addresses = self._get_local_addresses()

    @staticmethod
    def _get_local_addresses():
        """Collect local IPv4 addresses without requiring third-party modules."""
        addresses = {"127.0.0.1"}

        # Hostname resolution catches addresses configured in the system's
        # hosts/DNS configuration.
        try:
            hostname = socket.gethostname()
            for item in socket.getaddrinfo(
                hostname, None, socket.AF_INET, socket.SOCK_DGRAM
            ):
                addresses.add(item[4][0])
        except OSError:
            pass

        try:
            addresses.update(socket.gethostbyname_ex(socket.gethostname())[2])
        except OSError:
            pass

        # Determine the source address selected for the default route.
        # UDP connect() does not transmit a packet.
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("192.0.2.1", 9))
            addresses.add(probe.getsockname()[0])
        except OSError:
            pass
        finally:
            probe.close()

        # On Linux, enumerate addresses on every interface. fcntl is
        # optional so importing this module remains portable.
        try:
            import fcntl
            import struct

            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
                for _, ifname in socket.if_nameindex():
                    name = ifname.encode("utf-8")[:15]
                    request = struct.pack("256s", name)
                    try:
                        result = fcntl.ioctl(probe.fileno(), 0x8915, request)
                        addresses.add(socket.inet_ntoa(result[20:24]))
                    except OSError:
                        continue
        except (ImportError, OSError, AttributeError):
            pass

        return addresses

    @property
    def peers(self):
        now = time.monotonic()
        with self._lock:
            self._expire_peers(now)
            return list(self._peers)

    def _expire_peers(self, now):
        expired = [
            host for host, last_seen in self._peers.items()
            if now - last_seen > self.peer_timeout
        ]
        for host in expired:
            del self._peers[host]

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # SO_REUSEPORT is not available on every platform. It is not
            # required for normal operation, so treat it as optional.
            if hasattr(socket, "SO_REUSEPORT"):
                try:
                    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
                except OSError:
                    pass

            sock.bind(("", self.PORT))
            sock.settimeout(0.25)
        except OSError:
            sock.close()
            raise

        self._socket = sock
        self._stop.clear()
        self._local_addresses = self._get_local_addresses()

        self._thread = threading.Thread(
            target=self._sweep,
            args=(sock,),
            name="MYMSG-discovery",
            daemon=True,
        )
        self._thread.start()

    def _sweep(self, sock):
        while not self._stop.is_set():
            token = secrets.token_bytes(8)

            try:
                sock.sendto(
                    self.REQUEST + token,
                    (self.BROADCAST, self.PORT),
                )
            except OSError:
                if not self._stop.is_set():
                    time.sleep(0.25)
                continue

            deadline = time.monotonic() + self.window

            while not self._stop.is_set():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break

                try:
                    data, address = sock.recvfrom(1024)
                except socket.timeout:
                    continue
                except OSError:
                    return

                host = address[0]

                # Ignore loopback and every local interface address. This
                # also protects against receiving our own broadcast.
                if host in self._local_addresses:
                    continue

                if data.startswith(self.REQUEST):
                    # Preserve the original MYMSG/1 request/response format.
                    try:
                        sock.sendto(
                            self.RESPONSE + data[len(self.REQUEST):],
                            address,
                        )
                    except OSError:
                        if self._stop.is_set():
                            return

                elif data == self.RESPONSE + token:
                    with self._lock:
                        self._peers[host] = time.monotonic()
                        self._expire_peers(time.monotonic())

            self._stop.wait(self.interval)

    def stop(self):
        self._stop.set()

        sock = self._socket
        if sock:
            try:
                sock.close()
            except OSError:
                pass

        thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=2)

        self._thread = None
        self._socket = None


if __name__ == "__main__":
    discovery = Discovery()
    discovery.start()

    try:
        while True:
            print("Available peers:", discovery.peers)
            time.sleep(1)
    except KeyboardInterrupt:
        discovery.stop()

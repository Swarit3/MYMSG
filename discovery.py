import socket
import threading
import time
import secrets

from config import NAME, DISCOVERY_PORT


class Discovery:
    """LAN peer discovery using MYMSG/1 UDP broadcasts."""

    PORT = DISCOVERY_PORT
    BROADCAST = "255.255.255.255"

    REQUEST = b"MYMSG/1 DISCOVER "
    RESPONSE = b"MYMSG/1 HERE "

    def __init__(self, interval=5, window=2, peer_timeout=30):
        self.interval = interval
        self.window = window
        self.peer_timeout = max(float(peer_timeout), float(interval + window))
        self.name = str(NAME).strip() or socket.gethostname()

        # IP -> last-seen monotonic timestamp; names are kept separately so
        # the public .peers interface remains a list of IP addresses.
        self._peers = {}
        self._peer_names = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None
        self._socket = None
        self._local_addresses = self._get_local_addresses()

    @staticmethod
    def _get_local_addresses():
        addresses = {"127.0.0.1"}

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

        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(("192.0.2.1", 9))
            addresses.add(probe.getsockname()[0])
        except OSError:
            pass
        finally:
            probe.close()

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

    @property
    def peer_names(self):
        now = time.monotonic()
        with self._lock:
            self._expire_peers(now)
            return self._peer_names.copy()

    def _expire_peers(self, now):
        expired = [
            host for host, last_seen in self._peers.items()
            if now - last_seen > self.peer_timeout
        ]
        for host in expired:
            del self._peers[host]
            self._peer_names.pop(host, None)

    def start(self):
        if self._thread and self._thread.is_alive():
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
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
            own_token = secrets.token_bytes(8)
            try:
                sock.sendto(
                    self.REQUEST + own_token,
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
                if host in self._local_addresses:
                    continue

                if data.startswith(self.REQUEST):
                    token = data[len(self.REQUEST):]
                    if len(token) != 8:
                        continue
                    response = (
                        self.RESPONSE
                        + token.hex().encode("ascii")
                        + b" "
                        + self.name.encode("utf-8")
                    )
                    try:
                        sock.sendto(response, address)
                    except OSError:
                        if self._stop.is_set():
                            return

                elif data.startswith(self.RESPONSE):
                    payload = data[len(self.RESPONSE):]
                    token_hex, separator, encoded_name = payload.partition(b" ")
                    if not separator or token_hex != own_token.hex().encode("ascii"):
                        continue
                    try:
                        peer_name = encoded_name.decode("utf-8").strip()
                    except UnicodeDecodeError:
                        continue
                    if not peer_name:
                        continue
                    now = time.monotonic()
                    with self._lock:
                        self._peers[host] = now
                        self._peer_names[host] = peer_name
                        self._expire_peers(now)

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
            print("Available peers:", discovery.peer_names)
            time.sleep(1)
    except KeyboardInterrupt:
        discovery.stop()

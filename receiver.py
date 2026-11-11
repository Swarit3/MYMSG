import socket
import threading

from config import MESSAGE_PORT


class Receiver:
    """Receive messages and pairing requests over the same TCP port."""

    PAIR_REQUEST = b"\x00MYMSG/1 PAIR\x00"
    MESSAGE_PREFIX = b"\x00MYMSG/1 MESSAGE\x00"
    PAIR_ACCEPTED = b"\x06"
    PAIR_DECLINED = b"\x15"

    def __init__(self, host="0.0.0.0", port=MESSAGE_PORT):
        self.host = host
        self.port = port
        self.on_message = None
        self.on_request = None
        self._running = threading.Event()
        self._socket = None
        self._thread = None

    def start(self):
        if self._running.is_set():
            return

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind((self.host, self.port))
        sock.listen()
        sock.settimeout(1)

        self._socket = sock
        self._running.set()
        self._thread = threading.Thread(target=self._accept_loop, daemon=True)
        self._thread.start()

    def _accept_loop(self):
        while self._running.is_set():
            try:
                conn, address = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            threading.Thread(
                target=self._handle_connection,
                args=(conn, address),
                daemon=True,
            ).start()

    @staticmethod
    def _read_remaining(conn):
        chunks = []
        while True:
            chunk = conn.recv(65536)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def _read_packet(self, conn):
        """Identify a protocol prefix without waiting for a pairing reply."""
        prefixes = (self.PAIR_REQUEST, self.MESSAGE_PREFIX)
        initial = bytearray()

        while any(prefix.startswith(initial) for prefix in prefixes):
            if bytes(initial) in prefixes:
                return bytes(initial), b""
            chunk = conn.recv(1)
            if not chunk:
                break
            initial.extend(chunk)

        return None, bytes(initial) + self._read_remaining(conn)

    def _handle_connection(self, conn, address):
        with conn:
            try:
                packet_type, payload = self._read_packet(conn)

                if packet_type == self.PAIR_REQUEST:
                    accepted = bool(self.on_request and self.on_request(address[0]))
                    conn.sendall(
                        self.PAIR_ACCEPTED if accepted else self.PAIR_DECLINED
                    )
                    return

                if packet_type == self.MESSAGE_PREFIX:
                    data = self._read_remaining(conn)
                else:
                    # Accept unframed messages from older MYMSG clients too.
                    data = payload

                if data and self.on_message:
                    self.on_message(data, address)
            except OSError:
                pass

    def stop(self):
        self._running.clear()

        if self._socket:
            try:
                self._socket.close()
            except OSError:
                pass

        if self._thread:
            self._thread.join(timeout=2)

        self._thread = None
        self._socket = None

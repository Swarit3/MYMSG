import socket
import threading


class Receiver:
    def __init__(self, host="0.0.0.0", port=5000):
        self.host = host
        self.port = port

        self.on_message = None

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

        self._thread = threading.Thread(
            target=self._accept_loop,
            daemon=True
        )
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
                daemon=True
            ).start()

    def _handle_connection(self, conn, address):
        with conn:
            try:
                data = conn.recv(4096)

                if data and self.on_message:
                    self.on_message(data, address)

            except OSError:
                pass

    def stop(self):
        self._running.clear()

        if self._socket:
            self._socket.close()

        if self._thread:
            self._thread.join(timeout=2)

        self._thread = None
        self._socket = None

import socket
import threading


class ConnectionRequestor:
    PORT = 5002

    REQUEST = b"MYMSG/1 PAIR"
    ACCEPT = b"MYMSG/1 ACCEPT"
    REJECT = b"MYMSG/1 REJECT"

    def __init__(self, port=PORT, timeout=5):
        self.port = port
        self.timeout = timeout
        self.on_request = None

        self._running = False
        self._socket = None
        self._thread = None

    def request(self, host):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout)
            sock.connect((host, self.port))
            sock.sendall(self.REQUEST)

            response = sock.recv(1024)

        if response == self.ACCEPT:
            return True
        if response == self.REJECT:
            return False

        raise ConnectionError("Invalid response from peer")

    def start(self):
        if self._running:
            return

        self._running = True
        self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._socket.bind(("0.0.0.0", self.port))
        self._socket.listen()
        self._socket.settimeout(1)

        self._thread = threading.Thread(
            target=self._listen,
            daemon=True
        )
        self._thread.start()

    def stop(self):
        self._running = False

        if self._socket:
            self._socket.close()

        if self._thread:
            self._thread.join()

    def _listen(self):
        while self._running:
            try:
                conn, address = self._socket.accept()
            except socket.timeout:
                continue
            except OSError:
                break

            with conn:
                conn.settimeout(self.timeout)

                try:
                    data = conn.recv(1024)

                    if data != self.REQUEST:
                        continue

                    accepted = False

                    if self.on_request:
                        accepted = bool(self.on_request(address[0]))

                    response = self.ACCEPT if accepted else self.REJECT
                    conn.sendall(response)

                except OSError:
                    pass

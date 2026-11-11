import argparse
import secrets
import socket

from config import DISCOVERY_PORT, MESSAGE_PORT


class Destination:
    """Discover peers, send messages, and request pairing over shared ports."""

    DISCOVERY_REQUEST = b"MYMSG/1 DISCOVER "
    DISCOVERY_RESPONSE = b"MYMSG/1 HERE "

    MESSAGE_PREFIX = b"\x00MYMSG/1 MESSAGE\x00"
    PAIR_REQUEST = b"\x00MYMSG/1 PAIR\x00"
    PAIR_ACCEPTED = b"\x06"
    PAIR_DECLINED = b"\x15"

    def __init__(self, host, port=MESSAGE_PORT, timeout=5):
        self.host = host
        self.port = port
        self.timeout = timeout

    def send(self, data):
        """Send bytes to the remote Receiver over the shared TCP port."""
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout)
            sock.connect((self.host, self.port))
            sock.sendall(self.MESSAGE_PREFIX + data)

    def request_connection(self, timeout=35):
        """Ask the remote Receiver to approve pairing; return its decision."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect((self.host, self.port))
            sock.sendall(self.PAIR_REQUEST)
            response = sock.recv(1)

        if response == self.PAIR_ACCEPTED:
            return True
        if response == self.PAIR_DECLINED:
            return False
        raise ConnectionError("Invalid or missing pairing response")

    def request(self):
        """Compatibility alias for the previous pairing call spelling."""
        return self.request_connection()

    @classmethod
    def discover(cls, timeout=2):
        """Broadcast discovery and return {IP: client_name}."""
        peers = {}
        token = secrets.token_bytes(8)
        expected_token = token.hex().encode("ascii")

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            sock.settimeout(timeout)
            sock.sendto(
                cls.DISCOVERY_REQUEST + token,
                ("255.255.255.255", DISCOVERY_PORT),
            )

            while True:
                try:
                    data, address = sock.recvfrom(1024)
                except socket.timeout:
                    break

                if not data.startswith(cls.DISCOVERY_RESPONSE):
                    continue

                payload = data[len(cls.DISCOVERY_RESPONSE):]
                token_hex, separator, encoded_name = payload.partition(b" ")
                if not separator or token_hex != expected_token:
                    continue

                try:
                    name = encoded_name.decode("utf-8").strip()
                except UnicodeDecodeError:
                    continue

                if name:
                    peers[address[0]] = name

        return peers


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MYMSG destination utility")
    parser.add_argument("host", nargs="?")
    parser.add_argument("message", nargs="?")
    parser.add_argument("--port", type=int, default=MESSAGE_PORT)
    parser.add_argument("--discover", action="store_true")
    args = parser.parse_args()

    if args.discover:
        for ip, name in Destination.discover().items():
            print(f"{name} ({ip})")
    elif args.host and args.message:
        Destination(args.host, args.port).send(args.message.encode("utf-8"))
        print("Message transmitted.")
    else:
        parser.print_help()

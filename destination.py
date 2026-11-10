import socket


class Destination:
    DISCOVERY_PORT = 5001
    DISCOVERY_REQUEST = b"MYMSG/1 DISCOVER"
    DISCOVERY_RESPONSE = b"MYMSG/1 HERE"

    def __init__(self, host, port=5000, timeout=5):
        self.host = host
        self.port = port
        self.timeout = timeout

    def send(self, data):
        """Send bytes to the remote receiver over TCP."""
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(self.timeout)
            sock.connect((self.host, self.port))
            sock.sendall(data)

    @classmethod
    def discover(cls, timeout=2):
        """Broadcast a discovery request and return responding IPs."""
        peers = set()

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.setsockopt(
                socket.SOL_SOCKET,
                socket.SO_BROADCAST,
                1
            )
            sock.settimeout(timeout)

            sock.sendto(
                cls.DISCOVERY_REQUEST,
                ("255.255.255.255", cls.DISCOVERY_PORT)
            )

            while True:
                try:
                    data, address = sock.recvfrom(1024)
                except socket.timeout:
                    break

                if data == cls.DISCOVERY_RESPONSE:
                    peers.add(address[0])

        return list(peers)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="TCP message destination and LAN discovery"
    )

    parser.add_argument("host", nargs="?")
    parser.add_argument("message", nargs="?")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--discover", action="store_true")

    args = parser.parse_args()

    if args.discover:
        for peer in Destination.discover():
            print(peer)

    elif args.host and args.message:
        destination = Destination(args.host, args.port)
        destination.send(args.message.encode("utf-8"))
        print("Message transmitted.")

    else:
        parser.print_help()

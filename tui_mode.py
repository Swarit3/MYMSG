import curses
import queue
import threading
import time
import textwrap
from collections import defaultdict

from discovery import Discovery
from receiver import Receiver
from destination import Destination
from connection_requestor import ConnectionRequestor


class Interface:
    def __init__(self):
        self.discovery = Discovery()
        self.receiver = Receiver()
        self.requestor = ConnectionRequestor()

        self.events = queue.Queue()
        self.messages = defaultdict(list)
        self.peers = []
        self.selected = 0
        self.selected_host = None
        self.paired = set()

        self.focus = 2
        self.input = ""
        self.cursor = 0
        self.input_offset = 0
        self.chat_scroll = 0

        self.status = "Starting..."
        self.running = True
        self.pending_request = None

        self.receiver.on_message = self.network_message
        self.requestor.on_request = self.network_request

        self.discovery.start()
        self.receiver.start()
        self.requestor.start()

    # ---------------- Networking ----------------

    def network_message(self, data, address):
        message = data.decode("utf-8", errors="replace")
        self.events.put(("message", address[0], message))

    def network_request(self, host):
        request = {
            "host": host,
            "accepted": False,
            "event": threading.Event()
        }

        self.events.put(("request", request))
        request["event"].wait(30)
        return request["accepted"]

    def connect(self, host):
        def worker():
            try:
                result = self.requestor.request(host)
                self.events.put(("connected", host, result, None))
            except Exception as error:
                self.events.put(("connected", host, False, str(error)))

        threading.Thread(target=worker, daemon=True).start()
        self.status = f"Requesting connection to {host}"

    def send_message(self, host, message):
        def worker():
            try:
                Destination(host).send(message.encode("utf-8"))
                self.events.put(("sent", host, message, None))
            except Exception as error:
                self.events.put(("sent", host, message, str(error)))

        threading.Thread(target=worker, daemon=True).start()
        self.status = f"Sending to {host}..."

    # ---------------- State ----------------

    def process_events(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break

            kind = event[0]

            if kind == "message":
                _, host, message = event
                self.messages[host].append(
                    ("Peer", message, time.strftime("%H:%M"))
                )
                self.status = f"Message received from {host}"

            elif kind == "sent":
                _, host, message, error = event

                if error:
                    self.messages[host].append(
                        ("Failed", message, time.strftime("%H:%M"))
                    )
                    self.status = f"Send failed: {error}"
                else:
                    self.messages[host].append(
                        ("You", message, time.strftime("%H:%M"))
                    )
                    self.status = f"Message sent to {host}"

            elif kind == "connected":
                _, host, accepted, error = event

                if error:
                    self.status = f"Connection failed: {error}"
                elif accepted:
                    self.paired.add(host)
                    self.status = f"Connected to {host}"
                else:
                    self.status = f"{host} declined the request"

            elif kind == "request":
                self.pending_request = event[1]

    def refresh_peers(self):
        discovered = self.discovery.peers

        old_host = self.selected_host

        # Paired peers remain visible even when discovery stops seeing them.
        self.peers = sorted(set(discovered) | self.paired)

        if old_host in self.peers:
            self.selected = self.peers.index(old_host)
        else:
            self.selected = min(
                self.selected,
                max(0, len(self.peers) - 1)
            )

        self.selected_host = (
            self.peers[self.selected] if self.peers else None
        )

    def current_host(self):
        if not self.peers:
            return None

        self.selected = max(
            0, min(self.selected, len(self.peers) - 1)
        )
        return self.peers[self.selected]

    # ---------------- Drawing helpers ----------------

    def put(self, screen, y, x, value, attr=0):
        height, width = screen.getmaxyx()

        if y < 0 or y >= height or x < 0 or x >= width:
            return

        value = str(value)
        value = value[:max(0, width - x - 1)]

        try:
            screen.addstr(y, x, value, attr)
        except curses.error:
            pass

    def horizontal(self, screen, y, x, length, char):
        for i in range(length):
            try:
                screen.addch(y, x + i, char)
            except curses.error:
                break

    def vertical(self, screen, y, x, length, char):
        for i in range(length):
            try:
                screen.addch(y + i, x, char)
            except curses.error:
                break

    def box(self, screen, y, x, height, width, title, active=False):
        if height < 2 or width < 2:
            return

        color = curses.color_pair(2) if active else curses.color_pair(1)

        try:
            screen.addch(y, x, curses.ACS_ULCORNER, color)
            screen.addch(y, x + width - 1, curses.ACS_URCORNER, color)
            screen.addch(y + height - 1, x, curses.ACS_LLCORNER, color)
            screen.addch(
                y + height - 1, x + width - 1,
                curses.ACS_LRCORNER, color
            )

            self.horizontal(
                screen, y, x + 1, width - 2, curses.ACS_HLINE
            )
            self.horizontal(
                screen, y + height - 1,
                x + 1, width - 2, curses.ACS_HLINE
            )
            self.vertical(
                screen, y + 1, x, height - 2, curses.ACS_VLINE
            )
            self.vertical(
                screen, y + 1, x + width - 1,
                height - 2, curses.ACS_VLINE
            )
        except curses.error:
            pass

        self.put(
            screen, y, x + 2, f" {title} ",
            color | curses.A_BOLD
        )

    # ---------------- Peer panel ----------------

    def draw_peers(self, screen, y, x, height, width):
        self.box(
            screen, y, x, height, width,
            "Peers", self.focus == 0
        )

        if not self.peers:
            self.put(screen, y + 2, x + 2, "Searching for peers...",
                     curses.A_DIM)
            return

        visible = height - 3
        start = 0

        if self.selected >= visible:
            start = self.selected - visible + 1

        for index, host in enumerate(self.peers[start:start + visible]):
            actual = start + index
            paired = host in self.paired

            marker = "[+]" if paired else "[ ]"
            label = f"{marker} {host}"

            if paired and host in self.discovery.peers:
                attr = curses.color_pair(3)  # Online: green
            elif paired:
                attr = curses.A_DIM         # Offline: grey
            else:
                attr = curses.A_NORMAL

            if actual == self.selected:
                attr |= curses.A_REVERSE | curses.A_BOLD

            self.put(screen, y + 1 + index, x + 2, label, attr)

    # ---------------- Conversation panel ----------------

    def conversation_lines(self, host, width):
        lines = []

        for sender, message, timestamp in self.messages[host]:
            prefix = f"[{timestamp}] {sender}: "
            available = max(1, width - len(prefix) - 3)

            wrapped = textwrap.wrap(
                message,
                available,
                replace_whitespace=False,
                drop_whitespace=False
            ) or [""]

            lines.append((prefix + wrapped[0], sender))

            for part in wrapped[1:]:
                lines.append((" " * len(prefix) + part, sender))

        return lines


    def draw_chat(self, screen, y, x, height, width):
        self.box(
            screen, y, x, height, width,
            "Conversation", self.focus in (1, 2)
        )

        host = self.current_host()

        if not host:
            self.put(screen, y + 2, x + 2, "Select a peer to begin.")
            return

        self.put(
            screen, y + 1, x + 2,
            host,
            curses.color_pair(2) | curses.A_BOLD
        )

        # Reserve the last three rows for the message input.
        available = height - 6
        lines = self.conversation_lines(host, width)

        max_scroll = max(0, len(lines) - available)
        self.chat_scroll = min(self.chat_scroll, max_scroll)

        end = len(lines) - self.chat_scroll
        start = max(0, end - available)

        for index, (line, sender) in enumerate(lines[start:end]):
            attr = curses.A_NORMAL

            if sender == "You":
                attr = curses.color_pair(3)
            elif sender == "Failed":
                attr = curses.color_pair(4)

            self.put(screen, y + 2 + index, x + 2, line, attr)

        if self.chat_scroll:
            self.put(
                screen, y + height - 5, x + 2,
                f"Older messages: {self.chat_scroll} lines above",
                curses.A_DIM
            )

        # Message input is now inside the conversation panel.
        input_y = y + height - 3
        self.horizontal(screen, input_y - 1, x + 1, width - 2, curses.ACS_HLINE)

        if host not in self.paired:
            self.put(
                screen, input_y, x + 2,
                "Connect to this peer before sending.",
                curses.A_DIM
            )
            return

        available_input = max(1, width - 5)

        if self.cursor < self.input_offset:
            self.input_offset = self.cursor
        elif self.cursor >= self.input_offset + available_input:
            self.input_offset = self.cursor - available_input + 1

        visible = self.input[
            self.input_offset:self.input_offset + available_input
        ]

        self.put(
            screen, input_y, x + 2,
            visible,
            curses.color_pair(2) if self.focus == 2 else curses.A_NORMAL
        )

        if self.focus == 2:
            try:
                screen.move(
                    input_y,
                    min(x + 2 + self.cursor - self.input_offset, x + width - 2)
                )
            except curses.error:
                pass



    # ---------------- Status and dialogs ----------------

    def draw_status(self, screen, y, width):
        self.put(screen, y, 1, self.status, curses.color_pair(2))
        self.put(
            screen, y + 1, 1,
            "TAB: Focus   UP/DOWN: Navigate   ENTER: Select/Send   "
            "C: Connect   PGUP/PGDN: Scroll   Q: Quit",
            curses.A_DIM
        )

    def draw_request(self, screen):
        if not self.pending_request:
            return

        height, width = screen.getmaxyx()
        box_width = min(54, width - 4)
        box_height = 7

        y = (height - box_height) // 2
        x = (width - box_width) // 2

        self.box(
            screen, y, x, box_height, box_width,
            "Pairing request", True
        )

        self.put(
            screen, y + 2, x + 2,
            f"{self.pending_request['host']} wants to connect."
        )
        self.put(
            screen, y + 4, x + 2,
            "Y: Accept     N: Reject",
            curses.A_BOLD
        )

    # ---------------- Full screen draw ----------------

    def draw(self, screen):
        screen.erase()

        height, width = screen.getmaxyx()

        if height < 16 or width < 60:
            self.put(screen, 1, 1, "Terminal too small. Minimum: 60x16.")
            screen.noutrefresh()
            curses.doupdate()
            return

        self.put(
            screen, 0, 2, "MYMSG",
            curses.color_pair(2) | curses.A_BOLD
        )
        self.put(
            screen, 1, 2, "DECENTRALIZED MESSENGER",
            curses.A_DIM
        )

        top = 3
        bottom = height - 2
        panel_height = bottom - top

        peer_width = max(22, width // 3)
        chat_width = width - peer_width

        self.draw_peers(
            screen, top, 0, panel_height, peer_width
        )
        self.draw_chat(
            screen, top, peer_width,
            panel_height, chat_width
        )

        self.draw_status(screen, height - 2, width)
        self.draw_request(screen)

        screen.noutrefresh()
        curses.doupdate()

    # ---------------- Input handling ----------------

    def accept_request(self, accepted):
        request = self.pending_request

        if request is None:
            return

        request["accepted"] = accepted
        request["event"].set()

        if accepted:
            self.paired.add(request["host"])
            self.status = f"Accepted {request['host']}"
        else:
            self.status = f"Rejected {request['host']}"

        self.pending_request = None

    def _handle_input_key(self, key):
        if key in ("\n", "\r", curses.KEY_ENTER):
            host = self.current_host()

            if not self.input.strip():
                return

            if not host:
                self.status = "Select a peer first."
            elif host not in self.paired:
                self.status = "Connect to this peer first."
            else:
                message = self.input
                self.input = ""
                self.cursor = 0
                self.input_offset = 0
                self.send_message(host, message)

        elif key in (curses.KEY_BACKSPACE, "\b", "\x7f"):
            if self.cursor > 0:
                self.input = (
                    self.input[:self.cursor - 1]
                    + self.input[self.cursor:]
                )
                self.cursor -= 1

        elif key == curses.KEY_DC:
            self.input = (
                self.input[:self.cursor]
                + self.input[self.cursor + 1:]
            )

        elif key == curses.KEY_LEFT:
            self.cursor = max(0, self.cursor - 1)

        elif key == curses.KEY_RIGHT:
            self.cursor = min(len(self.input), self.cursor + 1)

        elif key == curses.KEY_HOME:
            self.cursor = 0

        elif key == curses.KEY_END:
            self.cursor = len(self.input)

        elif key == "\x15":  # Ctrl+U
            self.input = ""
            self.cursor = 0
            self.input_offset = 0

        elif isinstance(key, str) and key.isprintable():
            self.input = (
                self.input[:self.cursor]
                + key
                + self.input[self.cursor:]
            )
            self.cursor += len(key)

    def handle_key(self, key):
        if self.pending_request:
            if key in ("y", "Y"):
                self.accept_request(True)
            elif key in ("n", "N", "\x1b"):
                self.accept_request(False)
            return

        if key == "\t":
            self.focus = (self.focus + 1) % 3
            return

        if key == "\x1b":
            if self.focus == 2:
                self.focus = 1
            return

        if key in ("q", "Q") and self.focus != 2:
            self.running = False
            return

        if self.focus == 0:
            if key == curses.KEY_UP:
                self.selected = max(0, self.selected - 1)
                self.selected_host = self.current_host()
                self.chat_scroll = 0

            elif key == curses.KEY_DOWN:
                self.selected = min(
                    max(0, len(self.peers) - 1),
                    self.selected + 1
                )
                self.selected_host = self.current_host()
                self.chat_scroll = 0

            elif key in ("\n", "\r", curses.KEY_ENTER):
                self.focus = 1

            elif key in ("c", "C"):
                host = self.current_host()

                if host:
                    if host in self.paired:
                        self.status = f"Already connected to {host}"
                    else:
                        self.connect(host)

        elif self.focus == 1:
            if key == curses.KEY_PPAGE:
                self.chat_scroll += 8
            elif key == curses.KEY_NPAGE:
                self.chat_scroll = max(0, self.chat_scroll - 8)
            else:
                # Any other key moves directly into the message input.
                self.focus = 2
                self._handle_input_key(key)

        elif self.focus == 2:
            if key == curses.KEY_PPAGE:
                self.chat_scroll += 8
            elif key == curses.KEY_NPAGE:
                self.chat_scroll = max(0, self.chat_scroll - 8)
            else:
                self._handle_input_key(key)

    # ---------------- Main loop ----------------

    def run(self, screen):
        curses.curs_set(1)
        screen.keypad(True)
        screen.timeout(50)

        curses.start_color()
        curses.use_default_colors()

        curses.init_pair(1, curses.COLOR_WHITE, -1)
        curses.init_pair(2, curses.COLOR_CYAN, -1)
        curses.init_pair(3, curses.COLOR_GREEN, -1)
        curses.init_pair(4, curses.COLOR_RED, -1)

        while self.running:
            self.process_events()
            self.refresh_peers()
            self.draw(screen)

            try:
                key = screen.get_wch()
                self.handle_key(key)
            except curses.error:
                pass

    def stop(self):
        self.running = False

        for component in (
            self.discovery,
            self.receiver,
            self.requestor
        ):
            try:
                component.stop()
            except Exception:
                pass


def main():
    interface = Interface()

    try:
        curses.wrapper(interface.run)
    finally:
        interface.stop()


if __name__ == "__main__":
    main()

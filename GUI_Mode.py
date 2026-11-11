#!/usr/bin/env python3
"""PySide6 interface for MYMSG. Uses the same networking modules as tui_mode.py."""

import html
import queue
import sys
import threading
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QTextCursor, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from discovery import Discovery
from receiver import Receiver
from destination import Destination
from chat_store import ChatStore


class MessageInput(QLineEdit):
    """Single-line composer; PageUp/PageDown are reserved for chat scrolling."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scroll_chat = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_PageUp:
            if self.scroll_chat:
                self.scroll_chat(-8)
            event.accept()
            return
        if event.key() == Qt.Key_PageDown:
            if self.scroll_chat:
                self.scroll_chat(8)
            event.accept()
            return
        super().keyPressEvent(event)


class Interface(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("MYMSG — Decentralized Messenger")
        self.resize(1050, 680)
        self.setMinimumSize(720, 460)

        self.events = queue.Queue()
        self.store = ChatStore()
        self.messages = self.store.load_messages()
        self.peers = []
        self.paired = self.store.paired_peers()
        self.selected_host = None
        self.pending_request = None
        self.running = True

        self.discovery = Discovery()
        self.receiver = Receiver()
        self.receiver.on_message = self.network_message
        self.receiver.on_request = self.network_request

        self._build_ui()
        self._apply_style()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_state)
        self.timer.start(100)

        self.discovery.start()
        self.receiver.start()
        self.statusBar().showMessage("Searching for peers…")

    # ---------------- UI ----------------

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        header = QHBoxLayout()
        branding = QVBoxLayout()
        title = QLabel("MYMSG")
        title.setObjectName("brandTitle")
        subtitle = QLabel("DECENTRALIZED MESSENGER")
        subtitle.setObjectName("subtitle")
        branding.addWidget(title)
        branding.addWidget(subtitle)
        header.addLayout(branding)
        header.addStretch(1)
        self.connection_label = QLabel("●  Initializing")
        self.connection_label.setObjectName("connectionLabel")
        header.addWidget(self.connection_label, alignment=Qt.AlignVCenter)
        layout.addLayout(header)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        peer_panel = QWidget()
        peer_layout = QVBoxLayout(peer_panel)
        peer_layout.setContentsMargins(0, 0, 0, 0)
        peer_layout.setSpacing(8)
        peer_heading = QLabel("PEERS")
        peer_heading.setObjectName("sectionHeading")
        peer_layout.addWidget(peer_heading)
        self.peer_list = QListWidget()
        self.peer_list.setObjectName("peerList")
        self.peer_list.currentItemChanged.connect(self.select_peer)
        peer_layout.addWidget(self.peer_list, 1)
        self.connect_button = QPushButton("Connect to peer")
        self.connect_button.clicked.connect(self.connect_selected)
        peer_layout.addWidget(self.connect_button)
        splitter.addWidget(peer_panel)

        chat_panel = QWidget()
        chat_layout = QVBoxLayout(chat_panel)
        chat_layout.setContentsMargins(0, 0, 0, 0)
        chat_layout.setSpacing(8)

        chat_header = QHBoxLayout()
        self.chat_title = QLabel("Conversation")
        self.chat_title.setObjectName("sectionHeading")
        chat_header.addWidget(self.chat_title)
        chat_header.addStretch(1)
        self.peer_state = QLabel("Select a peer")
        self.peer_state.setObjectName("peerState")
        chat_header.addWidget(self.peer_state)
        chat_layout.addLayout(chat_header)

        self.conversation = QTextBrowser()
        self.conversation.setObjectName("conversation")
        self.conversation.setOpenExternalLinks(False)
        self.conversation.setPlaceholderText("Select a peer to begin.")
        chat_layout.addWidget(self.conversation, 1)

        self.input = MessageInput()
        self.input.setObjectName("messageInput")
        self.input.setPlaceholderText("Write a message…")
        self.input.returnPressed.connect(self.send_message)
        self.input.scroll_chat = self.scroll_chat
        chat_layout.addWidget(self.input)
        splitter.addWidget(chat_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        splitter.setSizes([270, 730])
        layout.addWidget(splitter, 1)

        self.setCentralWidget(root)
        self._update_controls()

    def _apply_style(self):
        # Use the active Qt/application palette instead of imposing a theme.
        palette = QApplication.palette()
        window = palette.color(QPalette.Window)
        base = palette.color(QPalette.Base)
        alternate = palette.color(QPalette.AlternateBase)
        text = palette.color(QPalette.Text)
        button = palette.color(QPalette.Button)
        button_text = palette.color(QPalette.ButtonText)
        highlight = palette.color(QPalette.Highlight)
        highlighted_text = palette.color(QPalette.HighlightedText)
        mid = palette.color(QPalette.Mid)
        link = palette.color(QPalette.Link)
        disabled_text = palette.color(QPalette.Disabled, QPalette.Text)

        self.setStyleSheet(f"""
            QMainWindow, QWidget {{
                background-color: {window.name()};
                color: {text.name()};
            }}
            QLabel#brandTitle {{ font-weight: 800; }}
            QLabel#subtitle {{ color: {mid.name()}; }}
            QLabel#connectionLabel {{ color: {link.name()}; }}
            QLabel#sectionHeading {{ font-weight: 700; }}
            QLabel#peerState {{ color: {mid.name()}; }}
            QListWidget, QTextBrowser {{
                background-color: {base.name()};
                color: {text.name()};
                border: 1px solid {mid.name()};
                border-radius: 8px;
                padding: 8px;
                selection-background-color: {highlight.name()};
                selection-color: {highlighted_text.name()};
            }}
            QListWidget {{ alternate-background-color: {alternate.name()}; }}
            QListWidget::item {{ padding: 12px 9px; border-radius: 5px; }}
            QListWidget::item:selected {{
                background-color: {highlight.name()};
                color: {highlighted_text.name()};
            }}
            QLineEdit {{
                background-color: {base.name()};
                border: 1px solid {mid.name()};
                border-radius: 7px;
                padding: 12px;
                color: {text.name()};
                selection-background-color: {highlight.name()};
                selection-color: {highlighted_text.name()};
            }}
            QLineEdit:focus {{ border: 2px solid {highlight.name()}; }}
            QPushButton {{
                background-color: {button.name()};
                color: {button_text.name()};
                border: 1px solid {mid.name()};
                border-radius: 7px;
                padding: 10px 14px;
                font-weight: 650;
            }}
            QPushButton:hover {{ border-color: {highlight.name()}; }}
            QPushButton:disabled {{ color: {disabled_text.name()}; }}
            QStatusBar {{ color: {text.name()}; }}
            QSplitter::handle {{ background-color: {mid.name()}; width: 5px; }}
        """)

    # ---------------- Networking callbacks ----------------

    def network_message(self, data, address):
        message = data.decode("utf-8", errors="replace")
        self.events.put(("message", address[0], message))

    def network_request(self, host):
        request = {
            "host": host,
            "accepted": False,
            "event": threading.Event(),
        }
        self.events.put(("request", request))
        request["event"].wait(30)
        return request["accepted"]

    def connect_selected(self):
        host = self.selected_host
        if not host:
            return
        if host in self.paired:
            self.statusBar().showMessage(f"Already connected to {host}", 4000)
            return

        self.connect_button.setEnabled(False)
        self.statusBar().showMessage(f"Requesting connection to {host}…")

        def worker():
            try:
                accepted = Destination(host).request_connection()
                self.events.put(("connected", host, accepted, None))
            except Exception as error:
                self.events.put(("connected", host, False, str(error)))

        threading.Thread(target=worker, daemon=True).start()

    def send_message(self):
        host = self.selected_host
        message = self.input.text()
        if not message.strip():
            return
        if not host:
            self.statusBar().showMessage("Select a peer first.", 4000)
            return
        if host not in self.paired:
            self.statusBar().showMessage("Connect to this peer before sending.", 4000)
            return

        self.input.clear()

        def worker():
            try:
                Destination(host).send(message.encode("utf-8"))
                self.events.put(("sent", host, message, None))
            except Exception as error:
                self.events.put(("sent", host, message, str(error)))

        threading.Thread(target=worker, daemon=True).start()

    # ---------------- State and rendering ----------------

    def update_state(self):
        self._process_events()
        self.refresh_peers()
        self._update_controls()

    def _process_events(self):
        while True:
            try:
                event = self.events.get_nowait()
            except queue.Empty:
                break

            kind = event[0]
            if kind == "message":
                _, host, message = event
                self.messages.setdefault(host, []).append(
                    ("Peer", message, time.strftime("%H:%M"))
                )
                self.store.add_message(host, "Peer", message)
                self.statusBar().showMessage(f"Message received from {host}", 5000)
                if host == self.selected_host:
                    self.render_conversation()

            elif kind == "sent":
                _, host, message, error = event
                sender = "Failed" if error else "You"
                self.messages.setdefault(host, []).append(
                    (sender, message, time.strftime("%H:%M"))
                )
                if not error:
                    self.store.add_message(host, "You", message)
                self.statusBar().showMessage(
                    f"Send failed: {error}" if error else f"Message sent to {host}", 5000
                )
                if host == self.selected_host:
                    self.render_conversation()
                self.input.setFocus()

            elif kind == "connected":
                _, host, accepted, error = event
                if error:
                    self.statusBar().showMessage(f"Connection failed: {error}", 7000)
                elif accepted:
                    self.paired.add(host)
                    self.store.set_paired(host)
                    self.statusBar().showMessage(f"Connected to {host}", 5000)
                else:
                    self.statusBar().showMessage(f"{host} declined the request", 5000)

            elif kind == "request":
                request = event[1]
                answer = QMessageBox.question(
                    self,
                    "Pairing request",
                    f"{request['host']} wants to connect.\n\nAccept this connection?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                request["accepted"] = answer == QMessageBox.Yes
                request["event"].set()
                if request["accepted"]:
                    self.paired.add(request["host"])
                    self.store.set_paired(request["host"])
                    self.statusBar().showMessage(f"Accepted {request['host']}", 5000)
                else:
                    self.statusBar().showMessage(f"Rejected {request['host']}", 5000)

    def refresh_peers(self):
        discovered = set(self.discovery.peers)
        hosts = sorted(discovered | self.paired | self.store.known_peers())
        if hosts == self.peers:
            self._refresh_peer_appearance(discovered)
            return

        previous = self.selected_host
        self.peers = hosts
        self.peer_list.blockSignals(True)
        self.peer_list.clear()
        for host in hosts:
            item = QListWidgetItem()
            item.setData(Qt.UserRole, host)
            self.peer_list.addItem(item)
        self.peer_list.blockSignals(False)

        row = hosts.index(previous) if previous in hosts else (0 if hosts else -1)
        if row >= 0:
            self.peer_list.setCurrentRow(row)
        else:
            self.selected_host = None
            self.render_conversation()
        self._refresh_peer_appearance(discovered)

    def _refresh_peer_appearance(self, discovered):
        names = self.discovery.peer_names
        for index, host in enumerate(self.peers):
            item = self.peer_list.item(index)
            paired = host in self.paired
            marker = "●" if paired else "○"
            state = "Connected" if paired else "Discovered"
            name = names.get(host)
            label = f"{name}  ({host})" if name else host
            item.setText(f"{marker}  {label}\n     {state}")
            if paired and host in discovered:
                item.setForeground(QColor("#70d6a0"))
                item.setToolTip("Paired · Online")
            elif paired:
                item.setForeground(QColor("#7f8792"))
                item.setToolTip("Paired · Offline or not currently discovered")
            else:
                item.setForeground(QColor("#d5d9df"))
                item.setToolTip("Discovered · Not paired")

    def select_peer(self, current, _previous=None):
        self.selected_host = current.data(Qt.UserRole) if current else None
        self.render_conversation()
        self._update_controls()

    def render_conversation(self):
        host = self.selected_host
        if not host:
            self.chat_title.setText("Conversation")
            self.peer_state.setText("Select a peer")
            self.conversation.clear()
            return

        self.chat_title.setText(self.discovery.peer_names.get(host, host))
        self.peer_state.setText("PAIRED" if host in self.paired else "NOT PAIRED")
        palette = self.conversation.palette()
        text_color = palette.color(QPalette.Text).name()
        muted_color = palette.color(QPalette.Mid).name()
        own_color = palette.color(QPalette.Link).name()
        failed_color = palette.color(QPalette.BrightText).name()
        chunks = []
        for sender, message, timestamp in self.messages.get(host, []):
            safe_message = html.escape(message).replace("\n", "<br>")
            safe_sender = html.escape(sender)
            if sender == "You":
                color = own_color
                align = "right"
            elif sender == "Failed":
                color = failed_color
                align = "left"
            else:
                color = text_color
                align = "left"
            chunks.append(
                f'<div style="margin: 9px 4px; text-align: {align};">'
                f'<span style="color: {color}; font-weight: 650;">{safe_sender}</span> '
                f'<span style="color: {muted_color};">{timestamp}</span><br>'
                f'<span style="color: {text_color};">{safe_message}</span></div>'
            )
        self.conversation.setHtml(
            '<div style="font-family: sans-serif;">' + "".join(chunks) + "</div>"
        )
        cursor = self.conversation.textCursor()
        cursor.movePosition(QTextCursor.End)
        self.conversation.setTextCursor(cursor)
        self.conversation.ensureCursorVisible()

    def scroll_chat(self, direction):
        bar = self.conversation.verticalScrollBar()
        bar.setValue(bar.value() + direction * max(1, bar.singleStep()))

    def _update_controls(self):
        host = self.selected_host
        self.connect_button.setEnabled(bool(host) and host not in self.paired)
        self.input.setEnabled(bool(host) and host in self.paired)
        if host and host in self.paired:
            self.input.setPlaceholderText("Write a message…  (Enter to send)")
        else:
            self.input.setPlaceholderText("Connect to this peer to send messages")
        discovered = set(self.discovery.peers)
        online_count = len(discovered)
        self.connection_label.setText(f"●  {online_count} peer{'s' if online_count != 1 else ''} online")

    # ---------------- Shutdown ----------------

    def closeEvent(self, event):
        self.running = False
        self.timer.stop()
        for component in (self.discovery, self.receiver):
            try:
                component.stop()
            except Exception:
                pass
        self.store.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    window = Interface()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

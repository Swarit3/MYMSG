#!/usr/bin/env python3
"""Local SQLite storage for MYMSG conversations and paired peers."""

import os
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime
from pathlib import Path


class ChatStore:
    def __init__(self, path=None):
        if path is None:
            path = Path(__file__).resolve().parent / "messages.db"

        self.path = str(path)
        parent = Path(self.path).expanduser().parent
        parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._db = sqlite3.connect(self.path, check_same_thread=False)
        self._db.execute("PRAGMA foreign_keys = ON")
        self._db.execute("PRAGMA journal_mode = WAL")
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS peers (
                host TEXT PRIMARY KEY,
                paired INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._db.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                host TEXT NOT NULL,
                sender TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(host) REFERENCES peers(host)
            )
        """)
        self._db.execute(
            "CREATE INDEX IF NOT EXISTS messages_host_id ON messages(host, id)"
        )
        self._db.commit()

    def known_peers(self):
        with self._lock:
            rows = self._db.execute("SELECT host FROM peers").fetchall()
            return {row[0] for row in rows}

    def paired_peers(self):
        with self._lock:
            rows = self._db.execute(
                "SELECT host FROM peers WHERE paired = 1"
            ).fetchall()
            return {row[0] for row in rows}

    def set_paired(self, host):
        with self._lock, self._db:
            self._db.execute("""
                INSERT INTO peers(host, paired) VALUES (?, 1)
                ON CONFLICT(host) DO UPDATE SET paired = 1
            """, (host,))

    def add_message(self, host, sender, content, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now().astimezone().isoformat(timespec="seconds")
        with self._lock, self._db:
            self._db.execute(
                "INSERT OR IGNORE INTO peers(host, paired) VALUES (?, 0)",
                (host,),
            )
            self._db.execute("""
                INSERT INTO messages(host, sender, content, timestamp)
                VALUES (?, ?, ?, ?)
            """, (host, sender, content, timestamp))

    def load_messages(self):
        messages = defaultdict(list)
        with self._lock:
            rows = self._db.execute("""
                SELECT host, sender, content, timestamp
                FROM messages ORDER BY id
            """).fetchall()

        for host, sender, content, timestamp in rows:
            try:
                display_time = datetime.fromisoformat(timestamp).astimezone().strftime("%H:%M")
            except ValueError:
                display_time = timestamp
            messages[host].append((sender, content, display_time))
        return messages

    def close(self):
        with self._lock:
            if self._db is not None:
                self._db.close()
                self._db = None

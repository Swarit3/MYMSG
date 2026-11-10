# MYMSG — Decentralized LAN Messenger

## Overview

MYMSG is a peer-to-peer messaging application written in Python. It allows devices connected to the same local network to discover one another, request connections, and exchange text messages without relying on a central messaging server.

The project provides two interfaces:

- **GUI:** a desktop graphical interface built with PySide6.
- **TUI:** a terminal-based interface built with Python's `curses` module.

Both interfaces use the same networking components and local storage system.

## Features

- Automatic peer discovery over the local network.
- Connection requests that the receiving user can accept or reject.
- Direct messaging between paired peers over TCP.
- Separate conversations for individual peers.
- Persistent message history using SQLite.
- Previously paired peers and conversations remain available after restarting the application.
- Peers remain listed while temporarily offline; their online status is updated through discovery.
- GUI and TUI share the same backend and message database.

## How It Works

MYMSG uses a decentralized architecture: each running client can discover peers, receive messages, and send messages directly. There is no central server or account service.

The application uses three network ports:

| Port | Protocol | Purpose |
|---|---|---|
| 5000 | TCP | Message transmission |
| 5001 | UDP | Peer discovery |
| 5002 | TCP | Connection requests and pairing |

Peer discovery uses UDP broadcast messages. When a client discovers another client, it can send a connection request. Once the request is accepted, messages are sent directly between the two devices over TCP.

## Project Structure

| File | Responsibility |
|---|---|
| `gui_mode.py` | Graphical user interface |
| `tui_mode.py` | Terminal user interface |
| `discovery.py` | Finds other MYMSG clients on the local network |
| `receiver.py` | Listens for incoming messages |
| `destination.py` | Sends messages to another peer |
| `connection_requestor.py` | Handles connection requests and pairing |
| `chat_store.py` | Stores conversations and paired peers in SQLite |

The networking components are independent of the user interface. This allows both interfaces to use the same communication logic without duplicating the networking implementation.

## Requirements

- Python 3
- PySide6 (for the graphical interface)
- A local network connection shared with the other participating devices

The TUI uses Python's standard `curses` module. On some platforms, such as Windows, an additional curses-compatible package may be required.

## Running the Application

Run these commands from the project directory:

**Graphical interface**
```bash
python3 gui_mode.py
```

**Terminal interface**
```bash
python3 tui_mode.py
```

The GUI requires PySide6 to be installed:

```bash
python3 -m pip install PySide6
```

All project Python files should be kept in the same directory so the modules can import one another.

## Data Storage

Chat history and paired-peer information are stored locally in an SQLite database.

By default, the database is created at:

```text
~/.local/share/mymsg/messages.db
```

If `XDG_DATA_HOME` is set, MYMSG stores its data under:

```text
$XDG_DATA_HOME/mymsg/messages.db
```

The database is local to each device. It is not hosted on a server or automatically synchronized between devices.

## Network Notes

- Devices should be connected to the same local network.
- The network must permit local UDP broadcast and the TCP connections used by MYMSG.
- A firewall may need to allow UDP port `5001` and TCP ports `5000` and `5002`.
- Peer conversations are currently identified by IP address. If a device receives a different IP address, it may appear as a new peer.

## Scope and Limitations

MYMSG is a local-network messaging project intended to demonstrate peer discovery, direct network communication, connection handling, and persistent local storage.

It does not currently provide internet-wide messaging, centralized account management, message synchronization, or end-to-end encryption. Messages and peer identities should therefore not be treated as secure against interception or impersonation on an untrusted network.

---

**MYMSG — Direct messaging, without a central server.**

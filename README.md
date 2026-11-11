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
- Said backend can be implemented in any format on *almost any platform that supports python.
  *(There's always exceptions. We can never be too sure)

## How It Works

MYMSG uses a decentralized architecture: each running client can discover peers, receive messages, and send messages directly. There is no central server or account service.

The application uses three network ports:

| Port | Protocol | Purpose |
|---|---|---|
| 9999 | TCP | Message transmission |
| 9900 | UDP | Peer discovery,connection requests and pairing |

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
- The TUI uses Python's standard `curses` module. (Curses may not work on Windows out of the box. Install it to use the TUI interface
```bash
python3 -m pip install windows-curses
```
- The GUI uses PySide6, which also *might* not always be installed.
```bash
python3 -m install PySide6
```

## Running the Application

Run these commands from the project directory or add the project to PATH:

**Graphical interface**
```bash
python3 GUI_Mode.py
```

**Terminal interface**
```bash
python3 tui_mode.py
```


All project Python files should be kept in the same directory so the modules can import one another.

## Data Storage

Chat history and paired-peer information are stored locally in an SQLite database.

The database is created inside the application folder. Installations are expected to be userlevel.

The database is local to each device. It is not hosted on a server or automatically synchronized between devices.

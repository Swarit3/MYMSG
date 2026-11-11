"""MYMSG client configuration."""

# Name advertised to other MYMSG clients during LAN discovery.
NAME = "USER"

# UDP port used for peer discovery. This is separate from the TCP ports
# used by the message receiver and connection-request service.
DISCOVERY_PORT = 9900
#TCP port used for messaging
MESSAGE_PORT = 9999

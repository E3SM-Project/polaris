"""
How the scheduler, the residents and the steps reach one another.

Every connection is authenticated with a key generated for the run.  The key
travels to a launched resident through its environment rather than its
command line: other users on a node can read a process's command line, and
cannot read its environment.

Every connection also sends small messages at once rather than holding them
to batch.  Without that, a reply sent right behind another waits for the
first one's acknowledgement, which the other end delays by up to 40 ms --
measured on Chrysalis, where it tripled the cost of handing out a piece of
work.

This module is deliberately light, since a resident imports it before
anything else and a step's process imports it to hand out work.
"""

import os
import socket
from multiprocessing.connection import Client, Connection, Listener
from typing import Optional, Tuple

import psutil

# the variable through which a launched resident is given the run's key
KEY_VARIABLE = 'POLARIS_RESIDENT_KEY'

# how many connections may wait to be accepted.  Every resident of a run
# says hello at about the same moment, and multiprocessing's own default of
# one would refuse most of them.
BACKLOG = 1024

Address = Tuple[str, int]


def new_key() -> bytes:
    """A key for one run's connections."""
    return os.urandom(32)


def bind_address(interface: Optional[str] = None) -> str:
    """
    The address to listen on, so that the other nodes can reach it.

    Parameters
    ----------
    interface : str, optional
        The network interface to use, such as ``ib0``.  The interface a
        node's hostname resolves to is used otherwise, which on some
        machines is a slow management network.

    Returns
    -------
    address : str
        An IPv4 address of this node
    """
    if interface:
        address = _interface_address(interface)
        if address is not None:
            return address
        raise ValueError(
            f'This node has no IPv4 address on interface {interface!r}.'
        )
    return socket.gethostbyname(socket.gethostname())


def listen(key: bytes, interface: Optional[str] = None) -> Listener:
    """
    Listen for authenticated connections on this node.

    Parameters
    ----------
    key : bytes
        The run's key

    interface : str, optional
        The network interface to listen on

    Returns
    -------
    listener : multiprocessing.connection.Listener
        The listener, whose ``address`` is what others connect to
    """
    return Listener((bind_address(interface), 0), authkey=key, backlog=BACKLOG)


def accept(listener: Listener) -> Connection:
    """Accept one authenticated connection, ready for small messages."""
    conn = listener.accept()
    no_delay(conn)
    return conn


def connect(address: Address, key: bytes) -> Connection:
    """
    Connect to a listener with the run's key.

    Parameters
    ----------
    address : tuple of str and int
        The host and port to connect to

    key : bytes
        The run's key

    Returns
    -------
    conn : multiprocessing.connection.Connection
        The connection, ready for small messages
    """
    conn = Client((address[0], address[1]), authkey=key)
    no_delay(conn)
    return conn


def listening_socket(listener: Listener) -> socket.socket:
    """
    The socket a listener accepts on, so that a loop can wait on it.

    ``multiprocessing`` offers no public way to ask whether a listener has
    a connection waiting without blocking on it, and a resident cannot block
    on one source while children and steps are waiting to be heard.
    """
    return listener._listener._socket  # type: ignore[attr-defined]


def no_delay(conn: Connection) -> None:
    """Send small messages on this connection at once."""
    try:
        sock = socket.fromfd(conn.fileno(), socket.AF_INET, socket.SOCK_STREAM)
    except OSError:
        # not a socket at all, such as a pipe
        return
    try:
        sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
    except OSError:
        # a socket, but not a TCP one
        pass
    finally:
        sock.close()


def _interface_address(interface: str) -> Optional[str]:
    """The IPv4 address of a network interface, if it has one."""
    for address in psutil.net_if_addrs().get(interface, []):
        if address.family == socket.AF_INET:
            return address.address
    return None

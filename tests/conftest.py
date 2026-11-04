"""Shared test setup: no test may touch the network.

Every download path (requests, and any outbound socket) raises during tests, so a
test that tries to download fails loudly. Tests that need real data use the
committed snapshots in results/, which makes them deterministic and runnable offline.
"""

from __future__ import annotations

import socket

import pytest


class NetworkBlocked(RuntimeError):
    """Raised when a test tries to download something."""


def _blocked(*args, **kwargs):
    raise NetworkBlocked("tests must not use the network: use the committed snapshots in results/")


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    import requests

    monkeypatch.setattr(requests.Session, "request", _blocked)
    monkeypatch.setattr(requests, "get", _blocked)
    real_connect = socket.socket.connect

    def local_only(sock, address):
        host = address[0] if isinstance(address, tuple) else address
        if host not in ("127.0.0.1", "localhost", "::1"):
            _blocked()
        return real_connect(sock, address)

    monkeypatch.setattr(socket.socket, "connect", local_only)

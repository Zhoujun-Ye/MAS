import sys
import socket
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture(autouse=True)
def no_paid_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Tests may not open network connections; use scripted models or MockTransport")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)

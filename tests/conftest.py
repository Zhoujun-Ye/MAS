import sys
import socket
import os
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


@pytest.fixture
def kramabench_upstream():
    configured = os.environ.get("KRAMABENCH_UPSTREAM")
    root = (Path(configured) if configured else Path(__file__).resolve().parents[2]
            / "mas-data/kramabench/upstream")
    if not root.is_dir():
        if configured:
            pytest.fail("KRAMABENCH_UPSTREAM does not point to an existing checkout")
        pytest.skip("Set KRAMABENCH_UPSTREAM for pinned-source integration checks")
    return root


@pytest.fixture(autouse=True)
def no_paid_network(monkeypatch):
    def denied(*args, **kwargs):
        raise AssertionError("Tests may not open network connections; use scripted models or MockTransport")
    monkeypatch.setattr(socket, "create_connection", denied)
    monkeypatch.setattr(socket.socket, "connect", denied)
    monkeypatch.setattr(socket.socket, "connect_ex", denied)

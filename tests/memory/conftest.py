import sqlite3

import pytest


@pytest.fixture
def opened_connections(monkeypatch):
    """Record every SQLite connection opened during the test, to check it gets closed."""
    opened: list[sqlite3.Connection] = []
    real_connect = sqlite3.connect

    def tracking_connect(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(sqlite3, "connect", tracking_connect)
    return opened

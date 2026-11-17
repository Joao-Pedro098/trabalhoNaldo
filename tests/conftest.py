import importlib
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture()
def cliente(tmp_path, monkeypatch):
    """App Flask com um SQLite novo e vazio a cada teste."""
    monkeypatch.setenv("DB_BACKEND", "sqlite")
    monkeypatch.setenv("SQLITE_PATH", str(tmp_path / "teste.db"))

    import db.database as database
    importlib.reload(database)  # relê as variáveis de ambiente
    import app as app_mod

    return app_mod.criar_app().test_client()

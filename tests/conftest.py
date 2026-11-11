import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_default_databases(tmp_path, monkeypatch):
    """Point the lazy default trigger DB and agent-store singleton at tmp_path so no test opens server/data/*.db."""
    from server.services import triggers as triggers_pkg
    from server.services.agents import store as agent_store_module

    monkeypatch.setattr(triggers_pkg, "_default_db_path", tmp_path / "default_triggers.db")
    monkeypatch.setattr(triggers_pkg, "_trigger_service", None)
    monkeypatch.setattr(agent_store_module, "_DEFAULT_DB_PATH", tmp_path / "default_agents.db")
    monkeypatch.setattr(agent_store_module, "_store", None)


@pytest.fixture(autouse=True)
def _isolate_indexer(monkeypatch):
    """No test warms a real embedder: reset the indexer's state and make building one fail."""
    from server.services.agents import indexer

    def _no_real_embedder():
        raise RuntimeError("tests must not build a real embedder; use indexer.warm_up(HashingEmbedder())")

    monkeypatch.setattr(indexer, "_embedder", None)
    monkeypatch.setattr(indexer, "_dim", None)
    monkeypatch.setattr(indexer, "_make_embedder", _no_real_embedder)

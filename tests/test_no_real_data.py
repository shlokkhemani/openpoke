"""Safety net: no test may default to the real server/data databases."""

from pathlib import Path

from server.services import triggers as triggers_pkg
from server.services.agents import store as agent_store_module

REAL_DATA = Path(triggers_pkg.__file__).resolve().parents[2] / "data"


def _under(path: Path, root: Path) -> bool:
    path = Path(path).resolve()
    return path == root or root in path.parents


def test_default_trigger_db_path_is_redirected_during_tests():
    assert not _under(triggers_pkg._default_db_path, REAL_DATA)
    assert triggers_pkg._trigger_service is None  # nothing built yet; first use builds on the tmp path


def test_default_agent_store_path_is_redirected_during_tests():
    assert not _under(agent_store_module._DEFAULT_DB_PATH, REAL_DATA)
    assert agent_store_module._store is None

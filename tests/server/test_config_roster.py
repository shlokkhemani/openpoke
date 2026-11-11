"""Task 13-I config: roster_mode (full|hybrid, default hybrid) and embedding_model."""

import importlib

import pytest
from pydantic import ValidationError

from server import config as config_module


@pytest.fixture
def fresh_config(monkeypatch):
    """Reload server.config under the monkeypatched env, then restore it afterwards."""

    def load(**env):
        for name in ("OPENPOKE_ROSTER_MODE", "OPENPOKE_EMBEDDING_MODEL"):
            monkeypatch.delenv(name, raising=False)
        for name, value in env.items():
            monkeypatch.setenv(name, value)
        return importlib.reload(config_module)

    yield load
    monkeypatch.undo()
    importlib.reload(config_module)


def test_roster_mode_defaults_to_hybrid(fresh_config):
    assert fresh_config().Settings().roster_mode == "hybrid"


def test_roster_mode_full_from_env_is_accepted(fresh_config):
    assert fresh_config(OPENPOKE_ROSTER_MODE="full").Settings().roster_mode == "full"


@pytest.mark.parametrize("bad", ["legacy", "recency", "adaptive"])
def test_roster_mode_other_values_from_env_raise(fresh_config, bad):
    mod = fresh_config(OPENPOKE_ROSTER_MODE=bad)
    with pytest.raises(ValidationError):
        mod.Settings()


def test_embedding_model_default(fresh_config):
    assert fresh_config().Settings().embedding_model == "BAAI/bge-small-en-v1.5"


def test_embedding_model_env_override_and_empty_means_bm25_only(fresh_config):
    assert fresh_config(OPENPOKE_EMBEDDING_MODEL="x/y").Settings().embedding_model == "x/y"
    # an empty env value is honoured (not replaced by the default): it means BM25 only
    assert fresh_config(OPENPOKE_EMBEDDING_MODEL="").Settings().embedding_model == ""


def test_retrieval_comment_no_longer_mentions_recency():
    import inspect

    assert "recency" not in inspect.getsource(config_module)

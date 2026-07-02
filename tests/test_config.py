"""Tests for the .env loader, the config file, and setting resolution order."""

import os

from vnote import config


def test_dotenv_loads_new_but_never_overrides(tmp_path, monkeypatch):
    monkeypatch.setenv("VNOTE_DOTENV_EXISTING", "keep-me")
    env_file = tmp_path / ".env"
    env_file.write_text(
        'VNOTE_DOTENV_NEW="from-file"\n'
        "VNOTE_DOTENV_EXISTING=should-not-win\n"
        "# a comment\n"
        "BARE_LINE_NO_EQUALS\n"
    )
    config._load_dotenv(env_file)

    assert os.environ["VNOTE_DOTENV_NEW"] == "from-file"  # quotes stripped
    assert os.environ["VNOTE_DOTENV_EXISTING"] == "keep-me"  # real env wins

    monkeypatch.delenv("VNOTE_DOTENV_NEW", raising=False)  # clean up the manual os.environ write


def test_load_config_missing_returns_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    assert config.load_config() == {}


def test_save_then_load_roundtrips(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    config.save_config({"backend": "claude", "ollama_model": "x"})
    assert config.load_config() == {"backend": "claude", "ollama_model": "x"}
    assert config.config_file().parent.name == "vnote"


def test_backend_resolution_order(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("VNOTE_BACKEND", raising=False)

    # 1. nothing set -> built-in
    assert config.backend() == config.BUILTIN_BACKEND

    # 2. config file overrides built-in
    config.save_config({"backend": "claude"})
    assert config.backend() == "claude"

    # 3. env var beats the file
    monkeypatch.setenv("VNOTE_BACKEND", "ollama")
    assert config.backend() == "ollama"


def test_ollama_model_resolution_order(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("VNOTE_OLLAMA_MODEL", raising=False)

    assert config.ollama_model() == config.BUILTIN_OLLAMA_MODEL
    config.save_config({"ollama_model": "qwen2.5:7b-instruct"})
    assert config.ollama_model() == "qwen2.5:7b-instruct"
    monkeypatch.setenv("VNOTE_OLLAMA_MODEL", "llama3.2:3b")
    assert config.ollama_model() == "llama3.2:3b"

"""Tests for first-run setup gating and VRAM-based model suggestion."""

from vnote import config, firstrun


def test_suggest_tier_by_vram():
    assert firstrun._suggest_tier(None) == 1  # unknown GPU -> middle tier
    assert firstrun._suggest_tier(24) == 0    # plenty -> 14b
    assert firstrun._suggest_tier(8) == 1     # mid -> 7b
    assert firstrun._suggest_tier(4) == 2     # small -> 3b
    assert firstrun._suggest_tier(1) == 2     # tiny -> still the smallest tier


def test_should_run_false_when_backend_flag_given(monkeypatch):
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    assert firstrun.should_run("ollama") is False


def test_should_run_false_when_env_forces_backend(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.setenv("VNOTE_BACKEND", "ollama")
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    assert firstrun.should_run(None) is False


def test_should_run_false_when_config_exists(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("VNOTE_BACKEND", raising=False)
    config.save_config({"backend": "ollama"})
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    assert firstrun.should_run(None) is False


def test_should_run_false_when_not_a_tty(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("VNOTE_BACKEND", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: False, raising=False)
    assert firstrun.should_run(None) is False


def test_should_run_true_when_interactive_and_unconfigured(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    monkeypatch.delenv("VNOTE_BACKEND", raising=False)
    monkeypatch.setattr("sys.stdin.isatty", lambda: True, raising=False)
    monkeypatch.setattr("sys.stdout.isatty", lambda: True, raising=False)
    assert firstrun.should_run(None) is True

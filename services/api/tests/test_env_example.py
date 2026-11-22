"""`.env.example` documents every setting, and nothing that doesn't exist."""

import re
from pathlib import Path

import pytest

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[3]


def _keys(text: str) -> set[str]:
    return set(re.findall(r"^(NEXUS_[A-Z0-9_]+)=", text, re.M))


def test_every_setting_is_in_env_example() -> None:
    example = _keys((ROOT / ".env.example").read_text())
    settings = {f"NEXUS_{name.upper()}" for name in Settings.model_fields}
    assert sorted(settings - example) == []


def test_extra_example_keys_are_used_by_docker_compose() -> None:
    example = _keys((ROOT / ".env.example").read_text())
    settings = {f"NEXUS_{name.upper()}" for name in Settings.model_fields}
    compose = (ROOT / "docker-compose.yml").read_text()
    assert sorted(k for k in example - settings if k not in compose) == []


def test_example_parses_as_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Every value in the example is valid as written (secrets are left empty)."""
    import os

    for key in [k for k in os.environ if k.startswith("NEXUS_")]:
        monkeypatch.delenv(key)
    s = Settings(_env_file=ROOT / ".env.example")  # type: ignore[call-arg]
    assert s.local_model == "qwen3:14b" and s.cloud_enabled is False
    assert s.cors_origins == ["http://localhost:3000"] and s.model_prices == {}


def test_api_reference_is_current() -> None:
    """docs/API.md and docs/api/openapi.json are generated from the routes."""
    import subprocess
    import sys

    script = Path(__file__).resolve().parents[1] / "scripts" / "export_openapi.py"
    run = subprocess.run([sys.executable, str(script), "--check"], capture_output=True, text=True)  # noqa: S603
    assert run.returncode == 0, run.stdout

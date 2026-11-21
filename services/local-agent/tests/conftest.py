from collections.abc import Iterator
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def agent_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    monkeypatch.setenv("NEXUS_AGENT_HOME", str(tmp_path))
    yield tmp_path

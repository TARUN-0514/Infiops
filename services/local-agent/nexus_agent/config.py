"""Where the agent keeps its pairing. The file holds a device refresh token, so it is written
readable by the current user only. Removing the device in NEXUS Settings makes it useless."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path


def config_dir() -> Path:
    if override := os.environ.get("NEXUS_AGENT_HOME"):
        return Path(override)
    if sys.platform == "win32":
        return Path(os.environ.get("APPDATA", Path.home())) / "NEXUS"
    return Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "nexus"


@dataclass
class AgentConfig:
    server: str = "http://localhost:8000"
    device_id: str = ""
    refresh_token: str = ""
    name: str = ""
    wake_word_model: str = "hey_jarvis"
    # Microphone level (0-1 RMS) that counts as speech. Raise it in a noisy room.
    speech_threshold: float = 0.015
    # Computer control is off on this PC until the owner runs `nexus-agent control on`,
    # whatever NEXUS's settings say.
    control: bool = False
    extra: dict[str, str] = field(default_factory=dict)

    @property
    def paired(self) -> bool:
        return bool(self.device_id and self.refresh_token)

    @property
    def path(self) -> Path:
        return config_dir() / "agent.json"

    @classmethod
    def load(cls) -> AgentConfig:
        path = config_dir() / "agent.json"
        if not path.exists():
            return cls()
        data = json.loads(path.read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known)

    def save(self) -> None:
        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)
        os.replace(tmp, path)

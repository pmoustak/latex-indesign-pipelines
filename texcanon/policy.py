"""Policy: classification of LaTeX commands and environments (see policy.toml)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_POLICY = Path(__file__).with_name("policy.toml")

CLASSES = ("content", "custom", "layout", "space", "definition")


@dataclass
class Policy:
    base_lang: str
    switches: dict[str, str]
    wrappers: dict[str, str]
    commands: dict[str, tuple[str, str]]          # name -> (class, argspec)
    strip: dict[str, str]                          # name -> argspec
    environments: dict[str, dict] = field(default_factory=dict)
    placeholders: list[str] = field(default_factory=list)

    def command(self, name: str) -> tuple[str | None, str]:
        return self.commands.get(name, (None, ""))

    def env(self, name: str) -> dict | None:
        return self.environments.get(name)


def load_policy(path: str | Path | None = None) -> Policy:
    data = tomllib.loads(Path(path or DEFAULT_POLICY).read_text(encoding="utf-8"))
    commands: dict[str, tuple[str, str]] = {}
    for cls in CLASSES:
        for name, spec in data.get("commands", {}).get(cls, {}).items():
            commands[name] = (cls, spec)
    lang = data.get("language", {})
    return Policy(
        base_lang=lang.get("base", "el"),
        switches=dict(lang.get("switches", {})),
        wrappers=dict(lang.get("wrappers", {})),
        commands=commands,
        strip=dict(data.get("commands", {}).get("strip", {})),
        environments=dict(data.get("environments", {})),
        placeholders=list(data.get("qa", {}).get("placeholders", [])),
    )

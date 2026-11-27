"""Policy: classification of LaTeX commands and environments (see policy.toml)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_POLICY = Path(__file__).with_name("policy.toml")

CLASSES = ("content", "custom", "layout", "space", "definition")
ENV_CLASSES = ("content", "tabular", "verbatim", "container", "math")
ARG_LETTERS = frozenset("sOoMm")


class PolicyError(ValueError):
    """policy.toml is inconsistent."""


def _check_spec(what: str, spec: object) -> None:
    if not isinstance(spec, str) or not set(spec) <= ARG_LETTERS:
        raise PolicyError(f"{what}: μη έγκυρο argspec {spec!r} (επιτρέπονται s o O m M)")


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
    tables = data.get("commands", {})
    for table in tables:
        if table not in CLASSES and table != "strip":
            raise PolicyError(f"Άγνωστος πίνακας [commands.{table}]")
    commands: dict[str, tuple[str, str]] = {}
    for cls in CLASSES:
        for name, spec in tables.get(cls, {}).items():
            if name in commands:
                raise PolicyError(f"Η εντολή \\{name} είναι και στο [commands.{commands[name][0]}] "
                                  f"και στο [commands.{cls}]")
            _check_spec(f"\\{name}", spec)
            commands[name] = (cls, spec)
    strip = dict(tables.get("strip", {}))
    for name, spec in strip.items():
        _check_spec(f"\\{name}", spec)
    environments = dict(data.get("environments", {}))
    for name, env in environments.items():
        if not isinstance(env, dict) or env.get("class") not in ENV_CLASSES:
            raise PolicyError(f"Περιβάλλον {name}: η class πρέπει να είναι μία από {ENV_CLASSES}")
        _check_spec(f"Περιβάλλον {name}", env.get("args", ""))
    lang = data.get("language", {})
    return Policy(
        base_lang=lang.get("base", "el"),
        switches=dict(lang.get("switches", {})),
        wrappers=dict(lang.get("wrappers", {})),
        commands=commands,
        strip=strip,
        environments=environments,
        placeholders=list(data.get("qa", {}).get("placeholders", [])),
    )

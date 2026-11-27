"""Book configuration (book.toml)."""
from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field


class BookSection(BaseModel):
    title: str
    root: str = "."                 # folder with the LaTeX sources, relative to book.toml
    main: str | None = None         # main.tex: defines which chapters make up the book
    chapters: list[str] = Field(default_factory=list)   # used only when main is missing
    assets_root: str = "."          # images are resolved relative to this (relative to root)
    preamble: str | None = None     # file with the book's \newcommand definitions
    language: str = "el"


class PandocSection(BaseModel):
    path: str | None = None
    version: str | None = None      # required Pandoc version (reproducibility)


class GateSection(BaseModel):
    max_errors: int = 0
    min_coverage: float = 1.0
    require_schema_valid: bool = True
    require_complete_book: bool = True


class BookConfig(BaseModel):
    book: BookSection
    pandoc: PandocSection = Field(default_factory=PandocSection)
    gate: GateSection = Field(default_factory=GateSection)
    policy: str | None = None
    config_path: Path | None = None

    @property
    def base_dir(self) -> Path:
        return self.config_path.parent if self.config_path else Path.cwd()

    @property
    def source_root(self) -> Path:
        return (self.base_dir / self.book.root).resolve()

    @property
    def assets_root(self) -> Path:
        return (self.source_root / self.book.assets_root).resolve()

    def policy_path(self) -> Path | None:
        return (self.base_dir / self.policy).resolve() if self.policy else None


def load_config(path: str | Path) -> BookConfig:
    path = Path(path).resolve()
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    cfg = BookConfig.model_validate(data)
    cfg.config_path = path
    return cfg

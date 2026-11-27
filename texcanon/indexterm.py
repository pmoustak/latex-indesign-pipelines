r"""Parsing of makeindex arguments: ``sort@text!sub|(``, ``x|see{y}``, ``"!`` escapes."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Level:
    text: str
    sort: str | None = None


@dataclass
class IndexTerm:
    levels: list[Level] = field(default_factory=list)
    range: str | None = None        # "open" | "close" | None
    encap: str | None = None        # e.g. "textbf"
    see: str | None = None
    see_kind: str | None = None     # "see" | "seealso"


def _split_top(s: str, sep: str) -> list[str]:
    """Split on ``sep`` outside braces, honouring the makeindex quote char ``"``."""
    parts, depth, cur, i = [], 0, [], 0
    while i < len(s):
        c = s[i]
        if c == '"' and i + 1 < len(s):
            cur.append(s[i + 1])
            i += 2
            continue
        if c == "\\" and i + 1 < len(s):
            cur.append(s[i:i + 2])
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        if c == sep and depth == 0:
            parts.append("".join(cur))
            cur = []
        else:
            cur.append(c)
        i += 1
    parts.append("".join(cur))
    return parts


def parse_index(arg: str) -> IndexTerm:
    term = IndexTerm()
    body, *enc = _split_top(arg, "|")
    if len(enc) > 1:
        raise ValueError(f"περισσότερα από ένα | στο λήμμα: {arg}")
    if enc:
        e = enc[0].strip()
        if e.startswith("("):
            term.range, e = "open", e[1:]
        elif e.startswith(")"):
            term.range, e = "close", e[1:]
        for kind in ("seealso", "see"):
            if e.startswith(kind + "{") and e.endswith("}"):
                term.see_kind, term.see, e = kind, e[len(kind) + 1:-1], ""
                break
        term.encap = e or None
    for part in _split_top(body, "!"):
        sort_text = _split_top(part, "@")
        if len(sort_text) == 2:
            term.levels.append(Level(text=sort_text[1].strip(), sort=sort_text[0].strip()))
        elif len(sort_text) == 1:
            term.levels.append(Level(text=part.strip()))
        else:
            raise ValueError(f"περισσότερα από ένα @ στο λήμμα: {arg}")
    if not any(lv.text for lv in term.levels):
        raise ValueError(f"κενό λήμμα ευρετηρίου: {arg}")
    return term

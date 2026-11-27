r"""Prepare a LaTeX source for Pandoc without changing its content.

Pandoc's LaTeX reader keeps no source positions, so before conversion we inject
plain-text markers ``⟦L123⟧`` at the start of source lines.  They travel through
Pandoc as ordinary text and the builder turns them back into ``src-line``
attributes (and removes them).  Markers are *not* placed where text would
change the meaning: inside verbatim, math, tabular bodies and non-content
arguments (e.g. ``\includegraphics[...]``).  On lines with ``\item`` the marker
goes after ``\item`` (Pandoc drops text that precedes the first item).

Other rewrites (all recorded, none of them touches content):
* verbatim-like environments (``code``, ``lstlisting``...) become ``verbatim``,
  because Pandoc parses unknown environments as raw LaTeX and a ``$`` inside R
  code makes it swallow everything up to the next ``$`` (figures included);
* container environments (``defarea``) become ``⟦BEGIN:k⟧ … ⟦END:k⟧`` paragraphs
  that the builder folds back into one element;
* commands Pandoc renders as stray text (``\cline{3-5}`` → "3-5") are blanked.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .latex import Container, Graphic, SourceInfo, Tabular, Verbatim, read_opt

ITEM_RE = re.compile(r"\\item(?![A-Za-z@])")
ARG_END_RE = re.compile(r"(\}|\]|\\[A-Za-z@]+\*?)\s*$")


def marker(line: int) -> str:
    return f"\u27e6L{line}\u27e7"


@dataclass
class Prepared:
    text: str
    verbatims: list[Verbatim]
    tabulars: list[Tabular]
    graphics: list[Graphic]
    containers: list[Container]
    captions: list[int]
    unmarked_lines: list[int] = field(default_factory=list)


def _inside(spans: list[tuple[int, int]], off: int, inclusive_start: bool = False) -> bool:
    for a, b in spans:
        if (a <= off if inclusive_start else a < off) and off < b:
            return True
    return False


def preprocess(info: SourceInfo) -> Prepared:
    s = info.text
    edits: list[tuple[int, int, str]] = []

    for a, b in info.strip_spans:
        edits.append((a, b, re.sub(r"[^\n]", " ", s[a:b])))
    for v in info.verbatims:
        edits.append((v.begin, v.content_start, "\\begin{verbatim}\n"))
        edits.append((v.end, v.end_after, "\\end{verbatim}"))
    for k, c in enumerate(info.containers):
        title = s[c.title[0]:c.title[1]] if c.title else ""
        edits.append((c.begin, c.begin_after,
                      f"\n\n\u27e6BEGIN:{k}\u27e7\n\n\u27e6TITLE:{k}\u27e7{marker(c.begin_line)}{title}\n\n"))
        edits.append((c.end, c.end_after, f"\n\n\u27e6END:{k}\u27e7\n\n"))

    no_mark: list[tuple[int, int]] = []
    no_mark += [(v.begin, v.end_after) for v in info.verbatims]
    no_mark += info.math_spans
    no_mark += [(info.lines.start(t.begin_line), info.lines.start(t.end_line) + 1) for t in info.tabulars]
    skip = info.skip_spans + info.raw_spans

    lines = s.split("\n")
    unmarked: list[int] = []
    prev = ""
    for no, text in enumerate(lines, 1):
        start = info.lines.start(no)
        stripped = text.strip()
        if not stripped or stripped.startswith("%"):
            continue
        if _inside(no_mark, start) or _inside(skip, start, inclusive_start=True):
            unmarked.append(no)
            prev = text
            continue
        if stripped[0] in "{[" and ARG_END_RE.search(prev):
            unmarked.append(no)          # continuation of a previous command's arguments
            prev = text
            continue
        m = ITEM_RE.search(text)
        if m and "%" not in text[:m.start()]:
            pos = m.end()
            k = pos
            while k < len(text) and text[k] in " \t":
                k += 1
            if text[k:k + 1] == "[":
                try:
                    _, _, pos = read_opt(text, k)
                except Exception:
                    pass
            edits.append((start + pos, start + pos, marker(no)))
        else:
            edits.append((start, start, marker(no)))
        prev = text

    # an insertion strictly inside a replaced range would corrupt it: drop it
    replaced = [(a, b) for a, b, _ in edits if b > a]
    edits = [e for e in edits if e[1] > e[0] or not _inside(replaced, e[0])]

    # apply right-to-left; at equal start the longer edit first so insertions end up in front
    out = s
    for a, b, rep in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        out = out[:a] + rep + out[b:]
    return Prepared(out, list(info.verbatims), list(info.tabulars), list(info.graphics),
                    list(info.containers), list(info.captions), unmarked)

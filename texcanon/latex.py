"""LaTeX helpers.

* argument readers (read_group / read_opt / read_args),
* ``analyze``: an independent scan of the source that does NOT use Pandoc.  It
  yields the command inventory, the content words per source line (the
  reference for the coverage proof) and the positions the preprocessor needs,
* ``convert_snippet``: converts the small LaTeX fragments Pandoc leaves raw
  (\\en, \\index{..}{..}, \\label, ...) into builder events.
"""
from __future__ import annotations

import bisect
import re
import unicodedata
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .policy import Policy

# Markers injected by the preprocessor (see preprocess.py).
TOKEN_RE = re.compile("\u27e6(?:L(\\d+)|(BEGIN|TITLE|END):(\\d+))\u27e7")
WORD_RE = re.compile(r"[^\W_]+")
CMD_RE = re.compile(r"\\([A-Za-z@]+)(\*?)|\\(.)", re.S)
MATH_CMD_RE = re.compile(r"\\[A-Za-z@]+")

ACCENTS = {
    "'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303",
    "=": "\u0304", ".": "\u0307",
}
# Single-character control symbols: text they produce ("" = nothing, " " = separator).
SINGLE_TEXT = {
    "%": "%", "&": "&", "$": "$", "#": "#", "_": "_", "{": "{", "}": "}",
    "-": "", "/": "", "@": "", "!": "", " ": " ", ",": " ", ";": " ", ":": " ",
    ">": " ", "\n": " ", "\t": " ", "\\": " ",
}


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def words(s: str, math: bool = False) -> list[str]:
    if math:
        s = MATH_CMD_RE.sub(" ", s)
    return [nfc(w) for w in WORD_RE.findall(s)]


class LatexError(Exception):
    def __init__(self, msg: str, pos: int):
        super().__init__(msg)
        self.pos = pos


def eol(s: str, i: int) -> int:
    j = s.find("\n", i)
    return len(s) if j < 0 else j


def skip_ws(s: str, i: int) -> int:
    n = len(s)
    while i < n:
        c = s[i]
        if c in " \t\r\n":
            i += 1
        elif c == "%":
            i = eol(s, i) + 1
        else:
            break
    return min(i, n)


def read_group(s: str, i: int) -> tuple[int, int, int]:
    """``s[i] == '{'``. Returns (content_start, content_end, next_index)."""
    depth, j, n = 0, i, len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "%":
            j = eol(s, j)
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return i + 1, j, j + 1
        j += 1
    raise LatexError("μη ισορροπημένο {", i)


def read_opt(s: str, i: int) -> tuple[int, int, int]:
    """``s[i] == '['``. Returns (content_start, content_end, next_index)."""
    depth, j, n = 0, i + 1, len(s)
    while j < n:
        c = s[j]
        if c == "\\":
            j += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        elif c == "]" and depth == 0:
            return i + 1, j, j + 1
        j += 1
    raise LatexError("μη ισορροπημένο [", i)


def _match_cmd(s: str, k: int) -> re.Match:
    """Control sequence at ``s[k] == '\\'``; a lone trailing backslash is an error."""
    m = CMD_RE.match(s, k)
    if m is None:
        raise LatexError("λείπει το όνομα της εντολής", k)
    return m


@dataclass
class Arg:
    kind: str
    start: int
    end: int


def read_args(s: str, i: int, spec: str) -> tuple[list[Arg], int]:
    args: list[Arg] = []
    n = len(s)
    for ch in spec:
        k = skip_ws(s, i)
        if ch == "s":
            if k < n and s[k] == "*":
                i = k + 1
        elif ch in "oO":
            if k < n and s[k] == "[":
                a, b, i = read_opt(s, k)
                args.append(Arg(ch, a, b))
        elif ch in "mM":
            if k >= n:
                raise LatexError("λείπει όρισμα", i)
            if s[k] == "{":
                a, b, i = read_group(s, k)
            elif s[k] == "\\":
                m = _match_cmd(s, k)
                a, b, i = k, m.end(), m.end()
            else:
                a, b, i = k, k + 1, k + 1
            args.append(Arg(ch, a, b))
    return args, i


def find_unescaped(s: str, ch: str, i: int) -> int:
    while True:
        j = s.find(ch, i)
        if j < 0:
            return -1
        k, bs = j - 1, 0
        while k >= 0 and s[k] == "\\":
            bs += 1
            k -= 1
        if bs % 2 == 0:
            return j
        i = j + 1


class LineMap:
    def __init__(self, s: str):
        self.starts = [0] + [m.end() for m in re.finditer("\n", s)]

    def line(self, off: int) -> int:
        return bisect.bisect_right(self.starts, off)

    def start(self, line: int) -> int:
        return self.starts[line - 1]


# --------------------------------------------------------------------------- analysis


@dataclass
class Verbatim:
    env: str
    begin: int
    begin_line: int
    opts: str | None
    content_start: int
    content_line: int
    end: int
    end_after: int
    end_line: int


@dataclass
class Tabular:
    begin_line: int
    end_line: int
    row_lines: list[int]


@dataclass
class Graphic:
    path: str
    options: str | None
    line: int


@dataclass
class Container:
    env: str
    element: str
    begin: int
    begin_after: int
    begin_line: int
    title: tuple[int, int] | None
    end: int = -1
    end_after: int = -1
    end_line: int = -1


@dataclass
class SourceInfo:
    text: str
    lines: LineMap
    commands: list[tuple[str, str, int]] = field(default_factory=list)   # (class, name, line)
    words: dict[int, Counter] = field(default_factory=lambda: defaultdict(Counter))
    verbatims: list[Verbatim] = field(default_factory=list)
    tabulars: list[Tabular] = field(default_factory=list)
    graphics: list[Graphic] = field(default_factory=list)
    containers: list[Container] = field(default_factory=list)
    captions: list[int] = field(default_factory=list)
    skip_spans: list[tuple[int, int]] = field(default_factory=list)
    math_spans: list[tuple[int, int]] = field(default_factory=list)
    strip_spans: list[tuple[int, int]] = field(default_factory=list)
    errors: list[tuple[str, int]] = field(default_factory=list)


class _Analyzer:
    def __init__(self, text: str, policy: Policy):
        self.s = text
        self.p = policy
        self.info = SourceInfo(text=text, lines=LineMap(text))
        self.lm = self.info.lines
        self.buf: list[str] = []
        self.buf_off: list[int] = []
        self.open_tabular: list[tuple[int, int]] = []
        self.open_containers: list[Container] = []

    # -- content buffer
    def add(self, text: str, off: int) -> None:
        for k, ch in enumerate(text):
            self.buf.append(ch)
            self.buf_off.append(off + k if len(text) > 1 else off)

    def sep(self) -> None:
        self.buf.append(" ")
        self.buf_off.append(-1)

    def line(self, off: int) -> int:
        return self.lm.line(off)

    def error(self, msg: str, off: int) -> None:
        self.info.errors.append((msg, self.line(off)))

    # -- main loop
    def run(self) -> SourceInfo:
        self.scan(0, len(self.s))
        joined = "".join(self.buf)
        for m in WORD_RE.finditer(joined):
            off = self.buf_off[m.start()]
            self.info.words[self.line(off)][nfc(m.group())] += 1
        for c in self.open_containers:
            self.error(f"Το περιβάλλον {c.env} δεν κλείνει", c.begin)
        self.info.tabulars.sort(key=lambda t: t.begin_line)
        self.info.containers.sort(key=lambda c: c.begin)
        return self.info

    def scan(self, a: int, b: int, index_mode: bool = False) -> None:
        s = self.s
        i = a
        while i < b:
            c = s[i]
            if c == "%":
                i = eol(s, i)
                continue
            if c == "\\":
                m = CMD_RE.match(s, i)
                if m is None:
                    i += 1
                    continue
                try:
                    i = self.control(m, i, index_mode)
                except LatexError as e:
                    # report and go on: the rest of the source must still be analysed
                    self.error(f"{m.group()}: {e}", e.pos)
                    i = m.end()
                continue
            if c == "$":
                if s.startswith("$$", i):
                    i = self.math(i + 2, s.find("$$", i + 2), 2, i)
                else:
                    i = self.math(i + 1, find_unescaped(s, "$", i + 1), 1, i)
                continue
            if c in "{}~":
                self.sep()
                i += 1
                continue
            if index_mode and c == "|":
                j = i + 1
                while j < b and s[j].isalpha():
                    j += 1
                self.sep()
                i = j
                continue
            if index_mode and c == '"' and i + 1 < b:
                self.add(s[i + 1], i + 1)
                i += 2
                continue
            self.add(c, i)
            i += 1

    def control(self, m: re.Match, i: int, index_mode: bool) -> int:
        """Handle the control sequence matched at ``i``; return the next index."""
        s = self.s
        if m.group(1):
            name, j = m.group(1), m.end()
            if name == "begin":
                return self.begin(i, j)
            if name == "end":
                return self.end(i, j)
            return self.command(name, i, j, index_mode)
        ch, j = m.group(3), m.end()
        if ch == "[":
            return self.math(j, s.find("\\]", j), 2, i)
        if ch == "(":
            return self.math(j, s.find("\\)", j), 2, i)
        if ch in ACCENTS:
            return self.accent(ch, j, i)
        if ch == "\\":
            self.sep()
            if s[j:j + 1] == "[":
                _, _, k = read_opt(s, j)
                self.info.skip_spans.append((j, k))
                return k
            return j
        t = SINGLE_TEXT.get(ch, " ")
        if t == " ":
            self.sep()
        elif t:
            self.add(t, i)
        return j

    def math(self, a: int, k: int, dlen: int, start: int) -> int:
        if k < 0:
            self.error("Μαθηματικά που δεν κλείνουν", start)
            return len(self.s)
        self.info.math_spans.append((start, k + dlen))
        cleaned = MATH_CMD_RE.sub(lambda m: " " * len(m.group()), self.s[a:k])
        self.sep()
        for off, ch in enumerate(cleaned):
            self.buf.append(ch)
            self.buf_off.append(a + off if ch != " " else -1)
        self.sep()
        return k + dlen

    def accent(self, ch: str, j: int, i: int) -> int:
        s = self.s
        if s[j:j + 1] == "{":
            a, b, k = read_group(s, j)
            base = s[a:b].strip()
        else:
            k = j + 1
            base = s[j:k]
        if base and base[0].isalpha():
            self.add(nfc(base[0] + ACCENTS[ch]) + base[1:], i)
        return k

    def command(self, name: str, i: int, j: int, index_mode: bool) -> int:
        s = self.s
        cls, spec = self.p.command(name)
        line = self.line(i)
        self.info.commands.append((cls or "unknown", name, line))
        self.sep()
        if cls == "definition":
            k = skip_ws(s, j)
            if s.startswith("\\", k):
                k = _match_cmd(s, k).end()
            elif s[k:k + 1] == "{":
                _, _, k = read_group(s, k)
            k2 = skip_ws(s, k)
            while s[k2:k2 + 1] == "[":
                _, _, k = read_opt(s, k2)
                k2 = skip_ws(s, k)
            if s[k2:k2 + 1] == "{":
                _, _, k = read_group(s, k2)
            self.info.skip_spans.append((j, k))
            return k
        try:
            args, k = read_args(s, j, spec)
        except LatexError as e:
            self.error(f"\\{name}: {e}", i)
            return j
        if name in self.p.strip:
            self.info.strip_spans.append((i, k))
        for arg in args:
            if arg.kind in "om":
                self.info.skip_spans.append((arg.start, arg.end))
            else:
                self.scan(arg.start, arg.end, index_mode or name == "index")
                self.sep()
        if name == "includegraphics":
            opts = next((s[a.start:a.end] for a in args if a.kind == "o"), None)
            path = next((s[a.start:a.end] for a in args if a.kind == "m"), "")
            self.info.graphics.append(Graphic(path.strip(), opts, line))
        elif name == "caption":
            self.info.captions.append(line)
        return k

    def begin(self, i: int, j: int) -> int:
        s = self.s
        line = self.line(i)
        k = skip_ws(s, j)
        if s[k:k + 1] != "{":
            self.error("\\begin χωρίς όνομα περιβάλλοντος", i)
            return j
        a, b, k = read_group(s, k)
        name = s[a:b].strip()
        env = self.p.env(name)
        cls = env["class"] if env else None
        self.info.commands.append(("env:" + (cls or "unknown"), name, line))
        self.sep()
        if cls == "verbatim":
            endtok = "\\end{" + name + "}"
            e = s.find(endtok, k)
            if e < 0:
                self.error(f"Το περιβάλλον {name} δεν κλείνει", i)
                return len(s)
            opts, k2 = None, k
            if "o" in env.get("args", "") and s[k:k + 1] == "[":
                oa, ob, k2 = read_opt(s, k)
                opts = s[oa:ob]
                self.info.skip_spans.append((oa, ob))
            line_end, rest = eol(s, k2), k2
            while rest < line_end and s[rest] in " \t\r":
                rest += 1
            if rest < min(line_end, e):
                # LaTeX engines disagree on this text (verbatim prints it, listings
                # drops it): keep it so nothing is lost, and let a human decide.
                self.error(f"Κείμενο στη γραμμή του \\begin{{{name}}}: ελέγξτε αν τυπώνεται", i)
                cstart = rest
            else:
                cstart = min(line_end + 1, e)
            self.sep()
            self.add(s[cstart:e], cstart)
            self.sep()
            self.info.verbatims.append(Verbatim(
                name, i, line, opts, cstart, self.line(cstart), e, e + len(endtok), self.line(e)))
            return e + len(endtok)
        if cls == "math":
            endtok = "\\end{" + name + "}"
            e = s.find(endtok, k)
            # the span must include \end{...}, or a line marker lands inside the math
            return self.math(k, e, len(endtok), i)
        try:
            args, k = read_args(s, k, env.get("args", "") if env else "")
        except LatexError as ex:
            self.error(f"\\begin{{{name}}}: {ex}", i)
            return k
        title = None
        for arg in args:
            if arg.kind in "om":
                self.info.skip_spans.append((arg.start, arg.end))
            else:
                if title is None:
                    title = (arg.start, arg.end)
                self.scan(arg.start, arg.end)
                self.sep()
        if cls == "tabular":
            self.open_tabular.append((line, k))
        elif cls == "container":
            self.open_containers.append(Container(name, env.get("element", name), i, k, line, title))
        return k

    def end(self, i: int, j: int) -> int:
        s = self.s
        k = skip_ws(s, j)
        if s[k:k + 1] != "{":
            return j
        a, b, k = read_group(s, k)
        name = s[a:b].strip()
        self.sep()
        env = self.p.env(name)
        cls = env["class"] if env else None
        if cls == "tabular" and self.open_tabular:
            bline, body = self.open_tabular.pop()
            self.info.tabulars.append(Tabular(bline, self.line(i), tabular_rows(s, body, i, self.lm)))
        elif cls == "container" and self.open_containers:
            c = self.open_containers.pop()
            c.end, c.end_after, c.end_line = i, k, self.line(i)
            self.info.containers.append(c)
        return k


_ROW_NOISE = re.compile(r"\\(?:hline|toprule|midrule|bottomrule)(?![A-Za-z])|\\cline\s*\{[^}]*\}|%[^\n]*")


def tabular_rows(s: str, a: int, b: int, lm: LineMap) -> list[int]:
    """Source line of every non-empty row of a tabular body."""
    segments, depth, start, i = [], 0, a, a
    while i < b:
        c = s[i]
        if c == "%":
            i = eol(s, i)
            continue
        if c == "\\":
            if s.startswith("\\\\", i) and depth == 0:
                segments.append((start, i))
                i += 2
                if s[i:i + 1] == "[":
                    _, _, i = read_opt(s, i)
                start = i
                continue
            i += 2
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
        i += 1
    segments.append((start, b))
    rows = []
    for x, y in segments:
        cleaned = _ROW_NOISE.sub(lambda m: " " * len(m.group()), s[x:y])
        m = re.search(r"\S", cleaned)
        if m:
            rows.append(lm.line(x + m.start()))
    return rows


def analyze(text: str, policy: Policy) -> SourceInfo:
    return _Analyzer(text, policy).run()


# --------------------------------------------------------------------------- snippets

FORMAT_TAGS = {
    "textit": "emph", "emph": "emph", "textbf": "strong", "texttt": "code",
    "textsc": "smallcaps", "underline": "u", "textsuperscript": "sup",
    "textsubscript": "sub", "textrm": None, "textnormal": None, "textup": None, "textsf": None,
}
DECL_TAGS = {
    "ttfamily": "code", "tt": "code", "bf": "strong", "bfseries": "strong",
    "it": "emph", "itshape": "emph", "em": "emph", "scshape": "smallcaps",
    "rm": None, "normalfont": None, "sffamily": None, "sf": None, "mdseries": None, "upshape": None,
}
REF_KINDS = {"ref", "pageref", "eqref"}


def _last_lang(events: list[tuple], default: str) -> str:
    for ev in reversed(events):
        if ev[0] == "lang":
            return ev[1]
    return default


def convert_snippet(s: str, policy: Policy, lang: str) -> list[tuple] | None:
    """Convert a raw LaTeX fragment into builder events.

    Returns ``None`` when the fragment contains anything we do not understand,
    so the caller can report it instead of converting it half-way.
    """
    events: list[tuple] = []
    frames: list[dict] = [{"tags": 0, "lang": lang}]
    cur = {"lang": lang}
    i, n = 0, len(s)
    text: list[str] = []

    def flush():
        if text:
            t = re.sub(r"\s+", " ", "".join(text))
            if t:
                events.append(("text", t))
            text.clear()

    def set_lang(code):
        if code != cur["lang"]:
            flush()
            cur["lang"] = code
            events.append(("lang", code))

    def close_frame():
        fr = frames.pop()
        flush()
        for _ in range(fr["tags"]):
            events.append(("close",))
        set_lang(fr["lang"])

    try:
        while i < n:
            c = s[i]
            if c == "%":
                i = eol(s, i)
                continue
            if c == "{":
                flush()
                frames.append({"tags": 0, "lang": cur["lang"]})
                i += 1
                continue
            if c == "}":
                if len(frames) == 1:
                    return None
                close_frame()
                i += 1
                continue
            if c == "~":
                text.append("\u00a0")
                i += 1
                continue
            if c == "$":
                flush()
                if s.startswith("$$", i):
                    k = s.find("$$", i + 2)
                    if k < 0:
                        return None
                    events.append(("math", "display", s[i + 2:k]))
                    i = k + 2
                else:
                    k = find_unescaped(s, "$", i + 1)
                    if k < 0:
                        return None
                    events.append(("math", "inline", s[i + 1:k]))
                    i = k + 1
                continue
            if c != "\\":
                text.append(c)
                i += 1
                continue
            m = CMD_RE.match(s, i)
            if m is None:
                return None
            if m.group(3) is not None:
                ch = m.group(3)
                i = m.end()
                if ch in ACCENTS:
                    if s[i:i + 1] == "{":
                        a, b, i = read_group(s, i)
                        base = s[a:b]
                    else:
                        base, i = s[i:i + 1], i + 1
                    text.append(nfc(base + ACCENTS[ch]))
                elif ch in SINGLE_TEXT:
                    text.append(SINGLE_TEXT[ch])
                else:
                    return None
                continue
            name = m.group(1)
            j = m.end()
            # a control word swallows the spaces after it
            k = j
            while k < n and s[k] in " \t\r\n":
                k += 1
            cls, spec = policy.command(name)
            if name in policy.switches:
                set_lang(policy.switches[name])
                i = k
            elif name in policy.wrappers:
                args, i = read_args(s, j, "M")
                flush()
                saved = cur["lang"]
                set_lang(policy.wrappers[name])
                sub = convert_snippet(s[args[0].start:args[0].end], policy, cur["lang"])
                if sub is None:
                    return None
                events.extend(sub)
                cur["lang"] = _last_lang(sub, cur["lang"])
                set_lang(saved)
            elif name == "index":
                args, i = read_args(s, j, "mM")
                flush()
                events.append(("index", s[args[0].start:args[0].end].strip(), s[args[1].start:args[1].end]))
            elif name == "label":
                args, i = read_args(s, j, "m")
                flush()
                events.append(("anchor", s[args[0].start:args[0].end].strip()))
            elif name in REF_KINDS:
                args, i = read_args(s, j, "m")
                flush()
                events.append(("xref", name, s[args[0].start:args[0].end].strip()))
            elif name == "url":
                args, i = read_args(s, j, "M")
                flush()
                events.append(("url", s[args[0].start:args[0].end]))
            elif name in FORMAT_TAGS:
                args, i = read_args(s, j, "M")
                flush()
                tag = FORMAT_TAGS[name]
                if tag:
                    events.append(("open", tag))
                saved = cur["lang"]
                sub = convert_snippet(s[args[0].start:args[0].end], policy, saved)
                if sub is None:
                    return None
                events.extend(sub)
                cur["lang"] = _last_lang(sub, saved)
                set_lang(saved)          # a group cannot leak its language switch
                if tag:
                    events.append(("close",))
            elif name in DECL_TAGS:
                i = k
                tag = DECL_TAGS[name]
                if tag:
                    flush()
                    events.append(("open", tag))
                    frames[-1]["tags"] += 1
            elif cls == "layout":
                _, i = read_args(s, j, spec)
                if spec == "":
                    i = k
                flush()
                events.append(("layout", name))
            elif cls == "space":
                text.append(" ")
                i = k
            elif name in ("ldots", "dots"):
                text.append("\u2026")
                i = k
            else:
                return None
        while len(frames) > 1:
            close_frame()
        flush()
        for _ in range(frames[0]["tags"]):
            events.append(("close",))
    except LatexError:
        return None
    return events

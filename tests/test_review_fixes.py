r"""Regression tests for the bugs found in the review of 27/11/2026."""
import pytest

from texcanon.indexterm import parse_index
from texcanon.latex import analyze
from texcanon.policy import load_policy
from texcanon.preprocess import marker, preprocess

P = load_policy()


# 1. text on the \begin{code} line must not vanish -----------------------------

VERB_SAME_LINE = "\\begin{code} x <- 1\ny <- 2\n\\end{code}\n"


def test_verbatim_text_on_begin_line_is_kept_in_output():
    out = preprocess(analyze(VERB_SAME_LINE, P)).text
    assert "x <- 1" in out


def test_verbatim_text_on_begin_line_counts_as_content():
    assert analyze(VERB_SAME_LINE, P).words[1]["x"] == 1


def test_verbatim_text_on_begin_line_is_reported():
    errors = analyze(VERB_SAME_LINE, P).errors
    assert [line for _, line in errors] == [1]


def test_verbatim_without_text_on_begin_line_is_not_reported():
    assert analyze("\\begin{code}\ny <- 2\n\\end{code}\n", P).errors == []


# 2. no line marker inside a math environment ---------------------------------

MATH_ENV = "Κείμενο\n\\begin{equation}\nx = 1\n\\end{equation}\nΤέλος\n"


def test_no_marker_before_end_of_math_environment():
    prep = preprocess(analyze(MATH_ENV, P))
    body = prep.text.split("\\begin{equation}")[1].split("\\end{equation}")[0]
    assert "\u27e6" not in body
    assert 4 in prep.unmarked_lines


def test_lines_after_math_environment_still_marked():
    assert marker(5) + "Τέλος" in preprocess(analyze(MATH_ENV, P)).text


# 3. makeindex quote escapes are unquoted exactly once -------------------------

@pytest.mark.parametrize("arg, text", [
    ('a"!b', "a!b"),
    ('a"@b', "a@b"),
    ('a"|b', "a|b"),
    ('a""b', 'a"b'),
])
def test_quoted_special_char_is_literal(arg, text):
    term = parse_index(arg)
    assert [(lv.sort, lv.text) for lv in term.levels] == [(None, text)]
    assert term.encap is None


def test_quoted_char_inside_sort_key_and_subentry():
    term = parse_index('a"!x@A!b"@y')
    assert [(lv.sort, lv.text) for lv in term.levels] == [("a!x", "A"), (None, "b@y")]


def test_tex_umlaut_is_not_treated_as_quote():
    assert parse_index('M\\"uller').levels[0].text == 'M\\"uller'


# 4. malformed LaTeX is reported, never raised ---------------------------------

@pytest.mark.parametrize("src, line", [
    ("Κείμενο\n\\'{a", 2),
    ("Κείμενο\n\\begin{itemize\nμετά", 2),
    ("Κείμενο\n\\end{itemize\nμετά", 2),
    ("Κείμενο\n\\newcommand{\\x}{abc", 2),
    ("γραμμή\\\\[σημείωση", 1),
    ("\\def\\", 1),
    ("Κείμενο\n\\textbf\\", 2),
])
def test_malformed_input_is_reported_as_error(src, line):
    info = analyze(src, P)
    assert line in [ln for _, ln in info.errors]


def test_text_after_malformed_command_is_still_counted():
    info = analyze("Κείμενο\n\\begin{itemize\nμετά", P)
    assert info.words[3]["μετά"] == 1

r"""Regression tests for the remaining review items (27/11/2026)."""
import pytest

from texcanon import pandoc
from texcanon.latex import analyze, convert_snippet, read_opt
from texcanon.policy import PolicyError, load_policy
from texcanon.preprocess import preprocess

P = load_policy()


# 5. \def parameter text is part of the definition, not content ----------------

@pytest.mark.parametrize("src", [
    "\\def\\foo#1{ΣΩΜΑ #1}\nκείμενο\n",
    "\\def\\foo(#1,#2){ΣΩΜΑ}\nκείμενο\n",
])
def test_def_with_parameters_is_skipped(src):
    info = analyze(src, P)
    assert dict(info.words[1]) == {}
    assert info.words[2]["κείμενο"] == 1
    assert info.errors == []


# 6. no line marker inside arguments that reach the builder as raw LaTeX -------

@pytest.mark.parametrize("src", [
    "Λέξη\\index{x}{Πρώτη\nΔεύτερη}\nΤέλος\n",
    "Λέξη \\textgreek{Πρώτη\nΔεύτερη} λέξη\nΤέλος\n",
])
def test_no_marker_inside_raw_custom_argument(src):
    prep = preprocess(analyze(src, P))
    assert "\u27e6L2\u27e7" not in prep.text
    assert 2 in prep.unmarked_lines
    assert "\u27e6L3\u27e7Τέλος" in prep.text


def test_marker_still_placed_inside_native_content_argument():
    prep = preprocess(analyze("Λέξη \\textbf{Πρώτη\nΔεύτερη}\n", P))
    assert "\u27e6L2\u27e7Δεύτερη" in prep.text


# accents: analyze and convert_snippet agree ------------------------------------

def test_snippet_accent_on_group_matches_analyze():
    assert convert_snippet("\\'{ab}", P, "el") == [("text", "\u00e1b")]
    assert dict(analyze("\\'{ab}", P).words[1]) == {"\u00e1b": 1}


# Pandoc folders: newest version first ------------------------------------------

def test_tool_dirs_sorted_by_version(tmp_path):
    for name in ("pandoc-3.9", "pandoc-3.14", "pandoc-3.14.1", "other"):
        (tmp_path / name).mkdir()
    assert [d.name for d in pandoc.tool_dirs(tmp_path)] == ["pandoc-3.14.1", "pandoc-3.14", "pandoc-3.9"]


# policy.toml is validated ------------------------------------------------------

def _policy(tmp_path, text):
    p = tmp_path / "policy.toml"
    p.write_text(text, encoding="utf-8")
    return p


def test_default_policy_is_valid():
    assert load_policy().command("textbf") == ("content", "M")


def test_command_in_two_classes_is_rejected(tmp_path):
    p = _policy(tmp_path, '[commands.content]\nfoo = ""\n[commands.layout]\nfoo = ""\n')
    with pytest.raises(PolicyError, match="foo"):
        load_policy(p)


def test_bad_argspec_is_rejected(tmp_path):
    p = _policy(tmp_path, '[commands.content]\nfoo = "mX"\n')
    with pytest.raises(PolicyError, match="foo"):
        load_policy(p)


def test_unknown_command_table_is_rejected(tmp_path):
    p = _policy(tmp_path, '[commands.layuot]\nfoo = ""\n')
    with pytest.raises(PolicyError, match="layuot"):
        load_policy(p)


def test_bad_environment_class_is_rejected(tmp_path):
    p = _policy(tmp_path, '[environments]\nfoo = { class = "nope" }\n')
    with pytest.raises(PolicyError, match="foo"):
        load_policy(p)


# read_opt honours % comments like read_group -----------------------------------

def test_read_opt_skips_comment():
    s = "[a %]\nb]"
    assert read_opt(s, 0) == (1, 7, 8)


# \end must match the open \begin ------------------------------------------------

def test_mismatched_end_is_reported():
    info = analyze("\\begin{defarea}{Τ}\nx\n\\end{itemize}\n", P)
    msgs = {line: msg for msg, line in info.errors}
    assert "itemize" in msgs[3]
    assert "defarea" in msgs[1]


def test_unclosed_content_environment_is_reported():
    info = analyze("\\begin{itemize}\n\\item x\n", P)
    assert [line for _, line in info.errors] == [1]


def test_nested_environments_close_cleanly():
    src = ("\\begin{figure}\n\\begin{center}\n\\begin{tabular}{l}\nx\n\\end{tabular}\n"
           "\\end{center}\n\\end{figure}\n\\begin{equation}\nx\n\\end{equation}\n"
           "\\begin{code}\n\\end{itemize}\n\\end{code}\n")
    assert analyze(src, P).errors == []

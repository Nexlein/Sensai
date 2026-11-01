"""Confirmation diff."""

from sensai.domain.models import ToolCall
from sensai.interfaces.diff import DiffLine, diff_text, parse_diff

EDIT = """--- a/f.txt
+++ b/f.txt
@@ -1,3 +1,3 @@
 one
-two
+TWO
 three
@@ -10,2 +10,3 @@
 ten
+-- not a header
 eleven
\\ No newline at end of file"""


def test_parse_diff_numbers_lines_and_marks_gaps():
    assert parse_diff(EDIT) == [
        DiffLine("context", 1, "one"),
        DiffLine("remove", 2, "two"),
        DiffLine("add", 2, "TWO"),
        DiffLine("context", 3, "three"),
        DiffLine("gap", None, "⋮"),
        DiffLine("context", 10, "ten"),
        DiffLine("add", 11, "-- not a header"),
        DiffLine("context", 12, "eleven"),
    ]


def _call(preview, **arguments):
    return ToolCall(
        name="write_file", arguments={"path": "f.txt", **arguments}, preview=preview
    )


def test_diff_text_none_without_preview():
    assert diff_text(_call(None)) is None


def _plain(call) -> str:
    rendered = diff_text(call)
    assert rendered is not None
    return rendered.plain


def test_diff_text_shows_header_counts_and_lines():
    text = _plain(_call(EDIT))

    assert text.startswith("● write_file(f.txt)\n  ⎿  +2 -1\n")
    assert "      2 - two\n" in text
    assert "      2 + TWO\n" in text
    assert "     11 + -- not a header\n" in text


def test_diff_text_shows_every_changed_line_of_a_long_diff():
    body = "\n".join(f"+row {i}" for i in range(30))
    text = _plain(_call(f"@@ -0,0 +1,30 @@\n{body}"))

    assert "+30 -0" in text
    assert "row 0\n" in text
    assert "row 29\n" in text
    assert "more lines" not in text


def test_diff_text_reports_no_changes():
    assert _plain(_call("")) == "● write_file(f.txt)\n  ⎿  No changes\n"

"""Presentation helpers.

The look is not testable here, but the HTML contract is: user-supplied strings must
be escaped (scene names and licence text reach these helpers), and the cover bracket
must clamp to 0-100% so a bad estimate cannot render a bar outside its track.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import theme  # noqa: E402


class Recorder:
    """Captures what the helpers would render, standing in for streamlit."""

    def __init__(self):
        self.html = []

    def markdown(self, body, unsafe_allow_html=False):
        self.html.append(body)

    @property
    def last(self):
        return self.html[-1]


@pytest.fixture
def recorder(monkeypatch):
    rec = Recorder()
    monkeypatch.setattr(theme, "st", rec)
    return rec


def test_palette_defines_every_colour_the_css_uses():
    for key in ("ink", "primary", "warn", "danger", "line", "surface"):
        assert theme.PALETTE[key].startswith("#")


def test_css_has_no_unresolved_placeholders():
    assert "%(" not in theme.CSS
    assert "--primary:" in theme.CSS


def test_hero_escapes_user_text(recorder):
    theme.hero("<script>alert(1)</script>", "sub")
    assert "<script>" not in recorder.last
    assert "&lt;script&gt;" in recorder.last


def test_pills_render_kind_classes(recorder):
    theme.pills([("Detector ready", "ok"), ("Masks off", "off")])
    assert 'class="fl-pill ok"' in recorder.last
    assert 'class="fl-pill off"' in recorder.last


def test_stats_marks_muted_entries(recorder):
    theme.stats([("A", "1", "note"), ("B", "2", "note")], muted={1})
    assert recorder.last.count("fl-stat ") >= 1
    assert "is-muted" in recorder.last


def test_note_escapes_and_applies_kind(recorder):
    theme.note("5 > 3 & counting", "warn")
    assert "fl-note warn" in recorder.last
    assert "&gt;" in recorder.last and "&amp;" in recorder.last


def test_bracket_fill_spans_lower_to_upper(recorder):
    theme.bracket(17.0, 92.6, "low", "high", "summary")
    assert "left:17.00%" in recorder.last
    assert "width:75.60%" in recorder.last


def test_bracket_clamps_out_of_range_estimates(recorder):
    """A cover estimate above 100% must not render a bar past its track."""
    theme.bracket(-5.0, 140.0, "low", "high", "summary")
    assert "left:0.00%" in recorder.last
    assert "width:100.00%" in recorder.last


def test_bracket_keeps_a_visible_sliver_when_bounds_coincide(recorder):
    theme.bracket(40.0, 40.0, "low", "high", "summary")
    assert "width:0.60%" in recorder.last

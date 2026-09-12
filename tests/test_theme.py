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


def _rules(css: str):
    """Yield (selectors, declarations) for each rule in the stylesheet."""
    body = css[css.index("<style>") + len("<style>") : css.index("</style>")]
    for chunk in body.split("}"):
        if "{" not in chunk:
            continue
        selectors, declarations = chunk.split("{", 1)
        yield selectors.strip().splitlines()[-1].strip(), declarations


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


def test_navbar_escapes_user_text(recorder):
    theme.navbar("<script>alert(1)</script>")
    assert "<script>" not in recorder.last
    assert "&lt;script&gt;" in recorder.last


def test_navbar_renders_tag_links(recorder):
    theme.navbar("ForestLens", tags=[("GitHub", "https://example.test"), ("Plain", "")])
    assert 'href="https://example.test"' in recorder.last
    assert 'rel="noopener"' in recorder.last
    assert "Plain" in recorder.last


def test_navbar_is_sticky_not_fixed(recorder):
    """Fixed positioning would overlay the sidebar and its expand control."""
    block = theme.CSS[theme.CSS.index("\n.fl-nav {"):]
    block = block[: block.index("}")]
    assert "position: sticky" in block


def test_sidebar_controls_are_not_hidden():
    """A blanket header rule once hid the only way to reopen a collapsed sidebar."""
    assert 'stSidebarCollapsed"] button' in theme.CSS
    assert "stHeaderActionElements" in theme.CSS
    hidden = theme.CSS[theme.CSS.index("#MainMenu"):]
    hidden = hidden[: hidden.index("}")]
    assert "stToolbar" not in hidden


def test_lede_escapes_user_text(recorder):
    theme.lede("a & b")
    assert "&amp;" in recorder.last


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


def test_every_class_the_components_emit_is_defined_in_the_css(recorder):
    """A class that exists in HTML but not in CSS renders unstyled and silent.

    Without a browser to look at, this is the check that catches a consolidated or
    renamed rule leaving a component bare.
    """
    import re

    theme.navbar("t", tags=[("x", "https://example.test")])
    theme.lede("lede")
    theme.pills([("a", "ok"), ("b", "off"), ("c", "warn"), ("d", "neutral")])
    theme.cards([("label", "body")])
    theme.stats([("a", "1", "n"), ("b", "2", "n")], muted={1})
    theme.section("title", kicker="kick", note="note")
    theme.note("text", "warn")
    theme.bracket(10.0, 90.0, "low", "high", "summary")

    emitted = set()
    for block in recorder.html:
        for attr in re.findall(r'class="([^"]+)"', block):
            emitted.update(attr.split())

    missing = sorted(name for name in emitted if f".{name}" not in theme.CSS)
    assert not missing, f"classes emitted but never styled: {missing}"


def test_no_component_relies_on_inherited_line_height(recorder):
    """Streamlit's container line-height clipped uppercase labels once already."""
    for selector in (".fl-card-label", ".fl-nav-brand", ".fl-section-title", ".fl-bracket"):
        # The property may come from a grouped rule, so check every rule that
        # matches the class rather than one block.
        supplied = any(
            "line-height" in declarations
            and any(selector == part.strip() for part in selectors.split(","))
            for selectors, declarations in _rules(theme.CSS)
        )
        assert supplied, f"{selector} gets no explicit line-height from any rule"

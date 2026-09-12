"""End-to-end render checks using Streamlit's own test harness.

These catch what a syntax check cannot: widget arguments the installed Streamlit
does not accept, and exceptions on code paths that only execute once a scene is
loaded and analysed. Running `python app/app.py` returns before reaching those.

The full-analysis case needs model weights, so it is opt-in:

    FORESTLENS_SLOW_TESTS=1 python -m pytest tests/test_app_renders.py -q
"""

import os
from pathlib import Path

import pytest

from src import detection

# Absolute: AppTest.from_file does not resolve relative to the repo root.
APP = str(Path(__file__).resolve().parents[1] / "app" / "app.py")
SLOW = os.environ.get("FORESTLENS_SLOW_TESTS") == "1"


@pytest.fixture(scope="module")
def app():
    at = pytest.importorskip("streamlit.testing.v1").AppTest.from_file(
        APP, default_timeout=900
    )
    return at.run()


def test_initial_render_raises_nothing(app):
    assert not app.exception, [e.value for e in app.exception]


def test_intro_and_status_render(app):
    blob = " ".join(m.value for m in app.markdown)
    assert "fl-nav-brand" in blob           # sticky navbar carries the brand
    assert "fl-lede" in blob                # one-line description
    assert "fl-card-label" in blob          # the three explanatory cards
    assert "fl-pill" in blob                # detector/mask status badges


def test_both_source_tabs_are_offered(app):
    assert len(app.tabs) == 2


def test_sample_scene_can_be_loaded(app):
    labels = [b.label for b in app.button]
    assert "Load sample scene" in labels


@pytest.mark.skipif(not SLOW, reason="needs model weights; set FORESTLENS_SLOW_TESTS=1")
@pytest.mark.skipif(not detection.available(), reason="no detector installed")
def test_full_analysis_renders_every_result_component():
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(APP, default_timeout=900).run()
    {b.label: b for b in at.button}["Load sample scene"].click().run()
    {b.label: b for b in at.button}["Run analysis"].click().run()

    assert not at.exception, [e.value for e in at.exception]
    blob = " ".join(m.value for m in at.markdown)
    for component in (
        "fl-stat-value",      # headline figures
        "fl-bracket",         # cover reported as a range
        "fl-track-fill",      # the range drawn on its track
        "fl-note warn",       # limitations panel
        "fl-section-kicker",  # section headings
    ):
        assert component in blob, f"{component} did not render"

    assert len(at.dataframe) == 1          # per-crown table
    assert len(at.download_button) == 4    # PNG, CSV, GeoJSON, run metadata


def test_every_sidebar_control_explains_itself(app):
    """Four unlabelled thresholds that silently change the headline count fail the
    "can a stranger use it" bar, so each must carry help text."""
    controls = list(app.sidebar.slider) + list(app.sidebar.select_slider) + list(app.sidebar.checkbox)
    assert len(controls) == 5
    missing = [c.label for c in controls if not getattr(c, "help", None)]
    assert not missing, f"controls without help text: {missing}"


def test_tile_size_help_names_the_validated_value(app):
    """Tile size nearly doubles the count, so its help must say which value the
    validation figures were produced at."""
    tile = next(s for s in app.sidebar.select_slider if "Tile size" in s.label)
    assert "800" in tile.help
    assert "VALIDATION" in tile.help


def test_thresholds_are_collapsed_by_default(app):
    """The landing state should be a sample scene and a Run button, not four sliders.

    The controls still exist and still render — they are just behind a closed
    expander, with the active values summarised beside it.
    """
    advanced = next(e for e in app.sidebar.expander if e.label == "Advanced settings")

    # The controls live inside it, not loose in the sidebar.
    nested = list(advanced.slider) + list(advanced.select_slider) + list(advanced.checkbox)
    assert len(nested) == 5

    # AppTest does not expose an expander's open state, so pin the intent at source.
    source = Path(APP).read_text()
    assert 'st.expander("Advanced settings", expanded=False)' in source


def test_active_settings_stay_visible_while_collapsed(app):
    """Hiding the controls must not hide what they are set to."""
    blob = " ".join(m.value for m in app.sidebar.markdown)
    for shown in ("confidence 0.25", "IoU 0.4", "tile 800 px", "overlap 0.15"):
        assert shown in blob, f"{shown!r} not summarised in the sidebar"

"""Presentation layer: palette, global CSS and the small components the app renders.

Kept separate from `app.py` so the page logic stays readable, and so the visual
language lives in one place. Streamlit's own widget classes are targeted only
through stable `data-testid` hooks; everything bespoke is plain HTML this module
emits itself, which does not break when Streamlit renames an internal class.
"""

from __future__ import annotations

import html

import streamlit as st

#: Forest palette. Deliberately low-chroma so the imagery is the loudest thing on
#: screen — the detections are the product, not the interface.
PALETTE = {
    "ink": "#10201A",
    "ink_soft": "#475A52",
    "muted": "#7C8F87",
    "line": "#E2EAE6",
    "surface": "#FFFFFF",
    "canvas": "#F7F9F8",
    "primary": "#1F6B47",
    "primary_dark": "#14512F",
    "primary_wash": "#ECF4EF",
    "warn": "#9A6206",
    "warn_wash": "#FDF6E7",
    "warn_line": "#F0DFB4",
    "danger": "#96392A",
    "danger_wash": "#FBEEEC",
}

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

:root {
  --ink: %(ink)s;
  --ink-soft: %(ink_soft)s;
  --muted: %(muted)s;
  --line: %(line)s;
  --surface: %(surface)s;
  --canvas: %(canvas)s;
  --primary: %(primary)s;
  --primary-dark: %(primary_dark)s;
  --primary-wash: %(primary_wash)s;
  --warn: %(warn)s;
  --warn-wash: %(warn_wash)s;
  --warn-line: %(warn_line)s;
  --danger: %(danger)s;
  --danger-wash: %(danger_wash)s;
  --radius: 12px;
  --shadow: 0 1px 2px rgba(16,32,26,.04), 0 8px 24px -12px rgba(16,32,26,.10);
}

html, body, [class*="css"], [data-testid="stAppViewContainer"] {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  color: var(--ink);
}

/* Hide only the menu and footer. An earlier blanket rule on the header also hid the
   sidebar's expand control, leaving no way to reopen a collapsed sidebar. */
#MainMenu, footer, [data-testid="stHeaderActionElements"] { visibility: hidden; }
[data-testid="stAppHeader"] { background: transparent; }

/* The sidebar's collapse and expand buttons must stay obvious. */
[data-testid="stSidebarCollapsed"] { z-index: 80; }
[data-testid="stSidebarCollapsed"] button,
[data-testid="stSidebarCollapseButton"] button {
  background: var(--surface) !important;
  border: 1px solid var(--line) !important;
  border-radius: 9px; color: var(--primary-dark) !important;
  box-shadow: var(--shadow);
}
[data-testid="stSidebarCollapsed"] button:hover,
[data-testid="stSidebarCollapseButton"] button:hover { border-color: var(--primary) !important; }

.block-container { padding-top: 1rem; padding-bottom: 4rem; max-width: 1180px; }

/* ---- Navbar -------------------------------------------------------------- */
/* Sticky inside the main column rather than fixed to the viewport, so it can never
   overlay the sidebar or its expand control. */
.fl-nav {
  position: sticky; top: 0; z-index: 60;
  display: flex; align-items: center; justify-content: space-between;
  gap: 1rem; flex-wrap: wrap;
  margin: 0 -1.3rem 1.7rem; padding: .7rem 1.3rem;
  background: rgba(255,255,255,.86);
  -webkit-backdrop-filter: saturate(180%%) blur(12px);
  backdrop-filter: saturate(180%%) blur(12px);
  border-bottom: 1px solid var(--line);
}
.fl-nav-brand {
  display: flex; align-items: center; gap: .6rem;
  font-size: 1.2rem; font-weight: 700; letter-spacing: -0.022em;
  line-height: 1.6; color: var(--ink);
}
.fl-nav-mark {
  width: 32px; height: 32px; border-radius: 9px; flex: none;
  background: linear-gradient(150deg, var(--primary) 0%%, var(--primary-dark) 100%%);
  display: grid; place-items: center; font-size: 1rem; line-height: 1;
  box-shadow: 0 3px 10px -4px rgba(31,107,71,.55);
}
.fl-nav-right { display: flex; align-items: center; gap: .45rem; flex-wrap: wrap; }
.fl-nav-tag {
  font-size: .74rem; font-weight: 550; color: var(--ink-soft);
  padding: .3rem .65rem; border: 1px solid var(--line); border-radius: 999px;
  background: var(--surface); line-height: 1.5; white-space: nowrap;
}
.fl-nav-tag a { color: inherit; text-decoration: none; }
.fl-nav-tag:hover { border-color: var(--primary); color: var(--primary-dark); }

/* ---- Lede ---------------------------------------------------------------- */
.fl-lede {
  font-size: 1.05rem; color: var(--ink-soft);
  max-width: 66ch; line-height: 1.6; margin: 0 0 1.5rem;
}

h1, h2, h3 { letter-spacing: -0.018em; font-weight: 650; color: var(--ink); line-height: 1.35; }

/* Numbers line up in columns when they share a width. */
.fl-stat-value, .fl-range-value, .fl-bracket { font-variant-numeric: tabular-nums; }

/* ---- Pills --------------------------------------------------------------- */
.fl-pills { display: flex; flex-wrap: wrap; gap: .45rem; margin-top: 1rem; }
.fl-pill {
  display: inline-flex; align-items: center; gap: .4rem;
  padding: .3rem .65rem; border-radius: 999px;
  font-size: .78rem; font-weight: 550; letter-spacing: .005em;
  border: 1px solid var(--line); background: var(--surface); color: var(--ink-soft);
  white-space: nowrap;
}
.fl-pill .fl-dot { width: 6px; height: 6px; border-radius: 50%%; flex: none; background: #C4D2CB; }
.fl-pill.ok { border-color: #C9E2D5; background: var(--primary-wash); color: var(--primary-dark); }
.fl-pill.ok .fl-dot { background: var(--primary); }
.fl-pill.off .fl-dot { background: var(--muted); }
.fl-pill.neutral { border-color: var(--line); background: var(--canvas); color: var(--ink-soft); }
.fl-pill.neutral .fl-dot { background: #C4D2CB; }
.fl-pill.warn { border-color: var(--warn-line); background: var(--warn-wash); color: var(--warn); }
.fl-pill.warn .fl-dot { background: var(--warn); }

/* ---- Cards --------------------------------------------------------------- */
.fl-grid { display: grid; gap: .75rem; }
.fl-grid-3 { grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.fl-card {
  border: 1px solid var(--line); border-radius: var(--radius);
  background: var(--surface); padding: 1rem 1.1rem; box-shadow: var(--shadow);
}
.fl-card-label, .fl-stat-label, .fl-range-name, .fl-section-kicker {
  font-size: .7rem; font-weight: 650; text-transform: uppercase;
  /* Explicit line-height: inheriting Streamlit's clipped the capitals. */
  line-height: 1.7; padding-bottom: 1px;
}
.fl-card-label { letter-spacing: .09em; color: var(--muted); margin-bottom: .35rem; }
.fl-card-body { font-size: .9rem; line-height: 1.6; color: var(--ink-soft); }
.fl-card-body strong { color: var(--ink); font-weight: 600; }

/* ---- Stats --------------------------------------------------------------- */
.fl-stats { display: grid; gap: .75rem; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); }
.fl-stat {
  border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface);
  padding: .95rem 1.05rem; box-shadow: var(--shadow); position: relative; overflow: hidden;
}
.fl-stat::before {
  content: ''; position: absolute; inset: 0 auto 0 0; width: 3px;
  background: linear-gradient(180deg, var(--primary), var(--primary-dark));
}
.fl-stat-label { letter-spacing: .09em; color: var(--muted); }
.fl-stat-value {
  margin-top: .25rem; font-size: 1.85rem; font-weight: 680;
  letter-spacing: -0.035em; line-height: 1.3; color: var(--ink);
  padding-bottom: 2px;
}
.fl-stat-note { margin-top: .3rem; font-size: .76rem; color: var(--muted); line-height: 1.45; }
.fl-stat.is-muted::before { background: var(--muted); }
.fl-stat.is-muted .fl-stat-value { color: var(--ink-soft); font-size: 1.3rem; }

/* ---- Cover bracket ------------------------------------------------------- */
.fl-bracket-wrap {
  border: 1px solid var(--line); border-radius: var(--radius); background: var(--surface);
  padding: 1.15rem 1.25rem 1rem; box-shadow: var(--shadow);
}
.fl-bracket {
  font-size: 1.9rem; font-weight: 690; letter-spacing: -0.035em;
  color: var(--ink); line-height: 1.25; padding-bottom: 2px;
}
.fl-bracket-sub { margin-top: .4rem; font-size: .84rem; color: var(--ink-soft); line-height: 1.55; }
.fl-track {
  position: relative; height: 10px; margin: 1.3rem 0 .55rem;
  border-radius: 999px; background: var(--canvas);
  border: 1px solid var(--line); overflow: hidden;
}
.fl-track-fill {
  position: absolute; top: 0; bottom: 0; border-radius: 999px;
  background: linear-gradient(90deg, var(--primary) 0%%, #7FBF9B 100%%);
}
.fl-track-labels {
  display: flex; justify-content: space-between;
  font-size: .72rem; color: var(--muted); font-variant-numeric: tabular-nums;
}
.fl-range-cols { display: grid; gap: .75rem; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); margin-top: 1rem; }
.fl-range-box { border-left: 2px solid var(--line); padding-left: .8rem; }
.fl-range-name { letter-spacing: .09em; color: var(--muted); }
.fl-range-value {
  font-size: 1.15rem; font-weight: 650; color: var(--ink);
  line-height: 1.4; margin: .1rem 0 .25rem;
}
.fl-range-note { font-size: .8rem; color: var(--ink-soft); line-height: 1.55; }

/* ---- Section headings ---------------------------------------------------- */
.fl-section { margin: 2.2rem 0 .9rem; }
.fl-section-kicker { letter-spacing: .1em; color: var(--primary); }
.fl-section-title {
  font-size: 1.2rem; font-weight: 650; letter-spacing: -0.02em;
  line-height: 1.45; margin-top: .1rem;
}
.fl-section-note { margin-top: .25rem; font-size: .85rem; color: var(--muted); }

/* ---- Notes (our own, so they read calmer than stock alerts) -------------- */
.fl-note {
  border: 1px solid var(--line); border-left: 3px solid var(--muted);
  border-radius: 8px; background: var(--surface);
  padding: .7rem .9rem; margin-bottom: .5rem;
  font-size: .85rem; line-height: 1.6; color: var(--ink-soft);
}
.fl-note.warn { border-left-color: var(--warn); background: var(--warn-wash); border-color: var(--warn-line); color: #6F4A08; }
.fl-note.info { border-left-color: var(--primary); background: var(--primary-wash); border-color: #C9E2D5; color: #17452F; }
.fl-note.danger { border-left-color: var(--danger); background: var(--danger-wash); border-color: #EBCFCA; color: #7A2E22; }
.fl-note strong { font-weight: 620; }

/* ---- Streamlit widgets --------------------------------------------------- */
[data-testid="stSidebar"] { background: var(--canvas); border-right: 1px solid var(--line); }
[data-testid="stSidebar"] .block-container { padding-top: 1.6rem; }

.stButton > button, [data-testid="stBaseButton-primary"] {
  border-radius: 9px; font-weight: 580; letter-spacing: .002em;
  border: 1px solid transparent; transition: transform .06s ease, box-shadow .18s ease;
}
[data-testid="stBaseButton-primary"] {
  background: linear-gradient(160deg, var(--primary), var(--primary-dark));
  box-shadow: 0 4px 14px -6px rgba(31,107,71,.55);
}
.stButton > button:hover { transform: translateY(-1px); }

[data-testid="stDownloadButton"] button {
  border-radius: 9px; border: 1px solid var(--line); background: var(--surface);
  color: var(--ink); font-weight: 550; width: 100%%;
}
[data-testid="stDownloadButton"] button:hover { border-color: var(--primary); color: var(--primary-dark); }

.stTabs [data-baseweb="tab-list"] { gap: .3rem; border-bottom: 1px solid var(--line); }
.stTabs [data-baseweb="tab"] { font-weight: 550; font-size: .92rem; color: var(--muted); }
.stTabs [aria-selected="true"] { color: var(--primary-dark); }

[data-testid="stExpander"] {
  border: 1px solid var(--line); border-radius: var(--radius);
  background: var(--surface); box-shadow: none;
}
[data-testid="stExpander"] summary { font-weight: 550; font-size: .88rem; }

[data-testid="stFileUploaderDropzone"] {
  border: 1px dashed #C7D6CE; border-radius: var(--radius); background: var(--canvas);
}
[data-testid="stImage"] img { border-radius: 10px; border: 1px solid var(--line); }
[data-testid="stDataFrame"] { border-radius: 10px; overflow: hidden; border: 1px solid var(--line); }

hr { border-color: var(--line); }
</style>
""" % PALETTE


def inject() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def _esc(text: object) -> str:
    return html.escape(str(text))


def navbar(title: str, tags: list[tuple[str, str]] | None = None, emoji: str = "🌲") -> None:
    """Sticky brand bar. `tags` is a list of (label, href); href may be empty."""
    right = "".join(
        '<span class="fl-nav-tag">'
        + (f'<a href="{_esc(href)}" target="_blank" rel="noopener">{_esc(label)}</a>' if href else _esc(label))
        + "</span>"
        for label, href in (tags or [])
    )
    st.markdown(
        f"""<div class="fl-nav">
          <div class="fl-nav-brand"><span class="fl-nav-mark">{emoji}</span>{_esc(title)}</div>
          <div class="fl-nav-right">{right}</div>
        </div>""",
        unsafe_allow_html=True,
    )


def lede(text: str) -> None:
    st.markdown(f'<div class="fl-lede">{_esc(text)}</div>', unsafe_allow_html=True)


def pills(items: list[tuple[str, str]]) -> None:
    """Compact status badges. `items` is a list of (label, kind) with kind
    one of ok / off / warn / neutral."""
    rendered = "".join(
        f'<span class="fl-pill {kind}"><span class="fl-dot"></span>{_esc(label)}</span>'
        for label, kind in items
    )
    st.markdown(f'<div class="fl-pills">{rendered}</div>', unsafe_allow_html=True)


def cards(items: list[tuple[str, str]]) -> None:
    """Equal-weight explanatory cards. `items` is (label, html body)."""
    rendered = "".join(
        f'<div class="fl-card"><div class="fl-card-label">{_esc(label)}</div>'
        f'<div class="fl-card-body">{body}</div></div>'
        for label, body in items
    )
    st.markdown(
        f'<div class="fl-grid fl-grid-3">{rendered}</div>', unsafe_allow_html=True
    )


def stats(items: list[tuple[str, str, str]], muted: set[int] | None = None) -> None:
    """Headline figures. `items` is (label, value, note)."""
    muted = muted or set()
    rendered = "".join(
        f'<div class="fl-stat{" is-muted" if i in muted else ""}">'
        f'<div class="fl-stat-label">{_esc(label)}</div>'
        f'<div class="fl-stat-value">{_esc(value)}</div>'
        f'<div class="fl-stat-note">{_esc(note)}</div></div>'
        for i, (label, value, note) in enumerate(items)
    )
    st.markdown(f'<div class="fl-stats">{rendered}</div>', unsafe_allow_html=True)


def section(title: str, kicker: str = "", note: str = "") -> None:
    parts = ['<div class="fl-section">']
    if kicker:
        parts.append(f'<div class="fl-section-kicker">{_esc(kicker)}</div>')
    parts.append(f'<div class="fl-section-title">{_esc(title)}</div>')
    if note:
        parts.append(f'<div class="fl-section-note">{_esc(note)}</div>')
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def note(text: str, kind: str = "") -> None:
    """A calmer alternative to st.warning; `kind` is warn / info / danger / ''."""
    st.markdown(f'<div class="fl-note {kind}">{_esc(text)}</div>', unsafe_allow_html=True)


def bracket(lower: float, upper: float, lower_note: str, upper_note: str, summary: str) -> None:
    """Canopy cover drawn as a range, because a single number would be a lie.

    The bar shows where the two independent estimates sit on 0-100%, so the width
    of the disagreement is the first thing the eye lands on.
    """
    left = max(0.0, min(lower, 100.0))
    right = max(left, min(upper, 100.0))
    st.markdown(
        f"""<div class="fl-bracket-wrap">
          <div class="fl-bracket">{lower:.1f}% &ndash; {upper:.1f}%</div>
          <div class="fl-bracket-sub">{_esc(summary)}</div>
          <div class="fl-track">
            <div class="fl-track-fill" style="left:{left:.2f}%;width:{max(right - left, 0.6):.2f}%"></div>
          </div>
          <div class="fl-track-labels"><span>0%</span><span>50%</span><span>100%</span></div>
          <div class="fl-range-cols">
            <div class="fl-range-box">
              <div class="fl-range-name">Lower bound</div>
              <div class="fl-range-value">{lower:.1f}%</div>
              <div class="fl-range-note">{_esc(lower_note)}</div>
            </div>
            <div class="fl-range-box">
              <div class="fl-range-name">Upper bound</div>
              <div class="fl-range-value">{upper:.1f}%</div>
              <div class="fl-range-note">{_esc(upper_note)}</div>
            </div>
          </div>
        </div>""",
        unsafe_allow_html=True,
    )

#!/usr/bin/env python
"""Assemble the self-contained IEEE-format report from its template and figures.

The template references figures by placeholder; this inlines them as data URIs so
docs/report/index.html is a single file that opens offline, prints to PDF from any
browser, and can be published as-is.

    python scripts/build_figures.py && python scripts/build_report.py
"""

from __future__ import annotations

import base64
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "docs" / "report"
FIGURES = REPORT / "figures"

PLACEHOLDERS = {
    "FIG_NATIVE": "fig_native.jpg",
    "FIG_RESAMPLED": "fig_resampled.jpg",
    "FIG_CLOSED": "fig_closed.jpg",
}


def main() -> int:
    template = (REPORT / "report.template.html").read_text()
    html = template
    for placeholder, filename in PLACEHOLDERS.items():
        path = FIGURES / filename
        if not path.exists():
            raise SystemExit(f"missing {path}; run scripts/build_figures.py first")
        html = html.replace(placeholder, base64.b64encode(path.read_bytes()).decode())

    leftover = [p for p in PLACEHOLDERS if p in html]
    if leftover:
        raise SystemExit(f"placeholders not substituted: {leftover}")

    out = REPORT / "index.html"
    out.write_text(html)
    print(f"wrote {out.relative_to(ROOT)} ({out.stat().st_size / 1e6:.2f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

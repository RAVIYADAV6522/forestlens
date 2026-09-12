#!/usr/bin/env python
"""Deploy ForestLens to a Hugging Face Space (Docker SDK).

Requires a write token first:

    hf auth login

then:

    python scripts/deploy_hf_space.py                # deploy
    python scripts/deploy_hf_space.py --check        # pre-flight only, no writes
    python scripts/deploy_hf_space.py --name my-app  # non-default Space name

Docker, not Streamlit: Spaces removed the streamlit SDK. `create_repo` with
space_sdk="streamlit" now fails with "Invalid option: expected one of
gradio|docker|static", even though the Streamlit Spaces documentation still
describes it. The app therefore ships with a Dockerfile.

NOTE: Hugging Face no longer hosts Docker or Gradio Spaces on the free CPU tier —
create_repo returns 402 Payment Required and points at PRO. This script is kept
because it works and is pre-flighted, but the live demo runs on Streamlit
Community Cloud instead. Run it only with a PRO account.

The Space needs a YAML header in README.md that the repo does not otherwise carry
(it would be misleading in a repo deployed elsewhere), so the header is written in
just before upload.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_NAME = "forestlens"

#: Never upload these to the Space.
IGNORE = [
    ".git/*", ".git*", ".venv/*", "__pycache__/*", "*/__pycache__/*", "*.pyc",
    ".pytest_cache/*", "lightning_logs/*", "outputs/*", ".DS_Store", "*/.DS_Store",
]

#: Spaces reads its config from a YAML header in README.md. The repo README has none,
#: because this project's live demo is hosted elsewhere; it is added at upload time.
SPACE_HEADER = """---
title: ForestLens
emoji: 🌳
colorFrom: green
colorTo: gray
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: Tree-crown detection and canopy-area estimation from forest imagery
---

"""

#: Files the Space cannot run without.
REQUIRED = [
    "README.md", "Dockerfile", "requirements.txt", "app/app.py", "src/pipeline.py",
    "data/sample/bc_open_canopy.tif",
]


def fail(message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(1)


def preflight() -> list[str]:
    """Checks that do not need credentials. Returns warnings."""
    problems, warnings = [], []

    for relative in REQUIRED:
        if not (ROOT / relative).exists():
            problems.append(f"missing required file: {relative}")

    dockerfile = (ROOT / "Dockerfile").read_text()
    port = re.search(r"app_port:\s*(\d+)", SPACE_HEADER)
    if port and f"--server.port={port.group(1)}" not in dockerfile:
        problems.append(
            f"Space header app_port is {port.group(1)} but the Dockerfile does not bind it"
        )
    if "--server.address=0.0.0.0" not in dockerfile:
        problems.append("Dockerfile must bind 0.0.0.0 or the Space is unreachable")
    if "useradd" not in dockerfile:
        problems.append("Dockerfile must run as uid 1000; Spaces does not run as root")

    requirements = (ROOT / "requirements.txt").read_text()
    if "sam2 @" in requirements:
        problems.append("requirements.txt says 'sam2 @'; the distribution is named 'sam-2'")
    if "sam-2 @" not in requirements:
        warnings.append("SAM 2 is not in requirements.txt; the Space will use labelled box proxies")
    if "download.pytorch.org/whl/cpu" not in requirements:
        warnings.append("torch is not pinned to the CPU index; the Space will pull a CUDA wheel")
    elif "sam-2 @" in requirements:
        warnings.append(
            "sam-2 builds a CUDA extension by default; it tolerates the failure "
            "(SAM2_BUILD_ALLOW_ERRORS=1) but the build log will show a warning"
        )

    total = sum(
        p.stat().st_size for p in (ROOT / "data/sample").glob("*.tif")
    ) / 1e6
    if total > 50:
        warnings.append(f"sample imagery is {total:.0f} MB; consider smaller crops")

    if problems:
        for problem in problems:
            print(f"  FAIL  {problem}")
        fail(f"{len(problems)} pre-flight problem(s); nothing was deployed")

    print(f"  PASS  pre-flight ({len(REQUIRED)} required files, Dockerfile, requirements)")
    print(f"  PASS  sample imagery {total:.1f} MB")
    for warning in warnings:
        print(f"  WARN  {warning}")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", default=DEFAULT_NAME)
    parser.add_argument("--check", action="store_true", help="pre-flight only, no writes")
    parser.add_argument("--private", action="store_true")
    args = parser.parse_args()

    print("Pre-flight")
    preflight()
    if args.check:
        print("\n--check: no Space was created or uploaded.")
        return 0

    try:
        from huggingface_hub import HfApi
        from huggingface_hub.errors import HfHubHTTPError
    except ImportError:
        fail("huggingface_hub is not installed (pip install -r requirements.txt)")

    api = HfApi()
    try:
        user = api.whoami()["name"]
    except Exception:
        fail(
            "not authenticated. Create a WRITE token at "
            "https://huggingface.co/settings/tokens then run:  hf auth login"
        )

    repo_id = f"{user}/{args.name}"
    print(f"\nSpace: {repo_id}")

    api.create_repo(
        repo_id=repo_id,
        repo_type="space",
        space_sdk="docker",
        private=args.private,
        exist_ok=True,
    )
    print("  created (or already existed)")

    readme = ROOT / "README.md"
    original = readme.read_text()
    if not original.startswith("---"):
        readme.write_text(SPACE_HEADER + original)
        print("  added the Space YAML header to README.md")

    print("\nUploading")
    url = api.upload_folder(
        folder_path=str(ROOT),
        repo_id=repo_id,
        repo_type="space",
        ignore_patterns=IGNORE,
        commit_message="Deploy ForestLens",
    )
    print(f"  {url}")

    if not original.startswith("---"):
        readme.write_text(original)   # keep the repo README free of Space config
        print("  restored the repo README")

    space_url = f"https://huggingface.co/spaces/{repo_id}"
    print(
        f"\nSpace:  {space_url}\n"
        f"Build log: {space_url}?logs=build\n\n"
        "The Docker build takes a while (torch, DeepForest, SAM 2). The first analysis\n"
        "then downloads model weights (DeepForest plus a ResNet-50 backbone), so it is\n"
        "slow once and fast after.\n\n"
        "If the build fails on sam-2, drop that line from requirements.txt and redeploy:\n"
        "the app falls back to bounding-box areas and labels them a proxy."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

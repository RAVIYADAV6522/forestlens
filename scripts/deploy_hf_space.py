#!/usr/bin/env python
"""Deploy ForestLens to a Hugging Face Space (Streamlit SDK).

Requires a write token first:

    hf auth login

then:

    python scripts/deploy_hf_space.py                # deploy
    python scripts/deploy_hf_space.py --check        # pre-flight only, no writes
    python scripts/deploy_hf_space.py --name my-app  # non-default Space name

Why it reads the Space's own README before pushing: Hugging Face supports only some
Streamlit versions for the streamlit SDK, and the published list is stale. Rather than
guess a version and watch the build fail, this creates the Space, reads the
`sdk_version` Hugging Face generated for it, and adopts that.
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

#: Files the Space cannot run without.
REQUIRED = [
    "README.md", "requirements.txt", "app/app.py", "src/pipeline.py",
    ".streamlit/config.toml", "data/sample/bc_open_canopy.tif",
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

    readme = (ROOT / "README.md").read_text()
    if not readme.startswith("---"):
        problems.append("README.md has no YAML header; the Space needs one")
    header = readme.split("---")[1] if readme.startswith("---") else ""
    for field in ("title:", "sdk:", "app_file:"):
        if field not in header:
            problems.append(f"README YAML header missing {field}")
    if "sdk: streamlit" not in header:
        problems.append("README YAML header must declare 'sdk: streamlit'")

    config = (ROOT / ".streamlit/config.toml").read_text()
    if re.search(r"^\s*port\s*=", config, re.MULTILINE):
        # Streamlit Spaces only allow port 8501; overriding it breaks the Space.
        problems.append(".streamlit/config.toml overrides the port; Spaces requires 8501")

    requirements = (ROOT / "requirements.txt").read_text()
    if "sam2 @" in requirements:
        problems.append("requirements.txt says 'sam2 @'; the distribution is named 'sam-2'")
    if "download.pytorch.org/whl/cpu" not in requirements:
        warnings.append("torch is not pinned to the CPU index; the Space will pull a CUDA wheel")
    if "sam-2 @" in requirements:
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

    print(f"  PASS  pre-flight ({len(REQUIRED)} required files, YAML header, port, requirements)")
    print(f"  PASS  sample imagery {total:.1f} MB")
    for warning in warnings:
        print(f"  WARN  {warning}")
    return warnings


def set_sdk_version(version: str) -> bool:
    """Pin README's sdk_version to what Hugging Face actually supports."""
    readme = ROOT / "README.md"
    text = readme.read_text()
    current = re.search(r"^sdk_version:\s*(\S+)\s*$", text, re.MULTILINE)
    if current and current.group(1) == version:
        return False
    if current:
        text = re.sub(r"^sdk_version:.*$", f"sdk_version: {version}", text, count=1, flags=re.MULTILINE)
    else:
        text = text.replace("sdk: streamlit", f"sdk: streamlit\nsdk_version: {version}", 1)
    readme.write_text(text)
    return True


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
        space_sdk="streamlit",
        private=args.private,
        exist_ok=True,
    )
    print("  created (or already existed)")

    # Adopt the Streamlit version Hugging Face generated for this Space.
    try:
        from huggingface_hub import hf_hub_download

        remote = Path(
            hf_hub_download(repo_id, "README.md", repo_type="space")
        ).read_text()
        found = re.search(r"^sdk_version:\s*(\S+)\s*$", remote, re.MULTILINE)
        if found:
            version = found.group(1)
            if set_sdk_version(version):
                print(f"  pinned sdk_version to {version} (from the Space's own README)")
            else:
                print(f"  sdk_version already matches the Space ({version})")
        else:
            print("  no sdk_version in the Space README; leaving ours as-is")
    except Exception as exc:
        print(f"  could not read the Space README ({exc}); leaving sdk_version as-is")

    print("\nUploading")
    url = api.upload_folder(
        folder_path=str(ROOT),
        repo_id=repo_id,
        repo_type="space",
        ignore_patterns=IGNORE,
        commit_message="Deploy ForestLens",
    )
    print(f"  {url}")

    space_url = f"https://huggingface.co/spaces/{repo_id}"
    print(
        f"\nSpace:  {space_url}\n"
        f"Build log: {space_url}?logs=build\n\n"
        "First run downloads model weights (DeepForest ~120 MB plus a ResNet-50\n"
        "backbone), so the first analysis is slow and later ones are not.\n\n"
        "If the build fails on sam-2, drop that line from requirements.txt and redeploy:\n"
        "the app falls back to bounding-box areas and labels them a proxy."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

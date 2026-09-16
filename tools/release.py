"""Cut a release: bump the version, commit, tag and push.

    python tools/release.py 0.3.0              # show what would change
    python tools/release.py 0.3.0 --write      # edit the version files
    python tools/release.py 0.3.0 --write --commit --tag --push

Pushing the tag is what triggers .github/workflows/release.yml, which builds
the installer and publishes it as a GitHub Release. The workflow refuses to
publish when the tag and ``__version__`` disagree, so always go through this
script (or update both files by hand).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INIT_FILE = REPO_ROOT / "elite_hud" / "__init__.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"

INIT_PATTERN = re.compile(r'^(__version__\s*=\s*")([^"]+)(")', re.MULTILINE)
PYPROJECT_PATTERN = re.compile(r'^(version\s*=\s*")([^"]+)(")', re.MULTILINE)
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def current_version() -> str:
    match = INIT_PATTERN.search(INIT_FILE.read_text(encoding="utf-8"))
    if not match:
        raise SystemExit("cannot read __version__ from elite_hud/__init__.py")
    return match.group(2)


def validate(version: str) -> None:
    if not SEMVER.match(version):
        raise SystemExit(f"'{version}' is not a plain MAJOR.MINOR.PATCH version")


def plan(version: str) -> list[tuple[Path, str, str]]:
    """(file, before, after) for every file that carries the version."""
    changes = []
    for path, pattern in ((INIT_FILE, INIT_PATTERN), (PYPROJECT, PYPROJECT_PATTERN)):
        text = path.read_text(encoding="utf-8")
        matches = pattern.findall(text)
        if not matches:
            raise SystemExit(f"cannot find a version string in {path}")
        if len(matches) > 1:
            # Replacing blindly would rewrite whichever line came last.
            raise SystemExit(f"{path} has {len(matches)} version strings; resolve that by hand")
        changes.append((path, matches[0][1], version))
    return changes


def run(args: list[str], *, dry_run: bool) -> int:
    print(("would run: " if dry_run else "running: ") + " ".join(args))
    if dry_run:
        return 0
    return subprocess.run(args, cwd=REPO_ROOT, check=False).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="new version, e.g. 0.3.0")
    parser.add_argument("--write", action="store_true", help="apply the version bump")
    parser.add_argument("--commit", action="store_true", help="git commit the bump")
    parser.add_argument("--tag", action="store_true", help="create the git tag")
    parser.add_argument("--push", action="store_true", help="push the commit and the tag")
    options = parser.parse_args()

    validate(options.version)
    old = current_version()
    if old == options.version:
        print(f"version is already {old}")
        return 1 if (options.commit or options.tag or options.push) else 0

    print(f"elite-hud {old} -> {options.version}")
    changes = plan(options.version)
    for path, before, after in changes:
        print(f"  {path.relative_to(REPO_ROOT)}: {before} -> {after}")

    if not options.write:
        print("\nnothing written; re-run with --write")
        return 0

    for path, _before, after in changes:
        text = path.read_text(encoding="utf-8")
        pattern = INIT_PATTERN if path == INIT_FILE else PYPROJECT_PATTERN
        path.write_text(pattern.sub(rf"\g<1>{after}\g<3>", text), encoding="utf-8")
    print("version files updated")

    tag = f"v{options.version}"
    if options.commit:
        if run(["git", "add", str(INIT_FILE), str(PYPROJECT)], dry_run=False) != 0:
            return 1
        if run(["git", "commit", "-m", f"Release {options.version}"], dry_run=False) != 0:
            return 1
    if options.tag:
        if run(["git", "tag", "-a", tag, "-m", f"elite-hud {options.version}"], dry_run=False) != 0:
            return 1
    if options.push:
        if options.commit:
            if run(["git", "push"], dry_run=False) != 0:
                return 1
        if options.tag:
            if run(["git", "push", "origin", tag], dry_run=False) != 0:
                return 1
        print("\nthe release workflow will now build and publish the installer")

    if not (options.commit or options.tag or options.push):
        print(f"\nnext: git commit -am 'Release {options.version}' && git tag {tag} && git push origin {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

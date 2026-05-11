#!/usr/bin/env python3
"""Move CHANGELOG.md's [Unreleased] section under a versioned header.

Called by scripts/release.sh as part of cutting a release. Refuses to run if:
  - CHANGELOG.md doesn't exist
  - the [Unreleased] section is missing or empty
  - the new version already appears in the file

Pass --dry-run to preview the new content on stdout without writing.
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

REPO_URL = "https://github.com/Cyfrin/clearsig"
CHANGELOG = Path(__file__).resolve().parent.parent / "CHANGELOG.md"


def transform(text: str, new_version: str, prev_version: str, today: str) -> str:
    if f"[{new_version}]" in text:
        raise SystemExit(f"Error: CHANGELOG.md already mentions version {new_version}")

    match = re.search(
        r"^## \[Unreleased\]\s*\n(.*?)(?=^## \[)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise SystemExit("Error: could not find ## [Unreleased] section in CHANGELOG.md")

    body = match.group(1).strip()
    if not body or not any(line.lstrip().startswith("-") for line in body.splitlines()):
        raise SystemExit(
            "Error: [Unreleased] section has no entries — nothing to release. "
            "Add changelog entries before cutting a release."
        )

    new_section = f"## [Unreleased]\n\n## [{new_version}] - {today}\n\n{body}\n\n"
    text = text[: match.start()] + new_section + text[match.end() :]

    # Refresh the [Unreleased] compare link and insert one for the new version.
    text = re.sub(
        r"^\[Unreleased\]:.*$",
        f"[Unreleased]: {REPO_URL}/compare/{new_version}...HEAD",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^(\[Unreleased\]:.*\n)",
        f"\\1[{new_version}]: {REPO_URL}/compare/{prev_version}...{new_version}\n",
        text,
        count=1,
        flags=re.MULTILINE,
    )
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_version", help="The new version being released (e.g., 0.2.0)")
    parser.add_argument("prev_version", help="The version this is being cut from (e.g., 0.1.0)")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print the new content to stdout instead of writing"
    )
    args = parser.parse_args()

    if not CHANGELOG.exists():
        print(f"Error: {CHANGELOG} does not exist", file=sys.stderr)
        return 1

    today = date.today().isoformat()
    new_text = transform(CHANGELOG.read_text(), args.new_version, args.prev_version, today)

    if args.dry_run:
        sys.stdout.write(new_text)
    else:
        CHANGELOG.write_text(new_text)
        print(f"Updated CHANGELOG.md: moved Unreleased → [{args.new_version}] ({today})")
    return 0


if __name__ == "__main__":
    sys.exit(main())

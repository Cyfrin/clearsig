#!/usr/bin/env bash
#
# Cut a GitHub release that matches pyproject.toml's version.
#
#   ./scripts/release.sh patch          # 0.1.0 → 0.1.1, tag v0.1.1, push, release
#   ./scripts/release.sh minor          # 0.1.0 → 0.2.0
#   ./scripts/release.sh major          # 0.1.0 → 1.0.0
#   ./scripts/release.sh --draft minor  # cut release as a draft
#
# What it does:
#   1. `uv version --bump <level>` bumps pyproject.toml.
#   2. Reads the new version with `uv version --short`.
#   3. Moves CHANGELOG.md's [Unreleased] content under a [vX.Y.Z] header with today's date
#      (refuses if there's nothing to release).
#   4. Commits the bump + changelog as "release vX.Y.Z" and creates a matching `vX.Y.Z` tag.
#   5. Pushes the commit AND the tag.
#   6. `gh release create` opens a GitHub Release on that tag with
#      auto-generated notes; the publish workflow picks it up from there.
#
# Pre-flight: working tree must be clean and on main.

set -euo pipefail

DRAFT=""
LEVEL=""

for arg in "$@"; do
  case "$arg" in
    --draft) DRAFT="--draft" ;;
    patch | minor | major) LEVEL="$arg" ;;
    -h | --help)
      awk '/^#!/ {next} /^#/ {sub(/^# ?/, ""); print; next} {exit}' "$0"
      exit 0
      ;;
    *)
      echo "Unknown argument: $arg" >&2
      exit 64
      ;;
  esac
done

if [ -z "$LEVEL" ]; then
  echo "Usage: $0 <patch|minor|major> [--draft]" >&2
  exit 64
fi

for cmd in uv gh git; do
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: '$cmd' is not installed." >&2
    exit 127
  fi
done

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "Error: working tree is dirty. Commit or stash first." >&2
  git status -s
  exit 1
fi

BRANCH=$(git rev-parse --abbrev-ref HEAD)
if [ "$BRANCH" != "main" ]; then
  echo "Warning: not on main (current: $BRANCH). Continue? [y/N]"
  read -r reply
  [ "$reply" = "y" ] || [ "$reply" = "Y" ] || exit 1
fi

PREV_VERSION=$(uv version --short)

echo "→ bumping version ($LEVEL) in pyproject.toml"
uv version --bump "$LEVEL" >/dev/null
NEW_VERSION=$(uv version --short)
NEW_TAG="v$NEW_VERSION"
echo "  $PREV_VERSION → $NEW_VERSION"

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
if [ -f "$SCRIPT_DIR/../CHANGELOG.md" ]; then
  echo "→ updating CHANGELOG.md"
  uv run python "$SCRIPT_DIR/update_changelog.py" "$NEW_VERSION" "$PREV_VERSION"
  CHANGELOG_PATH="$SCRIPT_DIR/../CHANGELOG.md"
else
  echo "  (no CHANGELOG.md; skipping)"
  CHANGELOG_PATH=""
fi

echo "→ committing and tagging $NEW_TAG"
git add pyproject.toml uv.lock ${CHANGELOG_PATH:+"$CHANGELOG_PATH"}
git commit -m "release $NEW_TAG"
# Annotated tag (lightweight tags are not pushed by --follow-tags).
git tag -a "$NEW_TAG" -m "release $NEW_TAG"

echo "→ pushing commit + tag"
git push --follow-tags

echo "→ cutting GitHub release for $NEW_TAG"
gh release create "$NEW_TAG" --generate-notes $DRAFT

echo ""
echo "✓ Release $NEW_TAG cut. The publish workflow will pick it up."

set shell := ["bash", "-cu"]

default:
    @just --list

# Sync dependencies
sync:
    uv sync

# Run ruff lint
lint:
    uv run ruff check

# Run ruff lint with --fix
lint-fix:
    uv run ruff check --fix

# Check formatting
format:
    uv run ruff format --check

# Reformat files in-place
format-fix:
    uv run ruff format

# Run the test suite
test:
    uv run pytest -q

# Run typechecker
ty:
    uv run ty check

# Run lint + format check + typecheck + tests
check: lint format ty test

# Cut a release (level = patch | minor | major)
release LEVEL:
    ./scripts/release.sh {{LEVEL}}

# Cut a draft release (level = patch | minor | major)
release-draft LEVEL:
    ./scripts/release.sh --draft {{LEVEL}}

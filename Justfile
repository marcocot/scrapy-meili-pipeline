# Justfile for scrapy-meili-pipeline
# Run any task with `just <target>` (requires `just` installed)

# set shell to bash for proper command chaining
set shell := ["bash", "-cu"]

# Default task
default: help

# ─────────────────────────────────────────────
# 🧱 Setup & Environment
# ─────────────────────────────────────────────

# Sync project dependencies
sync:
	uv sync --all-extras --dev

# Clean build, caches and temporary files
clean:
	rm -rf dist build .pytest_cache .mypy_cache .ruff_cache .coverage
	find . -type d -name "__pycache__" -exec rm -rf {} +

# Open project in interactive shell (with all deps available)
shell:
	uv run bash

# ─────────────────────────────────────────────
# 🧹 Linting, Formatting, Type checking
# ─────────────────────────────────────────────

# Run ruff linter
lint:
	uv run ruff check src tests

# Auto-fix lint issues
lint-fix:
	uv run ruff check --fix src tests

# Run black check (no changes)
format-check:
	uv run black --check src tests

# Auto-format with black
format:
	uv run black src tests

# Run mypy for type checking
types:
	uv run mypy src tests

# ─────────────────────────────────────────────
# 🧪 Tests
# ─────────────────────────────────────────────

# Run all tests with pytest
test:
	uv run pytest -q

# Run tests with coverage report
coverage:
	uv run pytest --cov-report html:cov_html --cov=src --cov-report=term-missing

# ─────────────────────────────────────────────
# 📦 Build & Publish
# ─────────────────────────────────────────────

# Build sdist + wheel using uv
build:
	uv build

# Publish to PyPI (requires trusted publisher or token)
publish:
	uv publish

# ─────────────────────────────────────────────
# 🧭 Utilities
# ─────────────────────────────────────────────

# Format, lint, type check, and test — all in one go
check:
	just lint
	just format-check
	just types
	just test

# Complete cleanup + rebuild
rebuild:
	just clean
	just sync
	just build

example:
	cd examples/simple_project && PYTHONPATH="$(git rev-parse --show-toplevel)/src" uv run scrapy crawl demo -s LOG_LEVEL=INFO


# Show help
help:
	@echo "Available commands:"
	@echo "  just sync           # install all deps with uv"
	@echo "  just clean          # clean build and cache files"
	@echo "  just lint           # run ruff lint checks"
	@echo "  just lint-fix       # auto-fix lint issues"
	@echo "  just format         # format code with black"
	@echo "  just types          # run mypy type checks"
	@echo "  just test           # run unit tests"
	@echo "  just coverage       # run tests with coverage"
	@echo "  just build          # build wheel and sdist"
	@echo "  just publish        # publish to PyPI"
	@echo "  just check          # run lint, format-check, types, tests"
	@echo "  just rebuild        # clean, sync, build"
	@echo "  just shell          # open shell with uv env"

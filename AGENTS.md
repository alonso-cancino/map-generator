# Repository Guidelines

## Project Structure & Module Organization
`dcel_builder/` contains the application code and CLI entry point (`__main__.py`). The current runtime path is small: `tree_loader.py` validates the hierarchy input, `hierarchy.py` builds the recursive raster subdivision, `raster_dcel.py` converts the leaf raster into polygons/DCEL, and `render.py` produces preview PNGs. Core DCEL types and JSON I/O live in `dcel.py` and `serializer.py`. Tests are split into `tests/unit/` for module behavior and `tests/integration/` for CLI/pipeline coverage. Repository-root JSON files are the current sample inputs; generated outputs should stay untracked.

## Build, Test, and Development Commands
Use Python 3.11+.

- `uv sync --dev`: install runtime and development dependencies.
- `uv run pytest`: run the full test suite.
- `uv run pytest tests/unit/test_hierarchy.py`: run a focused unit test file while iterating.
- `uv run ruff check .`: lint imports and basic style issues.
- `uv run ruff format .`: apply formatting before opening a PR.
- `uv run python -m dcel_builder` or `uv run dcel-map`: run the CLI locally.

## Coding Style & Naming Conventions
Follow PEP 8 with 4-space indentation and a maximum line length of 100 characters, matching `ruff` settings in `pyproject.toml`. Use `snake_case` for modules, functions, variables, and test files; use `PascalCase` only for classes. Keep modules narrowly scoped by responsibility. Prefer explicit type-friendly function signatures and small pure helpers for geometry transforms.

## Testing Guidelines
Tests use `pytest` and are discovered from `tests/`. Name new files `test_<feature>.py` and new tests `test_<behavior>`. Add unit tests for deterministic logic and integration tests when CLI behavior, JSON I/O, or full pipeline assembly changes. Run `uv run pytest` before submitting changes; update or add fixture data only when behavior intentionally changes.

## Commit & Pull Request Guidelines
Recent history favors short, imperative commit subjects such as `Implement foundational modules`. Keep the first line concise and descriptive. Pull requests should explain the behavioral change, mention affected modules or specs, and note test coverage. Include sample command output or updated artifact references when CLI behavior or generated map outputs change.

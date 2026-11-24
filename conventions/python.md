# Python conventions

For every Python repo, whether an app run from its checkout or a package published to PyPI. `all.md` applies too.

- **Python version**: Each repo picks its own minimum, stated in `pyproject.toml`'s `requires-python` as a lower bound (`">= 3.12"`), never a cap.
- **Environment**: A gitignored `.venv` at the repo root, with the repo installed editable: `pip install -e ".[dev]"`, plus any other extras the code needs.
- **`pyproject.toml` is the one config file**: the package, its dependencies, and every tool's settings (`[tool.ruff]`, `[tool.pyright]`, `[tool.pytest]`). No `setup.py`, `setup.cfg`, `requirements.txt`, or separate tool configs.
- **Dependencies**
  - **Ranges**: Each repo picks its own, except Ruff's pin below.
  - **Extras**: Developer-only tools (Ruff, pyright, pytest, any other linter) go in a `dev` extra. Anything heavy that only one feature imports goes in an extra named for that feature.
  - **Only what's imported**: Declare every dependency the repo's own code imports, and nothing else, so none relies on arriving through another package.
- **Formatting and linting**: Ruff does both. The format script is `ruff check --fix .` then `ruff format .`.
  - **Line length**: Each repo picks its own, set once in `[tool.ruff]`.
  - **Rules**: `select = ["ALL"]`, with an `ignore` list giving each entry's reason in a comment. Whole families first, then single rules from families otherwise on. `extend-select` brings back a rule a family ignore would turn off.
    - **The usual ignores**: Each still needs its own reason in the repo.
      - **Everywhere**: `D` (docstrings follow `all.md` instead), `CPY`, `COM` and `ISC001` (they conflict with the formatter), and `E501` (the formatter wraps code; what's left is long strings).
      - **More than a thin wrapper's code**: usually also `ANN` (pyright checks the types), `PTH`, `FBT`, `EM`, `TD`, `FIX`, `C90`, `N`, `S101`, `TRY003`, `PLR2004`, `PLR09`, and `TC006`.
  - **One-off findings**: A finding that's right as it is gets `# noqa: RULE` and a reason on its own line, not an ignore-list entry. A rule ignored for a set of files (`SLF001` for tests reaching into internals, `T201` for a CLI module that prints) goes in `[tool.ruff.lint.per-file-ignores]`, with a reason.
  - **Imports**: Absolute from the package or repo root. No `sys.path` hacks.
  - **Pinned below its next minor**: `ruff>=0.17,<0.18` in the `dev` extra, since with `ALL` selected a minor's new stable rules would fail CI on an unrelated PR. Moving to the next minor is its own PR, deciding for each new rule whether to fix what it flags or ignore it.
- **Type checking**: pyright, configured in `[tool.pyright]`. Setting `exclude` replaces pyright's defaults, and it doesn't read `.gitignore`, so set `["build", "dist", "**/__pycache__", "**/.*"]`.
  - **Silencing a finding**: `# pyright: ignore[rule]` with a reason, never a bare `# type: ignore`.
- **Typing**
  - **Structured data**: A `@dataclass` for a value the code builds, a `TypedDict` for a dict shaped from outside (an API response, a config file), and a `StrEnum` for a fixed set of strings.
- **Layout**
  - **Apps run from their checkout**: List the packages and top-level modules in `[tool.setuptools]`, so the editable install makes them importable anywhere in the venv, and a script in a subfolder runs directly as well as with `python -m`.
- **Testing**: pytest, with `testpaths` set in `pyproject.toml`, run from the repo root.
  - **Style**: Plain test functions with bare `assert`s (with a message where it says what a check means), fixtures rather than setup methods, and `pytest.mark.parametrize` rather than a loop over cases. A class groups tests only where they share a fixture of their own.
  - **Fixtures**: Shared ones go in a `conftest.py`. `tmp_path` for files and `monkeypatch` for the network, never real user data or a real account.
  - **Platform-specific tests**: Skipped on other OSes with `pytest.mark.skipif`, beside a matching test for the other OS family where one applies.
- **CI**: `.github/workflows/ci.yml`, with `fail-fast: false` on every matrix.
  - **pyright on every supported version**: It checks against the running interpreter, so the matrix runs from `requires-python` up to the newest version `setup-python` offers.
  - **Ruff once**: It checks against `requires-python`, so it runs on one matrix entry only: `ruff check --output-format=github .` and `ruff format --check --diff .`.
- **Editor**
  - **`.vscode/settings.json`**: committed, with the venv as the interpreter (`"python.venvPath": ".venv"`), Ruff as the formatter on save, and `"ruff.importStrategy": "fromEnvironment"` so the editor uses the pinned Ruff.
  - **`.vscode/extensions.json`**: recommends `ms-python.python`, `ms-python.vscode-pylance`, and `charliermarsh.ruff`.

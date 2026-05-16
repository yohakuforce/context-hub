# Contributing to Context-Hub

Thank you for your interest in Context-Hub.

## v0.x Status

Context-Hub is in pre-release (v0.x). The architecture and API surface are still evolving.
At this stage, **design discussions are prioritised over code contributions**.

Before opening a PR, please open an issue or discussion to align on the direction.
Unsolicited large PRs may be closed without review.

## Development Setup

```bash
git clone https://github.com/yohakuforce/context-hub.git
cd context-hub
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Run tests:

```bash
pytest tests/
```

Run linting and type checking:

```bash
ruff check src/ tests/
mypy src/
```

## Code Style

- Python 3.12+
- `ruff` for linting (line length 100)
- `mypy` strict mode
- All new functionality must have tests (80%+ coverage target)
- Prefer small, focused files (< 800 lines)
- Immutable data patterns — no in-place mutation

## Testing

```bash
# All tests
pytest tests/

# With RuntimeWarning as error (CI requirement)
pytest tests/ -W error::RuntimeWarning

# Coverage report
pytest tests/ --cov=src --cov-report=term-missing
```

## Commit Messages

Follow [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add search_context tool to MCP server
fix: mask database password in dry-run output
docs: update architecture overview
test: add chmod 0600 test for init command
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`, `perf`, `ci`

## Pull Request Process

1. Fork the repository and create a feature branch
2. Ensure all tests pass: `pytest tests/ -W error::RuntimeWarning`
3. Ensure coverage stays at 80%+
4. Ensure `ruff` and `mypy` report 0 errors in new code
5. Open a PR with a clear description of what and why
6. Link any related issues

## Architecture Notes

Context-Hub follows these design principles (see `docs/architecture.md`):

- **MCP as a first-class citizen**: MCP and HTTP are equally capable entry points
- **Thin adapters**: MCP tools and HTTP handlers delegate to shared services
- **Protocol-based abstractions**: `VectorStore`, `FTSStore`, `SchedulerStore` are Protocols, not base classes
- **Repository pattern**: all data access goes through repository interfaces
- **Immutable domain objects**: domain entities use `dataclasses` with `frozen=True` where appropriate

## Reporting Bugs

Use [GitHub Issues](https://github.com/yohakuforce/context-hub/issues).
For security vulnerabilities, see [SECURITY.md](SECURITY.md).

# Contributing

## Source of Truth

Use these in order:

1. `AGENTS.md` for contributor rules, architecture, and code conventions
2. GitHub issues for the live roadmap and unfinished work
3. `docs/` for operational and design detail

## Development Environment

### Prerequisites

| Tool | Version | Check |
|------|---------|-------|
| Python | 3.11+ | `python3 --version` |
| Node.js | 20+ | `node --version` |
| MediaMTX | 1.18+ | Optional for integration tests |

### Setup

```bash
git clone https://github.com/josiah-nelson/ONVIFy.git
cd ONVIFy
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Testing Expectations

- **Unit tests** use fixtures (mp4 samples in `tests/fixtures/`) and run without external services.
- **Integration tests** require MediaMTX and/or real ONVIF devices. Mark them with `@pytest.mark.integration`.
- Inference pipeline tests assert deterministic results against known frame content.
- All tests must pass before opening a PR.

## Workflow

1. Read `AGENTS.md` before making non-trivial changes.
2. Check GitHub issues before starting work in an area.
3. Update docs when behavior, paths, or architecture changes.
4. Use pull requests for all non-trivial work.

## GitHub Workflow

### Repo Operations

- Use `gh` CLI for GitHub operations.
- Do not push directly to `main`.
- Open a pull request for all non-trivial work.

### Issues

- Before starting work, identify the issue that owns the task.
- Mark the issue as in progress before beginning implementation.
- Label issues by domain for parallel work:
  - `domain:streaming` — RTSP/MJPEG/MediaMTX
  - `domain:onvif` — ONVIF protocol and discovery
  - `domain:inference` — AI detection pipeline
  - `domain:api` — REST API and WebSocket
  - `domain:ui` — Frontend
  - `domain:packaging` — Installers and deployment
  - `domain:docs` — Documentation
  - `domain:test` — Testing and CI

### Pull Requests

**Keep PRs to ~500 LOC of diff.** Larger changes should be split into stacked PRs or sequential commits that each stand alone. Exceptions: scaffolding commits, generated code, and large test fixture additions don't count toward the limit.

1. **Validate locally** before opening:
   - `ruff check .` — must pass with 0 errors
   - `mypy .` — must pass in strict mode
   - `pytest` — all tests must pass

2. Open the PR with a structured body: summary table of changes, test plan with checkboxes
3. Wait for CI
4. Wait for automated reviews — Greptile and Copilot typically post within ~5 minutes
5. Address all issues immediately; either fix or clearly justify if not fixing
6. Push fixes to the same branch — never open a new PR for review feedback
7. Target Greptile score >= 4/5 before considering the PR ready for human reviewPR Workflow

### Definition of Done

A contribution is not done until all of the following are true:

- Local validation has been run (`ruff`, `mypy`, `pytest`)
- A PR has been opened with a structured summary and test plan
- CI has completed and all checks pass
- Review feedback has been addressed

## Build and Test Commands

### Backend

```bash
# Install in development mode
pip install -e ".[dev]"

# Run the server
onvify --debug

# Or directly
python -m onvify.cli --debug
```

### Tests

```bash
# All unit tests
pytest

# Specific test file
pytest tests/unit/test_config.py

# With coverage
pytest --cov=onvify

# Skip integration tests
pytest -m "not integration"

# Verbose output
pytest -v
```

### Linting and Type Checking

```bash
ruff check .
ruff format --check .
mypy .
```

## Code Conventions

See `AGENTS.md` for the full set. Key rules:

- **Async-first**: no sync blocking in async code paths
- **Type hints everywhere**: `mypy --strict` must pass
- **Pydantic models** for all external data boundaries
- **structlog** for logging, never `print()`
- **Tests required** for new functionality

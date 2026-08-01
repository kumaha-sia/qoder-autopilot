# AGENTS.md

## Project Context (MUST READ)

Before implementing any code, read the project context file:

**`_bmad-output/project-context.md`**

This file contains critical rules, patterns, and conventions for this project. Follow ALL rules exactly as documented.

## Quick Reference

- **Language:** Python 3.10+ (use `str | None`, not `Optional[str]`)
- **Linter/Formatter:** Ruff (line-length 100, rules: E, W, F, I, N, UP, B, SIM)
- **Type checker:** MyPy (python_version 3.10, warn_return_any)
- **Test:** `python -m pytest tests/ -v --tb=short --cov=qoder_autopilot --cov-report=term-missing`
- **Lint:** `ruff check . && ruff format --check .`
- **Type check:** `mypy src/`

## Pre-commit Checklist

Run before pushing:

```bash
ruff check . && ruff format --check . && mypy src/ && pytest tests/ -v --tb=short
```

---
project_name: 'autopilot'
user_name: 'Kumaha-sia'
date: '2026-07-30'
sections_completed:
  ['technology_stack', 'language_rules', 'framework_rules', 'testing_rules', 'quality_rules', 'workflow_rules', 'anti_patterns']
status: 'complete'
rule_count: 65
optimized_for_llm: true
---

# Project Context for AI Agents

_This file contains critical rules and patterns that AI agents must follow when implementing code in this project. Focus on unobvious details that agents might otherwise miss._

---

## Technology Stack & Versions

### Core Runtime
- **Python 3.10+** (supports 3.10, 3.11, 3.12, 3.13) — MUST use modern union syntax (`str | None`, not `Optional[str]`)
- **Build system:** Hatchling (`hatchling`)
- **Packages:** `qoder-autopilot` (v0.6.3) and `pateway-autopilot` — both published to PyPI

### Core Dependencies
| Package | Version | Purpose |
|---------|---------|---------|
| `camoufox[geoip]` | >=0.4 | Anti-detect Firefox browser (stealth fork) |
| `playwright` | >=1.40 | Browser automation |
| `requests` | >=2.28 | HTTP client (temp mail, OAuth polling) |
| `python-dotenv` | >=1.0 | `.env` file loading |
| `pydantic` | >=2.0 | Data validation |
| `pydantic-settings` | >=2.0 | Configuration management (env + user config + defaults) |
| `faker` | >=20.0 | Identity generation (id_ID locale) |

### Optional Dependencies (Extras)
| Extra | Packages | Purpose |
|-------|----------|---------|
| `captcha` | `opencv-python-headless>=4.8`, `numpy>=1.24`, `openai>=1.0` | AI-powered captcha solving |
| `relay` | `fastapi>=0.100`, `uvicorn[standard]>=0.23`, `pydantic[email]>=2.0` | Relay server for remote 9Router |
| `all` | `qoder-autopilot[captcha,relay]` | Everything |
| `dev` | `pytest>=7.0`, `pytest-asyncio>=0.21`, `pytest-cov>=4.0`, `ruff>=0.4`, `mypy>=1.0` | Development |

### Worker Template (Cloudflare Worker)
- **Node.js** microservice bundled in `src/qoder_autopilot/worker_template/`
- **Wrangler** >=4.100.0, **postal-mime** ^2.7.4, **Cloudflare D1** (SQLite)

### Development Tools
- **Linter/Formatter:** Ruff (target py310, line-length 100, rules: E, W, F, I, N, UP, B, SIM; ignores E501, B008, SIM105)
- **Type checker:** MyPy (python_version 3.10, warn_return_any, ignore_missing_imports)
- **Test framework:** pytest + pytest-asyncio (auto mode) + pytest-cov
- **CI:** GitHub Actions — matrix (ubuntu-latest + macos-latest × Python 3.10–3.13)

---

## Critical Implementation Rules

### Language-Specific Rules (Python)

- **Type annotations:** Use Python 3.10+ union syntax (`str | None`, `dict | None`, `int | None`). Do NOT use `Optional[X]` or `Union[X, Y]`.
- **Imports within packages:** Use relative imports (`from ..infra import config`, `from .ai_vision import gemini_detect_gap`). Do NOT use absolute imports for intra-package references.
- **Optional dependency imports:** Use lazy imports inside functions for optional deps (`from camoufox.async_api import AsyncCamoufox` inside the function body). This ensures the package works without `[captcha]` or `[relay]` extras installed.
- **Async is the default:** All browser automation and network I/O must be async. Use `async def` functions, `await` for coroutines.
- **Blocking calls:** Wrap synchronous blocking calls with `asyncio.to_thread()` (e.g., `poll_device_token`, SQLite writes). NEVER call blocking I/O directly in async context.
- **Context managers:** Use `@asynccontextmanager` for resource lifecycles (browser launch, file locks). Example: `async with launch_browser(...) as browser:`.
- **Parallel operations:** Use `asyncio.gather()` for concurrent account registration with staggered starts.
- **Error handling hierarchy:** All custom exceptions MUST inherit from the base error (`QoderAutopilotError` for qoder, equivalent for pateway). Each exception carries `message` and `detail` attributes. The base class provides `format()` → `f"{self.message} — {self.detail}"`.
- **String formatting:** Use f-strings. Avoid `.format()` unless the template is dynamic.
- **collections.abc:** Import `AsyncIterator` from `collections.abc`, not `typing`.

### Framework-Specific Rules

#### Pydantic Settings (3-Tier Config Priority)
- Config resolution order: **(1) Environment variables** (`QODER_*` prefix for qoder, `PATEWAY_*` for pateway) → **(2) User config file** (`~/.qoder-autopilot/config.json` or `~/.pateway-autopilot/config.json`) → **(3) Built-in defaults** (in pydantic `Settings` class).
- The `Settings` class is a singleton — module-level constants (`WORKER_URL`, `CAPTCHA_TIMEOUT`, etc.) are exported from `config.py` reading the singleton.
- CLI config keys are `kebab-case` (e.g., `worker-url`); code-level attributes are `snake_case` (e.g., `worker_url`).
- `qoder-autopilot config show/set/get/reset` commands manage user config file.

#### Playwright / Camoufox Browser Automation
- **Camoufox** is the browser engine (anti-detect Firefox fork). Launch via `AsyncCamoufox` with random OS fingerprint.
- Browser lifecycle MUST be wrapped in `asynccontextmanager`. Never leave browser processes dangling.
- Element interaction fallback chain: **Playwright click → JS evaluate → keyboard press**. If one method fails, try the next.
- Human-like behavior is required for pateway: use `human_delay()`, `human_think()`, `human_type()`, `human_click()`, `human_scroll()`, `random_mouse_movement()`.

#### Captcha Solving (3-Tier Fallback Chain)
- Strategy order MUST be: **AI Vision (Gemini/GPT)** → **OpenCV (4-method voting)** → **Manual (pause for user)**.
- AI Vision: extracts puzzle piece silhouette, applies CLAHE + edge detection, sends composite to AI for gap identification.
- OpenCV: 4 methods — column brightness drop, edge density analysis, masked template matching (TM_CCOEFF_NORMED), masked SQDIFF matching. Results combined via voting.
- NEVER skip a tier and go straight to manual unless explicitly configured (`--manual-captcha`).

#### FastAPI Relay Server
- Binds to `127.0.0.1:8765` by default. Non-localhost bindings MUST trigger HTTPS warning.
- Auth: Bearer token with **timing-safe comparison** (`hmac.compare_digest()`). NEVER use `==` for token comparison.
- Rate limiting: 30 requests / 60s per IP.
- Input validation: Pydantic models with `EmailStr`, constrained strings.
- SQLite: MUST use WAL mode for safe concurrent access.

#### Cloudflare Worker (Temp Mail)
- Worker source is bundled in `src/qoder_autopilot/worker_template/`.
- Uses D1 (SQLite) for email storage. Schema in `schema.sql`.
- Deploy via `qoder-autopilot deploy` command (wraps Wrangler).

### Testing Rules

- **Framework:** pytest + pytest-asyncio (mode: `auto`). All async tests run automatically without `@pytest.mark.asyncio`.
- **Test file location:** `tests/` for qoder, `tests/pateway/` for pateway.
- **Test file naming:** `test_*.py`. **Test class naming:** `Test*` (PascalCase).
- **Test grouping:** Class-based — group related tests in `TestXxx` classes.
- **Fixtures:** Shared fixtures in `tests/conftest.py` (e.g., `sample_otp_html`, `mock_env_vars`, `temp_creds_file`, `device_token_body`).
- **Environment override:** Use `monkeypatch` for env var and path overrides. NEVER modify `os.environ` directly.
- **Temp files:** Use `tmp_path` fixture for temporary file operations.
- **Mocking:** Tests are unit-level. Do NOT mock external services (Playwright, Camoufox, real APIs). Test pure logic functions.
- **Markers:** `@pytest.mark.slow` for slow tests, `@pytest.mark.integration` for integration tests.
- **Coverage:** CI runs `--cov=qoder_autopilot --cov-report=term-missing`. Maintain coverage for core logic.
- **Run command:** `python -m pytest tests/ -v --tb=short --cov=qoder_autopilot --cov-report=term-missing`

### Code Quality & Style Rules

- **Linter/Formatter:** Ruff. Run `ruff check .` and `ruff format --check .` before committing.
- **Line length:** 100 characters max (E501 is ignored, but keep lines reasonable).
- **Naming conventions:**
  - Modules/files: `snake_case` (`temp_mail.py`, `ai_vision.py`)
  - Classes: `PascalCase` (`CaptchaSolver`, `CloudflareProvider`)
  - Functions: `snake_case` (`register_and_verify`, `initiate_device_flow`)
  - Constants: `UPPER_SNAKE_CASE` (`WORKER_URL`, `CAPTCHA_TIMEOUT`)
  - CLI flags: `kebab-case` (`--manual-captcha`, `--mail-provider`)
- **Docstrings:** Every module MUST have a docstring with purpose, usage, and examples. Use triple-quoted `"""` docstrings.
- **Comments:** Use Unicode box-drawing characters for section headers in code: `# ═══ SECTION NAME ═══`. Use `╔═══╗`, `───` for decorative banners in CLI output.
- **No comments in code logic** unless explaining a non-obvious decision. Do not state the obvious.
- **Type checker:** Run `mypy src/` before committing. `warn_return_any` is enabled.

### Development Workflow Rules

- **Git branches:** No strict branch naming convention detected. Use descriptive branch names.
- **Commit messages:** No conventional-commits enforcement detected. Write clear, descriptive commit messages.
- **CI gates:** GitHub Actions runs on push (main/develop) and PR (main). MUST pass: pytest with coverage, `ruff check`, `ruff format --check`. Matrix: ubuntu + macOS × Python 3.10–3.13.
- **Publishing:** On release, builds with `python -m build`, publishes to PyPI + TestPyPI via trusted publishing (OIDC). NEVER publish manually — use the release workflow.
- **Pre-commit checklist:** Run `ruff check . && ruff format --check . && mypy src/ && pytest tests/ -v --tb=short` before pushing.
- **`.gitignore` note:** `.agents`, `.claude`, `.opencode`, `_bmad` directories are gitignored (AI tool directories). Credentials, screenshots, `.env`, SQLite files are also gitignored.

### Critical Don't-Miss Rules

#### Security (MUST FOLLOW)
- **File permissions:** Credential files and config files MUST be `chmod 600` (owner-only). Use `os.chmod(path, 0o600)` after writing.
- **File locking:** Use `fcntl.flock` for concurrent file writes (Unix). No-op on Windows is acceptable.
- **Password masking:** Passwords in logs MUST be shown as `••••••••`. API keys MUST be shown as `***configured***`. NEVER log raw secrets.
- **Token comparison:** ALWAYS use `hmac.compare_digest()` for auth token comparison. NEVER use `==`.
- **Rate limiting:** Relay server MUST enforce rate limits (30 req/60s per IP).
- **Input validation:** All external input (relay endpoints, CLI args) MUST be validated with Pydantic models.
- **SQLite WAL mode:** Relay server SQLite MUST use WAL mode for concurrent access safety.
- **`.env` files:** NEVER commit `.env` files. Use `.env.example` as template. Load via `python-dotenv`.

#### Anti-Patterns to Avoid
- **DO NOT** use `Optional[X]` or `Union[X, Y]` — use `X | None` and `X | Y`.
- **DO NOT** use absolute imports within packages — use relative imports (`from ..infra import config`).
- **DO NOT** import optional dependencies at module top-level — use lazy imports inside functions.
- **DO NOT** call blocking I/O in async context — wrap with `asyncio.to_thread()`.
- **DO NOT** skip captcha solving tiers — always follow AI → OpenCV → Manual fallback chain.
- **DO NOT** leave browser processes dangling — always use `async with` context managers.
- **DO NOT** use `==` for security-sensitive string comparison — use `hmac.compare_digest()`.
- **DO NOT** log raw passwords, API keys, tokens, or credentials — always mask.
- **DO NOT** write credential/config files without `chmod 600`.
- **DO NOT** use `os.environ` directly in tests — use `monkeypatch.setenv()`.

#### Edge Cases to Handle
- **OTP HTML variations:** OTP extraction must handle: letter-spacing CSS, big font sizes, nested HTML structures, missing codes. See `tests/test_otp.py` for all edge cases.
- **Browser element interaction:** Playwright click may fail — always have JS evaluate and keyboard press fallbacks.
- **Cross-platform:** Code runs on Linux and macOS (CI matrix). `fcntl` is Unix-only — handle Windows gracefully (no-op).
- **Temp mail provider failures:** Multiple providers (Cloudflare, Moca Supabase, mail.tm, guerrilla, 1secmail). Handle provider-specific response formats and failures.
- **Device token polling:** PKCE device flow may timeout. Use `asyncio.to_thread` for blocking poll and handle `DeviceTokenTimeout` exception.
- **Concurrent registration:** Parallel mode uses `asyncio.gather` with staggered starts. Handle race conditions in credential file writes with `fcntl.flock`.

#### Platform Adapter Pattern
- `qoder_autopilot` is the **generic engine** (anti-detect browser, captcha solving, temp mail, credentials, OAuth).
- `pateway_autopilot` is a **platform adapter** that reuses 80%+ of the engine.
- When adding a new platform: write a new adapter package (`src/<platform>_autopilot/`) with `register.py` (flow), `config.py` (pydantic Settings with `<PLATFORM>_` prefix), and platform-specific auth/browser/captcha overrides as needed. Reuse engine utilities where possible.
- Each platform package has its own CLI entry point in `pyproject.toml` `[project.scripts]`.

#### Architecture Flow (Qoder)
```
CLI → register.py → [browser + captcha + temp_mail] → [oauth + otp + ninerouter]
```
1. Generate temp email (Cloudflare Worker or Moca Supabase)
2. Generate identity (Faker, id_ID locale — Indonesian names)
3. Launch Camoufox (anti-detect Firefox, random OS fingerprint)
4. Navigate to Qoder sign-up or OAuth URL
5. Fill form (name, email, ToS checkbox)
6. Enter password (16-char strong password)
7. Solve captcha (AI → OpenCV → Manual fallback chain)
8. Wait for OTP (poll temp mail inbox)
9. Enter OTP (6-digit code into Ant Design OTP inputs)
10. Verify success (redirect check)
11. Poll device token (PKCE device authorization flow)
12. Insert into 9Router (SQLite DB or relay server)

#### Architecture Flow (Pateway)
```
CLI → register.py → [browser + captcha + temp_mail/proxy] → [otp + api_key_capture]
```
7-step flow: navigate → email → slider captcha → OTP → password → signup → API key capture.
API key capture uses 3-tier strategy: intercept response → extract from UI → read clipboard.

#### Supervised Mode (`--supervised`)
- `pateway-autopilot --supervised` spawns a browser worker that waits for
  commands instead of running the full register flow. Useful for driving
  registrations step-by-step with human/AI supervision and a full audit trail.
- `pateway-autopilot supervised <cmd> [key=value ...]` sends one command to the
  newest worker. Commands: goto, click, fill, type, press, check, wait,
  eval, shot, html_info, url, close (see `src/pateway_autopilot/supervised/cli.py`).
- Every executed command is timestamped in
  `runs/<id>/supervised/session.log`; mutating commands auto-screenshot to
  `runs/<id>/supervised/shots/`. Run loop exits on `close`.

---

## Usage Guidelines

**For AI Agents:**

- Read this file before implementing any code
- Follow ALL rules exactly as documented
- When in doubt, prefer the more restrictive option
- Update this file if new patterns emerge

**For Humans:**

- Keep this file lean and focused on agent needs
- Update when technology stack changes
- Review quarterly for outdated rules
- Remove rules that become obvious over time

Last Updated: 2026-07-30

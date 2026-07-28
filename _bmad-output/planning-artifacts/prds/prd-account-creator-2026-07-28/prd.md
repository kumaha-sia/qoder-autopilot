---
title: "Pateway Autopilot"
status: draft
created: 2026-07-28
updated: 2026-07-28
---

# PRD: Pateway Autopilot
*Working title — confirm.*

## 0. Document Purpose

This PRD defines the requirements for **Pateway Autopilot**, a Python CLI tool that automates bulk account registration and API key creation on PatewayAI. It is intended for the developer (Juragan) building the tool, and for any future contributors or downstream workflow owners (architecture, epics, implementation). The document is structured with Glossary-anchored vocabulary, features grouped with globally numbered FRs, and assumptions tagged inline. Technical implementation details live in `addendum.md`, not here.

## 1. Vision

Pateway Autopilot eliminates the tedious, error-prone process of manually registering PatewayAI accounts to obtain API keys. What takes 3-5 minutes per account (including slider captcha, email verification, and one-time key capture) becomes a single command that runs in the background, optionally in parallel across multiple accounts.

The tool reuses 80%+ of the battle-tested `qoder-autopilot` engine — anti-detect browser, temp mail, captcha solving, credential storage — and adds only a PatewayAI-specific adapter. This generic engine approach means adding support for other AI API relay services in the future is just writing a new adapter, while all infrastructure is shared.

For developers who need multiple API keys for distribution, redundancy, or cost optimization (maximizing free $3 credits per account), this tool transforms a 50-minute manual task (10 accounts) into a 15-minute automated run.

## 2. Target User

### 2.1 Jobs To Be Done

- **Functional**: I need multiple PatewayAI API keys to distribute across my AI tools (Claude Code, Cursor, Windsurf) without hitting rate limits on a single key.
- **Functional**: I want to maximize the free $3 credits PatewayAI gives per account, but manual registration is too slow at scale.
- **Functional**: I need backup keys ready when my primary key gets rate-limited or suspended.
- **Contextual**: I'm a solo developer or small team operator in China/SEA who can't afford to waste time on repetitive account creation.

### 2.2 Non-Users (v1)

- Enterprise teams needing account management dashboards or SSO integration.
- Users who want to automate payment/top-up (out of scope).
- Users targeting platforms other than PatewayAI (v1 is single-target).

### 2.3 Key User Journeys

- **UJ-1. Juragan bulk-registers 10 PatewayAI accounts in one command.**
  - **Persona + context:** Solo developer who uses Claude Code and Cursor daily, needs multiple API keys to avoid rate limits.
  - **Entry state:** Terminal open, `pateway-autopilot` installed and configured.
  - **Path:** Runs `pateway-autopilot -n 10 --parallel`. Tool generates 10 temp emails, launches 10 Camoufox windows, solves slider captchas (auto or manual), enters OTPs, creates API keys, stores all credentials.
  - **Climax:** Sees `📊 DONE: 10/10 succeeded` and finds 10 API keys in `pateway_accounts.json`.
  - **Resolution:** Copies keys into his tools' config files. Keys are secure (chmod 600).
  - **Edge case:** If slider auto-solve fails, falls back to manual mode for that account; others continue in parallel.

- **UJ-2. Juragan creates a single account with manual captcha fallback.**
  - **Persona + context:** First-time user, wants to verify the tool works before bulk runs.
  - **Entry state:** Terminal open, first run.
  - **Path:** Runs `pateway-autopilot --manual-captcha`. Browser opens visible. Navigates to pateway.ai, fills email, pauses for manual slider solve, waits for OTP, completes registration, creates API key.
  - **Climax:** Sees `✅ Account registered & verified!` and API key displayed.
  - **Resolution:** Key saved to `pateway_accounts.json`. User confirms it works by testing with a simple API call.

## 3. Glossary

- **PatewayAI** — AI API relay service (https://pateway.ai) providing access to Claude and OpenAI models via proxy. Chinese platform, accepts Alipay.
- **Slider CAPTCHA** — Image puzzle where user drags a slider to restore/complete a distorted image. Used by PatewayAI for verification.
- **OTP** — One-Time Password, 6-digit code sent to email for verification.
- **API Key** — Credential string prefixed `sk-ptw-*` used to authenticate API requests to `api.pateway.ai/v1`. Shown only once at creation.
- **Base URL** — `https://api.pateway.ai/v1`, the endpoint for all API requests.
- **Service Mode** — PatewayAI pricing tier for API keys. Default: "Economy Mode" (discounted rates).
- **Tempik** — Self-hosted disposable email service running on Cloudflare Workers. API at `tempik.webkarya.net`. Provides temporary email addresses with REST API for inbox management and message retrieval.
- **Temp Mail** — Temporary email address generated via Tempik API for receiving OTPs.
- **Camoufox** — Anti-detect browser (stealth Firefox fork) used to bypass bot detection.
- **Generic Engine** — Architecture pattern where platform-specific logic is isolated in adapters, while infrastructure (browser, captcha, temp mail) is shared.

## 4. Features

### 4.1 Account Registration

**Description:** Automates the complete PatewayAI registration flow (Steps 1-5): navigate to homepage, click "Get Started", enter email, solve slider CAPTCHA, enter OTP + password, complete signup. The tool handles all form interactions, waits for OTP delivery, and verifies successful account creation. Realizes UJ-1, UJ-2.

**Functional Requirements:**

#### FR-1: Navigate to PatewayAI and Initiate Registration

The system can navigate to `https://pateway.ai` and click the "Get Started" button to open the "Create an account" modal.

**Consequences (testable):**
- System successfully loads pateway.ai homepage within 30 seconds.
- System locates and clicks "Get Started" button in the header.
- "Create an account" modal appears with email input field.

#### FR-2: Enter Email and Trigger Verification

The system can enter a generated temp email address into the email field and click "Send code" to trigger the verification flow.

**Consequences (testable):**
- System fills the email input with a valid temp email address.
- System clicks "Send code" button.
- Slider CAPTCHA modal appears after clicking.

#### FR-3: Solve Slider Puzzle CAPTCHA

The system can solve the slider puzzle CAPTCHA by detecting the image gap and dragging the slider to the correct position. Supports auto-solve (OpenCV) and manual fallback.

**Consequences (testable):**
- Auto mode: System detects gap position within 2 seconds with >70% accuracy.
- Auto mode: System drags slider to correct position using Playwright mouse API.
- Manual mode: System pauses and displays instruction for user to solve manually.
- If auto-solve fails after 3 attempts, system falls back to manual mode.
- After successful solve, OTP is sent to the email address.

**Out of Scope:**
- AI Vision solving (GPT-4V) — deferred to v2.
- Paid solving service integration (CapSolver) — deferred to v2.

#### FR-4: Enter OTP and Complete Registration

The system can retrieve the 6-digit OTP from the Tempik temp mail inbox, enter it along with password and optional invite code, and click "Sign up" to complete registration.

**Consequences (testable):**
- System creates temp email via `POST https://tempik.webkarya.net/api/inboxes` (returns random address like `kopihujan42@webkarya.net`).
- System polls Tempik inbox via `GET https://tempik.webkarya.net/api/inboxes/:address/messages` for OTP email within configurable timeout (default: 60s).
- System extracts 6-digit OTP from email `body` field.
- System fills: verification code, password, confirm password, optional invite code.
- System checks Terms of Service checkbox.
- System clicks "Sign up" button.
- "Account created" modal appears with 3 free credits confirmation.

**Out of Scope:**
- Resend OTP logic — if OTP not received within timeout, mark as failed.

#### FR-5: Confirm Account Creation

The system can detect the "Account created" success modal and click "Get started" to proceed to the dashboard.

**Consequences (testable):**
- System detects "Account created" modal text.
- System clicks "Get started" button.
- Dashboard/console page loads successfully.
- Account credentials (email, password) are stored temporarily for API key creation.

**Feature-specific NFRs:**
- Registration flow must complete within 2 minutes (auto captcha) or 5 minutes (manual).
- Browser must use Camoufox anti-detect fingerprint to avoid bot detection.

---

### 4.2 API Key Creation and Capture

**Description:** After successful registration, automates the API key creation flow (Steps 6-7): navigate to Console, click "Create Key", fill key name and service mode, create key, and critically — intercept the API key value from the response before the modal closes. The key is shown only once; missing it means the key is lost. Realizes UJ-1, UJ-2.

**Functional Requirements:**

#### FR-6: Navigate to API Keys Console

The system can navigate to the Console page and locate the API Keys section with the "Create Key" button.

**Consequences (testable):**
- System navigates to Console page (sidebar visible: API Keys, Usage Logs, etc.).
- System locates "Create Key" button in the API Keys table area.
- System clicks "Create Key" to open the creation modal.

#### FR-7: Fill API Key Creation Form

The system can fill the "Create Key" modal form with key name, service mode, and optional monthly spending limit.

**Consequences (testable):**
- System enters a key name (default: "prod", configurable).
- System selects "Economy Mode" from Service Mode dropdown (default).
- System leaves Monthly Spending Limit toggle off (default).
- System clicks "Create" button.

#### FR-8: Capture API Key (Critical Path)

The system can capture the API key value from the "Key Created" modal before it closes. The key is shown only once — this is the most critical step in the entire flow.

**Consequences (testable):**
- System intercepts API response from key creation endpoint and extracts `sk-ptw-*` value.
- Fallback: System reads API key text from the "Key Created" modal element.
- Last resort: System clicks copy button and reads clipboard content.
- Captured key is stored immediately (before clicking "Done, close").
- Key capture success rate is >95% of successful registrations.

**Out of Scope:**
- Re-creating keys if capture fails — the account is still usable, just needs manual key creation.

#### FR-9: Store Credentials Securely

The system can store all account credentials (email, password, API key, base URL) in a JSON file with restricted permissions.

**Consequences (testable):**
- Credentials saved to `pateway_accounts.json` (configurable path).
- File permissions set to `600` (owner-only read/write on Unix).
- Each entry contains: email, password, api_key, base_url, created_at, status.
- Concurrent writes are atomic (file locking for parallel mode).

**Feature-specific NFRs:**
- API key must be captured within 2 seconds of modal appearance.
- Passwords and API keys must never be logged to stdout (masked as `••••••••`).

---

### 4.3 Bulk and Parallel Execution

**Description:** Supports creating multiple accounts in a single run, with optional parallel execution for speed. Handles staggering, error isolation, and aggregate reporting. Realizes UJ-1.

**Functional Requirements:**

#### FR-10: Sequential Bulk Registration

The system can register N accounts sequentially with configurable delay between each.

**Consequences (testable):**
- User specifies count via `-n N` flag (1-100).
- System registers accounts one by one with delay between each (default: 30s, configurable).
- Progress shown as `Account 3/10`.
- Aggregate result: `📊 DONE: 8/10 succeeded`.

#### FR-11: Parallel Bulk Registration

The system can register N accounts concurrently in separate browser windows.

**Consequences (testable):**
- User enables parallel mode via `--parallel` flag.
- System launches N browser windows with staggered start (2s apart).
- Each account runs independently — failure in one doesn't affect others.
- All credentials saved atomically (no file corruption).
- Warning displayed if `--parallel` + `--manual-captcha` with count >1.

**Feature-specific NFRs:**
- Must support at least 10 concurrent browser sessions.
- Memory usage must not exceed 500MB per browser session.

---

### 4.4 Configuration Management

**Description:** Provides persistent configuration via CLI commands and environment variables, following the same pattern as `qoder-autopilot config`. Covers PatewayAI-specific settings, captcha strategy, temp mail provider, and behavioral tuning.

**Functional Requirements:**

#### FR-12: Show and Manage Configuration

The system can show, set, get, and reset configuration values via CLI subcommands.

**Consequences (testable):**
- `pateway-autopilot config show` displays all settings with source (default/config/env).
- `pateway-autopilot config set <key> <value>` persists to `~/.pateway-autopilot/config.json`.
- `pateway-autopilot config get <key>` returns current value.
- `pateway-autopilot config reset` deletes config file.
- Sensitive fields (API keys, passwords) are masked in `config show` output.

#### FR-13: Environment Variable Override

The system can read all configuration from environment variables with `PATEWAY_` prefix.

**Consequences (testable):**
- `PATEWAY_WORKER_URL` overrides `worker-url` config.
- `PATEWAY_AI_API_KEY` overrides `ai-api-key` config.
- `.env` file is loaded if present.
- Priority: env vars > user config > defaults.

## 5. Non-Goals (Explicit)

- **Payment/top-up automation** — PatewayAI requires Alipay; automating payments is out of scope.
- **Invite code generation** — The tool accepts invite codes but does not generate or farm them.
- **Multi-platform support** — v1 targets PatewayAI only. Other platforms (OpenRouter, etc.) are v2+.
- **Web UI / dashboard** — CLI-only for v1.
- **Account rotation / load balancing** — The tool creates accounts and keys; using them is the user's responsibility.
- **API key proxy / relay server** — Out of scope; the tool outputs raw keys.
- **Account recovery** — If an account is banned or suspended, the tool does not attempt recovery.

## 6. MVP Scope

### 6.1 In Scope

- PatewayAI account registration (Steps 1-5: email, slider CAPTCHA, OTP, password, signup)
- API key creation and capture (Steps 6-7: Console → Create Key → intercept response)
- Slider CAPTCHA solving: OpenCV auto-detect + manual fallback
- Temp email generation via Tempik API (`tempik.webkarya.net`)
- Credential storage (email, password, API key, base URL) in JSON with chmod 600
- CLI with flags: `-n`, `--parallel`, `--manual-captcha`, `--delay`, `--proxy`, `--verbose`, `--quiet`
- Configuration management via `pateway-autopilot config` subcommand
- Sequential and parallel bulk execution (1-100 accounts)

### 6.2 Out of Scope for MVP

- **AI Vision captcha solving** (GPT-4V/Gemini) — deferred to v2. Manual mode is the fallback.
- **Paid solving service** (CapSolver/2Captcha) — deferred to v2. OpenCV + manual covers v1.
- **Multi-platform adapters** — deferred to v2. PatewayAI only for v1.
- **API key pool management** — deferred to v2. Tool outputs keys; management is user's job.
- **Docker deployment** — deferred to v2. CLI-only for v1.
- **First-run wizard** — deferred to v2. Manual config for v1.

## 7. Success Metrics

**Primary**
- **SM-1**: Registration success rate — >80% of attempts result in verified account. Validates FR-1 through FR-5.
- **SM-2**: API key capture rate — >95% of verified accounts have key captured. Validates FR-6 through FR-8.
- **SM-3**: End-to-end time — <2 minutes per account (auto captcha), <5 minutes (manual). Validates FR-1 through FR-9.

**Secondary**
- **SM-4**: Parallel capacity — 10+ concurrent sessions without crash. Validates FR-11.
- **SM-5**: Credential security — zero leaks in logs or file permissions. Validates FR-9.

**Counter-metrics (do not optimize)**
- **SM-C1**: Account ban rate — do not optimize registration speed at the cost of higher ban rates. Slower, more human-like behavior is preferred over speed. Counterbalances SM-3.

## 8. Open Questions

1. **OQ-1**: What is the exact selector for the slider CAPTCHA element? Needs inspection of live PatewayAI page.
2. **OQ-2**: What is the API endpoint for creating API keys? (Likely `/apikey/create` but needs confirmation from Console page JS.)
3. **OQ-3**: Does PatewayAI have IP rate limiting per registration? If so, what are the thresholds?
4. **OQ-4**: What password complexity requirements does PatewayAI enforce? (Minimum length, special chars, etc.)
5. **OQ-5**: Can the slider CAPTCHA be solved reliably with OpenCV, or is a paid service needed for v1?

## 9. Assumptions Index

- **A-1** (§4.1): PatewayAI's slider CAPTCHA uses consistent image gap detection — OpenCV can identify the puzzle gap reliably. `[ASSUMPTION: needs validation with live testing]`
- **A-2** (§4.2): API key creation endpoint returns the key in JSON response body, interceptable via Playwright response listener. `[ASSUMPTION: endpoint shape not yet confirmed]`
- **A-3** (§4.1): Temp email domain `webkarya.net` from Tempik is not blocked by PatewayAI. `[ASSUMPTION: needs validation]`
- **A-4** (§4.3): 10 concurrent Camoufox sessions can run on a machine with 16GB RAM. `[ASSUMPTION: based on qoder-autopilot experience]`
- **A-5** (§4.1): PatewayAI does not require phone number verification — email-only registration. `[CONFIRMED from user flow screenshots]`
- **A-6** (§4.1): The "Resend (60s)" OTP cooldown means we have at least 60 seconds to retrieve the OTP from temp mail. `[CONFIRMED from user flow screenshots]`
- **A-7** (§4.2): "Economy Mode" is the default and sufficient for API key creation — no need to select other modes. `[CONFIRMED from user flow screenshots]`

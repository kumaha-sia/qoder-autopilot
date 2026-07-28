---
title: "Pateway Autopilot — Bulk API Key Automation"
status: draft
created: 2026-07-28
updated: 2026-07-28
---

# Product Brief: Pateway Autopilot

## Executive Summary

**Pateway Autopilot** is a Python CLI tool that automates bulk account registration and API key creation on [PatewayAI](https://pateway.ai/) — a Chinese AI API relay service providing access to Claude and OpenAI models. Built on top of the existing `qoder-autopilot` engine (anti-detect browser, captcha solving, temp mail), it reuses proven infrastructure while targeting a new platform.

The tool solves a real operational need: PatewayAI offers $3 free credit per account, and developers/power users need multiple API keys for distribution, redundancy, or cost optimization. Manual registration is tedious (7-step flow including slider captcha, email verification, and one-time API key creation) and doesn't scale. This tool automates the entire flow — from email generation to API key capture — in a single command.

## The Problem

Developers and AI tool users who want to access Claude/GPT APIs via PatewayAI face:
- **$3 free credit per account** — but manual registration takes 3-5 minutes each across 7 steps
- **Slider puzzle CAPTCHA** — requires visual interaction to solve image puzzle
- **Email verification** — needs working email for 6-digit OTP
- **API key shown only ONCE** — must capture immediately or it's lost forever
- **No bulk tooling exists** — PatewayAI has no public API for account creation

Current workaround: Register accounts one by one, manually solve slider captcha, wait for OTP, create API key, copy-paste before modal closes. At scale (10+ accounts), this becomes impractical and error-prone.

## The Solution

A Python CLI tool (`pateway-autopilot`) that automates the complete 7-step flow:

1. **Generates temp emails** via [Tempik](https://github.com/kumaha-sia/tempik) API (`tempik.webkarya.net`) — self-hosted disposable email on Cloudflare Workers
2. **Launches anti-detect browser** (Camoufox) to bypass bot detection
3. **Navigates to PatewayAI** and clicks "Get Started"
4. **Enters email** and clicks "Send code"
5. **Solves slider puzzle CAPTCHA** via OpenCV (detect gap, calculate slide distance) or manual mode
6. **Enters 6-digit OTP** (from temp mail inbox) + password + optional invite code
7. **Creates API key** in Console → intercepts key value from response (shown only once!)
8. **Stores everything** (email, password, API key, base URL) securely in local JSON

```bash
# Single account, manual slider solve
pateway-autopilot --manual-captcha

# 10 accounts in parallel, auto slider solve
pateway-autopilot -n 10 --parallel

# With proxy for IP rotation
pateway-autopilot -n 20 --parallel --proxy socks5://host:port
```

## What Makes This Different

| Aspect | This Tool | Manual Registration |
|--------|-----------|-------------------|
| Speed | ~1-2 min/account | ~3-5 min/account |
| Parallel | Yes (configurable) | No |
| Slider CAPTCHA | Auto (OpenCV) or manual | Manual |
| API Key capture | Automatic intercept | Manual copy (one-shot!) |
| Credential storage | Encrypted JSON | Spreadsheets/notes |
| Error recovery | Auto-retry on failure | Start over |

**Unfair advantage**: Reuses battle-tested `qoder-autopilot` engine — Camoufox browser, temp mail, captcha solver (adapted for slider), credential storage — all proven in production. Only the target platform adapter is new.

## Who This Serves

**Primary**: Developers/power users who need multiple PatewayAI API keys for:
- Distributing keys across tools (Claude Code, Cursor, Windsurf, etc.)
- Cost optimization (maximize free $3 credits per account)
- Redundancy (backup keys when rate-limited)
- Reselling API access as a service

**Secondary**: AI tool operators who manage API keys for teams/clients.

## Success Criteria

| Metric | Target |
|--------|--------|
| Registration success rate | >80% (accounting for captcha failures) |
| API key capture rate | >95% of registered accounts |
| Time per account | <2 minutes (auto captcha), <5 min (manual) |
| Parallel capacity | 10+ concurrent browser sessions |
| Zero credential leakage | All stored with chmod 600 |

## Scope

### In Scope (v1)
- PatewayAI account registration (complete 7-step flow)
- Slider puzzle CAPTCHA solving (OpenCV auto + manual fallback)
- Temp email generation via Tempik API (`tempik.webkarya.net`)
- API key creation and capture (intercept from response)
- Credential storage (email, password, API key, base URL)
- CLI with parallel mode
- Configuration management (`pateway-autopilot config`)

### Out of Scope (v1)
- Payment/top-up automation
- Invite code generation
- Multi-platform support (only PatewayAI)
- Web UI / dashboard
- Account rotation / load balancing
- API key proxy / relay server

### Deferred (v2+)
- Multi-platform: add other AI API relay services (OpenRouter, etc.)
- API key pool management with automatic rotation
- Webhook notifications for key exhaustion
- Docker deployment

## Technical Architecture

```
pateway-autopilot/
├── src/pateway_autopilot/
│   ├── cli.py              # CLI entry point (adapted from qoder)
│   ├── config.py           # Settings (PatewayAI URLs, captcha config)
│   ├── register.py         # PatewayAI 7-step registration flow
│   ├── api_key.py          # API key creation + capture
│   ├── browser/            # REUSE from qoder_autopilot (Camoufox)
│   ├── captcha/
│   │   ├── slider.py       # NEW: OpenCV slider puzzle solver
│   │   ├── manual.py       # REUSE from qoder (pause for manual solve)
│   │   └── solver.py       # ADAPT: add slider strategy
│   ├── infra/
│   │   ├── tempik.py       # NEW: Tempik API client (tempik.webkarya.net)
│   │   └── config.py       # ADAPT: PatewayAI-specific settings
│   └── auth/
│       ├── credentials.py  # REUSE from qoder_autopilot
│       └── identity.py     # REUSE from qoder_autopilot
└── tests/
```

### Registration Flow (7 Steps)

```
Step 1: Navigate to pateway.ai → Click "Get Started"
Step 2: Enter email → Click "Send code"
Step 3: Solve slider puzzle CAPTCHA (OpenCV or manual)
Step 4: Enter 6-digit OTP + password + confirm + invite code → "Sign up"
Step 5: Account created (3 free credits) → Click "Get started"
Step 6: Console → API Keys → "Create Key" → Fill name + mode → "Create"
Step 7: ⚠️ API key shown ONCE → Intercept & store immediately
```

### API Key Capture Strategy

**Critical**: API key is only visible once after creation. Strategy:

1. **Primary**: Intercept API response from key creation endpoint
   - Monitor network requests during "Create" click
   - Extract `sk-ptw-*` value from JSON response
2. **Fallback**: Read modal text before it's closed
   - Locate API key element in "Key Created" modal
   - Extract text content immediately
3. **Last resort**: Click copy button and read clipboard

## Risks & Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Slider CAPTCHA solving fails | High | Manual fallback; retry with different strategy |
| API key not captured (missed) | **Critical** | Multiple extraction strategies (intercept + UI + clipboard) |
| PatewayAI changes flow/selectors | High | Modular adapter design; easy to update |
| IP rate limiting | Medium | Proxy support; configurable delays |
| Account ban/suspension | Medium | Realistic browser fingerprints (Camoufox) |
| Temp email domain blocked | Low | Tempik uses `webkarya.net` domain; can add more domains if needed |

## Vision

**v1**: Single-target bulk registration tool (PatewayAI only)
**v2**: Multi-platform engine — add adapters for other AI API relay services
**v3**: API key management platform — pool, rotate, monitor, and proxy API keys across services

The generic engine approach means adding a new platform is just writing an adapter (register.py + config), while all infrastructure (browser, captcha, temp mail, credentials) is shared.

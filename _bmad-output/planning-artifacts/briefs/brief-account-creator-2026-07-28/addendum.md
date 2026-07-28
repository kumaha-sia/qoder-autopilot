# Addendum: PatewayAI Technical Analysis

## Registration Flow — Verified from User Screenshots

### Complete 7-Step Flow

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Homepage → Click "Get Started"                      │
│   - URL: https://pateway.ai                                 │
│   - Button: "Get Started" (top right header, next to        │
│             "Contact")                                       │
│   - Result: Modal "Create an account" appears                │
├─────────────────────────────────────────────────────────────┤
│ STEP 2: Enter Email → Click "Send code"                     │
│   - Field: Email address (placeholder: you@example.com)     │
│   - Button: "Send code"                                     │
│   - Info: "Sign up and get 3 free credits"                   │
│   - Result: Slider CAPTCHA modal appears                     │
├─────────────────────────────────────────────────────────────┤
│ STEP 3: Slider Puzzle CAPTCHA                               │
│   - Type: Image puzzle slider (NOT Cloudflare Turnstile!)   │
│   - UI: Anime image with gap, slider arrow (>>) to drag     │
│   - Action: Drag slider to restore/complete the image       │
│   - Result: OTP sent to email                               │
├─────────────────────────────────────────────────────────────┤
│ STEP 4: Enter OTP + Create Password                         │
│   - Fields:                                                   │
│     • "Code sent to" — shows email + "Back" button          │
│     • "Verification code" — 6-digit input + "Resend (60s)"  │
│     • "Password" — new password                              │
│     • "Confirm password" — re-enter password                │
│     • "Invitation code (optional)" — optional invite code   │
│     • Checkbox: Terms of Service & Privacy Policy            │
│   - Button: "Sign up"                                        │
├─────────────────────────────────────────────────────────────┤
│ STEP 5: Account Created                                     │
│   - Modal: "Account created" with 🎉                        │
│   - Info: 3 reward credits added                             │
│   - Referral link shown (https://pateway.ai/?aff=...)       │
│   - Button: "Get started" → enters dashboard                 │
│   - Header changes: avatar + ♦3 badge                        │
├─────────────────────────────────────────────────────────────┤
│ STEP 6: Console → Create API Key                            │
│   - URL: Console page (sidebar: API Keys, Usage Logs, etc.) │
│   - Table: Empty ("No data")                                 │
│   - Button: "Create Key" (top right)                         │
│   - Modal "Create Key":                                      │
│     • Key Name (e.g., "prod")                                │
│     • Service Mode dropdown (default: "Economy Mode")        │
│     • Monthly Spending Limit (toggle, off by default)        │
│   - Button: "Create"                                         │
├─────────────────────────────────────────────────────────────┤
│ STEP 7: ⚠️ API Key Shown ONCE                               │
│   - Modal: "Key Created" with ✅                             │
│   - Warning: "Copy it now — you won't be able to view it    │
│              again after closing"                            │
│   - Shows:                                                    │
│     • API Key: sk-ptw-12hRGLmjPafjLGF81dKYnHXKdxgYQYgyzfMON│
│     • Base URL: https://api.pateway.ai/v1                    │
│   - Buttons: "Import to CC Switch" / "Done, close"          │
│   - Table now shows: Key Name | sk-ptw-... | Status | etc.  │
└─────────────────────────────────────────────────────────────┘
```

## PatewayAI Platform Details

- **URL**: https://pateway.ai
- **Language**: Chinese (zh-CN)
- **Framework**: Vue.js + Ant Design (antd)
- **CAPTCHA**: Slider puzzle (image-based, NOT Cloudflare Turnstile)
- **API Base**: `https://api.pateway.ai/v1`
- **Auth Token Storage**: `proxy-x-portal-token` (localStorage key)

## Discovered API Endpoints

All endpoints discovered by analyzing the JavaScript bundle (`assets/user-rlCzJV4k.js`):

| Endpoint | Method | Request Body | Response |
|----------|--------|-------------|----------|
| `/auth/send-code/precheck` | POST | `{verifyToken}` | Pre-check captcha |
| `/auth/send-code` | POST | `{email, verifyToken}` | Send OTP to email |
| `/auth/register` | POST | `{email, password, code, inviteCode, source: {url}, verifyToken, registerApplyId}` | `{token}` |
| `/auth/login` | POST | `{email, password}` | `{token}` |
| `/auth/logout` | POST | - | - |
| `/auth/reset-password` | POST | `{...}` | - |
| `/user/info` | GET | (auth header) | User profile |
| `/invite/check` | GET | `{code}` | Invite validity |

**API Key endpoints** (to be discovered in Console page JS):
- Likely `POST /apikey/create` or similar
- `GET /apikey/list` — list keys
- Response contains `sk-ptw-*` key value

## Error Codes

| Code | Meaning | Handling |
|------|---------|----------|
| `450040` | Invalid email format | Validate email before submit |
| `450041` | Invalid password format | Enforce password rules |
| `450042` | Captcha required | Ensure slider solved |
| `450043` | Captcha invalid/expired | Re-solve slider |
| `450044` | Email already registered | Skip, try new email |
| `450045` | Too many requests | Add delay, use proxy |
| `450046` | Account not found | - |
| `450047` | Account or password incorrect | - |

## Slider Puzzle CAPTCHA — Technical Approach

### NOT Cloudflare Turnstile!

The captcha is a **slider puzzle** where the user drags a slider to restore an image (anime-style). This is **significantly easier** to automate than Turnstile.

### Solving Strategy

```python
# OpenCV-based slider detection
1. Screenshot the captcha modal
2. Detect the puzzle gap (dark/empty region in image)
3. Calculate pixel distance from slider start to gap
4. Use Playwright drag API to move slider:
   await page.mouse.move(start_x, start_y)
   await page.mouse.down()
   await page.mouse.move(target_x, target_y, steps=10)
   await page.mouse.up()
```

### Alternative Approaches

| Method | Pros | Cons |
|--------|------|------|
| **OpenCV gap detection** | Fast, no API cost | May fail on complex puzzles |
| **AI Vision (GPT-4V)** | High accuracy | API cost per solve |
| **Manual solve** | 100% reliable | Not scalable |
| **CapSolver/2Captcha** | Professional service | ~$2-3 per 1000 solves |

### Recommendation

**Primary**: OpenCV gap detection (free, fast)
**Fallback**: Manual solve (user drags slider)
**Future**: CapSolver integration for fully automated bulk

## API Key Capture — Critical Strategy

### The Problem

API key is shown **ONLY ONCE** in the "Key Created" modal. After clicking "Done, close", the key is permanently hidden. If the script misses it, the key is lost.

### Capture Strategy (Priority Order)

1. **Network Interception** (most reliable)
   ```python
   # Listen for API response during key creation
   async def handle_response(response):
       if 'apikey' in response.url or 'key' in response.url:
           data = await response.json()
           if 'sk-ptw-' in str(data):
               save_api_key(data)
   
   page.on('response', handle_response)
   ```

2. **UI Extraction** (fallback)
   ```python
   # Read key from modal before closing
   key_element = page.locator('text=/sk-ptw-/')
   api_key = await key_element.text_content()
   ```

3. **Clipboard Copy** (last resort)
   ```python
   # Click copy button and read clipboard
   await page.locator('button:has-text("Copy")').click()
   api_key = await page.evaluate('navigator.clipboard.readText()')
   ```

## Tempik Temp Mail Service

**URL**: `https://tempik.webkarya.net/api/`
**Domain**: `webkarya.net` (emails: `xxx@webkarya.net`)
**Source**: [github.com/kumaha-sia/tempik](https://github.com/kumaha-sia/tempik)
**Stack**: Cloudflare Workers + D1 (SQLite) + Hono router

### API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/session` | GET | Create anonymous session → `{sessionId}` |
| `/api/inboxes` | POST | Create temp email → `{address, created_at}` |
| `/api/inboxes/:address/messages` | GET | Get messages → `[{id, from, subject, body, received_at}]` |
| `/api/inboxes/:address` | DELETE | Remove inbox from session |
| `/api/config` | GET | Get app config (domains, etc.) |

### Integration Flow

```
1. GET /api/session → sessionId
2. POST /api/inboxes {} → address (e.g., kopihujan42@webkarya.net)
3. Use address for PatewayAI registration
4. Poll GET /api/inboxes/:address/messages until OTP arrives
5. Extract 6-digit OTP from message body
```

### Advantages over qoder-autopilot temp mail

- **Self-hosted**: User controls the infrastructure
- **Free**: Runs on Cloudflare free tier
- **REST API**: Simple HTTP, no complex auth
- **Indonesian-style names**: Random addresses like `kopihujan42`, `bulanbiru17`
- **Instant delivery**: Email Worker → D1 → API polling

## Reusable Components from qoder-autopilot

| Component | Path | Reuse Strategy |
|-----------|------|----------------|
| Camoufox browser | `browser/camoufox.py` | ✅ Direct reuse |
| Window tiler | `browser/window_tiler.py` | ✅ Direct reuse |
| OTP extractor | `auth/otp.py` | ✅ Direct reuse |
| Identity generator | `auth/identity.py` | ✅ Direct reuse |
| Credential storage | `auth/credentials.py` | ✅ Direct reuse |
| Logger | `utils/logger.py` | ✅ Direct reuse |
| Config system | `infra/config.py` | 🔧 Adapt for PatewayAI |
| Manual captcha | `captcha/manual.py` | ✅ Direct reuse |
| Slider solver | `captcha/slider.py` | 🔧 Adapt existing |
| Temp mail | `infra/tempik.py` | 🆕 NEW: Tempik API client |
| OAuth flow | `auth/oauth.py` | ❌ Not applicable |
| 9Router integration | `infra/ninerouter.py` | ❌ Not applicable |

## UI Selectors (To Be Confirmed)

These selectors need to be verified by inspecting the actual PatewayAI page:

| Element | Likely Selector | Notes |
|---------|----------------|-------|
| "Get Started" button | `button:has-text("Get Started")` or `a:has-text("Get Started")` | Header nav |
| Email input | `input[type="email"]` or `input[placeholder*="example"]` | Modal form |
| "Send code" button | `button:has-text("Send code")` | Modal |
| Slider handle | `[class*="slider"]` or `[class*="drag"]` | CAPTCHA modal |
| OTP input | `input[maxlength="1"]` (6 inputs) or single `input` | Modal |
| Password input | `input[type="password"]` (2 fields) | Modal |
| Invite code input | `input[placeholder*="invitation"]` or `input[placeholder*="invite"]` | Optional |
| ToS checkbox | `input[type="checkbox"]` | Modal |
| "Sign up" button | `button:has-text("Sign up")` | Modal submit |
| "Get started" (post-reg) | `button:has-text("Get started")` | Success modal |
| "Create Key" button | `button:has-text("Create Key")` | Console page |
| Key Name input | `input[placeholder*="name"]` or `input[placeholder*="Name"]` | Create modal |
| Service Mode dropdown | `.ant-select` or `[class*="select"]` | Create modal |
| "Create" button | `button:has-text("Create")` | Create modal |
| API Key display | `text=/sk-ptw-/` or `code` element | Key Created modal |
| Copy button | `button:has-text("Copy")` | Key Created modal |

## Estimated Effort

| Task | Hours | Priority |
|------|-------|----------|
| Project setup (new package structure) | 1h | P0 |
| Config adaptation (PatewayAI URLs, settings) | 1h | P0 |
| Registration flow (Steps 1-5) | 3h | P0 |
| Slider CAPTCHA solver (OpenCV) | 3h | P0 |
| API key creation + capture (Steps 6-7) | 2h | P0 |
| CLI adaptation | 1h | P1 |
| Testing & debugging | 3h | P1 |
| Documentation | 1h | P2 |
| **Total** | **~15h** | - |

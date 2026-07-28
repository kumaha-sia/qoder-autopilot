# Addendum: Pateway Autopilot Technical Details

## PatewayAI Registration Flow (Verified)

### Complete 7-Step Flow

```
┌─────────────────────────────────────────────────────────────┐
│ STEP 1: Homepage → Click "Get Started"                      │
│   URL: https://pateway.ai                                   │
│   Button: "Get Started" (top right, next to "Contact")      │
│   Result: Modal "Create an account" appears                  │
├─────────────────────────────────────────────────────────────┤
│ STEP 2: Enter Email → Click "Send code"                     │
│   Field: Email address (placeholder: you@example.com)       │
│   Button: "Send code"                                       │
│   Result: Slider CAPTCHA modal appears                       │
├─────────────────────────────────────────────────────────────┤
│ STEP 3: Slider Puzzle CAPTCHA                               │
│   Type: Image puzzle slider (NOT Cloudflare Turnstile)      │
│   UI: Image with gap, slider arrow (>>) to drag             │
│   Action: Drag slider to restore/complete the image         │
│   Result: OTP sent to email                                  │
├─────────────────────────────────────────────────────────────┤
│ STEP 4: Enter OTP + Create Password                         │
│   Fields:                                                     │
│     • Verification code — 6-digit input + "Resend (60s)"    │
│     • Password — new password                                │
│     • Confirm password — re-enter password                  │
│     • Invitation code (optional)                             │
│     • Checkbox: Terms of Service & Privacy Policy            │
│   Button: "Sign up"                                          │
├─────────────────────────────────────────────────────────────┤
│ STEP 5: Account Created                                     │
│   Modal: "Account created" with 3 free credits              │
│   Button: "Get started" → enters dashboard                   │
├─────────────────────────────────────────────────────────────┤
│ STEP 6: Console → Create API Key                            │
│   Page: Console (sidebar: API Keys, Usage Logs, etc.)       │
│   Button: "Create Key" (top right)                           │
│   Form: Key Name, Service Mode (Economy), Monthly Limit     │
│   Button: "Create"                                           │
├─────────────────────────────────────────────────────────────┤
│ STEP 7: API Key Shown ONCE                                  │
│   Modal: "Key Created" with warning to copy immediately     │
│   Shows: API Key (sk-ptw-...) + Base URL                    │
│   Button: "Done, close"                                      │
│   ⚠️ Key is permanently hidden after modal closes            │
└─────────────────────────────────────────────────────────────┘
```

## Discovered API Endpoints

Base URL: `https://pateway.ai/api/v1` (SPA proxies to this)

| Endpoint | Method | Request | Response |
|----------|--------|---------|----------|
| `/auth/send-code/precheck` | POST | `{verifyToken}` | Pre-check captcha |
| `/auth/send-code` | POST | `{email, verifyToken}` | Send OTP |
| `/auth/register` | POST | `{email, password, code, inviteCode, source: {url}, verifyToken, registerApplyId}` | `{token}` |
| `/auth/login` | POST | `{email, password}` | `{token}` |
| `/auth/logout` | POST | - | - |
| `/user/info` | GET | auth header | User profile |

API Key endpoints (to be discovered):
- Likely `POST /apikey/create` — creates key, returns `sk-ptw-*`
- Likely `GET /apikey/list` — lists keys (without secret values)

## Error Codes

| Code | Meaning |
|------|---------|
| `450040` | Invalid email format |
| `450041` | Invalid password format |
| `450042` | Captcha required |
| `450043` | Captcha invalid/expired |
| `450044` | Email already registered |
| `450045` | Too many requests |

## Tempik Temp Mail API

**Base URL**: `https://tempik.webkarya.net/api/`
**Domain**: `webkarya.net` (emails: `xxx@webkarya.net`)
**Auth**: Anonymous session tokens (`x-session-id` header)
**Source**: [github.com/kumaha-sia/tempik](https://github.com/kumaha-sia/tempik)

### Endpoints

| Endpoint | Method | Headers | Body | Response |
|----------|--------|---------|------|----------|
| `/api/session` | GET | - | - | `{sessionId}` |
| `/api/inboxes` | POST | `x-session-id` | `{localPart?, domain?}` | `{address, created_at}` |
| `/api/inboxes/:address/messages` | GET | `x-session-id` | - | `[{id, from, subject, body, received_at}]` |
| `/api/inboxes/:address` | DELETE | `x-session-id` | - | `{ok: true}` |
| `/api/config` | GET | - | - | `{appName, mailDomain, mailDomains, webHost}` |

### Integration Flow

```python
import httpx

class TempikClient:
    def __init__(self, base_url: str = "https://tempik.webkarya.net/api"):
        self.base_url = base_url
        self.session_id: str | None = None

    async def create_session(self) -> str:
        """Get or create anonymous session."""
        resp = await httpx.AsyncClient().get(f"{self.base_url}/session")
        self.session_id = resp.json()["sessionId"]
        return self.session_id

    async def create_inbox(self, local_part: str | None = None) -> str:
        """Create temp email address. Returns full email."""
        headers = {"x-session-id": self.session_id}
        body = {"localPart": local_part} if local_part else {}
        resp = await httpx.AsyncClient().post(
            f"{self.base_url}/inboxes", headers=headers, json=body
        )
        return resp.json()["address"]  # e.g., "kopihujan42@webkarya.net"

    async def get_messages(self, address: str) -> list[dict]:
        """Get all messages for an inbox."""
        headers = {"x-session-id": self.session_id}
        encoded = httpx.URL(path=address).path
        resp = await httpx.AsyncClient().get(
            f"{self.base_url}/inboxes/{encoded}/messages", headers=headers
        )
        return resp.json()

    async def wait_for_otp(self, address: str, timeout: int = 60) -> str | None:
        """Poll inbox until OTP email arrives."""
        import time, re
        start = time.time()
        while time.time() - start < timeout:
            messages = await self.get_messages(address)
            for msg in messages:
                body = msg.get("body", "")
                otp_match = re.search(r'\b(\d{6})\b', body)
                if otp_match:
                    return otp_match.group(1)
            await asyncio.sleep(2)
        return None
```

### Key Features

- **Random addresses**: Indonesian-style names (e.g., `kopihujan42`, `bulanbiru17`)
- **No signup required**: Anonymous sessions, no API keys needed
- **Self-hosted**: Runs on Cloudflare Workers (free tier)
- **Instant delivery**: Email Worker → D1 database → API polling

## Slider CAPTCHA Solving

### OpenCV Approach

```python
import cv2
import numpy as np

def detect_gap(screenshot_path: str) -> int:
    """Detect horizontal gap position in slider puzzle image."""
    img = cv2.imread(screenshot_path, cv2.IMREAD_GRAYSCALE)
    # Edge detection to find the puzzle gap
    edges = cv2.Canny(img, 100, 200)
    # Find vertical lines (gap edges)
    # Return x-coordinate of gap center
    ...
```

### Playwright Drag

```python
async def drag_slider(page, slider_selector: str, distance: int):
    """Drag slider element by given pixel distance."""
    slider = page.locator(slider_selector)
    box = await slider.bounding_box()
    start_x = box['x'] + box['width'] / 2
    start_y = box['y'] + box['height'] / 2
    target_x = start_x + distance

    await page.mouse.move(start_x, start_y)
    await page.mouse.down()
    # Human-like movement with acceleration/deceleration
    for i in range(20):
        progress = i / 19
        eased = progress * progress * (3 - 2 * progress)  # smoothstep
        x = start_x + (target_x - start_x) * eased
        await page.mouse.move(x, start_y)
        await asyncio.sleep(random.uniform(0.01, 0.03))
    await page.mouse.up()
```

## API Key Capture Strategy

### Priority 1: Network Interception

```python
captured_key = None

async def on_response(response):
    global captured_key
    url = response.url
    if any(kw in url for kw in ['apikey', 'api-key', 'key/create']):
        try:
            body = await response.json()
            key = extract_key(body)  # find sk-ptw-* in response
            if key:
                captured_key = key
        except Exception:
            pass

page.on('response', on_response)
```

### Priority 2: UI Extraction

```python
# After "Create" click, immediately read from modal
key_element = page.locator('[class*="key"], code, pre').filter(has_text='sk-ptw-')
api_key = await key_element.first.text_content()
```

### Priority 3: Clipboard

```python
copy_btn = page.locator('button').filter(has_text='Copy').first
await copy_btn.click()
api_key = await page.evaluate('navigator.clipboard.readText()')
```

## UI Selectors (Estimated)

| Element | Selector Strategy |
|---------|------------------|
| "Get Started" | `button:has-text("Get Started")` or `a:has-text("Get Started")` |
| Email input | `input[type="email"]` or `input[placeholder*="example"]` |
| "Send code" | `button:has-text("Send code")` or `button:has-text("发送")` |
| Slider handle | `[class*="slider"], [class*="drag"], [class*="handler"]` |
| OTP input | `input[maxlength="1"]` (6 inputs) or single input |
| Password | `input[type="password"]` (first = password, second = confirm) |
| Invite code | `input[placeholder*="invitation"], input[placeholder*="invite"]` |
| ToS checkbox | `input[type="checkbox"]` |
| "Sign up" | `button:has-text("Sign up"), button:has-text("注册")` |
| "Get started" (post-reg) | `button:has-text("Get started")` |
| "Create Key" | `button:has-text("Create Key"), button:has-text("创建")` |
| Key Name input | `input[placeholder*="name"], input[placeholder*="Name"]` |
| Service Mode | `.ant-select, [class*="select"]` |
| "Create" (key) | `button:has-text("Create")` |
| API Key display | `text=/sk-ptw-/` |

## Reusable Components from qoder-autopilot

| Component | Path | Strategy |
|-----------|------|----------|
| Camoufox browser | `browser/camoufox.py` | ✅ Direct reuse |
| Window tiler | `browser/window_tiler.py` | ✅ Direct reuse |
| OTP extractor | `auth/otp.py` | ✅ Direct reuse (regex for 6-digit codes) |
| Identity generator | `auth/identity.py` | ✅ Direct reuse |
| Credential storage | `auth/credentials.py` | ✅ Direct reuse |
| Logger | `utils/logger.py` | ✅ Direct reuse |
| Manual captcha | `captcha/manual.py` | ✅ Direct reuse |
| Slider captcha | `captcha/slider.py` | 🔧 Adapt existing (OpenCV) |
| Config | `infra/config.py` | 🔧 Adapt for PatewayAI |
| Temp mail | `infra/tempik.py` | 🆕 NEW: Tempik API client |

## Configuration Keys

| Key | CLI Flag | Default | Description |
|-----|----------|---------|-------------|
| `tempik-url` | `--tempik-url` | `https://tempik.webkarya.net/api` | Tempik API base URL |
| `tempik-domain` | `--tempik-domain` | `webkarya.net` | Email domain for temp addresses |
| `mail-provider` | `--mail-provider` | `tempik` | Temp mail provider (tempik only for v1) |
| `otp-timeout` | `--otp-timeout` | `60` | Max seconds to wait for OTP |
| `captcha-timeout` | `--captcha-timeout` | `120` | Max seconds for manual captcha |
| `parallel-delay` | `--parallel-delay` | `30` | Delay between sequential accounts |
| `key-name` | `--key-name` | `prod` | Default API key name |
| `invite-code` | `--invite-code` | (empty) | Invite code to use |

## Environment Variables

All keys with `PATEWAY_` prefix:
```
PATEWAY_TEMPIK_URL=https://tempik.webkarya.net/api
PATEWAY_TEMPIK_DOMAIN=webkarya.net
PATEWAY_MAIL_PROVIDER=tempik
PATEWAY_OTP_TIMEOUT=60
PATEWAY_CAPTCHA_TIMEOUT=120
PATEWAY_PARALLEL_DELAY=30
PATEWAY_KEY_NAME=prod
PATEWAY_INVITE_CODE=...
```

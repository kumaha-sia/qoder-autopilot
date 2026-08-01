"""
Supervised Session Worker
=========================

File-driven semi-manual browser runner for pateway-autopilot.

Dipakai saat operator (manusia/AI) mau drive langkah registrasi satu per satu,
dengan audit trail lengkap: setiap command = 1 file JSON di `inbox/`, hasilnya
di `outbox/`, tiap mutasi otomatis screenshot ke `shots/`, semua ke-log di
`session.log`.

Flow pakai:
    pateway-autopilot --supervised          # spawn worker, print run dir
    pateway-autopilot supervised goto https://pateway.ai/
    pateway-autopilot supervised click 'button:has-text("Get Started")'
    pateway-autopilot supervised shot my_state
    pateway-autopilot supervised close

Kontrak file:
    runs/<RUN_ID>/supervised/inbox/NN_cmd.json    — ditulis oleh operator
    runs/<RUN_ID>/supervised/outbox/NN_cmd.json   — ditulis oleh worker
    runs/<RUN_ID>/supervised/shots/NN_cmd.png    — auto-screenshot per command
    runs/<RUN_ID>/supervised/session.log          — timestamped log semua step

Commands yang dikenali worker: goto, click, dblclick, fill, type, press, check,
hover, select, wait, wait_selector, wait_url, eval, shot, url, html_info,
scroll, mouse_drag, status, close.
"""

import asyncio
import datetime as dt
import json
import traceback
from pathlib import Path
from typing import Any

from ..browser.camoufox import launch_browser, setup_page

MUTATING_CMDS = {
    "goto",
    "click",
    "dblclick",
    "fill",
    "type",
    "press",
    "check",
    "select",
    "scroll",
    "mouse_drag",
    "wait_selector",
    "wait_url",
}


class SupervisedSession:
    """Worker that executes one browser command per inbox JSON file."""

    def __init__(self, run_dir: Path, headless: bool = False):
        self.run_dir = Path(run_dir)
        self.sup_dir = self.run_dir / "supervised"
        self.inbox = self.sup_dir / "inbox"
        self.outbox = self.sup_dir / "outbox"
        self.shots = self.sup_dir / "shots"
        self.log_path = self.sup_dir / "session.log"
        self.headless = headless
        self.step = 0
        self.page: Any = None  # Playwright Page once browser is up

    # ── logging helpers ─────────────────────────────────────────────────────

    def _ts(self) -> str:
        return dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    def slog(self, message: str) -> None:
        line = f"[{self._ts()}] {message}"
        print(line, flush=True)

        try:
            with self.log_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except Exception:  # noqa: BLE001
            pass  # never let logging crash the worker

    # ── screenshot ──────────────────────────────────────────────────────────

    async def snap(self, name: str) -> str:
        fname = f"{self.step:02d}_{name}.png"
        path = self.shots / fname
        try:
            await self.page.screenshot(path=str(path), full_page=False)
            return f"shots/{fname}"
        except Exception as exc:  # noqa: BLE001
            self.slog(f"screenshot FAILED ({name}): {exc}")
            return ""

    # ── command dispatcher ─────────────────────────────────────────────────

    async def handle(self, cmd: dict):
        page = self.page
        c = cmd.get("cmd")

        if c == "goto":
            await page.goto(cmd["url"], wait_until="domcontentloaded", timeout=60000)
            return {"url": page.url, "title": await page.title()}
        if c == "click":
            await page.locator(cmd["selector"]).first.click(timeout=cmd.get("timeout", 10000))
            return {"clicked": cmd["selector"]}
        if c == "dblclick":
            await page.locator(cmd["selector"]).first.dblclick(timeout=10000)
            return {"dblclicked": cmd["selector"]}
        if c == "fill":
            await page.locator(cmd["selector"]).first.fill(cmd["text"])
            return {"filled": cmd["selector"]}
        if c == "type":
            await page.locator(cmd["selector"]).first.type(cmd["text"], delay=cmd.get("delay", 60))
            return {"typed": cmd["selector"]}
        if c == "press":
            await page.keyboard.press(cmd["key"])
            return {"pressed": cmd["key"]}
        if c == "check":
            await page.locator(cmd["selector"]).first.check()
            return {"checked": cmd["selector"]}
        if c == "hover":
            await page.locator(cmd["selector"]).first.hover()
            return {"hovered": cmd["selector"]}
        if c == "select":
            await page.locator(cmd["selector"]).first.select_option(cmd["value"])
            return {"selected": cmd["value"]}
        if c == "wait":
            await page.wait_for_timeout(cmd.get("ms", 1000))
            return {"waited_ms": cmd.get("ms", 1000)}
        if c == "wait_selector":
            await page.wait_for_selector(cmd["selector"], timeout=cmd.get("timeout", 15000))
            return {"found": cmd["selector"]}
        if c == "wait_url":
            await page.wait_for_url(cmd["url"], timeout=cmd.get("timeout", 15000))
            return {"url": page.url}
        if c == "eval":
            result = await page.evaluate(cmd["js"])
            return {"result": result}
        if c == "scroll":
            await page.mouse.wheel(0, cmd.get("dy", 400))
            return {"scrolled": cmd.get("dy", 400)}
        if c == "mouse_drag":
            sx, sy = cmd["start"]
            dx = cmd.get("dx", 200)
            steps = cmd.get("steps", 25)
            await page.mouse.move(sx, sy)
            await page.mouse.down()
            for i in range(1, steps + 1):
                await page.mouse.move(sx + dx * i / steps, sy, steps=1)
                await asyncio.sleep(0.015)
            await page.mouse.up()
            return {"dragged_px": dx}
        if c == "shot":
            return {"shot": await self.snap(cmd.get("name", "manual"))}
        if c == "url":
            return {"url": page.url, "title": await page.title()}
        if c == "html_info":
            return await page.evaluate(
                """() => {
                    const buttons = [...document.querySelectorAll('button, a')]
                        .filter(b => b.offsetParent !== null)
                        .map(b => (b.textContent || '').trim())
                        .filter(t => t && t.length < 60).slice(0, 30);
                    const inputs = [...document.querySelectorAll('input')]
                        .filter(i => i.offsetParent !== null)
                        .map(i => `${i.type}|${i.placeholder || i.name || ''}`)
                        .slice(0, 20);
                    return {buttons, inputs};
                }"""
            )
        if c == "status":
            return {"alive": True, "url": page.url, "title": await page.title()}
        if c == "close":
            return "closing"
        raise ValueError(f"unknown cmd: {c}")

    # ── main loop ──────────────────────────────────────────────────────────

    async def run(self) -> None:
        for d in (self.inbox, self.outbox, self.shots):
            d.mkdir(parents=True, exist_ok=True)
        self.slog("═" * 60)
        self.slog("SUPERVISED SESSION START (file-driven)")
        self.slog(f"run_dir={self.run_dir}")
        self.slog(f"headless={self.headless}")

        async with launch_browser(headless=self.headless) as browser:
            self.page = await browser.new_page()
            await setup_page(self.page)
            self.slog(f"browser launched | viewport={self.page.viewport_size}")
            self.slog("READY — waiting for commands in supervised/inbox/")

            while True:
                # drain all pending command files, one at a time
                for job in sorted(self.inbox.glob("*.json")):
                    self.step += 1
                    try:
                        cmd = json.loads(job.read_text())
                    except Exception as exc:  # noqa: BLE001
                        self.slog(f"BAD JSON {job.name}: {exc}")
                        job.rename(job.with_suffix(".bad"))
                        self.step -= 1
                        continue

                    cname = cmd.get("cmd")
                    args = {k: v for k, v in cmd.items() if k != "cmd"}
                    self.slog(
                        f"── step {self.step} → CMD {cname} {json.dumps(args, ensure_ascii=False)}"
                    )

                    result: dict = {"step": self.step, "cmd": cname}
                    shot = None
                    try:
                        if cname == "close":
                            self.slog("close requested by operator")
                            result.update(ok=True, result="closing")
                        else:
                            out = await self.handle(cmd)
                            if cname in MUTATING_CMDS:
                                shot = await self.snap(cname)
                                self.slog(f"   📷 shot: {shot}")
                            self.slog(f"   ✓ OK: {json.dumps(out, ensure_ascii=False)[:300]}")
                            result.update(ok=True, result=out, shot=shot)
                    except Exception as exc:  # noqa: BLE001
                        self.slog(f"   ✗ ERROR: {type(exc).__name__}: {exc}")
                        self.slog(traceback.format_exc(limit=3))
                        shot = await self.snap(f"error_{cname}")
                        result.update(
                            ok=False,
                            error=f"{type(exc).__name__}: {exc}",
                            shot=shot,
                            url=self.page.url,
                        )

                    result["url"] = self.page.url
                    (self.outbox / job.name).write_text(
                        json.dumps(result, ensure_ascii=False, indent=2)
                    )
                    job.unlink()

                    if cname == "close":
                        self.slog("SUPERVISED SESSION END")
                        return

                await asyncio.sleep(0.5)


def default_run_dir() -> Path:
    """Create a new timestamped run directory under ./runs."""
    stamp = dt.datetime.now().strftime("supervised_%Y%m%d_%H%M%S")
    base = Path.cwd() / "runs"
    base.mkdir(exist_ok=True)
    d = base / stamp
    d.mkdir(exist_ok=True)
    return d


async def run_supervised_async(run_dir: str | None = None, headless: bool = False) -> Path:
    """Spawn a supervised browser worker; block until closed via `close` command."""
    rd = Path(run_dir) if run_dir else default_run_dir()
    session = SupervisedSession(rd, headless=headless)
    await session.run()
    return rd

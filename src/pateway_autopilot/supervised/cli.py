"""
Supervised Session Client
=========================

Sends one command to a running supervised worker and waits for its result.

Dipanggil via: ``pateway-autopilot supervised <cmd> [key=value ...]``

Examples:
    pateway-autopilot supervised goto url=https://pateway.ai/
    pateway-autopilot supervised click 'selector=button:has-text("Get Started")'
    pateway-autopilot supervised fill selector=input[type=email] text=x@y.com
    pateway-autopilot supervised eval 'js=() => document.title'
    pateway-autopilot supervised wait ms=2000
    pateway-autopilot supervised shot name=after_click
    pateway-autopilot supervised close

Matching worker: started via ``pateway-autopilot --supervised`` which prints
the run directory (containing ``supervised/inbox``). The client discovers the
newest run dir automatically, or use ``PATEWAY_SUPERVISED_DIR=<path>``.
"""

import json
import os
import sys
import time
from pathlib import Path

TIMEOUT = 60.0  # seconds to wait for a single command result


def _parse_args(argv: list[str]) -> dict:
    """Turn ['goto','url=https://x'] into {'cmd':'goto','url':'https://x'}.

    Bare value without '=' is treated as the primary argument for the command
    (url for goto, selector for click/fill..., js for eval, name for shot).
    """
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        sys.exit(0)

    cmd = argv[0]
    params: dict = {"cmd": cmd}
    primary = {
        "goto": "url",
        "click": "selector",
        "dblclick": "selector",
        "fill": "selector",
        "type": "selector",
        "check": "selector",
        "hover": "selector",
        "select": "selector",
        "wait_selector": "selector",
        "wait_url": "url",
        "eval": "js",
        "shot": "name",
        "press": "key",
    }.get(cmd)

    positional: list[str] = []
    for arg in argv[1:]:
        # 'key=value' only when what precedes '=' looks like a plain identifier.
        # Prevents selectors like 'input[type=email]' being mis-split (the part
        # before '=' contains brackets).
        key_part = arg.split("=", 1)[0]
        is_kv = "=" in arg and key_part.replace("-", "").replace("_", "").isalnum()
        if is_kv:
            key, _, value = arg.partition("=")
            # coerce simple types
            if key in ("ms", "timeout", "delay", "steps", "dx", "dy"):
                try:
                    value = int(value)
                except ValueError:
                    pass
            elif key == "start":
                value = [int(x) for x in value.split(",")]
            params[key] = value
        else:
            positional.append(arg)

    # Positional args: fill/type take (selector, text); others take single primary.
    if cmd in ("fill", "type") and len(positional) >= 2:
        params[primary] = positional[0]
        params["text"] = " ".join(positional[1:])
    elif positional and primary:
        params[primary] = " ".join(positional)

    return params


def _default_runs() -> Path:
    return Path.cwd() / "runs"


def _find_run_dir() -> Path:
    env = os.environ.get("PATEWAY_SUPERVISED_DIR")
    if env:
        return Path(env)
    runs = _default_runs()
    if not runs.is_dir():
        raise SystemExit(f"No runs/ directory at {runs}")
    candidates = sorted(
        (d for d in runs.iterdir() if d.is_dir() and (d / "supervised" / "inbox").is_dir()),
        key=lambda d: d.stat().st_mtime,
    )
    if not candidates:
        raise SystemExit("No active supervised session found under runs/")
    return candidates[-1]


def _next_number(inbox: Path, outbox: Path) -> int:
    """Next step filename number based on existing files on both sides."""
    nums = [0]
    for d in (inbox, outbox):
        for f in d.glob("*.json"):
            try:
                nums.append(int(f.name.split("_", 1)[0]))
            except ValueError:
                continue
    return max(nums) + 1


def cli(argv: list[str]) -> int:
    params = _parse_args(argv)
    run_dir = _find_run_dir()
    inbox = run_dir / "supervised" / "inbox"
    outbox = run_dir / "supervised" / "outbox"

    if not inbox.is_dir():
        raise SystemExit(f"Worker inbox not found: {inbox}")

    n = _next_number(inbox, outbox)
    name = f"{n:02d}_{params['cmd']}.json"
    job = inbox / name
    job.write_text(json.dumps(params))

    res_path = outbox / name
    deadline = time.time() + TIMEOUT
    while time.time() < deadline:
        if (inbox / f"{n:02d}_{params['cmd']}.bad").exists():
            print(f"command rejected as bad JSON by worker ({name})", file=sys.stderr)
            return 2
        if res_path.exists():
            result = json.loads(res_path.read_text())
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("ok") else 1
        time.sleep(0.4)

    print(f"timeout waiting for {res_path}", file=sys.stderr)
    return 3


if __name__ == "__main__":
    sys.exit(cli(sys.argv[1:]))

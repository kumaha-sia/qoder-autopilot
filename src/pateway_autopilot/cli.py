"""
Pateway Autopilot — CLI Entry Point
=====================================

Command-line interface for automated PatewayAI account registration.

Usage:
    pateway-autopilot -n 5 --manual-captcha --parallel
    python -m pateway_autopilot -n 3 --headless
"""

import argparse
import asyncio
import random
import signal
import sys

from .auth.credentials import save_creds, mask_value
from .auth.identity import gen_identity
from .browser.camoufox import launch_browser, setup_page
from .infra import config
from .infra.tempik import TempikClient
from .register import register_and_verify
from .utils.logger import (
    log,
    log_ok,
    log_err,
    log_warn,
    log_debug,
    log_banner,
    set_verbosity,
    set_account_tag,
    set_log_file,
    close_log_file,
)


async def run_one(
    headless: bool = True,
    manual_captcha: bool = False,
    acct_num: int = 0,
    proxy: str | None = None,
    invite_code: str = "",
) -> dict | None:
    """Register a single PatewayAI account.

    Args:
        headless: Run browser in headless mode.
        manual_captcha: Pause for manual captcha solving.
        acct_num: Account number for parallel mode logging.
        proxy: Proxy URL for browser.
        invite_code: Optional invite code.

    Returns:
        Dict with email, password, api_key on success, None on failure.
    """
    tag = f"#{acct_num}" if acct_num else ""
    if tag:
        set_account_tag(tag)

    # Force non-headless when manual captcha is enabled
    if manual_captcha:
        headless = False

    log("=" * 60)
    log(f"🤖 PATEWAY AUTOPILOT — Register + API Key {tag}")
    if manual_captcha:
        log("🧑 Manual captcha mode — browser will stay visible")
    log("=" * 60)

    # 1. Generate temp email via Tempik
    log("📋 Step 1/3: Generating temp email via Tempik...")
    tempik = TempikClient(base_url=config.TEMPIK_URL)
    try:
        edata = await tempik.generate()
        email = edata["address"]
        log_ok(f"Email: {email}")
    except Exception as e:
        log_err(f"Failed to generate temp email: {e}")
        return None

    # 2. Generate identity
    log("📋 Step 2/3: Generating identity...")
    ident = gen_identity()
    log_ok(f"{ident['display_name']} | pw: {mask_value(ident['password'])}")

    # 3. Register + create API key
    log("📋 Step 3/3: Registering account + creating API key...")

    # Calculate window size
    win_w, win_h = 900, 600

    async with launch_browser(
        headless=headless,
        window_width=win_w,
        window_height=win_h,
        proxy=proxy,
    ) as browser:
        page = await browser.new_page()
        await setup_page(page)

        api_key = await register_and_verify(
            page,
            email,
            ident,
            tempik,
            manual_captcha=manual_captcha,
            acct_num=acct_num,
            invite_code=invite_code,
        )

        # Keep browser open briefly
        await asyncio.sleep(1)
        await page.screenshot(path=str(config.SCREENSHOTS_DIR / "final_state.png"))
        final_url = page.url
        log(f"   📍 Final URL: {final_url}")

    # Close Tempik client
    await tempik.close()

    if not api_key:
        log_err("Registration/API key creation failed!")
        save_creds(
            {
                "email": email,
                "password": ident["password"],
                "display_name": ident["display_name"],
                "status": "failed",
            }
        )
        return None

    log_ok("Account registered & API key created! ✅")

    # Save credentials
    save_creds(
        {
            "email": email,
            "password": ident["password"],
            "display_name": ident["display_name"],
            "api_key": api_key,
            "base_url": config.PATEWAY_API_URL,
            "status": "success",
        }
    )

    log_ok(f"🎉 {email} → API Key: {mask_value(api_key)}")
    return {"email": email, "password": ident["password"], "api_key": api_key}


async def main_async(args: argparse.Namespace) -> None:
    """Async main entry point."""
    # Graceful shutdown on Ctrl+C
    _shutdown_event = asyncio.Event()

    def _handle_signal():
        log_warn("Shutdown requested (Ctrl+C) — cleaning up...")
        _shutdown_event.set()

    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _handle_signal)
    except NotImplementedError:
        pass  # Windows doesn't support add_signal_handler

    headless = args.headless
    manual_captcha = args.manual_captcha
    parallel = args.parallel

    # Apply verbosity
    if args.verbose:
        set_verbosity(2)
    elif args.quiet:
        set_verbosity(0)

    # Log file
    log_file_handle = None
    if args.log_file:
        log_file_handle = set_log_file(args.log_file)
        log(f"📝 Logging to: {args.log_file}")

    proxy = args.proxy
    output_format = args.output_format
    invite_code = args.invite_code or config.INVITE_CODE

    # Dry-run mode
    if args.dry_run:
        log_ok("Dry-run mode: configuration is valid ✅")
        log(f"  Accounts: {args.count}")
        log(f"  Headless: {headless}")
        log(f"  Manual captcha: {manual_captcha}")
        log(f"  Parallel: {parallel}")
        log(f"  Tempik URL: {config.TEMPIK_URL}")
        log(f"  PatewayAI URL: {config.PATEWAY_URL}")
        return

    log_banner()
    log(
        f"🎯 Creating {args.count} account(s) | "
        f"headless={headless} | manual_captcha={manual_captcha} | parallel={parallel}"
    )

    if parallel and args.count > 1:
        # PARALLEL MODE
        log(f"⚡ Parallel mode: launching {args.count} browser windows")

        async def staggered_run(i: int) -> dict | None:
            if i > 0:
                await asyncio.sleep(i * 2)
            return await run_one(
                headless=headless,
                manual_captcha=manual_captcha,
                acct_num=i + 1,
                proxy=proxy,
                invite_code=invite_code,
            )

        tasks = [staggered_run(i) for i in range(args.count)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        for i, r in enumerate(results):
            if isinstance(r, Exception):
                log_err(f"Account #{i + 1} crashed: {r}")
                results[i] = None
    else:
        # SEQUENTIAL MODE
        results = []
        for i in range(args.count):
            log(f"\n{'─' * 60}\n📦 Account {i + 1}/{args.count}\n{'─' * 60}")
            r = await run_one(
                headless=headless,
                manual_captcha=manual_captcha,
                acct_num=i + 1 if args.count > 1 else 0,
                proxy=proxy,
                invite_code=invite_code,
            )
            results.append(r)
            if i < args.count - 1:
                d = config.PARALLEL_DELAY + random.randint(0, 15)
                log(f"⏳ Waiting {d}s...")
                await asyncio.sleep(d)

    s = sum(1 for r in results if r)
    log(f"\n{'═' * 60}\n📊 DONE: {s}/{len(results)} succeeded\n{'═' * 60}")

    # Output results
    valid_results = [r for r in results if r]
    if output_format == "json":
        import json

        print(json.dumps(valid_results, indent=2))
    elif output_format == "csv":
        if valid_results:
            keys = list(valid_results[0].keys())
            print(",".join(keys))
            for r in valid_results:
                print(",".join(str(r.get(k, "")) for k in keys))

    # Cleanup screenshots on success
    try:
        import shutil

        if config.SCREENSHOTS_DIR.exists() and not any(config.SCREENSHOTS_DIR.glob("*fail*")):
            shutil.rmtree(config.SCREENSHOTS_DIR, ignore_errors=True)
            log_debug("Cleaned up debug screenshots")
    except Exception:
        pass

    # Close log file
    if log_file_handle:
        close_log_file()
        log(f"📝 Log saved to: {args.log_file}")


def main() -> None:
    """CLI entry point with config management subcommand."""
    # Quick check for subcommands
    if len(sys.argv) > 1:
        sub = sys.argv[1]

        if sub == "config":
            _handle_config_command(sys.argv[2:])
            return

    # Main registration arguments
    p = argparse.ArgumentParser(
        prog="pateway-autopilot",
        description="Automated PatewayAI account registration with API key creation",
        epilog=(
            "subcommands:\n"
            "  config           Manage configuration (show/set/get/reset)\n"
            "\n"
            "examples:\n"
            "  pateway-autopilot -n 3 --manual-captcha\n"
            "  pateway-autopilot -n 10 --parallel\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    def _valid_count(val: str) -> int:
        n = int(val)
        if n < 1 or n > 100:
            raise argparse.ArgumentTypeError(f"Count must be between 1 and 100, got {n}")
        return n

    p.add_argument(
        "-n",
        "--count",
        type=_valid_count,
        default=1,
        help="Number of accounts to create (1-100)",
    )
    p.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode (hidden)",
    )
    p.add_argument(
        "--manual-captcha",
        action="store_true",
        help="Pause for manual CAPTCHA solving (forces non-headless)",
    )
    p.add_argument(
        "--parallel",
        action="store_true",
        help="Run all accounts concurrently",
    )
    p.add_argument(
        "--delay",
        type=int,
        default=config.PARALLEL_DELAY,
        help=f"Delay between sequential accounts (default: {config.PARALLEL_DELAY}s)",
    )
    p.add_argument(
        "--invite-code",
        type=str,
        default="",
        help="Invite code for registration",
    )
    p.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show debug-level logs",
    )
    p.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Only show errors and warnings",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and exit",
    )
    p.add_argument(
        "--proxy",
        type=str,
        default=None,
        metavar="URL",
        help="Proxy URL (e.g., socks5://host:port)",
    )
    p.add_argument(
        "--format",
        choices=["text", "json", "csv"],
        default="text",
        dest="output_format",
        help="Output format for results",
    )
    p.add_argument(
        "--log-file",
        type=str,
        default=None,
        metavar="PATH",
        help="Write logs to file",
    )
    args = p.parse_args()

    asyncio.run(main_async(args))


def _handle_config_command(argv: list[str]) -> None:
    """Handle 'pateway-autopilot config' subcommands."""
    from .infra.config import (
        USER_CONFIG_FILE,
        load_user_config,
        set_user_config_value,
        delete_user_config,
    )

    if not argv or argv[0] in ("-h", "--help"):
        print("Usage: pateway-autopilot config <command> [args]")
        print()
        print("Commands:")
        print("  show                    Show all current settings")
        print("  set <key> <value>       Set a config value")
        print("  get <key>               Get a config value")
        print("  reset                   Reset all settings to defaults")
        print()
        print("Configurable keys:")
        keys = [
            ("tempik-url", "Tempik API base URL"),
            ("tempik-domain", "Email domain for temp addresses"),
            ("otp-timeout", "Max seconds to wait for OTP"),
            ("captcha-timeout", "Max seconds for manual captcha"),
            ("parallel-delay", "Delay between sequential accounts"),
            ("key-name", "Default API key name"),
            ("invite-code", "Invite code for registration"),
        ]
        for cli, desc in keys:
            print(f"  {cli:<25} {desc}")
        print()
        print(f"Config file: {USER_CONFIG_FILE}")
        return

    cmd = argv[0]

    if cmd == "show":
        cfg = load_user_config()
        from .infra.config import settings

        print(f"{'Setting':<25} {'Value':<50} {'Source':<10}")
        print("─" * 85)
        for key in [
            "tempik_url", "tempik_domain", "otp_timeout",
            "captcha_timeout", "parallel_delay", "key_name", "invite_code",
        ]:
            cli = key.replace("_", "-")
            current = getattr(settings, key, None)
            source = "config" if key in cfg else "default"
            val_str = str(current) if current else "(empty)"
            if "invite" in key and val_str:
                val_str = val_str[:4] + "••••" if len(val_str) > 4 else "***"
            print(f"  {cli:<23} {val_str:<50} {source}")
        print()
        print(f"Config file: {USER_CONFIG_FILE}")

    elif cmd == "set":
        if len(argv) < 3:
            print("Usage: pateway-autopilot config set <key> <value>")
            sys.exit(1)
        cli_flag = argv[1]
        value = argv[2]
        key_map = {
            "tempik-url": "tempik_url",
            "tempik-domain": "tempik_domain",
            "otp-timeout": "otp_timeout",
            "captcha-timeout": "captcha_timeout",
            "parallel-delay": "parallel_delay",
            "key-name": "key_name",
            "invite-code": "invite_code",
        }
        key = key_map.get(cli_flag)
        if not key:
            print(f"❌ Unknown key: {cli_flag}")
            print(f"Available: {', '.join(key_map.keys())}")
            sys.exit(1)
        if set_user_config_value(key, value):
            print(f"✅ {cli_flag} = {value}")
            print(f"   Saved to {USER_CONFIG_FILE}")
        else:
            print(f"❌ Failed to set {cli_flag}")
            sys.exit(1)

    elif cmd == "get":
        if len(argv) < 2:
            print("Usage: pateway-autopilot config get <key>")
            sys.exit(1)
        cli_flag = argv[1]
        cfg = load_user_config()
        key = cli_flag.replace("-", "_")
        val = cfg.get(key, "(not set)")
        print(f"{cli_flag} = {val}")

    elif cmd == "reset":
        if delete_user_config():
            print(f"✅ Config reset — deleted {USER_CONFIG_FILE}")
        else:
            print("ℹ️  No config file to delete")

    else:
        print(f"❌ Unknown command: {cmd}")
        print("Run 'pateway-autopilot config --help' for usage")
        sys.exit(1)

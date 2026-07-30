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
from .infra.proxies import load_proxies, ProxyRotator
from .infra.temp_mail import TempMailClient
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
    user_email: str | None = None,
    mail_provider: str | None = None,
    gmail_password: str | None = None,
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

    # 1. Generate email
    temp_mail = None
    # Use config values as defaults, CLI args as overrides
    effective_email = user_email or config.GMAIL_EMAIL
    effective_password = gmail_password or config.GMAIL_APP_PASSWORD

    if effective_email:
        # If Gmail with app password → use IMAP for auto OTP
        if "gmail.com" in effective_email.lower() or "googlemail.com" in effective_email.lower():
            from .infra.email_gen import GmailAliasGenerator
            gen = GmailAliasGenerator(effective_email, method="dot")
            email = gen.get(acct_num) if acct_num > 0 else gen.next()
            log_ok(f"Gmail alias: {email}")

            if effective_password:
                from .infra.gmail_imap import GmailImapClient
                try:
                    temp_mail = GmailImapClient(effective_email, effective_password)
                    await temp_mail.create()
                    log_ok(f"Gmail IMAP connected — OTP will be auto-read")
                except Exception as e:
                    log_warn(f"Gmail IMAP failed: {e} — will use manual OTP")
                    temp_mail = None
            else:
                log_warn("No Gmail app password — OTP must be entered manually")
        else:
            email = effective_email
            log_ok(f"Using provided email: {email}")
    else:
        log("📋 Step 1/3: Generating temp email...")
        provider = mail_provider or config.MAIL_PROVIDER
        temp_mail = TempMailClient(preferred_provider=provider)
        try:
            email = await temp_mail.create()
            log_ok(f"Email: {email} (via {temp_mail.provider})")
        except Exception as e:
            log_err(f"Failed to generate temp email: {e}")
            return None

    # 2. Generate identity
    log("📋 Step 2/3: Generating identity...")
    ident = gen_identity()
    log_ok(f"{ident['display_name']} | pw: {mask_value(ident['password'])}")

    # 3. Register + create API key
    log("📋 Step 3/3: Registering account + creating API key...")

    async with launch_browser(
        headless=headless,
        proxy=proxy,
    ) as browser:
        page = await browser.new_page()
        await setup_page(page)

        api_key = await register_and_verify(
            page,
            email,
            ident,
            temp_mail,
            manual_captcha=manual_captcha,
            acct_num=acct_num,
            invite_code=invite_code,
        )

        # Keep browser open briefly so user can see what happened
        if not api_key:
            log_warn("Registration failed — browser will stay open for 10s for inspection")
            await asyncio.sleep(10)
        else:
            await asyncio.sleep(1)
        await page.screenshot(path=str(config.SCREENSHOTS_DIR / "final_state.png"))
        final_url = page.url
        log(f"   📍 Final URL: {final_url}")

    # Close temp mail client
    if temp_mail:
        await temp_mail.close()

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
        # Windows: set up KeyboardInterrupt handler via signal.signal
        def _win_signal_handler(sig, frame):
            _handle_signal()
        signal.signal(signal.SIGINT, _win_signal_handler)

    headless = args.headless
    manual_captcha = args.manual_captcha
    parallel = args.parallel

    # Apply verbosity (mutually exclusive: verbose takes precedence, warn if both)
    if args.verbose and args.quiet:
        log_warn("Both --verbose and --quiet specified — using verbose mode")
        set_verbosity(2)
    elif args.verbose:
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
    user_email = args.email
    mail_provider = args.mail_provider
    # Use args.invite_code if provided (even if empty string), else fall back to config
    invite_code = args.invite_code if args.invite_code is not None else config.INVITE_CODE

    # Proxy rotation setup
    proxy_rotator = None
    if args.proxy_file:
        proxy_list = load_proxies(args.proxy_file)
        if proxy_list:
            proxy_rotator = ProxyRotator(proxy_list)
            log(f"🔄 Proxy rotation enabled: {proxy_rotator.count} proxies")
        else:
            log_warn("No proxies loaded from file, falling back to single proxy")
    elif proxy:
        # Single proxy → wrap in rotator for consistent API
        proxy_rotator = ProxyRotator([proxy])
        proxy = None  # Clear single proxy, rotator handles it

    # Dry-run mode
    if args.dry_run:
        log_ok("Dry-run mode: configuration is valid ✅")
        log(f"  Accounts: {args.count}")
        log(f"  Headless: {headless}")
        log(f"  Manual captcha: {manual_captcha}")
        log(f"  Parallel: {parallel}")
        log(f"  Mail provider: {config.MAIL_PROVIDER}")
        log(f"  Proxy: {proxy or ('rotation (' + str(proxy_rotator.count) + ' proxies)' if proxy_rotator else 'none')}")
        log(f"  Tempik URL: {config.TEMPIK_URL}")
        log(f"  PatewayAI URL: {config.PATEWAY_URL}")
        return

    log_banner()
    proxy_info = f"proxies={proxy_rotator.count}" if proxy_rotator else f"proxy={proxy or 'none'}"
    log(
        f"🎯 Creating {args.count} account(s) | "
        f"headless={headless} | manual_captcha={manual_captcha} | parallel={parallel} | {proxy_info}"
    )

    if parallel and args.count > 1:
        # PARALLEL MODE
        if manual_captcha:
            log_warn("⚠️ Parallel + manual captcha with count >1: multiple browser windows will pause simultaneously")
            log_warn("   Consider using auto captcha or reducing count for manual mode")
        log(f"⚡ Parallel mode: launching {args.count} browser windows")

        async def staggered_run(i: int) -> dict | None:
            if i > 0:
                await asyncio.sleep(i * 2)
            acct_proxy = proxy_rotator.get_for_account(i + 1) if proxy_rotator else None
            return await run_one(
                headless=headless,
                manual_captcha=manual_captcha,
                acct_num=i + 1,
                proxy=acct_proxy,
                invite_code=invite_code,
                user_email=user_email,
                mail_provider=mail_provider,
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
            acct_proxy = proxy_rotator.get_for_account(i + 1) if proxy_rotator else None
            log(f"\n{'─' * 60}\n📦 Account {i + 1}/{args.count}\n{'─' * 60}")
            r = await run_one(
                headless=headless,
                manual_captcha=manual_captcha,
                acct_num=i + 1 if args.count > 1 else 0,
                proxy=acct_proxy,
                invite_code=invite_code,
                user_email=user_email,
                mail_provider=mail_provider,
            )
            results.append(r)
            if i < args.count - 1:
                d = args.delay + random.randint(0, 15)
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
        import csv
        import io
        if valid_results:
            keys = list(valid_results[0].keys())
            buf = io.StringIO()
            writer = csv.writer(buf)
            writer.writerow(keys)
            for r in valid_results:
                writer.writerow([str(r.get(k, "")) for k in keys])
            print(buf.getvalue(), end="")

    # Cleanup screenshots on success
    try:
        import shutil

        if config.SCREENSHOTS_DIR.exists():
            # Only delete if ALL accounts succeeded (no failure/error/no_captcha screenshots)
            fail_patterns = ["*fail*", "*error*", "*no_captcha*", "*send_code_error*", "*otp_timeout*"]
            has_failure_screenshots = any(
                config.SCREENSHOTS_DIR.glob(pattern)
                for pattern in fail_patterns
            )
            if not has_failure_screenshots:
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
    def _valid_delay(val: str) -> int:
        n = int(val)
        if n < 1:
            raise argparse.ArgumentTypeError(f"Delay must be at least 1 second, got {n}")
        return n

    p.add_argument(
        "--delay",
        type=_valid_delay,
        default=config.PARALLEL_DELAY,
        help=f"Delay between sequential accounts (default: {config.PARALLEL_DELAY}s)",
    )
    p.add_argument(
        "--email",
        type=str,
        default=None,
        metavar="EMAIL",
        help="Use specific email address instead of auto-generating temp email",
    )
    p.add_argument(
        "--mail-provider",
        type=str,
        choices=["mail.tm", "guerrilla", "1secmail", "tempik"],
        default=None,
        help="Temp mail provider (default: mail.tm)",
    )
    p.add_argument(
        "--invite-code",
        type=str,
        default=None,
        help="Invite code for registration (use empty string to override config default)",
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
        help="Single proxy URL (e.g., socks5://host:port)",
    )
    p.add_argument(
        "--proxy-file",
        type=str,
        default=None,
        metavar="PATH",
        help="Proxy list file (host:port:user:pass per line, rotates per account)",
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
            ("gmail-email", "Your Gmail address (for dot/plus alias + auto OTP)"),
            ("gmail-app-password", "Gmail App Password (16 chars) for IMAP auto-OTP"),
            ("mail-provider", "Temp mail provider: mail.tm, guerrilla, 1secmail, tempik"),
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
            "gmail_email", "gmail_app_password", "mail_provider",
            "otp_timeout", "captcha_timeout", "parallel_delay", "key_name", "invite_code",
        ]:
            cli = key.replace("_", "-")
            current = getattr(settings, key, None)
            source = "config" if key in cfg else "default"
            val_str = str(current) if current else "(empty)"
            # Mask sensitive fields
            if any(s in key for s in ("invite", "password", "app_password")) and val_str and val_str != "(empty)":
                val_str = val_str[:4] + "••••" if len(val_str) > 4 else "***"
            print(f"  {cli:<23} {val_str:<50} {source}")
        print()
        print(f"Config file: {USER_CONFIG_FILE}")

    elif cmd == "set":
        if len(argv) < 3:
            print("Usage: pateway-autopilot config set <key> <value>")
            sys.exit(1)
        cli_flag = argv[1]
        # Support multi-word values (e.g., gmail app password with spaces)
        value = " ".join(argv[2:]) if len(argv) > 3 else argv[2]
        key_map = {
            "gmail-email": ("gmail_email", str),
            "gmail-app-password": ("gmail_app_password", str),
            "mail-provider": ("mail_provider", str),
            "otp-timeout": ("otp_timeout", int),
            "captcha-timeout": ("captcha_timeout", int),
            "parallel-delay": ("parallel_delay", int),
            "key-name": ("key_name", str),
            "invite-code": ("invite_code", str),
        }
        key_entry = key_map.get(cli_flag)
        if not key_entry:
            print(f"❌ Unknown key: {cli_flag}")
            print(f"Available: {', '.join(key_map.keys())}")
            sys.exit(1)
        key, expected_type = key_entry
        if expected_type == int:
            try:
                int(value)
            except ValueError:
                print(f"❌ {cli_flag} requires a numeric value, got: '{value}'")
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

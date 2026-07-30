"""Live test: connect to Gmail and read the LATEST PatewayAI OTP email.

This test actually connects to Gmail IMAP using your credentials
and dumps the raw body of the most recent PatewayAI email so we can
see the exact format and verify OTP extraction works correctly.

Usage:
    python3 tests/pateway/test_gmail_live_otp.py
"""

import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from pateway_autopilot.infra.gmail_imap import GmailImapClient
from pateway_autopilot.infra.config import Settings


async def main():
    settings = Settings()
    email_addr = settings.gmail_email
    app_password = settings.gmail_app_password

    if not email_addr or not app_password:
        print("ERROR: Gmail credentials not set. Run:")
        print("  pateway-autopilot config set gmail-email you@gmail.com")
        print("  pateway-autopilot config set gmail-app-password xxxx xxxx xxxx xxxx")
        sys.exit(1)

    print(f"Connecting to Gmail as {email_addr}...")
    client = GmailImapClient(email_addr, app_password)
    await client.create()

    print(f"Baseline IDs: {len(client._baseline_ids)} old emails")

    messages = await client.get_messages()
    print(f"\nTotal recent messages: {len(messages)}")

    # Find PatewayAI emails
    pateway_emails = []
    for msg in messages:
        from_addr = msg.get("from_address", "") or ""
        subject = msg.get("subject", "") or ""
        if "pateway" in from_addr.lower() or "验证码" in subject or "verification" in subject.lower():
            pateway_emails.append(msg)

    print(f"PatewayAI emails found: {len(pateway_emails)}")

    if not pateway_emails:
        print("\nNo PatewayAI emails found. Showing ALL recent emails:")
        for i, msg in enumerate(messages):
            print(f"\n--- Email {i+1} ---")
            print(f"  From: {msg.get('from_address', '')}")
            print(f"  Subject: {msg.get('subject', '')}")
            print(f"  Body (first 200 chars): {(msg.get('body', '') or '')[:200]}")
        await client.close()
        return

    # Show each PatewayAI email with full body
    for i, msg in enumerate(pateway_emails):
        print(f"\n{'='*60}")
        print(f"PatewayAI Email #{i+1}")
        print(f"{'='*60}")
        print(f"  ID: {msg.get('id', '')[:60]}")
        print(f"  From: {msg.get('from_address', '')}")
        print(f"  Subject: {msg.get('subject', '')}")
        print(f"  Date: {msg.get('received_at', '')}")

        body = msg.get("body", "") or ""
        print(f"\n  BODY (raw):")
        print(f"  {'-'*50}")
        for line in body.split("\n"):
            print(f"  | {line}")
        print(f"  {'-'*50}")

        # Test OTP extraction patterns
        print(f"\n  OTP EXTRACTION TESTS:")

        # Strategy 1: VERIFICATION CODE pattern
        pat_verify = re.compile(r"VERIFICATION\s*CODE\D*(\d{6})", re.IGNORECASE)
        for label, text in [("subject", msg.get("subject", "")), ("body", body)]:
            if not isinstance(text, str) or not text:
                continue
            match = pat_verify.search(text)
            if match:
                print(f"  ✅ Strategy 1 (VERIFICATION CODE) in {label}: {match.group(1)}")
            else:
                print(f"  ❌ Strategy 1 (VERIFICATION CODE) in {label}: no match")

        # Strategy 2: 验证码 pattern
        pat_cn = re.compile(r"验证码\D*(\d{6})")
        for label, text in [("subject", msg.get("subject", "")), ("body", body)]:
            if not isinstance(text, str) or not text:
                continue
            match = pat_cn.search(text)
            if match:
                print(f"  ✅ Strategy 2 (验证码) in {label}: {match.group(1)}")
            else:
                print(f"  ❌ Strategy 2 (验证码) in {label}: no match")

        # Strategy 3: Generic 6-digit fallback
        pat_generic = re.compile(r"\b(\d{6})\b")
        for label, text in [("subject", msg.get("subject", "")), ("body", body)]:
            if not isinstance(text, str) or not text:
                continue
            all_matches = pat_generic.findall(text)
            if all_matches:
                print(f"  ⚠️  Strategy 3 (generic \\d{{6}}) in {label}: {all_matches}")
            else:
                print(f"  ❌ Strategy 3 (generic \\d{{6}}) in {label}: no match")

        # NEW: Try improved patterns
        # Pattern: "VERIFICATION CODE" on one line, digits on next line
        pat_multiline = re.compile(r"VERIFICATION\s*CODE\s*\n\s*(\d{6})", re.IGNORECASE)
        match = pat_multiline.search(body)
        if match:
            print(f"  ✅ NEW (multiline VERIFICATION CODE): {match.group(1)}")
        else:
            print(f"  ❌ NEW (multiline VERIFICATION CODE): no match")

        # Pattern: digits after Chinese text + newline
        pat_cn_multiline = re.compile(r"验证码[^\d]*\n\s*(\d{6})")
        match = pat_cn_multiline.search(body)
        if match:
            print(f"  ✅ NEW (multiline 验证码): {match.group(1)}")
        else:
            print(f"  ❌ NEW (multiline 验证码): no match")

        # Show all 6-digit numbers found in body for debugging
        all_digits = re.findall(r"\d{6}", body)
        print(f"\n  ALL 6-digit numbers in body: {all_digits}")

    # Also test wait_for_otp with the latest PatewayAI email
    if pateway_emails:
        print(f"\n\n{'='*60}")
        print(f"TESTING wait_for_otp() with LATEST PatewayAI email")
        print(f"{'='*60}")
        # Reset baseline so the latest email is treated as "new"
        client._baseline_ids = set()
        otp = await client.wait_for_otp(timeout=5, poll_interval=1)
        print(f"\n  wait_for_otp() result: {otp}")

    await client.close()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())

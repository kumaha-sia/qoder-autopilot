"""
Gmail IMAP Client — Auto-Read OTP
===================================

Connects to Gmail via IMAP to automatically read OTP emails.
Works with Gmail dot/plus trick — all aliases land in the same inbox.

Setup:
  1. Enable 2-Step Verification: https://myaccount.google.com/security
  2. Generate App Password: https://myaccount.google.com/apppasswords
  3. Use: pateway-autopilot --email you@gmail.com --gmail-password xxxx xxxx xxxx xxxx

Flow:
  - GmailAliasGenerator creates unique alias (dot+plus trick)
  - PatewayAI sends OTP to alias → lands in your Gmail inbox
  - GmailImapClient reads inbox via IMAP → extracts OTP automatically
  - No manual checking needed!
"""

import asyncio
import email
import imaplib
import re
import time
from email.header import decode_header

from ..utils.logger import log, log_debug, log_err, log_ok


class GmailImapClient:
    """Gmail IMAP client for auto-reading OTP emails."""

    IMAP_SERVER = "imap.gmail.com"
    IMAP_PORT = 993

    def __init__(self, email_address: str, app_password: str):
        """Initialize Gmail IMAP client.

        Args:
            email_address: Your Gmail address (e.g., "you@gmail.com").
            app_password: Gmail App Password (16 chars, spaces ok).
                         Generate at: https://myaccount.google.com/apppasswords
        """
        self.email_address = email_address
        # Remove spaces from app password (Google shows it with spaces)
        self.app_password = app_password.replace(" ", "")
        self._conn: imaplib.IMAP4_SSL | None = None
        self.address = email_address  # Compatible with TempMailClient interface
        self._baseline_ids: set = set()  # IDs of emails before we start waiting

    def _connect(self) -> imaplib.IMAP4_SSL:
        """Connect and login to Gmail IMAP."""
        if self._conn is not None:
            try:
                # Test if connection is alive
                self._conn.noop()
                return self._conn
            except Exception:
                self._conn = None

        conn = imaplib.IMAP4_SSL(self.IMAP_SERVER, self.IMAP_PORT)
        conn.login(self.email_address, self.app_password)
        log_debug(f"Gmail IMAP: connected as {self.email_address}")
        self._conn = conn
        return conn

    async def create(self) -> str:
        """Compatible with TempMailClient interface.

        Connects to Gmail and records baseline message IDs so we only
        pick up NEW emails that arrive after this point.
        """
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._connect)

        # Record baseline: all existing message IDs so we skip old emails
        baseline_msgs = await self.get_messages()
        self._baseline_ids = {m.get("id", "") for m in baseline_msgs}
        log_ok(
            f"Gmail IMAP: connected to {self.email_address} ({len(self._baseline_ids)} existing emails)"
        )
        return self.email_address

    async def get_messages(self) -> list[dict]:
        """Get recent messages from inbox.

        Returns:
            List of message dicts with from_address, subject, body.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_recent_messages)

    def _fetch_recent_messages(self) -> list[dict]:
        """Fetch recent messages from Gmail using UID (persistent IDs)."""
        try:
            conn = self._connect()
            conn.select("INBOX")

            import datetime

            today = datetime.datetime.now().strftime("%d-%b-%Y")

            # Use UID search for persistent message IDs.  charset=None is
            # accepted by Gmail at runtime; the imaplib type stubs incorrectly
            # require str, so we suppress the type check.
            status, data = conn.uid("search", None, f"(SINCE {today})")  # type: ignore[arg-type]
            if status != "OK":
                return []

            uid_list = data[0].split()
            # Get last 10 UIDs max
            uid_list = uid_list[-10:] if len(uid_list) > 10 else uid_list

            messages = []
            for uid in reversed(uid_list):  # Newest first
                try:
                    status, msg_data = conn.uid("fetch", uid, "(RFC822)")
                    if status != "OK":
                        continue

                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    subject = self._decode_header(msg.get("Subject", ""))
                    from_addr = self._decode_header(msg.get("From", ""))
                    body = self._extract_body(msg)

                    # Use Message-ID header as stable unique identifier
                    message_id = msg.get("Message-ID", uid.decode())

                    messages.append(
                        {
                            "id": message_id,
                            "uid": uid.decode(),
                            "from_address": from_addr,
                            "subject": subject,
                            "body": body,
                            "received_at": msg.get("Date", ""),
                        }
                    )
                except Exception:
                    continue

            return messages

        except Exception as e:
            log_debug(f"Gmail IMAP fetch error: {e}")
            return []

    def _decode_header(self, header: str) -> str:
        """Decode email header."""
        if not header:
            return ""
        try:
            decoded = decode_header(header)
            parts = []
            for part, charset in decoded:
                if isinstance(part, bytes):
                    parts.append(part.decode(charset or "utf-8", errors="replace"))
                else:
                    parts.append(part)
            return "".join(parts)
        except Exception:
            return header

    def _extract_body(self, msg) -> str:
        """Extract text body from email message."""
        body = ""
        if msg.is_multipart():
            for part in msg.walk():
                content_type = part.get_content_type()
                content_disposition = str(part.get("Content-Disposition", ""))
                if content_type == "text/plain" and "attachment" not in content_disposition:
                    try:
                        payload = part.get_payload(decode=True)
                        if payload:
                            charset = part.get_content_charset() or "utf-8"
                            body = payload.decode(charset, errors="replace")
                            break
                    except Exception:
                        continue
            # Fallback to HTML if no plain text
            if not body:
                for part in msg.walk():
                    content_type = part.get_content_type()
                    if content_type == "text/html":
                        try:
                            payload = part.get_payload(decode=True)
                            if payload:
                                charset = part.get_content_charset() or "utf-8"
                                html = payload.decode(charset, errors="replace")
                                body = self._html_to_text(html)
                                break
                        except Exception:
                            continue
        else:
            try:
                payload = msg.get_payload(decode=True)
                if payload:
                    charset = msg.get_content_charset() or "utf-8"
                    body = payload.decode(charset, errors="replace")
            except Exception:
                pass

        return body

    @staticmethod
    def _html_to_text(html: str) -> str:
        """Convert HTML to clean text, removing style/script blocks first."""
        # Remove <style> and <script> blocks entirely (they contain CSS numbers that
        # falsely match as OTP codes — e.g. "0.475569" → "475569")
        text = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # Replace <br>, <div>, <p>, <tr>, <td> with newlines for readability
        text = re.sub(
            r"<br\s*/?>|</?(?:div|p|tr|td|h[1-6]|li|table)[^>]*>", "\n", text, flags=re.IGNORECASE
        )
        # Strip remaining HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Collapse whitespace but preserve newlines
        text = re.sub(r"[^\S\n]+", " ", text)
        # Remove leading/trailing whitespace per line
        lines = [line.strip() for line in text.split("\n")]
        return "\n".join(line for line in lines if line).strip()

    async def wait_for_otp(
        self,
        timeout: int = 120,
        poll_interval: float = 3.0,
        otp_pattern: str = r"\b(\d{6})\b",
    ) -> str | None:
        """Poll Gmail inbox until OTP email arrives.

        Only checks emails that arrived AFTER create() was called
        (using baseline message IDs).

        PatewayAI email format:
            Subject: 【验证码】欢迎注册
            Body: VERIFICATION CODE\\n330605

        Strategy:
            1. Filter: only process emails from PatewayAI sender or with OTP-related subject
            2. Look for "VERIFICATION CODE" followed by 6 digits (most precise)
            3. Look for "验证码" followed by 6 digits
            4. Fall back to any standalone 6-digit number (only on confirmed OTP emails)

        Args:
            timeout: Max seconds to wait.
            poll_interval: Seconds between polls.
            otp_pattern: Regex pattern to match OTP (fallback).

        Returns:
            OTP string if found, None if timeout.
        """
        start = time.time()
        # PatewayAI-specific patterns
        # After HTML-to-text conversion, "VERIFICATION CODE" and the OTP digits
        # are on separate lines. Match "VERIFICATION CODE" followed by digits
        # within a few lines (allowing newlines/spaces between).
        pat_verify_code = re.compile(r"VERIFICATION\s*CODE\s*\n?\s*(\d{6})", re.IGNORECASE)
        # Chinese: 验证码 (verification code) followed by 6 digits
        pat_cn_code = re.compile(r"验证码\D{0,50}(\d{6})")
        # Also match the CSS class pattern: otp-code">NNNNNN</div> (raw HTML fallback)
        pat_otp_class = re.compile(r"otp-code[^>]*>\s*(\d{6})", re.IGNORECASE)
        # Sender/subject filters — only process emails that look like PatewayAI OTP
        pat_sender = re.compile(r"pateway", re.IGNORECASE)
        pat_subject = re.compile(r"验证码|verification|verify|otp|code", re.IGNORECASE)
        check_count = 0
        seen_ids = set()

        log(
            f"   📧 Monitoring Gmail for new OTP email (ignoring {len(self._baseline_ids)} old emails)..."
        )

        while time.time() - start < timeout:
            check_count += 1
            try:
                messages = await self.get_messages()
                for msg in messages:
                    msg_id = msg.get("id", "")

                    # Skip emails that existed before we started waiting
                    if msg_id in self._baseline_ids:
                        continue

                    # Skip emails we already checked
                    if msg_id in seen_ids:
                        continue

                    subject = msg.get("subject", "") or ""
                    body = msg.get("body", "") or ""
                    from_addr = msg.get("from_address", "") or ""

                    log_debug(f"New email: from={from_addr[:40]}, subject={subject[:60]}")

                    # ── Filter: only process emails that look like PatewayAI OTP ──
                    # Accept if sender contains "pateway" OR subject contains OTP keywords
                    is_otp_email = bool(pat_sender.search(from_addr) or pat_subject.search(subject))
                    if not is_otp_email:
                        log_debug(
                            f"Skipping non-OTP email: from={from_addr[:40]}, subject={subject[:60]}"
                        )
                        seen_ids.add(msg_id)
                        continue

                    # ── Extraction (subject first, then body — consistent order) ──
                    # Strategy 1: "VERIFICATION CODE" followed by 6 digits (newline-aware)
                    for text in [subject, body]:
                        if not isinstance(text, str) or not text:
                            continue
                        match = pat_verify_code.search(text)
                        if match:
                            elapsed = int(time.time() - start)
                            log_ok(
                                f"OTP found via VERIFICATION CODE pattern after {elapsed}s: {match.group(1)}"
                            )
                            return match.group(1)

                    # Strategy 1b: HTML class "otp-code" (raw HTML may survive in non-multipart)
                    for text in [subject, body]:
                        if not isinstance(text, str) or not text:
                            continue
                        match = pat_otp_class.search(text)
                        if match:
                            elapsed = int(time.time() - start)
                            log_ok(
                                f"OTP found via otp-code class pattern after {elapsed}s: {match.group(1)}"
                            )
                            return match.group(1)

                    # Strategy 2: Chinese 验证码 followed by 6 digits
                    for text in [subject, body]:
                        if not isinstance(text, str) or not text:
                            continue
                        match = pat_cn_code.search(text)
                        if match:
                            elapsed = int(time.time() - start)
                            log_ok(
                                f"OTP found via 验证码 pattern after {elapsed}s: {match.group(1)}"
                            )
                            return match.group(1)

                    # Strategy 3: Generic 6-digit fallback (only on confirmed OTP emails)
                    # After HTML cleaning, the FIRST 6-digit number should be the OTP
                    # (CSS numbers are stripped, so this is safe now)
                    pattern = re.compile(r"\b(\d{6})\b")
                    for text in [subject, body]:
                        if not isinstance(text, str) or not text:
                            continue
                        match = pattern.search(text)
                        if match:
                            elapsed = int(time.time() - start)
                            log_ok(f"OTP found (fallback) after {elapsed}s: {match.group(1)}")
                            return match.group(1)

                    seen_ids.add(msg_id)

                if check_count % 5 == 0:
                    elapsed = int(time.time() - start)
                    new_count = len(messages) - len(self._baseline_ids)
                    log_debug(
                        f"OTP check #{check_count} ({elapsed}s): {new_count} new emails, no OTP yet"
                    )

            except Exception as e:
                log_debug(f"Gmail OTP poll error: {e}")

            await asyncio.sleep(poll_interval)

        log_err(f"OTP not received within {timeout}s ({check_count} checks)")
        return None

    async def close(self):
        """Close IMAP connection."""
        if self._conn:
            try:
                self._conn.close()
                self._conn.logout()
            except Exception:
                pass
            self._conn = None

    @property
    def provider(self) -> str:
        """Provider name."""
        return "gmail-imap"

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
from typing import Optional

from ..utils.logger import log, log_ok, log_err, log_warn, log_debug


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
        self._conn: Optional[imaplib.IMAP4_SSL] = None
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
        log_ok(f"Gmail IMAP: connected to {self.email_address} ({len(self._baseline_ids)} existing emails)")
        return self.email_address

    async def get_messages(self) -> list[dict]:
        """Get recent messages from inbox.

        Returns:
            List of message dicts with from_address, subject, body.
        """
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._fetch_recent_messages)

    def _fetch_recent_messages(self) -> list[dict]:
        """Fetch recent unread messages from Gmail."""
        try:
            conn = self._connect()
            conn.select("INBOX")

            # Search for recent emails (last 5 minutes)
            # IMAP date format: DD-Mon-YYYY
            import datetime
            today = datetime.datetime.now().strftime("%d-%b-%Y")

            # Search for today's emails
            status, data = conn.search(None, f'(SINCE {today})')
            if status != "OK":
                return []

            mail_ids = data[0].split()
            # Get last 10 emails max
            mail_ids = mail_ids[-10:] if len(mail_ids) > 10 else mail_ids

            messages = []
            for mail_id in reversed(mail_ids):  # Newest first
                try:
                    status, msg_data = conn.fetch(mail_id, "(RFC822)")
                    if status != "OK":
                        continue

                    raw_email = msg_data[0][1]
                    msg = email.message_from_bytes(raw_email)

                    # Decode subject
                    subject = self._decode_header(msg.get("Subject", ""))
                    from_addr = self._decode_header(msg.get("From", ""))

                    # Extract body
                    body = self._extract_body(msg)

                    messages.append({
                        "id": mail_id.decode(),
                        "from_address": from_addr,
                        "subject": subject,
                        "body": body,
                        "received_at": msg.get("Date", ""),
                    })
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
                                # Strip HTML tags
                                body = re.sub(r"<[^>]+>", " ", html).strip()
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

    async def wait_for_otp(
        self,
        timeout: int = 120,
        poll_interval: float = 3.0,
        otp_pattern: str = r"\b(\d{6})\b",
    ) -> Optional[str]:
        """Poll Gmail inbox until OTP email arrives.

        Only checks emails that arrived AFTER create() was called
        (using baseline message IDs).

        Args:
            timeout: Max seconds to wait.
            poll_interval: Seconds between polls.
            otp_pattern: Regex pattern to match OTP.

        Returns:
            OTP string if found, None if timeout.
        """
        start = time.time()
        pattern = re.compile(otp_pattern)
        check_count = 0
        seen_ids = set()

        log(f"   📧 Monitoring Gmail for new OTP email (ignoring {len(self._baseline_ids)} old emails)...")

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

                    subject = msg.get("subject", "")
                    body = msg.get("body", "")
                    from_addr = msg.get("from_address", "")

                    log_debug(f"New email: from={from_addr[:40]}, subject={subject[:60]}")

                    # Search for OTP in subject first, then body
                    for text in [subject, body]:
                        if not isinstance(text, str) or not text:
                            continue
                        match = pattern.search(text)
                        if match:
                            elapsed = int(time.time() - start)
                            log_ok(f"OTP found after {elapsed}s ({check_count} checks): {match.group(1)}")
                            log_debug(f"  From: {from_addr}, Subject: {subject[:60]}")
                            return match.group(1)

                    seen_ids.add(msg_id)

                if check_count % 5 == 0:
                    elapsed = int(time.time() - start)
                    new_count = len(messages) - len(self._baseline_ids)
                    log_debug(f"OTP check #{check_count} ({elapsed}s): {new_count} new emails, no OTP yet")

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

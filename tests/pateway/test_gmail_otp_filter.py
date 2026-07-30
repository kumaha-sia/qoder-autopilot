"""Test Gmail IMAP OTP filtering — ensures only PatewayAI emails are processed.

Regression tests for bug where promo/bank emails with 6-digit numbers
were incorrectly extracted as OTP.
"""

import asyncio
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src"))

from pateway_autopilot.infra.gmail_imap import GmailImapClient


def _make_msg(msg_id, from_addr, subject, body):
    return {
        "id": msg_id,
        "uid": msg_id,
        "from_address": from_addr,
        "subject": subject,
        "body": body,
        "received_at": "",
    }


async def _run_otp_test(messages, baseline_ids=None):
    client = GmailImapClient("test@gmail.com", "dummy password")
    client._baseline_ids = baseline_ids or set()
    client.get_messages = AsyncMock(return_value=messages)
    return await client.wait_for_otp(timeout=1, poll_interval=0.1)


def test_pateway_verification_code_body():
    """PatewayAI email with 'VERIFICATION CODE\\n330605' in body → should extract 330605."""
    msg = _make_msg("m1", "noreply@pateway.ai", "【验证码】欢迎注册", "VERIFICATION CODE\n330605")
    otp = asyncio.run(_run_otp_test([msg]))
    assert otp == "330605", f"Expected 330605, got {otp}"


def test_pateway_verification_code_subject():
    """PatewayAI email with code in subject → should extract."""
    msg = _make_msg("m1", "noreply@pateway.ai", "VERIFICATION CODE 123456", "Please use this code")
    otp = asyncio.run(_run_otp_test([msg]))
    assert otp == "123456", f"Expected 123456, got {otp}"


def test_chinese_yanzhengma():
    """Chinese 验证码 pattern."""
    msg = _make_msg("m1", "noreply@pateway.ai", "【验证码】欢迎注册", "您的验证码是: 654321")
    otp = asyncio.run(_run_otp_test([msg]))
    assert otp == "654321", f"Expected 654321, got {otp}"


def test_promo_email_ignored():
    """Promo email with 6-digit number should NOT be extracted as OTP."""
    msg = _make_msg(
        "m1",
        "promo@tokopedia.com",
        "Diskon 50% untuk pembelian 250000 ke atas",
        "Belanja sekarang dan dapatkan cashback 150000!",
    )
    otp = asyncio.run(_run_otp_test([msg]))
    assert otp is None, f"Promo email should be ignored, but got OTP: {otp}"


def test_bank_email_ignored():
    """Bank notification with 6-digit number should NOT be extracted as OTP."""
    msg = _make_msg(
        "m1",
        "noreply@bca.co.id",
        "Notifikasi Transaksi",
        "Transfer 150000 berhasil pada tanggal hari ini. Ref: 987654",
    )
    otp = asyncio.run(_run_otp_test([msg]))
    assert otp is None, f"Bank email should be ignored, but got OTP: {otp}"


def test_baseline_emails_ignored():
    """Emails that existed before create() should be skipped."""
    old_msg = _make_msg("old1", "noreply@pateway.ai", "VERIFICATION CODE 111111", "")
    new_msg = _make_msg("new1", "noreply@pateway.ai", "VERIFICATION CODE 222222", "")
    otp = asyncio.run(_run_otp_test([old_msg, new_msg], baseline_ids={"old1"}))
    assert otp == "222222", f"Should pick new email's OTP 222222, got {otp}"


def test_non_otp_email_with_pateway_sender():
    """Email from PatewayAI but without OTP keywords in subject — should still try body."""
    msg = _make_msg("m1", "noreply@pateway.ai", "Welcome to PatewayAI", "Your code is 998877. Valid for 10 minutes.")
    otp = asyncio.run(_run_otp_test([msg]))
    assert otp == "998877", f"Should extract 998877 from PatewayAI email, got {otp}"


def test_subject_with_verification_keyword_from_non_pateway():
    """Email from non-Pateway with 'verification' in subject → should be processed (subject filter)."""
    msg = _make_msg(
        "m1",
        "security@example.com",
        "Your verification code",
        "Your verification code is 445566",
    )
    otp = asyncio.run(_run_otp_test([msg]))
    assert otp == "445566", f"Should extract 445566, got {otp}"


def test_first_otp_wins_when_multiple_emails():
    """When multiple new OTP emails arrive, the first match wins."""
    msg1 = _make_msg("m1", "noreply@pateway.ai", "VERIFICATION CODE 111111", "")
    msg2 = _make_msg("m2", "noreply@pateway.ai", "VERIFICATION CODE 222222", "")
    otp = asyncio.run(_run_otp_test([msg1, msg2]))
    assert otp == "111111", f"Should get first OTP 111111, got {otp}"


def test_real_pateway_email_format():
    """Test with the EXACT real email format from PatewayAI.

    From actual email:
        From: pateway.ai <contact@mail.pateway.ai>
        Subject: (likely 【验证码】欢迎注册 or similar)
        Body:
            ACCOUNT
            欢迎注册
            您的注册验证码如下，请在 10 分钟内完成验证。
            VERIFICATION CODE
            640065
            验证码仅用于本次注册操作，请勿泄露给他人。
            如果这不是您的操作，请忽略此邮件。
    """
    real_body = (
        "ACCOUNT\n"
        "欢迎注册\n"
        "\n"
        "您的注册验证码如下，请在 10 分钟内完成验证。\n"
        "VERIFICATION CODE\n"
        "640065\n"
        "\n"
        "验证码仅用于本次注册操作，请勿泄露给他人。\n"
        "\n"
        "如果这不是您的操作，请忽略此邮件。"
    )
    msg = _make_msg("m1", "contact@mail.pateway.ai", "【验证码】欢迎注册", real_body)
    otp = asyncio.run(_run_otp_test([msg]))
    assert otp == "640065", f"Expected 640065 from real PatewayAI email, got {otp}"


def test_real_pateway_email_with_other_emails():
    """Real scenario: PatewayAI OTP arrives alongside promo/bank emails.

    This is the exact bug that caused wrong OTP input — promo emails with
    6-digit numbers were extracted before the PatewayAI email was found.
    """
    promo = _make_msg(
        "promo1",
        "promo@tokopedia.com",
        "Flash Sale! Diskon 50%",
        "Belanja minimum 250000 dan dapatkan cashback 150000. Promo terbatas 100000 orang!",
    )
    bank = _make_msg(
        "bank1",
        "notification@bca.co.id",
        "Mutasi Rekening",
        "Transfer masuk Rp 1.250.000 dari 987654. Saldo: 5.430.000",
    )
    real_body = (
        "ACCOUNT\n"
        "欢迎注册\n"
        "\n"
        "您的注册验证码如下，请在 10 分钟内完成验证。\n"
        "VERIFICATION CODE\n"
        "640065\n"
        "\n"
        "验证码仅用于本次注册操作，请勿泄露给他人。\n"
        "\n"
        "如果这不是您的操作，请忽略此邮件。"
    )
    pateway = _make_msg("pateway1", "contact@mail.pateway.ai", "【验证码】欢迎注册", real_body)

    # Promo email comes first (newer) — should be skipped
    # PatewayAI email comes second — should be extracted
    otp = asyncio.run(_run_otp_test([promo, bank, pateway]))
    assert otp == "640065", f"Expected 640065 from PatewayAI email, got {otp}"


def test_real_pateway_sender_filter():
    """Verify 'contact@mail.pateway.ai' sender matches the pateway filter."""
    msg = _make_msg("m1", "contact@mail.pateway.ai", "ACCOUNT", "VERIFICATION CODE\n640065")
    otp = asyncio.run(_run_otp_test([msg]))
    assert otp == "640065", f"Sender 'contact@mail.pateway.ai' should match pateway filter, got {otp}"


if __name__ == "__main__":
    tests = [
        test_pateway_verification_code_body,
        test_pateway_verification_code_subject,
        test_chinese_yanzhengma,
        test_promo_email_ignored,
        test_bank_email_ignored,
        test_baseline_emails_ignored,
        test_non_otp_email_with_pateway_sender,
        test_subject_with_verification_keyword_from_non_pateway,
        test_first_otp_wins_when_multiple_emails,
        test_real_pateway_email_format,
        test_real_pateway_email_with_other_emails,
        test_real_pateway_sender_filter,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"  ❌ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"  💥 {t.__name__}: {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{'='*60}")
    print(f"Results: {passed} passed, {failed} failed, {len(tests)} total")
    sys.exit(1 if failed else 0)

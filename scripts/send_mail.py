"""发信：一人一封、Date/Message-ID、465 SSL 失败回退 587、3 次重试。

用法:
  python scripts/send_mail.py --subject "..." --html output/card-2026-11-22.html
  python scripts/send_mail.py --subject "..." --html ... --dry-run
  python scripts/send_mail.py --subject "..." --html ... --to a@b.com,c@d.com
"""
from __future__ import annotations

import argparse
import hashlib
import re
import smtplib
import ssl
import sys
import time
from email.message import EmailMessage
from email.utils import formatdate
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_env, log  # noqa: E402


def html_to_text(markup: str) -> str:
    text = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", " ", markup)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|tr|li|h[1-6])>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip()


def build_message(cfg: dict, subject: str, html: str, to_addr: str) -> EmailMessage:
    sender = cfg.get("MAIL_FROM") or cfg["MAIL_USER"]
    from_name = cfg.get("MAIL_FROM_NAME") or "美妆情报"
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f'"{from_name}" <{sender}>'
    msg["To"] = to_addr
    msg["Date"] = formatdate(localtime=True)
    token = hashlib.sha1(f"{subject}|{to_addr}".encode("utf-8")).hexdigest()[:12]
    msg["Message-ID"] = f"<beauty-brief-{token}@beautydaily.local>"
    msg.set_content(html_to_text(html))
    msg.add_alternative(html, subtype="html")
    return msg


def deliver(cfg: dict, msg: EmailMessage, dry_run: bool) -> None:
    if dry_run:
        print(f"[dry-run] 将发给 {msg['To']}｜主题：{msg['Subject']}")
        return
    host = cfg["MAIL_SMTP_HOST"]
    port_ssl = int(cfg.get("MAIL_SMTP_PORT", 465) or 465)
    last: Exception | None = None
    for attempt in range(1, 4):
        for mode, port in (("ssl", port_ssl), ("starttls", 587)):
            try:
                ctx = ssl.create_default_context()
                if mode == "ssl":
                    with smtplib.SMTP_SSL(host, port, context=ctx, timeout=30) as server:
                        server.login(cfg["MAIL_USER"], cfg["MAIL_PASS"])
                        server.send_message(msg)
                else:
                    with smtplib.SMTP(host, port, timeout=30) as server:
                        server.starttls(context=ctx)
                        server.login(cfg["MAIL_USER"], cfg["MAIL_PASS"])
                        server.send_message(msg)
                log(f"发送成功（{mode}:{port}）→ {msg['To']}")
                return
            except (smtplib.SMTPException, OSError) as exc:
                last = exc
                log(f"  {mode}:{port} 失败：{type(exc).__name__}: {exc}")
        time.sleep(2 ** attempt)
    raise RuntimeError(f"3 次重试均失败：{last}")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--subject", required=True)
    ap.add_argument("--html", required=True)
    ap.add_argument("--to", default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = load_env()
    html_path = Path(args.html)
    if not html_path.is_absolute():
        html_path = ROOT / html_path
    html = html_path.read_text(encoding="utf-8")
    recipients = [x.strip() for x in (args.to or cfg.get("MAIL_TO", "")).split(",") if x.strip()]
    if not recipients:
        print("没有收件人：检查 .env 的 MAIL_TO")
        return 1

    failed = []
    for addr in recipients:
        msg = build_message(cfg, args.subject, html, addr)
        try:
            deliver(cfg, msg, args.dry_run)
        except Exception as exc:  # noqa: BLE001
            failed.append(addr)
            log(f"发送失败 → {addr}：{type(exc).__name__}: {exc}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())

"""流水线失败时发一封提醒（CI 里用），不做任何内容生成本身的事。"""
from __future__ import annotations

import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> dict:
    cfg = {}
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip()
    for k in ("MAIL_SMTP_HOST", "MAIL_SMTP_PORT", "MAIL_USER", "MAIL_PASS",
              "MAIL_FROM", "MAIL_FROM_NAME", "MAIL_TO"):
        if os.environ.get(k):
            cfg[k] = os.environ[k]
    return cfg


def main() -> int:
    cfg = load_env()
    if not cfg.get("MAIL_USER"):
        print("没有邮件配置，跳过失败提醒")
        return 0
    run_url = (f"{os.environ.get('GITHUB_SERVER_URL', '')}/"
               f"{os.environ.get('GITHUB_REPOSITORY', '')}/actions/runs/"
               f"{os.environ.get('GITHUB_RUN_ID', '')}")
    msg = EmailMessage()
    msg["Subject"] = "[美妆情报] 今天没发成"
    msg["From"] = cfg.get("MAIL_FROM") or cfg["MAIL_USER"]
    msg["To"] = (cfg.get("MAIL_TO") or cfg["MAIL_USER"]).split(",")[0].strip()
    msg.set_content(f"今天的流水线失败了，没有发出简报。\n\n看日志：{run_url}\n")
    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(cfg["MAIL_SMTP_HOST"], int(cfg.get("MAIL_SMTP_PORT") or 465),
                          context=ctx, timeout=30) as s:
        s.login(cfg["MAIL_USER"], cfg["MAIL_PASS"])
        s.send_message(msg)
    print("失败提醒已发送")
    return 0


if __name__ == "__main__":
    sys.exit(main())

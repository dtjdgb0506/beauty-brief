"""公共工具：抓取、解码、日期、日志、配置。"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")
HEADERS = {
    "User-Agent": UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.6",
}


# ---------- 网络 ----------
def decode_bytes(raw: bytes, content_type: str = "", forced: str | None = None) -> str:
    """按 头 -> meta -> utf-8 -> gb18030 的顺序解码。中文老站大量 gb2312。"""
    if forced:
        return raw.decode(forced, "replace")
    m = re.search(r"charset=([\w-]+)", content_type or "", re.I)
    candidates = [m.group(1)] if m else []
    head = raw[:3000].decode("ascii", "ignore").lower()
    m2 = re.search(r'charset=["\']?([\w-]+)', head)
    if m2:
        candidates.append(m2.group(1))
    candidates += ["utf-8", "gb18030"]
    for enc in candidates:
        enc = {"gb2312": "gb18030", "gbk": "gb18030", "x-gbk": "gb18030"}.get(enc.lower(), enc)
        try:
            return raw.decode(enc)
        except (LookupError, UnicodeDecodeError):
            continue
    return raw.decode("utf-8", "replace")


def fetch(url: str, timeout: int = 15, retries: int = 2, forced_encoding: str | None = None) -> str:
    """抓页面。若配置了 BEAUTY_PROXY_PREFIX，命中的域名会走中转（云端补国内源用）。

    例：BEAUTY_PROXY_PREFIX="https://your-worker.workers.dev/?url={}"
    """
    prefix = os.environ.get("BEAUTY_PROXY_PREFIX", "").strip()
    proxy_hosts = [h.strip() for h in os.environ.get(
        "BEAUTY_PROXY_HOSTS", "winshang.com,linkshop.com").split(",") if h.strip()]
    if prefix and any(h in url for h in proxy_hosts):
        url = prefix.replace("{}", urllib.parse.quote(url, safe=""))
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read()
                if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                    raw = gzip.decompress(raw)
                return decode_bytes(raw, resp.headers.get("Content-Type", ""), forced_encoding)
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1 + attempt)
    raise ConnectionError(f"{url} 抓取失败: {last}")


# ---------- 文本 ----------
def clean_text(s: str) -> str:
    s = unescape(s or "")
    s = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", s)
    s = re.sub(r"<[^>]+>", " ", s)
    s = re.sub(r"&nbsp;", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def clip(s: str, n: int = 120) -> str:
    s = clean_text(s)
    return s if len(s) <= n else s[: n - 1].rstrip("，,、 ") + "…"


def fingerprint(title: str, url: str) -> str:
    return hashlib.sha1((clean_text(title) + "|" + url).encode("utf-8")).hexdigest()[:12]


def title_fp(title: str) -> str:
    """只按标题算指纹，用于跨日去重（同一件事不同源、URL 不同，标题相近）。"""
    t = re.sub(r"[^\w\u4e00-\u9fff]+", "", clean_text(title)).lower()
    return hashlib.sha1(t.encode("utf-8")).hexdigest()[:16]


# ---------- 日期 ----------
DATE_PATTERNS = [
    re.compile(r"(20\d{2})[-/年](\d{1,2})[-/月](\d{1,2})"),
    re.compile(r"(20\d{2})(\d{2})(\d{2})"),
]


def parse_date(text: str, default: date | None = None) -> str:
    """从任意文本里挖出第一个日期，返回 YYYY-MM-DD；挖不到用默认值。"""
    text = text or ""
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            y, mo, d = (int(x) for x in m.groups())
            if 1 <= mo <= 12 and 1 <= d <= 31:
                return f"{y:04d}-{mo:02d}-{d:02d}"
    rel = re.search(r"(\d+)\s*(分钟|小时|天)前", text)
    if rel:
        n = int(rel.group(1))
        delta = {"分钟": timedelta(minutes=n), "小时": timedelta(hours=n), "天": timedelta(days=n)}[rel.group(2)]
        return (datetime.now() - delta).date().isoformat()
    if "刚刚" in text:
        return (default or date.today()).isoformat()
    return (default or date.today()).isoformat()


def parse_rfc822(text: str) -> str:
    try:
        return parsedate_to_datetime(text).date().isoformat()
    except Exception:  # noqa: BLE001
        return parse_date(text)


def days_ago(day: str) -> int:
    try:
        return (date.today() - date.fromisoformat(day)).days
    except ValueError:
        return 99


# ---------- 配置 ----------
def load_toml(path: Path) -> dict:
    import tomllib
    with path.open("rb") as f:
        return tomllib.load(f)


def load_profile() -> dict:
    return load_toml(ROOT / "config" / "profile.toml")


def load_lexicon() -> dict:
    return load_toml(ROOT / "config" / "lexicon.toml")


def load_sources() -> list[dict]:
    return load_toml(ROOT / "config" / "sources.toml").get("source", [])


def load_env() -> dict:
    cfg = {}
    p = ROOT / ".env"
    if not p.exists():
        return cfg
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        cfg[k.strip()] = v.strip()
    return cfg


# ---------- 落盘 ----------
def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def log(msg: str, path: Path | None = None) -> None:
    line = f"[{datetime.now():%H:%M:%S}] {msg}"
    print(line)
    if path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

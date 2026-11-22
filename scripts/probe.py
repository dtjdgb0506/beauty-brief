"""一次性结构探针：抓取每个源，打印标题/条目/日期样本，用于确认解析规则。

用法: python scripts/probe.py [源名...]
"""
from __future__ import annotations

import gzip
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def get(url: str, timeout: int = 15) -> tuple[str, int]:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "zh-CN,zh;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding") == "gzip":
            raw = gzip.decompress(raw)
        ct = resp.headers.get("Content-Type", "")
        m = re.search(r"charset=([\w-]+)", ct, re.I)
        enc = m.group(1) if m else "utf-8"
        try:
            return raw.decode(enc, "replace"), resp.status
        except LookupError:
            return raw.decode("utf-8", "replace"), resp.status


def show(name: str, url: str) -> None:
    print(f"\n=== {name} ===")
    try:
        html, code = get(url)
    except Exception as exc:  # noqa: BLE001
        print("  ERR", type(exc).__name__, exc)
        return
    title = re.search(r"<title[^>]*>(.*?)</title>", html, re.S | re.I)
    print(f"  {code} len={len(html)} title={(title.group(1).strip()[:60] if title else '')!r}")
    for pat, label in [
        (r'application/ld\+json', "json-ld"),
        (r'/media/\d+/?', "media-id"),
        (r'/news/view/\d+\.html', "jm-view"),
        (r'Details\.aspx\?id=\d+', "qy-detail"),
        (r'article-item|item-title', "jm-class"),
        (r'class="cov-card', "hz-card"),
        (r'<h4>', "h4"),
        (r'win-new-list1|win-new-tab', "ws-class"),
        (r'news/list-7001|list-7001', "ws-url"),
        (r'class="time"|time_overflow', "ls-time"),
        (r'/articles/\d+|/flashes/item/\d+', "mzt"),
        (r'<item>|<entry>', "rss-item"),
        (r'/c/20\d\d-\d\d-\d\d/\d+\.shtml', "cnpharm"),
        (r'sogou_vr_11002601|txt-box', "sogou"),
    ]:
        n = len(re.findall(pat, html))
        if n:
            print(f"    {label}: {n}")
    # 日期样本
    dates = re.findall(r"20\d{2}[-/年]\d{1,2}[-/月]\d{1,2}", html)[:3]
    if dates:
        print("    dates:", dates)
    if "ld+json" in html:
        m = re.search(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', html, re.S)
        if m:
            print("    jsonld sample:", m.group(1).strip()[:300])
    # 标题样本
    for m in list(re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>\s*([^<]{8,60})\s*</a>', html))[:4]:
        print(f"    a: {m.group(2).strip()[:40]!r} -> {m.group(1)[:80]}")


SOURCES = {
    "pinguan": "https://www.pinguan.com/media/",
    "jumeili": "https://www.jumeili.cn/industry/1.html",
    "qingyan": "https://www.iqingyan.cn/index.aspx",
    "mzt": "http://www.mztoutiao.com/news/all/",
    "winshang": "http://news.winshang.com/list-7001.html",
    "linkshop": "http://www.linkshop.com/news/pp/",
    "cosmeticsbusiness": "https://cosmeticsbusiness.com/rss",
    "wwd": "https://wwd.com/beauty-industry-news/feed/",
    "gci": "https://www.gcimagazine.com/feed",
    "mintel": "https://www.mintel.com/feed/",
    "36kr": "https://www.36kr.com/feed",
    "sogou": "https://weixin.sogou.com/weixin?type=2&query=%E6%8A%A4%E8%82%A4",
    "cnpharm": "https://www.cnpharm.com/hzp/",
}

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    names = sys.argv[1:] or list(SOURCES)
    for n in names:
        if n in SOURCES:
            show(n, SOURCES[n])

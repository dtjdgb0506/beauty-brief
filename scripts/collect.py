"""多类型采集：RSS + 中文垂类 HTML/JSON 列表 + 公众号弱信号。

用法:
  python scripts/collect.py            # 抓全部源 → output/candidates/<日期>.json
  python scripts/collect.py --only 品观网 青眼
  python scripts/collect.py --quiet
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ROOT, clean_text, clip, days_ago, fetch, fingerprint, load_profile,
    load_sources, log, parse_date, parse_rfc822, write_json,
)

ABS = {
    "pinguan": "https://www.pinguan.com",
    "jumeili": "https://www.jumeili.cn",
    "qingyan": "https://www.iqingyan.cn",
    "mzt": "http://www.mztoutiao.com",
    "winshang": "http://news.winshang.com",
    "linkshop": "http://www.linkshop.com",
    "cnpharm": "https://www.cnpharm.com",
    "sogou": "https://weixin.sogou.com",
}


def absolute(base: str, url: str) -> str:
    if not url:
        return ""
    if url.startswith("//"):
        return "https:" + url
    if url.startswith("/"):
        return base.rstrip("/") + url
    return url


def mk(source: dict, title: str, url: str, published: str, summary: str = "", tag: str = "") -> dict | None:
    title = clean_text(title)
    if len(title) < 6:
        return None
    return {
        "id": fingerprint(title, url),
        "title": title,
        "url": url,
        "summary": clip(summary, 200),
        "published": published,
        "tag": clean_text(tag),
        "source": source["name"],
        "tier": source.get("tier", "trade"),
        "section_hint": source.get("section", ""),
        "type": source.get("type", ""),
    }


# ---------------- 各站解析器 ----------------
def parse_rss(source: dict, html: str) -> list[dict]:
    # 有些站输出未转义的 &nbsp; / 裸 &，ElementTree 会整篇解析失败，先救一把
    safe = re.sub(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)", "&amp;", html)
    safe = safe.replace("&nbsp;", " ")
    try:
        root = ET.fromstring(safe)
    except ET.ParseError:
        return []
    out = []
    for node in root.iter():
        if node.tag.split("}")[-1] not in ("item", "entry"):
            continue
        title = link = pub = summary = ""
        for child in node:
            name = child.tag.split("}")[-1]
            if name == "title" and not title:
                title = child.text or ""
            elif name == "link" and not link:
                link = (child.get("href") or child.text or "").strip()
            elif name in ("pubDate", "published", "updated") and not pub:
                pub = child.text or ""
            elif name in ("description", "summary", "content") and not summary:
                summary = child.text or ""
            elif name == "link" and child.get("href"):
                link = child.get("href")
        if not title or not link:
            continue
        published = parse_rfc822(pub) if pub else date.today().isoformat()
        item = mk(source, title, link, published, summary)
        if item:
            out.append(item)
    return out


def parse_pinguan(source: dict, html: str) -> list[dict]:
    out = []
    for chunk in html.split('<div class="cov-card"')[1:]:
        url = re.search(r'href="(/media/\d+/)"', chunk)
        title = re.search(r"<h4>(.*?)</h4>", chunk, re.S)
        meta = re.search(r'<div class="meta"><span>(20\d\d-\d\d-\d\d)</span>.*?<span>([^<]+)</span>', chunk, re.S)
        if not (url and title):
            continue
        item = mk(source, title.group(1), absolute(ABS["pinguan"], url.group(1)),
                  meta.group(1) if meta else date.today().isoformat(),
                  tag=meta.group(2) if meta else "")
        if item:
            out.append(item)
    return out


def parse_jumeili(source: dict, html: str) -> list[dict]:
    out = []
    for chunk in html.split('<article class="article-item">')[1:]:
        url = re.search(r'href="(/news/view/\d+\.html)"', chunk)
        title = re.search(r'class="item-title[^"]*"[^>]*>(.*?)</a>', chunk, re.S)
        excerpt = re.search(r'class="item-excerpt">(.*?)</p>', chunk, re.S)
        dtime = re.search(r'class="dataTime">(.*?)</span>', chunk, re.S)
        if not (url and title):
            continue
        item = mk(source, title.group(1), absolute(ABS["jumeili"], url.group(1)),
                  parse_date(dtime.group(1) if dtime else ""),
                  summary=excerpt.group(1) if excerpt else "")
        if item:
            out.append(item)
    return out


def parse_qingyan(source: dict, html: str) -> list[dict]:
    out = []
    pat = re.compile(r'Details\.aspx\?id=(\d+)&type=\d+"><li>.*?<p>(.*?)</p>\s*<span>\s*([^<]+)</span>', re.S)
    for m in pat.finditer(html):
        item = mk(source, m.group(2), f"{ABS['qingyan']}/Details.aspx?id={m.group(1)}&type=1",
                  parse_date(m.group(3)))
        if item:
            out.append(item)
    return out


def parse_mzt(source: dict, html: str) -> list[dict]:
    """两种页面：文章列表（article-library-card）+ 快讯流（flash-full）。"""
    out = []
    for chunk in html.split('<article class="article-library-card"')[1:]:
        url = re.search(r'href="(/(?:articles|flashes/item)/\d+/?)"', chunk)
        title = re.search(r"<h2>(.*?)</h2>", chunk, re.S)
        excerpt = re.search(r"<p>(.*?)</p>", chunk, re.S)
        tm = re.search(r"<time>(.*?)</time>", chunk, re.S)
        if not (url and title):
            continue
        item = mk(source, title.group(1), absolute(ABS["mzt"], url.group(1)),
                  parse_date(tm.group(1) if tm else ""),
                  summary=excerpt.group(1) if excerpt else "")
        if item:
            out.append(item)
    for chunk in html.split('<article class="flash-full"')[1:]:
        title = re.search(r"<h2>(.*?)</h2>", chunk, re.S)
        excerpt = re.search(r"<p>(.*?)</p>", chunk, re.S)
        fid = re.search(r'data-flash-id="(\d+)"', chunk)
        tm = re.search(r'<time datetime="([\d-]+)"', chunk) or re.search(r"<time[^>]*>([^<]*)</time>", chunk)
        if not (title and fid):
            continue
        item = mk(source, title.group(1), f"{ABS['mzt']}/flashes/item/{fid.group(1)}/",
                  parse_date(tm.group(1) if tm else ""),
                  summary=excerpt.group(1) if excerpt else "")
        if item:
            out.append(item)
    return out


def parse_winshang(source: dict, html: str) -> list[dict]:
    out = []
    pat = re.compile(r'<h3>\s*<a href="([^"]+)"[^>]*>(.*?)</a>\s*</h3>', re.S)
    for m in pat.finditer(html):
        url, title = m.group(1), m.group(2)
        back = html[max(0, m.start() - 600): m.start()]
        tag = re.findall(r'<span class="tag">([^<]+)</span>', back)
        forward = html[m.end(): m.end() + 600]
        info = re.search(r'<p class="win-new-info">(.*?)</p>', forward, re.S)
        day = re.search(r"(20\d\d年\d{1,2}月\d{1,2}日)", forward) or \
              re.search(r"(20\d\d年\d{1,2}月\d{1,2}日)", back)
        item = mk(source, title, url,
                  parse_date(day.group(1)) if day else date.today().isoformat(),
                  summary=info.group(1) if info else "",
                  tag=tag[-1] if tag else "")
        if item:
            out.append(item)
    return out


def parse_linkshop(source: dict, html: str) -> list[dict]:
    out = []
    pat = re.compile(r'<h2>\s*<a href="(https?://www\.linkshop\.com/news/\d+\.shtml|/news/\d+\.shtml)"[^>]*>(.*?)</a>', re.S)
    for m in pat.finditer(html):
        window = html[m.end(): m.end() + 900]
        excerpt = re.search(r'<p class="text_overflow">(.*?)</p>', window, re.S)
        tm = re.search(r'<span class="time">\s*([\d-]{8,10}(?:\s+[\d:]+)?)\s*</span>', window)
        label = re.search(r'class="label_border">([^<]+)</a>', window)
        item = mk(source, m.group(2), absolute(ABS["linkshop"], m.group(1)),
                  parse_date(tm.group(1)) if tm else date.today().isoformat(),
                  summary=excerpt.group(1) if excerpt else "",
                  tag=label.group(1) if label else "")
        if item:
            out.append(item)
    return out


def parse_cnpharm(source: dict, html: str) -> list[dict]:
    out = []
    pat = re.compile(r'href="(/c/(20\d\d-\d\d-\d\d)/\d+\.shtml)"[^>]*>\s*([^<]{6,90}?)\s*</a>', re.S)
    for m in pat.finditer(html):
        item = mk(source, m.group(3), absolute(ABS["cnpharm"], m.group(1)), m.group(2))
        if item:
            out.append(item)
    return out


def parse_sogou(source: dict, html: str) -> list[dict]:
    out = []
    for chunk in html.split('<div class="txt-box"')[1:]:
        title = re.search(r"<h3>\s*<a[^>]*>(.*?)</a>", chunk, re.S)
        href = re.search(r'href="(/link\?url=[^"]+)"', chunk)
        summary = re.search(r'class="txt-info"[^>]*>(.*?)</p>', chunk, re.S)
        account = re.search(r'class="all-time-y2">([^<]+)</span>', chunk)
        tm = re.search(r"timeConvert\(['\"](\d+)['\"]\)", chunk)
        published = date.today().isoformat()
        if tm:
            published = datetime.fromtimestamp(int(tm.group(1))).date().isoformat()
        if not (title and href):
            continue
        item = mk(source, title.group(1), absolute(ABS["sogou"], href.group(1)),
                  published, summary=summary.group(1) if summary else "",
                  tag=account.group(1) if account else "")
        if item:
            out.append(item)
    return out


def parse_ebrun(source: dict, html: str) -> list[dict]:
    """亿邦动力零售频道：适合拿线下零售/门店/渠道动态。"""
    out = []
    pat = re.compile(r'href="(https://www\.ebrun\.com/\d{8}/\d+\.shtml)"[^>]*title="([^"]+)"', re.S)
    for m in pat.finditer(html):
        url, title = m.group(1), m.group(2)
        window = html[m.end(): m.end() + 1200]
        desc = re.search(r'class="liebiao-xinwen-des"[^>]*>(.*?)</p>', window, re.S)
        tm = re.search(r'class="time">\s*([\d-]{10})', window)
        item = mk(source, title, url,
                  parse_date(tm.group(1)) if tm else date.today().isoformat(),
                  summary=desc.group(1) if desc else "")
        if item:
            out.append(item)
    return out


PARSERS = {
    "rss": parse_rss, "pinguan": parse_pinguan, "jumeili": parse_jumeili,
    "qingyan": parse_qingyan, "mzt": parse_mzt, "winshang": parse_winshang,
    "linkshop": parse_linkshop, "cnpharm": parse_cnpharm, "sogou": parse_sogou,
    "ebrun": parse_ebrun,
}


def collect_one(source: dict, profile: dict) -> list[dict]:
    stype = source["type"]
    parser = PARSERS.get(stype)
    if not parser:
        raise ValueError(f"未知源类型 {stype}")
    pages = int(source.get("pages", 1) or 1)
    # 时间窗按源类型区分：中文日更源 4 天，低频的国际垂类/分析源、监管源放宽到 14 天
    tier = source.get("tier", "trade")
    fresh = 14 if tier in ("core", "analysis", "reg") else int(profile.get("delivery", {}).get("fresh_days", 4))
    items: list[dict] = []
    for page in range(1, pages + 1):
        url = source["url"]
        if page > 1:
            if stype == "pinguan":
                url = url.rstrip("/") + f"/page/{page}/"
            elif stype in ("jumeili",):
                url = re.sub(r"/1\.html$", f"/{page}.html", url)
            else:
                break
        html = fetch(url)
        items.extend(parser(source, html))
    # 时间窗（搜狗也带时间戳，按同一窗口过滤，避免旧文混进日报）
    items = [i for i in items if days_ago(i["published"]) <= fresh]
    return items


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    profile = load_profile()
    sources = load_sources()
    if args.only:
        sources = [s for s in sources if s["name"] in args.only]

    all_items: list[dict] = []
    stats = []
    for src in sources:
        try:
            items = collect_one(src, profile)
            all_items.extend(items)
            stats.append({"source": src["name"], "ok": True, "count": len(items)})
            if not args.quiet:
                log(f"  {src['name']:<22} {len(items):>3} 条")
        except Exception as exc:  # noqa: BLE001
            stats.append({"source": src["name"], "ok": False, "count": 0, "error": str(exc)[:160]})
            log(f"  {src['name']:<22} 失败: {type(exc).__name__}: {str(exc)[:80]}")

    # 去重：同 URL / 同标题
    seen_url, seen_title, unique = set(), set(), []
    for it in sorted(all_items, key=lambda x: x["published"], reverse=True):
        key_t = re.sub(r"\s+", "", it["title"])[:40]
        if it["url"] in seen_url or key_t in seen_title:
            continue
        seen_url.add(it["url"])
        seen_title.add(key_t)
        unique.append(it)

    out = Path(args.out) if args.out else ROOT / "output" / "candidates" / f"{date.today().isoformat()}.json"
    write_json(out, {"date": date.today().isoformat(), "stats": stats, "items": unique})
    ok = sum(1 for s in stats if s["ok"])
    log(f"采集完成：{ok}/{len(stats)} 源可用，{len(all_items)} 条原始 → 去重后 {len(unique)} 条")
    log(f"写入 {out}")
    return 0 if unique else 1


if __name__ == "__main__":
    sys.exit(main())

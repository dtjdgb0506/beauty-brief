"""渲染：邮件卡片 + 每件事的深度详情页 + 网页版 + 往期索引。

用法:
  python scripts/render.py                 # 读 config/brief.json
  python scripts/render.py --date 2026-11-22
"""
from __future__ import annotations

import argparse
import html
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_profile, log, read_json, write_json  # noqa: E402

ACCENT = "#b5365f"
INK = "#1a1a1a"
MUTED = "#6b7280"
LINE = "#eceff3"
BG = "#f6f7f9"
SOFT = "#fdf4f7"


def esc(s) -> str:
    return html.escape(str(s or ""), quote=True)


def chip(text: str, color: str = ACCENT, bg: str = SOFT) -> str:
    return (f'<span style="display:inline-block;padding:1px 7px;margin:0 6px 4px 0;'
            f'border-radius:3px;background:{bg};color:{color};font-size:11px;'
            f'font-weight:600;letter-spacing:.3px;">{esc(text)}</span>')


def meta_line(it: dict) -> str:
    parts = []
    if it.get("brand"):
        parts.append(chip(it["brand"]))
    move = (it.get("analysis") or {}).get("channel_move", "")
    if move:
        parts.append(chip(move, "#b45309", "#fff7ed"))
    if it.get("price"):
        parts.append(chip(it["price"], "#7c4a03", "#fdf6e3"))
    if it.get("channel"):
        parts.append(chip(it["channel"], "#1d4ed8", "#eef3ff"))
    if it.get("source"):
        parts.append(f'<span style="color:{MUTED};font-size:11px;">'
                     f'{esc(it["source"])} · {esc(it.get("published", ""))}</span>')
    return "".join(parts)


def detail_href(it: dict, n: int, date: str, web_base: str) -> str:
    """有托管地址就指详情页，没有就退回原文链接（保证点得开）。"""
    if web_base:
        return f"{web_base.rstrip('/')}/{date}/p{n}.html"
    return it.get("url", "")


def render_email(brief: dict, profile: dict) -> str:
    date = brief["date"]
    d = datetime.fromisoformat(date)
    weekday = "一二三四五六日"[d.weekday()]
    scope = brief.get("scope", {})
    items = brief.get("items", [])
    web_base = profile.get("delivery", {}).get("web_base", "") or ""

    today3 = brief.get("today3", [])
    t3 = []
    for i, t in enumerate(today3, 1):
        t3.append(
            f'<table role="presentation" width="100%" style="border-top:1px solid {LINE};"><tr>'
            f'<td width="28" valign="top" style="padding:10px 0 10px;color:{ACCENT};'
            f'font-size:17px;font-weight:700;">{i}</td>'
            f'<td valign="top" style="padding:10px 0 10px;">'
            f'<div style="font-size:15.5px;font-weight:700;color:{INK};line-height:1.5;">'
            f'{esc(t.get("headline"))}</div>'
            f'<div style="font-size:13.5px;color:#374151;line-height:1.7;margin-top:3px;">'
            f'{esc(t.get("why"))}</div></td></tr></table>'
        )

    groups: dict[str, list[tuple[int, dict]]] = {}
    for idx, it in enumerate(items, 1):
        groups.setdefault(it.get("section_label") or "其他", []).append((idx, it))

    sec_html = []
    for name, rows in groups.items():
        body = []
        for n, it in rows:
            ana = it.get("analysis", {}) or {}
            what = esc(clip_(ana.get("what", ""), 76))
            risk = esc(clip_(ana.get("risk", ""), 56))
            action = esc(clip_((ana.get("action") or [""])[0], 56))
            href = detail_href(it, n, date, web_base)
            extra = []
            if what:
                extra.append(f'<div style="margin-top:6px;font-size:13px;color:#4b5563;line-height:1.65;">'
                             f'<span style="color:#9ca3af;">发生了什么 · </span>{what}</div>')
            if risk:
                extra.append(f'<div style="margin-top:4px;font-size:13px;color:#4b5563;line-height:1.65;">'
                             f'<span style="color:{ACCENT};">最该防 · </span>{risk}</div>')
            if action:
                extra.append(f'<div style="margin-top:4px;font-size:13px;color:#4b5563;line-height:1.65;">'
                             f'<span style="color:#059669;">建议 · </span>{action}</div>')
            link = (f'<div style="margin-top:6px;"><a href="{esc(href)}" '
                    f'style="font-size:12.5px;color:{ACCENT};text-decoration:none;">'
                    f'看详细分析 →</a></div>' if href else "")
            body.append(
                f'<div style="padding:13px 0;border-top:1px solid {LINE};">'
                f'<a href="{esc(it.get("url",""))}" style="color:{INK};text-decoration:none;'
                f'font-size:14.5px;font-weight:700;line-height:1.55;">{esc(it.get("title"))}</a>'
                f'<div style="margin-top:6px;">{meta_line(it)}</div>'
                f'<div style="margin-top:6px;font-size:13.5px;color:#374151;line-height:1.7;">'
                f'<span style="color:{ACCENT};font-weight:700;">判断 · </span>{esc(it.get("so_what"))}</div>'
                f'{"".join(extra)}{link}</div>'
            )
        sec_html.append(
            f'<tr><td style="padding:22px 26px 6px;">'
            f'<div style="font-size:12px;font-weight:700;color:{ACCENT};letter-spacing:2px;">{esc(name)}</div>'
            f'<div style="font-size:11px;color:{MUTED};margin-top:2px;">{len(rows)} 条</div>'
            f'</td></tr><tr><td style="padding:0 26px 8px;">{"".join(body)}</td></tr>'
        )
        # 线下渠道速览：把没进正文的渠道动静也列出来，体现线下密度
        if name == "线下渠道" and brief.get("channel_pool"):
            scan = []
            for p in brief["channel_pool"]:
                tag = f'<span style="color:{ACCENT};font-weight:600;">{esc(p.get("tag"))}</span> · ' if p.get("tag") else ""
                scan.append(
                    f'<div style="padding:5px 0;font-size:12.5px;color:#4b5563;line-height:1.6;">'
                    f'· {tag}<a href="{esc(p.get("url",""))}" style="color:#374151;text-decoration:none;">'
                    f'{esc(p.get("title"))}</a></div>'
                )
            sec_html.append(
                f'<tr><td style="padding:2px 26px 8px;">'
                f'<div style="background:{BG};border-radius:8px;padding:10px 12px;">'
                f'<div style="font-size:11px;color:{MUTED};letter-spacing:1px;margin-bottom:4px;">'
                f'渠道速览 · 未展开的线下动静</div>{"".join(scan)}</div></td></tr>'
            )

    close = brief.get("close", "")
    close_html = (f'<tr><td style="padding:18px 26px 4px;">'
                  f'<div style="background:{SOFT};border-left:3px solid {ACCENT};padding:12px 14px;'
                  f'font-size:13.5px;line-height:1.7;color:#374151;">{esc(close)}</div></td></tr>'
                  if close else "")

    stats = brief.get("stats", {})
    foot = (f'本期 {len(items)} 条 · 来源 {len({i.get("source") for i in items})} 个 · '
            f'候选 {stats.get("candidates", "-")} 条 · 生成 {datetime.now():%H:%M}')
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(brief.get("title", "美妆情报"))} · {esc(date)}</title></head>
<body style="margin:0;padding:0;background:{BG};">
<div style="display:none;max-height:0;overflow:hidden;">{esc(" ".join(t.get("headline","") for t in today3))}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{BG};padding:18px 8px;">
<tr><td align="center">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="max-width:640px;background:#ffffff;border-radius:10px;overflow:hidden;
              font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;
              box-shadow:0 1px 3px rgba(0,0,0,.06);">
  <tr><td style="padding:22px 26px 16px;background:linear-gradient(135deg,#b5365f,#8e2b4d);color:#fff;">
    <div style="font-size:12px;letter-spacing:3px;opacity:.85;">{esc(brief.get("title","美妆情报")).upper()}</div>
    <div style="font-size:23px;font-weight:700;margin-top:6px;line-height:1.3;">{d.month} 月 {d.day} 日 · 周{weekday}</div>
    <div style="font-size:12.5px;opacity:.9;margin-top:6px;">{esc(scope.get("category",""))} · {esc(scope.get("one_liner",""))}</div>
  </td></tr>
  <tr><td style="padding:18px 26px 0;">
    <div style="font-size:12px;font-weight:700;color:{ACCENT};letter-spacing:2px;">今天必须知道</div>
  </td></tr>
  <tr><td style="padding:4px 26px 0;">{"".join(t3)}</td></tr>
  {"".join(sec_html)}
  {close_html}
  <tr><td style="padding:14px 26px 22px;">
    <div style="border-top:1px solid {LINE};padding-top:12px;font-size:11px;color:{MUTED};line-height:1.8;">
      {esc(foot)}<br>
      事实以原文为准；判断由 AI 依据素材生成，涉及数字/法规请点开原文复核。<br>
      想改口味（多几条渠道、少几条海外、加品牌、加深度分析）：直接回这封邮件说一句即可。
    </div>
  </td></tr>
</table>
</td></tr></table></body></html>"""


def clip_(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1].rstrip("，,、；; ") + "…"


def render_detail(it: dict, n: int, brief: dict) -> str:
    ana = it.get("analysis", {}) or {}
    date = brief["date"]
    blocks = []

    def block(title: str, body: str, color: str = INK) -> str:
        if not body:
            return ""
        return (f'<section style="margin:22px 0;">'
                f'<h2 style="font-size:15px;color:{ACCENT};margin:0 0 8px;letter-spacing:1px;">{esc(title)}</h2>'
                f'<div style="font-size:15px;line-height:1.85;color:{color};">{body}</div></section>')

    blocks.append(block("发生了什么", esc(ana.get("what", ""))))
    if ana.get("channel_move"):
        blocks.append(block("线下渠道动作",
                            f'<span style="background:{SOFT};color:{ACCENT};padding:2px 10px;'
                            f'border-radius:4px;font-weight:600;">{esc(ana["channel_move"])}</span>'))
    views = ana.get("views") or []
    if views:
        rows = "".join(
            f'<div style="margin:0 0 10px;"><b style="color:{INK};">{esc(v.get("who"))}</b>'
            f'<span style="color:#4b5563;">：{esc(v.get("text"))}</span></div>' for v in views)
        blocks.append(block("多方视角", rows))
    impact = ana.get("impact") or {}
    imp_rows = []
    for label, key in (("对品牌", "brand"), ("对渠道/代理", "channel"), ("对供应链/代工", "supply")):
        if impact.get(key):
            imp_rows.append(f'<div style="margin:0 0 8px;"><b>{label}</b>：{esc(impact[key])}</div>')
    blocks.append(block("对各方的意味", "".join(imp_rows)))
    blocks.append(block("最该防的是什么", esc(ana.get("risk", ""))))
    watch = ana.get("watch") or []
    if watch:
        blocks.append(block("接下来盯什么",
                            "".join(f'<div style="margin:0 0 6px;">· {esc(x)}</div>' for x in watch)))
    acts = ana.get("action") or []
    if acts:
        blocks.append(block("可以做什么",
                            "".join(f'<div style="margin:0 0 6px;">· {esc(x)}</div>' for x in acts)))
    blocks.append(block("值得琢磨的问题", esc(ana.get("question", ""))))

    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(it.get("title"))} · 美妆情报</title>
<style>html{{color-scheme:light;}} body{{max-width:720px;margin:0 auto;padding:28px 18px;color:{INK};background:#fff;
font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Microsoft YaHei',sans-serif;}}
a{{color:{ACCENT};}}</style></head><body>
<div style="font-size:12px;color:{ACCENT};letter-spacing:2px;">美妆情报 · {esc(date)} · {esc(it.get("section_label"))}</div>
<h1 style="font-size:24px;line-height:1.4;margin:10px 0 12px;">{esc(it.get("title"))}</h1>
<div style="font-size:13px;color:#6b7280;margin-bottom:6px;">{esc(it.get("source"))} · {esc(it.get("published"))}
{" · " + esc(it.get("brand")) if it.get("brand") else ""}</div>
<div style="background:{SOFT};border-left:3px solid {ACCENT};padding:12px 14px;margin:16px 0;
font-size:15px;line-height:1.75;"><b>判断</b> · {esc(it.get("so_what"))}</div>
{"".join(blocks)}
<div style="border-top:1px solid #eee;margin-top:26px;padding-top:14px;font-size:13px;color:#6b7280;">
原文：<a href="{esc(it.get("url",""))}">{esc(it.get("url",""))}</a><br>
分析由 AI 依据公开素材生成，事实以原文为准；素材不足的地方已标 limited。</div>
</body></html>"""


def render_site_page(brief: dict, dates: list[str]) -> str:
    date = brief["date"]
    items = brief.get("items", [])
    groups: dict[str, list[tuple[int, dict]]] = {}
    for n, it in enumerate(items, 1):
        groups.setdefault(it.get("section_label") or "其他", []).append((n, it))
    nav = " · ".join(f'<a href="../{x}/index.html">{x}</a>' for x in dates[:10])
    sec = []
    for name, rows in groups.items():
        li = "".join(
            f'<li style="margin-bottom:16px;"><a href="p{n}.html" style="font-weight:600;color:#111;">'
            f'{esc(it.get("title"))}</a>'
            f'<div style="color:#4b5563;font-size:14px;margin-top:2px;">判断 · {esc(it.get("so_what"))}</div></li>'
            for n, it in rows)
        sec.append(f'<h2 style="font-size:16px;color:{ACCENT};margin:26px 0 12px;">{esc(name)}</h2>'
                   f'<ul style="padding-left:18px;margin:0;">{li}</ul>')
    t3 = "".join(f'<li style="margin-bottom:8px;"><b>{esc(t.get("headline"))}</b> — {esc(t.get("why"))}</li>'
                 for t in brief.get("today3", []))
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>美妆情报 {esc(date)}</title>
<style>html{{color-scheme:light;}} body{{max-width:720px;margin:0 auto;padding:28px 18px;
font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;
line-height:1.75;color:#1a1a1a;background:#fff;}} a{{color:{ACCENT};}}</style></head><body>
<div style="font-size:12px;letter-spacing:2px;color:{ACCENT};">美妆情报 · {esc(date)}</div>
<h1 style="font-size:22px;margin:6px 0 4px;">{esc(brief.get("scope",{}).get("category",""))}</h1>
<div style="color:#888;font-size:13px;">{esc(brief.get("scope",{}).get("one_liner",""))}</div>
<h2 style="font-size:16px;color:{ACCENT};margin:26px 0 10px;">今天必须知道</h2><ol>{t3}</ol>
{"".join(sec)}
<div style="border-top:1px solid #eee;margin-top:28px;padding-top:12px;font-size:12px;color:#999;">
往期：{nav}</div></body></html>"""


def render_archive(dates: list[str]) -> str:
    li = "".join(f'<li><a href="{d}/index.html">{d}</a></li>' for d in dates)
    return f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>美妆情报 · 往期</title>
<style>body{{max-width:720px;margin:0 auto;padding:28px 18px;
font-family:-apple-system,BlinkMacSystemFont,'PingFang SC','Microsoft YaHei',sans-serif;line-height:1.9;}}
a{{color:{ACCENT};}}</style></head><body>
<h1 style="font-size:22px;">美妆情报 · 往期</h1><ul>{li}</ul></body></html>"""


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--brief", default=str(ROOT / "config" / "brief.json"))
    ap.add_argument("--date", default=None)
    args = ap.parse_args()

    profile = load_profile()
    brief = read_json(Path(args.brief))
    date = args.date or brief["date"]
    brief["date"] = date

    site_dir = ROOT / "site" / date
    site_dir.mkdir(parents=True, exist_ok=True)
    dates = sorted([p.name for p in (ROOT / "site").iterdir()
                    if p.is_dir() and p.name[:2] == "20"], reverse=True)

    email_html = render_email(brief, profile)
    card = ROOT / "output" / f"card-{date}.html"
    card.write_text(email_html, encoding="utf-8")

    pages = 0
    for n, it in enumerate(brief.get("items", []), 1):
        (site_dir / f"p{n}.html").write_text(render_detail(it, n, brief), encoding="utf-8")
        pages += 1

    (site_dir / "index.html").write_text(render_site_page(brief, dates), encoding="utf-8")
    (ROOT / "site" / "index.html").write_text(render_archive(dates), encoding="utf-8")
    write_json(ROOT / "output" / f"brief-{date}.json", brief)

    log(f"邮件卡片：{card}（{len(brief.get('items', []))} 条）")
    log(f"详情页：{pages} 个 → {site_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

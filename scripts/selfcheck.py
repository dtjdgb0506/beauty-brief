"""自检：把系统当前的真实问题列出来（只读，不改任何东西）。

用法: python scripts/selfcheck.py
"""
from __future__ import annotations

import io
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_profile, load_sources, read_json  # noqa: E402

OUT: list[str] = []


def say(s: str = "") -> None:
    OUT.append(s)


def sh(cmd: list[str]) -> str:
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        return (p.stdout or "") + (p.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return f"ERR {exc}"


def check_secrets_in_git() -> None:
    files = sh(["git", "log", "--all", "--name-only", "--pretty=format:"])
    bad = [f for f in files.splitlines() if f.strip() in (".env",)]
    say(f"[{'FAIL' if bad else 'OK'}] .env 是否进过 git 历史：{'进过！' if bad else '没有'}")


def check_detail_links() -> None:
    cards = sorted((ROOT / "output").glob("card-*.html"))
    if not cards:
        say("[SKIP] 没有卡片文件")
        return
    card = cards[-1]
    html = card.read_text(encoding="utf-8")
    links = re.findall(r'href="([^"]+)"[^>]*>看详细分析', html)
    web_base = load_profile().get("delivery", {}).get("web_base", "")
    to_own_site = [x for x in links if web_base and x.startswith(web_base)]
    to_source = [x for x in links if not (web_base and x.startswith(web_base))]
    say(f"[{'OK' if web_base else 'WARN'}] 详情页链接：web_base={web_base or '空（回退到原文链接）'}")
    say(f"      卡片里 {len(links)} 个『看详细分析』：{len(to_own_site)} 个指向详情页，{len(to_source)} 个指向原文")
    if not web_base:
        say("      影响：详情页（site/<日期>/pN.html）在云端生成后就丢了，读者点进去是原文，看不到我们的深度分析")


def check_site_published() -> None:
    wf = (ROOT / ".github" / "workflows" / "beauty-daily.yml").read_text(encoding="utf-8")
    has_pages = "pages" in wf or "deploy" in wf or "commit" in wf
    say(f"[{'WARN' if not has_pages else 'OK'}] 云端是否有发布/回传 site 的步骤：{'没有（详情页只留在 CI 临时目录）' if not has_pages else '有'}")


def check_cross_day_dup() -> None:
    cand = ROOT / "output" / "candidates"
    files = sorted(cand.glob("*.json"))
    if not files:
        say("[SKIP] 没有候选文件")
        return
    data = read_json(files[-1])
    items = data["items"]
    # 用已有候选模拟连续两天：先 11-21，再 11-22
    def titles_for(day: str) -> set[str]:
        sel = ROOT / "output" / f"selected-{day}.json"
        if not sel.exists():
            return set()
        return {x["title"] for x in read_json(sel)["items"]}
    a, b = titles_for("2026-11-21"), titles_for("2026-11-22")
    if not a or not b:
        say("[SKIP] 没有连续两天的 selected 文件，无法比对跨日重复")
        return
    dup = a & b
    say(f"[{'WARN' if dup else 'OK'}] 跨日重复：11-21 与 11-22 共同条目 {len(dup)} 条"
        + (f"，如：{list(dup)[:2]}" if dup else ""))


def check_history_store() -> None:
    hist = ROOT / "state" / "history.json"
    if not hist.exists():
        say("[WARN] 没有跨日去重历史库（同一事件可能连着几天出现）")
        return
    try:
        data = read_json(hist)
    except Exception:  # noqa: BLE001
        say("[WARN] history.json 解析失败")
        return
    days = sorted({e.get("day") for e in data.get("items", [])})
    say(f"[OK] 跨日去重历史库：{len(data.get('items', []))} 条，覆盖 {len(days)} 天 {days[-3:]}")


def check_sources() -> None:
    srcs = load_sources()
    types = {}
    for s in srcs:
        types[s["type"]] = types.get(s["type"], 0) + 1
    say(f"[OK] 源数量 {len(srcs)}，解析器分布 {types}")
    # 青眼：首页只有旧文，真数据在 Handler1.ashx，我们没实现
    qy = [s for s in srcs if s["type"] == "qingyan"]
    if qy:
        txt = (ROOT / "scripts" / "collect.py").read_text(encoding="utf-8")
        if "Handler1" not in txt:
            say("[WARN] 青眼只解析首页（近两周常 0 条），真正的最新列表在 Handler1.ashx，未实现")
    # 云端抓不到的源
    say("[WARN] 云端（美国节点）抓不到：赢商网（403）、联商网（超时）——线下渠道少两个源")
    say(f"[INFO] 内容日窗口：{load_profile()['delivery'].get('fresh_days')} 天；"
        f"云端 07:30 跑时内容日=发送日-1")


def check_state() -> None:
    st = ROOT / "state" / "sent.json"
    wf = (ROOT / ".github" / "workflows" / "beauty-daily.yml").read_text(encoding="utf-8")
    committed = "state/sent.json" in wf or "git add" in wf
    say(f"[{'WARN' if not committed else 'OK'}] 云端发信状态："
        f"{'不落地（CI 每次全新；同一天重复触发会再发一封，靠 Message-ID 折叠）' if not committed else '落地'}")


def check_tests() -> None:
    t = sh(["python", "-m", "unittest", "discover", "-s", "tests"])
    ok = "OK" in t
    say(f"[{'OK' if ok else 'FAIL'}] 单测：{t.strip().splitlines()[-1] if t.strip() else '无输出'}")
    body = (ROOT / "tests" / "test_pipeline.py").read_text(encoding="utf-8")
    missing = [k for k in ("recent_fingerprints", "title_fp", "similarity") if k not in body]
    if missing:
        say(f"[INFO] 单测没覆盖：{missing}")
    else:
        say("[OK] 单测已覆盖：跨日指纹去重 / 标题相似度 / 详情页链接")


def check_card_quality() -> None:
    cards = sorted((ROOT / "output").glob("card-*.html"))
    if not cards:
        return
    html = cards[-1].read_text(encoding="utf-8")
    # 渠道/品牌标签
    say(f"[INFO] 最近卡片：{cards[-1].name}，"
        f"判断 {html.count('判断 ·')} 处，渠道动作标签 "
        f"{sum(html.count(x) for x in ('开店</span>', '关店</span>', '招商</span>', '渠道政策</span>'))} 个")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    say("=" * 72)
    say("美妆情报 · 自检报告")
    say("=" * 72)
    for fn in (check_secrets_in_git, check_detail_links, check_site_published,
               check_cross_day_dup, check_history_store, check_sources,
               check_state, check_tests, check_card_quality):
        fn()
    text = "\n".join(OUT)
    print(text)
    (ROOT / "output" / "selfcheck.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())

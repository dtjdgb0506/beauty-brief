"""过滤 + 分栏 + 排序：从候选里挑出今天该给高管的 8~12 条。

用法:
  python scripts/score.py                    # 读最新 candidates → output/selected.json
  python scripts/score.py --date 2026-11-22
  python scripts/score.py --debug
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ROOT, clean_text, days_ago, load_lexicon, load_profile, log, read_json, title_fp,
    write_json,
)

HISTORY = ROOT / "state" / "history.json"
HISTORY_KEEP_DAYS = 3          # 最近 3 天发过的，不再重复上

TIER_W = {"core": 1.25, "analysis": 1.15, "trade": 1.10, "channel": 1.05,
          "reg": 1.15, "cn": 0.85, "weak": 0.55}
SECTION_NAME = {
    "channel": "线下渠道",
    "product": "竞品动作",
    "device": "械字号与监管",
    "trend": "趋势与海外",
}
# 通用财经源/弱信号源：必须命中这些词才收，否则噪音太大
BEAUTY_ANCHORS = ["美妆", "护肤", "化妆品", "彩妆", "香水", "个护", "洗护", "面膜",
                  "精华", "面霜", "防晒", "械字号", "医美", "成分", "功效", "美妆集合店"]
STRICT_ANCHORS = ["美妆", "护肤", "化妆品", "彩妆", "香水", "个护", "洗护", "面膜",
                  "精华", "面霜", "防晒", "械字号", "医美", "功效"]
REG_STRONG = ["抽检", "不合格", "处罚", "罚款", "通告", "通报", "立案", "查处",
              "新规", "征求意见", "标准", "条例", "办法", "禁用", "限用",
              "虚假宣传", "功效宣称", "标签", "召回", "备案", "注册", "停产", "下架"]
TREND_EN = ["beauty", "skincare", "skin care", "cosmetic", "fragrance", "makeup",
            "serum", "moistur", "suncare", "spf", "retail", "launch", "brand"]
# 两字品牌名极易在公告套话里误命中（"截至本公告日" → "至本"）
FALSE_POSITIVE = {"至本": ["截至本", "截止本"]}


def brand_in(blob: str, brand: str) -> bool:
    if not brand:
        return False
    if brand in FALSE_POSITIVE:
        cleaned = blob
        for bad in FALSE_POSITIVE[brand]:
            cleaned = cleaned.replace(bad, "××")
        return brand in cleaned
    return brand in blob


def hits(blob: str, words: list[str]) -> int:
    low = blob.lower()
    return sum(1 for w in words if w and w.lower() in low)


def is_noise(item: dict, profile: dict, lex: dict, blob: str) -> bool:
    for w in profile.get("block", {}).get("topics", []):
        if w and w in blob:
            return True
    for w in lex.get("exclude", {}).get("words", []):
        if w and w in blob:
            return True
    watch = profile.get("watch", {})
    anchors = watch.get("brands", []) + watch.get("devices", []) + \
        watch.get("retailers", []) + watch.get("groups", [])
    beauty = any(a in blob for a in BEAUTY_ANCHORS) or any(brand_in(blob, a) for a in anchors)
    strict = any(a in blob for a in STRICT_ANCHORS) or any(brand_in(blob, a) for a in anchors)
    if item["tier"] in ("cn", "weak"):
        # 通用源：必须明确提到美妆相关，否则丢
        if not strict:
            return True
    if item["tier"] == "channel":
        # 赢商网/联商网/亿邦是泛零售媒体：标题必须谈美妆，或"渠道商+门店动作"同时出现
        title = item["title"]
        has_beauty = any(a in title for a in BEAUTY_ANCHORS)
        has_retailer = any(brand_in(title, a) for a in anchors)
        channel_action = any(w in title for w in (
            "开店", "关店", "首店", "新店", "进驻", "入驻", "调改", "门店",
            "开工", "扩张", "关停", "撤店", "招商", "加盟", "布局", "旗舰店"))
        if not (has_beauty or (has_retailer and channel_action)):
            return True
    if item["source"].startswith("中国食品药品网"):
        # 监管站大量"某地举办培训会/观摩会"，只在真有事（抽检/处罚/新规）时才收
        if not any(w in blob for w in REG_STRONG):
            return True
    return False


def pick_section(item: dict, title: str, blob: str, lex: dict) -> tuple[str, dict]:
    hint = lex.get("section_hints", {})
    # 栏目判定只看标题：正文里顺嘴提一句"备案/监管"不该把一条品牌新闻判成监管新闻
    t_counts = {sec: hits(title, words) for sec, words in hint.items()}
    b_counts = {sec: hits(blob, words) for sec, words in hint.items()}
    counts = {sec: max(t_counts.get(sec, 0), b_counts.get(sec, 0) if b_counts.get(sec, 0) >= 2 else 0)
              for sec in hint}
    counts.update({k: v for k, v in t_counts.items() if k not in counts})
    src_section = item.get("section_hint", "")
    watch = lex.get("_watch", {})
    brand_hit = any(brand_in(blob, b) for b in watch.get("brands", []))

    # 1) 标题里就有抽检/处罚/新规/标准 → 械字号与监管
    #    "标准"太泛（"流程和标准"不是监管新闻），必须和发布/检验/检测/修订同现才算
    reg_title = [w for w in hint.get("regulatory", []) if w in title]
    if "标准" in reg_title and not any(
            x in title for x in ("发布", "实施", "修订", "检验", "检测", "抽检", "新国标")):
        reg_title = [w for w in reg_title if w != "标准"]
    if "标准" in reg_title and "流程" in title:
        reg_title = [w for w in reg_title if w != "标准"]
    if reg_title:
        return "device", counts
    # 2) 明确的械字号信号（标题 ≥1，或正文 ≥2 且源本身是械字号栏目）
    if t_counts.get("device", 0) >= 1 or (b_counts.get("device", 0) >= 2 and src_section == "device"):
        return "device", counts
    # 3) 资本动作（收购/并购/融资/上市）归"竞品动作"，别混进渠道雷达
    capital = any(w in title for w in ("收购", "并购", "融资", "上市", "IPO", "财报", "股权"))
    if capital and t_counts.get("channel", 0) == 0:
        return "product", counts
    # 4) 渠道动作：标题里有渠道信号，或渠道媒体且标题谈美妆
    beauty_title = any(a in title for a in BEAUTY_ANCHORS) or \
        any(brand_in(title, b) for b in watch.get("retailers", []))
    litigation = any(w in title for w in ("起诉", "诉讼", "索赔", "判决", "仲裁", "纠纷"))
    if not litigation and (t_counts.get("channel", 0) >= 1
                           or (item.get("tier") == "channel" and beauty_title)
                           or (b_counts.get("channel", 0) >= 3 and src_section == "channel")):
        return "channel", counts
    # 5) 品牌动作
    if brand_hit or b_counts.get("product", 0) >= 1:
        return "product", counts
    # 6) 国际/趋势
    if src_section == "trend" or item.get("tier") in ("core", "analysis", "cn"):
        return "trend", counts
    return "product", counts


def similarity(a: str, b: str) -> float:
    def bigrams(s: str) -> set[str]:
        s = re.sub(r"[\s\W]+", "", s)
        return {s[i:i + 2] for i in range(len(s) - 1)}
    A, B = bigrams(a), bigrams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def recent_fingerprints(hist: dict, ref_day, keep_days: int = HISTORY_KEEP_DAYS) -> set[str]:
    """从历史库里挑出"最近 keep_days 天内发过"的标题指纹。"""
    out: set[str] = set()
    for e in (hist or {}).get("items", []):
        try:
            d = date.fromisoformat(e.get("day", ""))
        except ValueError:
            continue
        if 0 <= (ref_day - d).days <= keep_days:
            out.add(e.get("fp", ""))
    return out


def score_item(item: dict, profile: dict, lex: dict, ref_day: str | None = None) -> dict:
    blob = f"{item['title']} {item.get('summary', '')}"
    watch = profile.get("watch", {})
    brands = watch.get("brands", []) + watch.get("devices", [])
    retailers = watch.get("retailers", [])
    groups = watch.get("groups", [])

    brand_hits = sum(1 for b in brands if brand_in(blob, b))
    retail_hits = sum(1 for b in retailers if brand_in(blob, b))
    group_hits = sum(1 for b in groups if brand_in(blob, b))
    offline_hits = hits(blob, watch.get("offline", []))
    if "渠道" in (item.get("tag") or "") or "零售" in (item.get("tag") or ""):
        offline_hits += 1          # 媒体自己标的"渠道/零售"分类，说明正文就是渠道稿
    action_hits = hits(blob, lex.get("actions", {}).get("product", []))
    channel_hits = hits(blob, lex.get("actions", {}).get("channel", []))
    device_hits = hits(blob, lex.get("actions", {}).get("device", []))
    reg_hits = hits(blob, lex.get("actions", {}).get("regulatory", []))
    trend_hits = hits(blob, lex.get("actions", {}).get("trend", []))

    lex = dict(lex)
    lex["_brands"] = brands
    lex["_watch"] = {"brands": brands, "retailers": retailers}
    section, counts = pick_section(item, item["title"], blob, lex)

    # 时效按"内容日"算，而不是按运行时刻：07:30 推前一天时，昨天的稿子应该算最新
    try:
        ref = date.fromisoformat(ref_day) if ref_day else date.today()
        pub = date.fromisoformat(item["published"])
        age = max(0, (ref - pub).days)
    except (TypeError, ValueError):
        age = 99
    fresh = {0: 4, 1: 4, 2: 3, 3: 2}.get(age, 0)
    base = 10 * TIER_W.get(item.get("tier", "trade"), 1.0)

    score = (base
             + min(brand_hits, 2) * (8 if item.get("tier") in ("trade", "reg", "channel") else 5)
             + min(group_hits, 1) * 4 + min(retail_hits, 2) * 4
             + min(action_hits, 3) * 4
             + min(channel_hits, 3) * 3
             + min(device_hits, 2) * 5
             + min(reg_hits, 3) * 4
             + min(offline_hits, 3) * 4          # 线下渠道信号（门店/代理/进驻/扣点…）
             + (6 if section == "channel" and offline_hits >= 2 else 0)
             + min(trend_hits, 2) * 1
             + (2 if item.get("tier") in ("trade", "reg") else 0)   # 行业/监管源本身更可信
             + fresh
             + (1 if re.search(r"\d", item["title"]) else 0)
             - (3 if len(item["title"]) > 45 else 0))

    return {**item, "section": section, "score": round(score, 1),
            "signals": {"brand": brand_hits, "group": group_hits, "retail": retail_hits,
                        "action": action_hits, "channel": channel_hits,
                        "offline": offline_hits,
                        "device": device_hits, "reg": reg_hits,
                        "trend": trend_hits, "age": age}}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat())
    ap.add_argument("--content-day", default=None,
                    help="只汇总这一天的稿子（默认不限）；再前一天也保留，防止漏掉深夜稿")
    ap.add_argument("--in", dest="inp", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-history", action="store_true", help="忽略跨日去重（补发/回溯时用）")
    ap.add_argument("--debug", action="store_true")
    args = ap.parse_args()

    profile = load_profile()
    lex = load_lexicon()
    inp = Path(args.inp) if args.inp else ROOT / "output" / "candidates" / f"{date.today().isoformat()}.json"
    if not inp.exists():
        cands = sorted((ROOT / "output" / "candidates").glob("*.json"))
        if not cands:
            log("没有候选文件，先跑 collect.py")
            return 1
        inp = cands[-1]
    data = read_json(inp)
    items = data["items"]

    if args.content_day:
        cd = __import__("datetime").date.fromisoformat(args.content_day)

        def _back(it):
            try:
                d = __import__("datetime").date.fromisoformat(it["published"])
            except ValueError:
                return 99
            return (cd - d).days
        before = len(items)
        # 内容日往前 3 天为主（行业媒体有 1~3 天滞后），条数太少再放宽到 5/7 天
        for window in (3, 5, 7):
            subset = [it for it in items if 0 <= _back(it) <= window]
            if len(subset) >= 20:
                items = subset
                break
        else:
            items = [it for it in items if 0 <= _back(it)] or items
        log(f"内容日 {args.content_day}：{before} 条候选中 {len(items)} 条落在 {args.content_day} 往前的时间窗内")

    # 跨日去重：最近 3 天已经发过的事件，不再重复上（否则每天看起来一模一样）
    ref_day = __import__("datetime").date.fromisoformat(args.content_day or args.date)
    recent_fps: set[str] = set()
    if HISTORY.exists() and not args.no_history:
        try:
            hist = read_json(HISTORY)
        except Exception:  # noqa: BLE001
            hist = {"items": []}
        recent_fps = recent_fingerprints(hist, ref_day)
        if recent_fps:
            history_dups = [it for it in items if title_fp(it["title"]) in recent_fps]
            fresh = [it for it in items if title_fp(it["title"]) not in recent_fps]
            dropped = len(items) - len(fresh)
            if len(fresh) >= 8:
                items = fresh
                log(f"跨日去重：跳过最近 {HISTORY_KEEP_DAYS} 天已发过的 {dropped} 条")
            else:
                history_dups = []
                log(f"跨日去重：只滤掉 {dropped} 条（剩下的不够一期，保留重复以保出刊）")
        else:
            history_dups = []
    else:
        history_dups = []

    scored, dropped_noise = [], 0
    for it in items:
        blob = f"{it['title']} {it.get('summary', '')}"
        if is_noise(it, profile, lex, blob):
            dropped_noise += 1
            continue
        s = score_item(it, profile, lex, ref_day=args.content_day)
        # 门槛：监管/械字号栏目宁可多收（漏一条法规比多一条更伤），弱信号源门槛更高
        if s["section"] == "device":
            min_score = 10
        elif s["tier"] == "weak":
            min_score = 22
        else:
            min_score = 16
        if s["score"] < min_score:
            continue
        scored.append(s)

    # 同一事件跨源去重：标题相似度 > 0.72，保留分高的
    scored.sort(key=lambda x: x["score"], reverse=True)
    kept: list[dict] = []
    for it in scored:
        dup = next((k for k in kept if similarity(k["title"], it["title"]) > 0.72), None)
        if dup:
            dup.setdefault("also_from", []).append(it["source"])
            continue
        kept.append(it)

    # 同一天、同一个主体（品牌/渠道商）+ 同栏目 → 视为同一事件，只留分高的
    watch = profile.get("watch", {})
    subjects = watch.get("brands", []) + watch.get("devices", []) + \
        watch.get("retailers", []) + watch.get("groups", [])
    seen_subject: dict[tuple, dict] = {}
    deduped: list[dict] = []
    for it in kept:
        title = it["title"]
        subject = next((s for s in subjects if brand_in(title, s)), "")
        key = (subject, it["published"], it["section"]) if subject else None
        if key and key in seen_subject:
            seen_subject[key].setdefault("also_from", []).append(it["source"])
            continue
        if key:
            seen_subject[key] = it
        deduped.append(it)
    kept = deduped

    # 按栏目配额取，保底不足时用剩余高分补
    quota = profile.get("quota", {})
    by_section: dict[str, list[dict]] = {}
    for it in kept:
        by_section.setdefault(it["section"], []).append(it)
    picked: list[dict] = []
    for sec, n in quota.items():
        picked.extend(by_section.get(sec, [])[:n])
    max_items = int(profile.get("delivery", {}).get("max_items", 12))
    if len(picked) < max_items:
        rest = [x for x in kept if x not in picked]
        picked.extend(rest[: max_items - len(picked)])
    picked = picked[:max_items]

    # 弱信号源（公众号标题党）最多占 2 条，多了会把正文版面挤掉
    weak = [x for x in picked if x.get("tier") == "weak"]
    if len(weak) > 2:
        worst = sorted(weak, key=lambda x: x["score"])[: len(weak) - 2]
        picked = [x for x in picked if x not in worst]
        for cand in [x for x in kept if x not in picked]:
            if len(picked) >= max_items:
                break
            picked.append(cand)

    # 线下渠道保底：去重后渠道栏可能见底，从"最近发过、但确实是线下动作"的池子里破例补 1 条
    channel_now = [x for x in picked if x["section"] == "channel"]
    if len(channel_now) < 2 and history_dups:
        spare = []
        for d in history_dups:
            s = score_item(d, profile, lex, ref_day=args.content_day)
            if s["section"] == "channel" and s["score"] >= 12:
                spare.append(s)
        spare.sort(key=lambda x: x["score"], reverse=True)
        for cand in spare[: 2 - len(channel_now)]:
            cand["repeat"] = True
            picked.append(cand)
        if spare:
            log(f"线下渠道保底：从历史重复池补 {min(len(spare), 2 - len(channel_now))} 条（标记为重复）")
        # 补进来的不能把总条数顶超，超了从非渠道栏里砍分最低的
        while len(picked) > max_items:
            cand = min((x for x in picked if x["section"] != "channel"),
                       key=lambda x: x["score"], default=None)
            if cand is None:
                break
            picked.remove(cand)

    order = {"channel": 0, "product": 1, "device": 2, "trend": 3}
    picked.sort(key=lambda x: (order.get(x["section"], 9), -x["score"]))

    # 线下渠道速览：渠道池里没进正文的，压成一行一条放进速览表（反映线下密度）
    picked_ids = {x["id"] for x in picked}
    pool: list[dict] = []
    for x in kept:
        if x["section"] != "channel" or x["id"] in picked_ids:
            continue
        # 和已入选/已入池的标题太像就跳过，避免同一件事出现两遍
        if any(similarity(x["title"], y["title"]) > 0.45 for y in picked + pool):
            continue
        pool.append(x)
        if len(pool) >= 6:
            break
    channel_pool = pool

    out = {
        "date": args.date,
        "content_day": args.content_day or args.date,
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "stats": {
            "candidates": len(items),
            "after_noise": len(scored),
            "after_dedupe": len(kept),
            "picked": len(picked),
        },
        "items": picked,
        "channel_pool": channel_pool,
        "sections": {sec: [i["id"] for i in picked if i["section"] == sec] for sec in order},
        "section_names": SECTION_NAME,
    }
    out_path = Path(args.out) if args.out else ROOT / "output" / "selected.json"
    write_json(out_path, out)
    log(f"候选 {len(items)} → 去噪 {len(scored)} → 跨源去重 {len(kept)} → 入选 {len(picked)}")
    for sec, name in SECTION_NAME.items():
        n = len([i for i in picked if i["section"] == sec])
        log(f"  {name:<8} {n} 条")
    if args.debug:
        for it in picked:
            log(f"  [{it['score']:>5}] {it['section']:<8} {it['title'][:38]}  ({it['source']})")
    return 0 if picked else 1


if __name__ == "__main__":
    sys.exit(main())

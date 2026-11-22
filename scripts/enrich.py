"""把选中的事实改写成高管能用的判断 + 深度分析。

每条产出：so_what（一句话判断）+ 详细分析（发生了什么 / 三方视角 / 对品牌渠道供应链的意味 /
最该防什么 / 接下来盯什么 / 可执行建议 / 值得琢磨的问题）。

规则优先抽字段（品牌/价格/渠道/动作），大模型负责分析与判断；模型失败则降级。

用法:
  python scripts/enrich.py                 # 读 output/selected.json → config/brief.json
  python scripts/enrich.py --no-llm        # 只用规则，不调模型
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    ROOT, clean_text, clip, load_env, load_lexicon, load_profile, log, read_json, write_json,
)

SECTION_LABEL = {
    "channel": "线下渠道",
    "product": "竞品动作",
    "device": "械字号与监管",
    "trend": "趋势与海外",
}

SYSTEM = """你是美妆产业情报分析师，服务对象是大众护肤 / 医美械字号品牌的市场部高管（CMO、市场总监）。
他们每天只有 3 分钟看邮件，但要能直接拿去做判断和开会。

对每条素材输出结构化分析。铁律：
1. 只用素材里的事实。不要编数字、时间、人物发言、机构表态。素材不够就明说，不要补。
2. 专有名词必须与素材一致：素材写"美瞳"就写"美瞳"，不要换成"医疗器械"；写"婴童护理"不要泛化。
3. 没有依据的推断要标"（推断）"。

每条输出字段：
- so_what：一句话判断，30~55 字，动词开头，**不要复述标题**（标题已经写了事实，这里写判断）。
- what：发生了什么，2~3 句，保留关键数字和时间。
- channel_move：如果这条涉及线下渠道，标注动作类型，只能从这几个词里选一个：
  "开店" / "关店" / "进驻" / "招商" / "加盟" / "代理签约" / "渠道政策" / "价格调整" / "陈列铺货"；
  与线下渠道无关就留空字符串。
- views：2~3 个视角，从不同角色的立场解读这件事（用 who 标注角色，如"品牌方""渠道方""资本/行业"），
  每方一句。必须是"这个角色会怎么看"，不能编造具体人物的原话。
  涉及线下渠道的条目，视角里必须有"代理商/经销商"或"门店/零售终端"。
- impact：分别写对 brand（品牌策略）、channel（**线下渠道/代理/门店**）、supply（供应链/代工/原料）的影响，
  各一句；channel 这一项要写清"对线下渠道意味着什么"（货架、代理政策、门店动作）。
  确实无关就留空字符串。
- risk：最该防的是什么，一句，要具体（踩什么坑、丢什么位置）。
- watch：接下来盯什么，2~3 条，尽量带时间点或数据口径（如"看 12 月抖音 GMV 是否止跌"）。
- action：市场部可执行动作 1~2 条，动词开头，具体到"本周能做什么"；与线下相关的要能落到渠道动作上。
- question：一个值得琢磨的问题，要有反常识或悬念，不要复述事实。
- depth：素材是否足够支撑分析，"full" 或 "limited"（只有标题一句话就是 limited）。

严格输出 JSON（不要 markdown 代码块）：
{"items":[{"id":"素材 id","so_what":"...","what":"...","channel_move":"",
           "views":[{"who":"品牌方","text":"..."}],
           "impact":{"brand":"...","channel":"...","supply":"..."},
           "risk":"...","watch":["..."],"action":["..."],
           "question":"...","depth":"full"}]}"""

TOP_SYSTEM = """你是美妆产业情报的选题编辑，读者是大众护肤 / 械字号品牌的市场部高管。
给你当天所有素材的标题和摘要，请挑出最重要的 3 件，并给一句总结。

要求：
1. 只用素材里的事实，不编数字和人名；专有名词与素材一致。
2. headline 是陈述句，≤22 字，不要问句，不要"为什么/如何"。
3. why 解释"为什么这件事对市场部重要"，≤45 字。
4. 三件事尽量覆盖不同性质：监管/合规、竞品动作、渠道变化，不要三件都是同一类。
5. close 一句今日小结，≤40 字，点出共同信号。

严格输出 JSON（不要 markdown 代码块）：
{"today3":[{"headline":"...","why":"..."}],"close":"..."}"""


def _parse_json(text: str) -> dict:
    text = text.strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # 常见问题：尾逗号、控制字符。修一次再试
        fixed = re.sub(r",\s*([}\]])", r"\1", text)
        fixed = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", fixed)
        return json.loads(fixed)


def call_llm(cfg: dict, system: str, prompt: str, max_tokens: int = 3000,
             timeout: int = 180, retries: int = 2) -> dict:
    url = cfg.get("LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/") + "/chat/completions"
    body = json.dumps({
        "model": cfg.get("LLM_MODEL", "deepseek-chat"),
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": prompt}],
        "temperature": 0.35,
        "response_format": {"type": "json_object"},
        "max_tokens": max_tokens,
    }).encode("utf-8")
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            req = urllib.request.Request(url, data=body, method="POST", headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {cfg['LLM_API_KEY']}",
            })
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            return _parse_json(data["choices"][0]["message"]["content"])
        except (json.JSONDecodeError, KeyError, IndexError) as exc:
            last = exc
            time.sleep(1 + attempt)
    raise last if last else RuntimeError("未知错误")


def extract_fields(item: dict, profile: dict, lex: dict) -> dict:
    blob = f"{item['title']} {item.get('summary', '')}"
    watch = profile["watch"]
    brand = next((b for b in watch["brands"] + watch["devices"] + watch["groups"]
                  if b in blob and b != "水羊"), "")
    if not brand:
        brand = next((b for b in watch["retailers"] if b in blob), "")
    price = re.search(r"(\d+(?:\.\d+)?\s*(?:元|块|美元|亿元|万元))", blob)
    channel = next((c for c in ["天猫", "抖音", "京东", "拼多多", "线下", "CS", "百货",
                                "购物中心", "集合店", "药房", "药店", "免税", "即时零售",
                                "山姆", "屈臣氏", "丝芙兰", "盒马"]
                    if c in blob), "")
    action = next((a for a in lex["actions"]["product"] if a in blob), "")
    return {"brand": brand, "price": price.group(1) if price else "",
            "channel": channel, "action": action}


def build_item_prompt(items: list[dict], today: str, scope: dict) -> str:
    lines = [f"日期：{today}",
             f"范围：{scope.get('category', '')}，{scope.get('price_band', '')}",
             "请为下面每一条素材输出分析："]
    for it in items:
        lines.append(f"[{it['id']}] {SECTION_LABEL.get(it['section'], '')} | {it['title']}")
        if it.get("summary"):
            lines.append(f"    摘要：{clip(it['summary'], 220)}")
        else:
            lines.append("    摘要：（无，仅标题，depth 应为 limited）")
        lines.append(f"    来源：{it['source']} {it['published']}")
    lines.append("")
    lines.append("请输出 JSON。")
    return "\n".join(lines)


def build_top_prompt(items: list[dict], today: str, scope: dict) -> str:
    lines = [f"日期：{today}",
             f"范围：{scope.get('category', '')}",
             "当天全部素材："]
    for it in items:
        lines.append(f"- [{SECTION_LABEL.get(it['section'], '')}] {it['title']}"
                     + (f"｜{clip(it.get('summary', ''), 90)}" if it.get("summary") else ""))
    lines.append("")
    lines.append("请挑出最重要的 3 件并输出 JSON。")
    return "\n".join(lines)


def fallback_item(it: dict, profile: dict, lex: dict) -> dict:
    f = extract_fields(it, profile, lex)
    summary = clip(it.get("summary") or "", 120)
    return {
        "id": it["id"],
        "so_what": clip((f["action"] + "：" if f["action"] else "") + (summary or it["title"]), 55),
        "what": summary or it["title"],
        "channel_move": "",
        "views": [],
        "impact": {"brand": "", "channel": "", "supply": ""},
        "risk": "",
        "watch": [],
        "action": [],
        "question": "",
        "depth": "limited",
    }


def fallback(selected: dict, profile: dict, lex: dict) -> dict:
    items = [fallback_item(it, profile, lex) for it in selected["items"]]
    top3 = [{"headline": it["title"][:22], "why": clip(it.get("summary", ""), 40)}
            for it in selected["items"][:3]]
    return {"today3": top3, "items": items, "close": "（模型未接入，本期为规则摘要）"}


def normalize_analysis(raw: dict, it: dict, profile: dict, lex: dict) -> dict:
    fb = fallback_item(it, profile, lex)
    out = {**fb, **{k: v for k, v in raw.items() if v not in (None, "", [], {})}}

    def strip_prefix(text: str, pats: list[str]) -> str:
        text = str(text or "").strip()
        for p in pats:
            text = re.sub(rf"^{p}\s*[：:，,。]?\s*", "", text)
        return text.strip()

    out["what"] = strip_prefix(out.get("what", ""), [r"发生了什么", r"事件"])
    out["risk"] = strip_prefix(out.get("risk", ""), [r"最该防的是", r"最该防", r"要防的是", r"风险在于"])
    out["so_what"] = strip_prefix(out.get("so_what", ""), [r"判断", r"结论"])
    out["channel_move"] = str(out.get("channel_move") or "").strip()[:6]
    if out["channel_move"] in ("无", "null", "None", "-", "—"):
        out["channel_move"] = ""
    if isinstance(out.get("action"), list):
        out["action"] = [strip_prefix(a, [r"建议", r"可以"]) for a in out["action"]]
    views = out.get("views") or []
    if isinstance(views, list):
        out["views"] = [v for v in views if isinstance(v, dict) and v.get("text")][:3]
    else:
        out["views"] = []
    impact = out.get("impact") or {}
    out["impact"] = {k: (impact.get(k) or "") for k in ("brand", "channel", "supply")}
    for k in ("watch", "action"):
        v = out.get(k) or []
        out[k] = [str(x) for x in v][:3] if isinstance(v, list) else []
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inp", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()

    profile = load_profile()
    lex = load_lexicon()
    selected = read_json(Path(args.inp) if args.inp else ROOT / "output" / "selected.json")
    today = selected.get("date", date.today().isoformat())
    cfg = load_env()

    enriched: dict = {"today3": [], "items": [], "close": ""}
    if not args.no_llm and cfg.get("LLM_API_KEY"):
        items_all = selected["items"]
        # 分批评析：一批 4 条，避免长输出被截断（截断会整批丢）
        for start in range(0, len(items_all), 4):
            batch = items_all[start:start + 4]
            try:
                res = call_llm(cfg, SYSTEM, build_item_prompt(batch, today, profile.get("scope", {})))
                got = [x for x in res.get("items", []) if x.get("id")]
                enriched["items"].extend(got)
                log(f"  分析批次 {start // 4 + 1}：{len(got)}/{len(batch)} 条")
            except Exception as exc:  # noqa: BLE001
                log(f"  分析批次 {start // 4 + 1} 失败：{type(exc).__name__}: {str(exc)[:90]}")
        try:
            top = call_llm(cfg, TOP_SYSTEM, build_top_prompt(items_all, today, profile.get("scope", {})), 900)
            enriched["today3"] = [x for x in top.get("today3", []) if x.get("headline")][:3]
            enriched["close"] = top.get("close", "")
            log(f"今日三件事：{len(enriched['today3'])} 条")
        except Exception as exc:  # noqa: BLE001
            log(f"今日三件事失败，用规则兜底：{type(exc).__name__}: {str(exc)[:90]}")
    if not enriched["items"]:
        enriched = fallback(selected, profile, lex)

    raw_map = {x["id"]: x for x in enriched.get("items", []) if x.get("id")}
    items = []
    for it in selected["items"]:
        f = extract_fields(it, profile, lex)
        ana = normalize_analysis(raw_map.get(it["id"], {}), it, profile, lex)
        items.append({
            **it,
            "section_label": SECTION_LABEL.get(it["section"], ""),
            "so_what": ana["so_what"],
            "analysis": {k: ana[k] for k in ("what", "channel_move", "views", "impact", "risk",
                                             "watch", "action", "question", "depth")},
            "brand": f["brand"], "price": f["price"],
            "channel": f["channel"], "action": f["action"],
        })

    today3 = [x for x in enriched.get("today3", []) if x.get("headline")][:3]
    if len(today3) < 3:
        for it in items:
            if len(today3) >= 3:
                break
            if not any(t["headline"] == it["title"][:22] for t in today3):
                today3.append({"headline": it["title"][:22], "why": it["so_what"]})

    brief = {
        "date": today,
        "content_day": selected.get("content_day", today),
        "title": profile.get("delivery", {}).get("title", "美妆情报"),
        "scope": profile.get("scope", {}),
        "today3": today3,
        "close": enriched.get("close", ""),
        "items": items,
        "channel_pool": [
            {"title": x["title"], "url": x["url"], "source": x["source"],
             "published": x["published"], "brand": extract_fields(x, profile, lex)["brand"],
             "tag": x.get("tag", "")}
            for x in selected.get("channel_pool", [])
        ],
        "stats": selected.get("stats", {}),
    }
    out = Path(args.out) if args.out else ROOT / "config" / "brief.json"
    write_json(out, brief)
    full = sum(1 for i in items if i["analysis"]["depth"] != "limited")
    log(f"简报落盘：{out}（{len(items)} 条，其中 {full} 条为完整分析）")
    return 0


if __name__ == "__main__":
    sys.exit(main())

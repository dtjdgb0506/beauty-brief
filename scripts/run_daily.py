"""一天一条命令：采集 → 打分选条 → 判断改写 → 渲染 → 发信。

用法:
  python scripts/run_daily.py --dry-run     # 全流程，不发信（推荐先这样验）
  python scripts/run_daily.py               # 真发（当天发过自动跳过）
  python scripts/run_daily.py --force       # 强制重发
  python scripts/run_daily.py --no-collect  # 复用已有 candidates
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, load_profile, log, read_json, write_json  # noqa: E402

PY = sys.executable
STATE = ROOT / "state" / "sent.json"
HISTORY = ROOT / "state" / "history.json"
LOGS = ROOT / "logs"
HISTORY_KEEP_DAYS = 30


def update_history(content_day: str) -> None:
    """把本期条目记进历史库，供后续几天跨日去重。"""
    sel_path = ROOT / "output" / "selected.json"
    if not sel_path.exists():
        return
    selected = read_json(sel_path)
    hist = {"items": []}
    if HISTORY.exists():
        try:
            hist = read_json(HISTORY)
        except Exception:  # noqa: BLE001
            hist = {"items": []}
    known = {(e.get("fp"), e.get("day")) for e in hist.get("items", [])}
    from common import title_fp

    for it in selected.get("items", []):
        fp = title_fp(it["title"])
        if (fp, content_day) in known:
            continue
        hist["items"].append({"day": content_day, "fp": fp, "title": it["title"][:80]})
    # 只留最近 30 天，文件不会无限长
    cutoff = datetime.now().date() - timedelta(days=HISTORY_KEEP_DAYS)
    kept = []
    for e in hist.get("items", []):
        try:
            if date.fromisoformat(e["day"]) >= cutoff:
                kept.append(e)
        except ValueError:
            continue
    hist["items"] = kept
    HISTORY.parent.mkdir(parents=True, exist_ok=True)
    HISTORY.write_text(json.dumps(hist, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"历史库更新：{len(kept)} 条（{HISTORY}）")


def run_step(name: str, args: list[str], log_path: Path) -> tuple[bool, str]:
    cmd = [PY] + args
    print(f"\n▶ {name}")
    proc = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    print(out.rstrip()[-3000:])
    with log_path.open("a", encoding="utf-8") as f:
        f.write(f"\n===== {name} =====\n{out.rstrip()}\nexit={proc.returncode}\n")
    return proc.returncode == 0, out


def load_state() -> dict:
    if not STATE.exists():
        return {}
    try:
        return read_json(STATE)
    except Exception:  # noqa: BLE001
        return {}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=date.today().isoformat(), help="发送日（默认今天）")
    ap.add_argument("--content-day", default=None, help="只汇总这一天的内容（默认发送日的前一天）")
    ap.add_argument("--same-day", action="store_true", help="不推前一天，就推当天")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-collect", action="store_true")
    ap.add_argument("--to", default=None)
    args = ap.parse_args()

    run_day = args.date                       # 发送日：幂等与日志用这个
    if args.content_day:
        content_day = args.content_day
    elif args.same_day:
        content_day = run_day
    else:
        content_day = (date.fromisoformat(run_day) - timedelta(days=1)).isoformat()
    LOGS.mkdir(parents=True, exist_ok=True)
    log_path = LOGS / f"{run_day}.log"
    started = datetime.now()
    profile = load_profile()
    print(f"美妆情报 · 发送日 {run_day} · 内容日 {content_day} · {started:%H:%M:%S} · "
          f"{'DRY-RUN' if args.dry_run else '真发'}")

    state = load_state()
    if state.get(run_day) and not args.force and not args.dry_run:
        print(f"今天已经发过（{state[run_day]}），跳过。要重发加 --force")
        return 0

    if not args.no_collect:
        ok, _ = run_step("采集", ["scripts/collect.py"], log_path)
        if not ok:
            print("⚠ 采集失败/无新内容，尝试用已有候选继续")
    ok, _ = run_step("打分选条", ["scripts/score.py", "--date", content_day,
                                  "--content-day", content_day], log_path)
    if not ok:
        print("✗ 没有可用内容，终止（不会硬凑一期垃圾）")
        return 1
    ok, _ = run_step("判断改写", ["scripts/enrich.py"], log_path)
    if not ok:
        print("✗ 改写失败，终止")
        return 1
    ok, _ = run_step("渲染", ["scripts/render.py", "--date", content_day], log_path)
    if not ok:
        print("✗ 渲染失败，终止")
        return 1

    brief = read_json(ROOT / "config" / "brief.json")
    head = brief["today3"][0]["headline"] if brief.get("today3") else brief["items"][0]["title"]
    subject = f"美妆情报 {content_day[5:].replace('-', '·')}｜{head[:24]}"
    html = f"output/card-{content_day}.html"

    send_args = ["scripts/send_mail.py", "--subject", subject, "--html", html]
    if args.to:
        send_args += ["--to", args.to]
    if args.dry_run:
        send_args.append("--dry-run")
    ok, _ = run_step("发信", send_args, log_path)
    if not ok:
        print("✗ 发信失败（内容已生成，可单独重跑 send_mail.py）")
        return 1

    if not args.dry_run:
        state[run_day] = datetime.now().isoformat(timespec="seconds")
        write_json(STATE, state)
        update_history(content_day)
        print(f"\n完成：{html} 已发出（内容日 {content_day}），状态写入 {STATE}")
    else:
        print(f"\n完成（dry-run，未发信）：{html}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
AI 管理者日报（ai-exec-brief）主入口。

两阶段流水线，跟 ai-news-daily 类似但增加「维度分类 + 管理者意义」：

  Phase 1（脚本 fetch + curate）：
    并发抓 9 个源近 24h → 写 ./ai-exec-brief-YYYYMMDD-HHMM.json
    每条带空字段 dimension / importance / headline / briefing / exec_meaning，
    等 Claude 在对话中填好后另存为 -curated.json

  Phase 2（脚本 render）：
    读 curated JSON，按 dimension 分组取每组前 N 条
    输出 HTML (16:9 dashboard)、PNG、PDF 深度报告

输出文件默认放在用户当前工作目录。
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fetchers import SOURCES

CN_TZ = timezone(timedelta(hours=8))


def parse_args():
    p = argparse.ArgumentParser(description="AI 管理者日报生成器。")
    sub = p.add_subparsers(dest="cmd")

    # 默认（无子命令）走 fetch
    p.add_argument("--curate", action="store_true",
                   help="抓完只输出 JSON，等 Claude 填维度/管理者意义后再 render")
    p.add_argument("--hours", type=int, default=24, help="只保留 H 小时内的新闻")
    p.add_argument("--json-out", type=Path, default=None)
    p.add_argument("--source", type=str, default=None,
                   help="逗号分隔，只跑指定源（调试用，如 huxiu,cls,tmtpost）")

    p_render = sub.add_parser("render", help="从 curated JSON 渲染 PNG + PDF")
    p_render.add_argument("json_path", type=Path)
    p_render.add_argument("--out", type=Path, default=None,
                          help="（已忽略，统一按 JSON 同名输出 .png / .pdf）")
    p_render.add_argument("--no-png", action="store_true", help="不输出 PNG")
    p_render.add_argument("--no-pdf", action="store_true", help="不输出 PDF")
    p_render.add_argument("--open-png", action="store_true", help="渲染后用预览打开 PNG")
    p_render.add_argument("--open-pdf", action="store_true", help="渲染后用预览打开 PDF")
    p_render.add_argument("--png-scale", type=int, default=2,
                          help="PNG 高清倍率（默认 2× = 3840×2160）")
    p_render.add_argument("--keep-html", action="store_true",
                          help="保留中间渲染的 dashboard.html / report.html（默认渲染完删除）")

    return p.parse_args()


def fetch_all(source_filter):
    sources = SOURCES
    if source_filter:
        sources = {k: v for k, v in SOURCES.items() if k in source_filter}
    all_items = []
    errors = []
    with cf.ThreadPoolExecutor(max_workers=len(sources)) as ex:
        futures = {ex.submit(fn): name for name, fn in sources.items()}
        for fut in cf.as_completed(futures, timeout=40):
            name = futures[fut]
            try:
                items = fut.result()
                print(f"[ok] {name}: {len(items)} items", file=sys.stderr)
                all_items.extend(items)
            except Exception as e:
                msg = f"{type(e).__name__}: {e}"
                print(f"[fail] {name}: {msg}", file=sys.stderr)
                errors.append((name, msg))
    return all_items, errors


def cmd_fetch(args) -> int:
    source_filter = [s.strip() for s in args.source.split(",")] if args.source else None
    items, errors = fetch_all(source_filter)
    if not items:
        print("[!] no items fetched", file=sys.stderr)
        return 2

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=args.hours)
    fresh = [it for it in items if it["published_at"] >= cutoff]
    print(f"[i] {len(items)} fetched, {len(fresh)} within last {args.hours}h",
          file=sys.stderr)

    # 按时效从新到旧
    fresh.sort(key=lambda x: x["published_at"], reverse=True)

    # 大模型榜单（独立于新闻源，失败不影响整体）
    leaderboard = []
    try:
        from fetchers import fetch_model_leaderboard
        leaderboard = fetch_model_leaderboard(20)
        print(f"[ok] leaderboard: {len(leaderboard)} models", file=sys.stderr)
    except Exception as e:
        print(f"[fail] leaderboard: {type(e).__name__}: {e}", file=sys.stderr)

    success_sources = {it["source"] for it in items}
    payload = {
        "generated_at": datetime.now(tz=CN_TZ).isoformat(timespec="seconds"),
        "total_scanned": len(items),
        "fresh_count": len(fresh),
        "source_count": len(success_sources),
        "errors": [list(e) for e in errors],
        "leaderboard": leaderboard,
        # 等 Claude 填
        "executive_summary": "",
        "action_items": [],
        "items": [
            {
                "id": i + 1,
                "source": it["source"],
                "title": it["title"],
                "url": it["url"],
                "summary": it.get("summary", "") or "",
                "published_at": it["published_at"].isoformat(),
                "image": it.get("image"),
                "metrics": it["metrics"],
                # 占位字段，等 Claude 在 curate 阶段填
                "dimension": None,    # "strategy" | "industry" | "practice" | null
                "importance": None,   # 1-5
                "headline": it["title"],
                "briefing": (it.get("summary") or "")[:120],
                "exec_meaning": "",   # 对管理者意味着什么
            }
            for i, it in enumerate(fresh)
        ],
    }

    out_dir = Path.cwd()
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    json_out = args.json_out or out_dir / f"ai-exec-brief-{stamp}.json"
    json_out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] wrote {json_out}", file=sys.stderr)

    # 摘要
    print(f"\n=== AI Exec Brief {datetime.now().strftime('%Y-%m-%d %H:%M')} ===")
    print(f"sources success: {len(success_sources)} / {len(SOURCES)}; fresh: {len(fresh)}")
    if errors:
        for n, m in errors:
            print(f"  - failed: {n} ({m})")
    print(f"\nLatest items (top 12 by time):")
    for it in fresh[:12]:
        pub = it["published_at"].astimezone(CN_TZ).strftime("%m-%d %H:%M")
        print(f"  [{pub}] {it['source']:5s} {it['title'][:60]}")
    print(f"\nJSON: {json_out}")

    if args.curate:
        print(f"\n[curate mode] next: Claude reads {json_out} and fills "
              f"`dimension` (strategy/industry/practice or null), `importance` (1-5), "
              f"`headline` (中文 12-22 字), `briefing` (中文 40-80 字), "
              f"`exec_meaning` (对管理者意味着什么 30-60 字), "
              f"plus top-level `executive_summary` and `action_items`. "
              f"Then run `brief.py render <curated.json>`.")
        return 0

    print("\n[i] no --curate flag, exiting (run with --curate to enter curation flow)",
          file=sys.stderr)
    return 0


def cmd_render(args) -> int:
    # 延迟 import，让 fetch 阶段不必依赖 render 模块
    from render import render_all
    return render_all(args)


def main():
    args = parse_args()
    if args.cmd == "render":
        return cmd_render(args)
    return cmd_fetch(args)


if __name__ == "__main__":
    sys.exit(main())

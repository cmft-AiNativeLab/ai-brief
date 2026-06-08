#!/usr/bin/env python3
"""一次性回填：用最新模板（card-pro.html）+ 每天 HTML 反解出的 curated 数据，
重新生成 docs/download/ai-brief-card-YYYYMMDD.png，让历史所有卡片版式与今天一致。

用法: python backfill_cards.py             # 处理 docs/ 下所有 20*.html（不含今天）
       python backfill_cards.py 20260607   # 只处理指定日期
"""
import re
import sys
import json
import shutil
import pathlib
import datetime

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
DL = DOCS / "download"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import build  # noqa
from render import render_dashboard, export_pdf, export_png  # noqa


COUNTRY_MAP_REV = {"美国": "US", "中国": "CN", "法国": "FR", "英国": "GB",
                   "加拿大": "CA", "德国": "DE", "以色列": "IL", "日本": "JP",
                   "韩国": "KR", "阿联酋": "AE", "新加坡": "SG"}
DIM_MAP = {"dim-strategy": "strategy", "dim-industry": "industry", "dim-practice": "practice"}


def parse_html(date):
    html = (DOCS / f"{date}.html").read_text(encoding="utf-8")

    # exec_summary
    m = re.search(r'<div class="cover-exec">.*?<div class="txt">(.*?)</div>', html, re.S)
    exec_summary = re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""

    # action_items
    m = re.search(r'<ol class="cover-action-list">(.*?)</ol>', html, re.S)
    action_items = []
    if m:
        action_items = [re.sub(r"<[^>]+>", "", x).strip()
                        for x in re.findall(r"<li[^>]*>(.*?)</li>", m.group(1), re.S)]

    # totals
    def i_or(pat, default=0):
        x = re.search(pat, html, re.S)
        return int(x.group(1)) if x else default
    total_scanned = i_or(r'class="lbl">SCANNED</div>\s*<div class="val">(\d+)')
    source_count = i_or(r'class="lbl">SOURCES</div>\s*<div class="val">(\d+)')

    # items
    items = []
    for dm in re.finditer(r'<div class="page (dim-[a-z]+)".*?<div class="dim-items">(.*?)</div>\s*<div class="page-footer"', html, re.S):
        dim = DIM_MAP.get(dm.group(1))
        if not dim:
            continue
        block = dm.group(2)
        for itm in re.finditer(r'<div class="item">(.*?)</div>\s*</div>', block, re.S):
            b = itm.group(1)
            stars = re.search(r'class="item-impl">([★☆—]+)', b)
            imp = stars.group(1).count("★") if stars else 0
            src = re.search(r'class="item-source">([^<]+)', b)
            source = (src.group(1).strip().split(" · ")[0] if src else "")
            url = re.search(r'<a href="([^"]+)" target="_blank">', b)
            headline = re.search(r'<div class="item-title"><a[^>]+>([^<]+)</a>', b)
            brief = re.search(r'<div class="item-brief">([^<]+)</div>', b)
            mean = re.search(r'<div class="item-meaning">([\s\S]*?)</div>', b)
            items.append({
                "id": len(items), "dimension": dim, "importance": imp,
                "source": source, "url": url.group(1) if url else "#",
                "headline": (headline.group(1) if headline else "").strip(),
                "title": (headline.group(1) if headline else "").strip(),
                "briefing": (brief.group(1) if brief else "").strip(),
                "exec_meaning": re.sub(r"<[^>]+>", "", mean.group(1) if mean else "").strip(),
                "published_at": f"{date[:4]}-{date[4:6]}-{date[6:8]}T08:00:00+00:00",
            })

    # leaderboard
    lb = []
    for m in re.finditer(r'<div class="lb-row[^"]*">(.*?)</div>\s*(?=<div class="lb-row"|<div class="lb-note")', html, re.S):
        b = m.group(1)
        rank = re.search(r"lb-rank[^>]*>(\d+)", b)
        name = re.search(r'lb-main">([^<]+)', b)
        cfg = re.search(r'lb-cfg">([^<]+)', b)
        full_name = (name.group(1).strip() if name else "")
        if cfg:
            full_name += " " + cfg.group(1).strip()
        cc = re.search(r'lb-creator">([^<]+)·([^<]+)<', b)
        creator = cc.group(1).strip() if cc else ""
        country_cn = cc.group(2).strip() if cc else ""
        score = re.search(r'lb-score">([\d.]+)', b)
        lb.append({
            "rank": int(rank.group(1)) if rank else len(lb) + 1,
            "name": full_name,
            "creator": creator,
            "country": COUNTRY_MAP_REV.get(country_cn, ""),
            "intelligence": float(score.group(1)) if score else 0,
            "reasoning": 'lb-tag">R<' in b,
            "price_in": None, "price_out": None,
        })

    return {
        "generated_at": f"{date[:4]}-{date[4:6]}-{date[6:8]}T07:30:00+08:00",
        "total_scanned": total_scanned, "source_count": source_count,
        "executive_summary": exec_summary, "action_items": action_items,
        "items": items, "leaderboard": lb,
    }


def regen_card(date, payload):
    """用最新模板渲染并截图卡片到 docs/download/。"""
    build._render_card(payload, date)
    card_html = DOCS / "card.html"
    out = DL / f"ai-brief-card-{date}.png"
    return build._screenshot(card_html, out, 580, 900, scale=2)


def main():
    targets = sys.argv[1:]
    if not targets:
        # 默认：所有 20YYMMDD.html，除了今天
        today = datetime.date.today().strftime("%Y%m%d")
        targets = sorted([p.stem for p in DOCS.glob("20*.html") if p.stem.isdigit() and p.stem != today])
    print(f"backfill targets: {targets}")
    for date in targets:
        if not (DOCS / f"{date}.html").exists():
            print(f"[skip] {date}: html missing"); continue
        try:
            payload = parse_html(date)
            ok = regen_card(date, payload)
            top = sorted(payload["items"], key=lambda x: -x["importance"])[0]["headline"][:24]
            print(f"[{'ok' if ok else 'FAIL'}] {date} · {top}…")
        except Exception as e:
            print(f"[err] {date}: {e}")

    # 关键：恢复 card*.html 为今天的内容（避免后续 cron 之前/分享时显示老数据）
    today = datetime.date.today().strftime("%Y%m%d")
    today_curated = ROOT / "build" / "curated.json"
    if today_curated.exists():
        try:
            today_payload = json.loads(today_curated.read_text(encoding="utf-8"))
            build._render_card(today_payload, today)
            print(f"[ok] restored docs/card*.html → {today}")
        except Exception as e:
            print(f"[warn] could not restore today's card: {e}")
    # 刷新下载页索引
    build._download_index(DL)
    print("[ok] download index regenerated")


if __name__ == "__main__":
    main()

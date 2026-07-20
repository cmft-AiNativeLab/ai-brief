#!/usr/bin/env python3
"""从 curated JSON 生成 Markdown 日报。
用法: python gen_md.py <curated.json> [out.md]
"""
import sys
import json
from pathlib import Path

DIMS = [("strategy", "一、战略动向 Strategy"),
        ("industry", "二、行业影响 Industry"),
        ("practice", "三、管理实践 Practice")]
COUNTRY = {"US": "美国", "CN": "中国", "FR": "法国", "GB": "英国", "UK": "英国",
           "CA": "加拿大", "DE": "德国", "IL": "以色列", "JP": "日本", "KR": "韩国", "": "—"}


def model_params(name):
    n = (name or "").lower()
    if "kimi k2" in n:
        return "1T MoE"
    if "deepseek v4" in n or "deepseek v3" in n:
        return "≈671B MoE"
    if "glm-5" in n or "glm5" in n:
        return "745B MoE"
    if "glm-4" in n or "glm4" in n:
        return "355B MoE"
    if "mimo" in n:
        return "未公开"
    if "qwen" in n and "max" in n:
        return "≈1T·闭源"
    return "闭源未知"


def fmt_price(p):
    return "—" if p is None else f"{round(float(p), 2):g}"


def main():
    if len(sys.argv) < 2:
        sys.exit("用法: python gen_md.py <curated.json> [out.md]")
    data = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    date = (data.get("generated_at") or "")[:10]
    items = data["items"]
    picked = [it for it in items if it.get("dimension")]

    o = []
    o.append(f"# AI 简讯 · {date}")
    o.append("")
    o.append(f"> 近 24 小时 AI 行业关键动向 ｜ 扫描 {data.get('total_scanned', 0)} 条 · "
             f"{data.get('source_count', 0)} 源 · 精选 {len(picked)} 条")
    o.append("")
    o.append("## 执行摘要")
    o.append("")
    o.append(data.get("executive_summary", "") or "（无）")
    o.append("")
    o.append("## 行动建议")
    o.append("")
    for i, a in enumerate(data.get("action_items", []), 1):
        o.append(f"{i}. {a}")
    o.append("")

    for key, title in DIMS:
        ds = sorted([it for it in items if it.get("dimension") == key],
                    key=lambda x: -(x.get("importance") or 0))
        if not ds:
            continue
        o.append(f"## {title}")
        o.append("")
        for j, it in enumerate(ds, 1):
            imp = int(it.get("importance") or 0)
            stars = "★" * imp + "☆" * (5 - imp)
            hl = it.get("headline") or it.get("title")
            o.append(f"### {j}. {hl}")
            o.append("")
            o.append(f"`{it.get('source', '')}` · {stars}")
            o.append("")
            if it.get("briefing"):
                o.append(it["briefing"])
                o.append("")
            if it.get("exec_meaning"):
                o.append(f"> **So What｜** {it['exec_meaning']}")
                o.append("")
            o.append(f"🔗 [阅读原文]({it.get('url', '')})")
            o.append("")

    lb = data.get("leaderboard") or []
    if lb:
        o.append("## 大模型能力榜 Top 20")
        o.append("")
        o.append("| # | 模型 | 参数量 | 单价 $/1M | 厂商 · 国家 | II 分数 |")
        o.append("|--:|------|--------|-----------|-------------|--------:|")
        for m in lb:
            cc = f"{m.get('creator', '')} · {COUNTRY.get(m.get('country', ''), m.get('country', ''))}"
            price = f"{fmt_price(m.get('price_in'))}/{fmt_price(m.get('price_out'))}"
            nm = m.get("name", "") + (" `R`" if m.get("reasoning") else "")
            o.append(f"| {m.get('rank')} | {nm} | {model_params(m.get('name'))} | "
                     f"{price} | {cc} | **{m.get('intelligence'):.1f}** |")
        o.append("")
        o.append("> 数据来源 artificialanalysis.ai ｜ II = 综合推理/编程/Agent 能力 ｜ "
                 "单价 = 每百万 token 输入/输出（美元）｜ `R` = 推理模型 ｜ 中国模型见「国家」列")
        o.append("")
        o.append("[查看实时完整榜单 →](https://artificialanalysis.ai/models#intelligence)")
        o.append("")

    md = "\n".join(o)
    out = sys.argv[2] if len(sys.argv) > 2 else f"AI简讯-{date.replace('-', '')}.md"
    Path(out).write_text(md, encoding="utf-8")
    print(f"[ok] wrote {out}  ({len(md)} chars, {len(picked)} 条 + 榜单 {len(lb)})")


if __name__ == "__main__":
    main()

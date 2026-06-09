"""
渲染：从 curated JSON 同时输出
  1. dashboard.html (16:9 1920×1080) + PNG (default 2× = 3840×2160)
  2. report.html (A4 多页) → 但 .html 不保存最终用户，仅作中间产物 → 用 Chrome 渲染为 PDF
"""
from __future__ import annotations

import argparse
import base64
import html
import io
import json
import math
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta

try:
    import qrcode
    _QR_OK = True
except ImportError:
    _QR_OK = False
from pathlib import Path
from typing import Any

ASSETS = Path(__file__).resolve().parent.parent / "assets"
DASHBOARD_TEMPLATE = ASSETS / "dashboard.html"
REPORT_TEMPLATE = ASSETS / "report.html"
LOGO_PATH = Path(__file__).resolve().parent.parent / "docs" / "logo.png"
CHROME_PATH = "/home/node/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome"
CN_TZ = timezone(timedelta(hours=8))

DIM_INFO = {
    "strategy": {"cn": "战略动向", "en": "STRATEGY",  "color": "#b8862b"},
    "industry": {"cn": "行业影响", "en": "INDUSTRY",  "color": "#2e5b9f"},
    "practice": {"cn": "管理实践", "en": "PRACTICE",  "color": "#2e8b57"},
}
DIM_ORDER = ["strategy", "industry", "practice"]


# ---------- shared helpers ----------

def _esc(s: str) -> str:
    return html.escape(s or "", quote=True)


def _logo_data_uri() -> str:
    """docs/logo.png 的 base64 data URI（用于深底仪表盘等非同目录场景）。"""
    try:
        return "data:image/png;base64," + base64.b64encode(LOGO_PATH.read_bytes()).decode()
    except Exception:
        return ""


def _dash_logo_html() -> str:
    """仪表盘头部 logo（白色药丸底，深色背景下可见）。"""
    uri = _logo_data_uri()
    return (f'<span class="dash-logo"><img src="{uri}" '
            f'alt="招商金融科技 · CMG Fintech"></span>') if uri else ""


def _format_pub_short(iso_str: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_str)
    except Exception:
        return ""
    now = datetime.now(tz=timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    hours = delta.total_seconds() / 3600
    if hours < 1:
        return f"{max(1, int(delta.total_seconds() / 60))} 分钟前"
    if hours < 24:
        return f"{int(hours)} 小时前"
    return dt.astimezone(CN_TZ).strftime("%m-%d %H:%M")


def _group_items(items: list[dict], per_dim: int = 3) -> dict[str, list[dict]]:
    """按 dimension 分组，每组按 importance 降序，取前 per_dim 条。"""
    g = {d: [] for d in DIM_ORDER}
    for it in items:
        d = it.get("dimension")
        if d in g:
            g[d].append(it)
    for d in g:
        g[d].sort(key=lambda x: -(x.get("importance") or 0))
        g[d] = g[d][:per_dim]
    return g


def _pie_svg(counts: dict[str, int], size: int = 180, *, stroke_width: int = 28) -> str:
    """donut-pie SVG。"""
    total = sum(counts.values()) or 1
    cx = cy = size / 2
    r = (size - stroke_width) / 2
    circ = 2 * math.pi * r
    colors = {d: DIM_INFO[d]["color"] for d in DIM_ORDER}
    parts = [
        f'<svg class="pie-svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">',
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="rgba(255,255,255,0.06)" stroke-width="{stroke_width}"/>',
    ]
    offset = 0.0
    for d in DIM_ORDER:
        c = counts.get(d, 0)
        if c == 0:
            continue
        dash = circ * c / total
        gap = circ - dash
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
            f'stroke="{colors[d]}" stroke-width="{stroke_width}" '
            f'stroke-dasharray="{dash:.2f} {gap:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 {cx} {cy})" stroke-linecap="butt"/>'
        )
        offset += dash
    parts.append(
        f'<text x="{cx}" y="{cy - 2}" text-anchor="middle" dominant-baseline="central" '
        f'fill="#ecf0fa" font-size="{size * 0.18:.0f}" font-weight="800" '
        f'font-family="JetBrains Mono, monospace">{total}</text>'
    )
    parts.append(
        f'<text x="{cx}" y="{cy + size*0.16:.0f}" text-anchor="middle" '
        f'fill="#9aa6c0" font-size="{size * 0.085:.0f}" letter-spacing="2">条目</text>'
    )
    parts.append('</svg>')
    return "".join(parts)


def _pie_svg_pdf(counts: dict[str, int], size: int = 200) -> str:
    """PDF 版的 donut，配色用 PDF 调色板。"""
    pdf_colors = {"strategy": "#b8862b", "industry": "#2e5b9f", "practice": "#2e8b57"}
    total = sum(counts.values()) or 1
    cx = cy = size / 2
    stroke_width = 32
    r = (size - stroke_width) / 2
    circ = 2 * math.pi * r
    parts = [
        f'<svg class="pie-svg" width="{size}" height="{size}" viewBox="0 0 {size} {size}">',
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#e8e2d2" stroke-width="{stroke_width}"/>',
    ]
    offset = 0.0
    for d in DIM_ORDER:
        c = counts.get(d, 0)
        if c == 0:
            continue
        dash = circ * c / total
        gap = circ - dash
        parts.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" '
            f'stroke="{pdf_colors[d]}" stroke-width="{stroke_width}" '
            f'stroke-dasharray="{dash:.2f} {gap:.2f}" '
            f'stroke-dashoffset="{-offset:.2f}" '
            f'transform="rotate(-90 {cx} {cy})" stroke-linecap="butt"/>'
        )
        offset += dash
    parts.append(
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" dominant-baseline="central" '
        f'fill="#1a1f2e" font-size="{size * 0.22:.0f}" font-weight="800">{total}</text>'
    )
    parts.append(
        f'<text x="{cx}" y="{cy + size*0.17:.0f}" text-anchor="middle" '
        f'fill="#8b94a5" font-size="{size * 0.08:.0f}" letter-spacing="2">条目</text>'
    )
    parts.append('</svg>')
    return "".join(parts)


# ---------- dashboard rendering ----------

def _dashboard_card(item: dict) -> str:
    src = _esc(item.get("source", ""))
    title = _esc(item.get("headline") or item.get("title"))
    brief = _esc(item.get("briefing") or item.get("summary") or "")
    meaning = _esc(item.get("exec_meaning") or "")
    if not meaning:
        meaning = "&nbsp;"
    impl = int(item.get("importance") or 0)
    stars = "★" * impl + "☆" * (5 - impl) if impl else ""
    pub = _esc(_format_pub_short(item.get("published_at", "")))
    url = _esc(item.get("url", "#"))
    return f"""
    <a class="card-link" href="{url}" target="_blank">
      <div class="card">
        <div class="card-top">
          <span class="card-source">{src} · {pub}</span>
          <span class="card-stars">{stars}</span>
        </div>
        <div class="card-title">{title}</div>
        <div class="card-brief">{brief}</div>
        <div class="card-meaning">{meaning}</div>
      </div>
    </a>
    """.strip()


def _dashboard_section(dim: str, items: list[dict]) -> str:
    info = DIM_INFO[dim]
    cards = "\n".join(_dashboard_card(it) for it in items)
    # 不足 3 条占位
    while items and len(items) < 3:
        cards += '<div class="card" style="opacity:0.18"><div class="card-top"><span>—</span><span></span></div></div>'
        items.append(None)
    return f"""
    <section class="section dim-{dim}">
      <div class="section-head">
        <span class="section-tag">{info['en']}</span>
        <span class="section-cn">{info['cn']}</span>
        <span class="section-count">{len(items)} 条</span>
        <span class="section-line"></span>
      </div>
      <div class="cards">{cards}</div>
    </section>
    """.strip()


def render_dashboard(payload: dict) -> str:
    template = DASHBOARD_TEMPLATE.read_text(encoding="utf-8")
    grouped = _group_items(payload["items"], per_dim=3)
    counts = {d: len(grouped[d]) for d in DIM_ORDER}
    sections = "\n".join(_dashboard_section(d, list(grouped[d])) for d in DIM_ORDER)

    action_items = "\n".join(
        f"<li>{_esc(a)}</li>"
        for a in (payload.get("action_items") or [])
    ) or '<li style="opacity:0.5">（今日无行动建议）</li>'

    now_cn = datetime.now(tz=CN_TZ)
    date_full = now_cn.strftime("%Y年%m月%d日 %A")
    for en, cn in [("Monday","周一"),("Tuesday","周二"),("Wednesday","周三"),
                   ("Thursday","周四"),("Friday","周五"),("Saturday","周六"),("Sunday","周日")]:
        date_full = date_full.replace(en, cn)

    return (
        template
        .replace("{{DATE}}", now_cn.strftime("%Y%m%d"))
        .replace("{{DATE_FULL}}", date_full)
        .replace("{{GENERATED_AT}}", now_cn.strftime("%H:%M"))
        .replace("{{TOTAL_SCANNED}}", str(payload.get("total_scanned", 0)))
        .replace("{{SOURCE_COUNT}}", str(payload.get("source_count", 0)))
        .replace("{{PIE_SVG}}", _pie_svg(counts, size=170))
        .replace("{{N_STRATEGY}}", str(counts["strategy"]))
        .replace("{{N_INDUSTRY}}", str(counts["industry"]))
        .replace("{{N_PRACTICE}}", str(counts["practice"]))
        .replace("{{ACTION_ITEMS}}", action_items)
        .replace("{{EXECUTIVE_SUMMARY}}",
                 _esc(payload.get("executive_summary") or "今日无执行摘要。"))
        .replace("{{SECTIONS}}", sections)
        .replace("{{LOGO}}", _dash_logo_html())
    )


# ---------- PDF report rendering ----------

def _short_url(url: str, max_len: int = 100) -> str:
    """供 PDF 显示的明文 URL（保留 https:// 前缀）。
    超长则截断中间。鸿蒙系统微信内置 PDF 阅读器不解析 link
    annotation，此处明文 URL 是用户复制访问的兜底。
    """
    if not url or url == "#":
        return ""
    u = url if url.startswith(("http://", "https://")) else "https://" + url
    if len(u) <= max_len:
        return u
    # 长 URL 中间省略（保留 https:// + host 头部 + 尾部 id）
    head = u[: max_len - 14]
    tail = u[-12:]
    return f"{head}…{tail}"


def _qr_data_uri(url: str, dark: str = "#14223a") -> str:
    """把 URL 生成二维码 PNG 的 base64 data URI（鸿蒙微信扫码跳转用）。
    qrcode 未安装或失败时返回空串，不影响其它渲染。
    """
    if not _QR_OK or not url or url == "#":
        return ""
    try:
        qr = qrcode.QRCode(
            error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=1
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color=dark, back_color="white")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return ""


def _report_item(idx: int, item: dict) -> str:
    title = _esc(item.get("headline") or item.get("title"))
    brief = _esc(item.get("briefing") or item.get("summary") or "")
    meaning = _esc(item.get("exec_meaning") or "（未填写「对管理者的意义」）")
    src = _esc(item.get("source", ""))
    pub = _esc(_format_pub_short(item.get("published_at", "")))
    impl = int(item.get("importance") or 0)
    stars = "★" * impl + "☆" * (5 - impl) if impl else "—"
    url = item.get("url", "#")
    url_esc = _esc(url)
    url_plain = _esc(_short_url(url))
    return f"""
    <div class="item">
      <div class="item-head">
        <span class="item-rank">#{idx:02d}</span>
        <span class="item-impl">{stars}</span>
        <span class="item-source">{src} · {pub}</span>
      </div>
      <div class="item-title"><a href="{url_esc}" target="_blank">{title}</a></div>
      <div class="item-brief">{brief}</div>
      <div class="item-meaning">{meaning}</div>
      <div class="item-url"><a href="{url_esc}" target="_blank">{url_plain}</a></div>
    </div>
    """.strip()


def _report_dim_page(dim_idx: int, dim: str, items: list[dict], total_pages: int = 4) -> str:
    info = DIM_INFO[dim]
    items_html = "\n".join(_report_item(i + 1, it) for i, it in enumerate(items))
    if not items_html:
        items_html = '<div class="item" style="opacity:0.5">（本维度今日无条目）</div>'
    page_no = dim_idx + 1  # 封面是 1，维度页从 2 起
    return f"""
    <div class="page dim-{dim}">
      <div class="dim-header">
        <div class="dim-no">{dim_idx:02d}</div>
        <div class="dim-cn">{info['cn']}</div>
        <div class="dim-en">{info['en']}</div>
        <div class="dim-count">{len(items)} 条</div>
      </div>
      <div class="dim-items">
{items_html}
      </div>
      <div class="page-footer">
        <span>AI 简讯 · {info['cn']}</span>
        <img class="footer-logo" src="logo.png" alt="招商金融科技">
        <span>{page_no} / {total_pages}</span>
      </div>
    </div>
    """.strip()


_COUNTRY_CN = {
    "US": "美国", "CN": "中国", "FR": "法国", "GB": "英国", "UK": "英国",
    "CA": "加拿大", "DE": "德国", "IL": "以色列", "JP": "日本", "KR": "韩国",
    "AE": "阿联酋", "SG": "新加坡", "": "—",
}


def _split_model_name(name: str) -> tuple[str, str]:
    """拆出主名与括号配置，用于两行显示。"""
    m = re.match(r'^(.*?)\s*(\(.*\))\s*$', name)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return name.strip(), ""


def _model_params(name: str) -> str:
    """模型参数量：开源系列据公开资料，闭源标「闭源未知」。"""
    n = name.lower()
    if "kimi k2" in n:
        return "1T MoE"            # Moonshot Kimi K2：1T 总 / 32B 激活
    if "deepseek v4" in n or "deepseek v3" in n:
        return "≈671B MoE"        # DeepSeek V3/V4：671B 总 / 37B 激活
    if "glm-5" in n or "glm5" in n:
        return "745B MoE"         # 智谱 GLM-5
    if "glm-4" in n or "glm4" in n:
        return "355B MoE"         # 智谱 GLM-4.6
    if "mimo" in n:
        return "未公开"           # 小米 MiMo 新版未公开
    if "qwen" in n and "max" in n:
        return "≈1T·闭源"         # Qwen Max：约 1T，已转闭源
    return "闭源未知"             # Anthropic/OpenAI/Google/xAI/Meta/Qwen Plus 等


def _fmt_price(p) -> str:
    """每百万 token 价格（美元），去尾零；无数据返回 —。"""
    if p is None:
        return "—"
    try:
        return f"{round(float(p), 2):g}"
    except (TypeError, ValueError):
        return "—"


def _leaderboard_page(lb: list[dict], page_no: int, total_pages: int) -> str:
    """大模型能力榜单页（artificialanalysis.ai · Intelligence Index）。"""
    if not lb:
        body = ('<div style="opacity:0.5;padding:20mm 0;text-align:center">'
                '榜单数据暂时获取失败（artificialanalysis.ai）</div>')
    else:
        maxii = max((m.get("intelligence") or 0) for m in lb) or 1
        rows = []
        for m in lb:
            rank = m.get("rank", 0)
            raw_name = m.get("name", "")
            main, cfg = _split_model_name(raw_name)
            main_e, cfg_e = _esc(main), _esc(cfg)
            param = _esc(_model_params(raw_name))
            pin, pout = _fmt_price(m.get("price_in")), _fmt_price(m.get("price_out"))
            price_html = (f'{_esc(pin)}<span class="lb-sep">/</span>{_esc(pout)}'
                          if not (pin == "—" and pout == "—") else "—")
            creator = _esc(m.get("creator", ""))
            country = m.get("country", "")
            cn = _COUNTRY_CN.get(country, country or "—")
            is_cn = country == "CN"
            ii = m.get("intelligence") or 0
            pct = ii / maxii * 100
            rk_cls = f" lb-rank-{rank}" if rank <= 3 else ""
            reason = '<span class="lb-tag">R</span>' if m.get("reasoning") else ""
            cfg_html = f'<span class="lb-cfg">{cfg_e}</span>' if cfg_e else ""
            rows.append(
                f'<div class="lb-row{" lb-cn" if is_cn else ""}">'
                f'<span class="lb-rank{rk_cls}">{rank}</span>'
                f'<span class="lb-name"><span class="lb-main">{main_e}{reason}</span>{cfg_html}</span>'
                f'<span class="lb-param">{param}</span>'
                f'<span class="lb-price">{price_html}</span>'
                f'<span class="lb-creator">{creator} · {cn}</span>'
                f'<span class="lb-bar"><span class="lb-bar-fill" style="width:{pct:.1f}%"></span></span>'
                f'<span class="lb-score">{ii:.1f}</span>'
                f'</div>'
            )
        body = "\n".join(rows)
    return (
        '<div class="page lb-page">'
        '<div class="dim-header lb-header">'
        '<div class="dim-cn">大模型能力榜</div>'
        '<div class="dim-en">MODEL LEADERBOARD · TOP 20</div>'
        f'<div class="dim-count">{len(lb)} 个</div>'
        '</div>'
        '<div class="lb-head">'
        '<span class="lb-rank">#</span>'
        '<span class="lb-name">模型</span>'
        '<span class="lb-param">参数量</span>'
        '<span class="lb-price">单价 $/1M</span>'
        '<span class="lb-creator">厂商 · 国家</span>'
        '<span class="lb-bar">能力分布（II）</span>'
        '<span class="lb-score">分数</span>'
        '</div>'
        f'<div class="lb-list">{body}</div>'
        '<div class="lb-note">数据来源：artificialanalysis.ai · II=综合推理/编程/Agent 能力 ·'
        ' 单价=每百万 token 输入/输出（美元）· 参数量据公开资料（闭源标「闭源未知」）·'
        ' <b>R</b>=推理模型 · 中国模型高亮</div>'
        '<div class="lb-link">完整榜单：'
        '<a href="https://artificialanalysis.ai/models#intelligence" target="_blank">'
        'https://artificialanalysis.ai/models#intelligence</a></div>'
        '<div class="page-footer">'
        '<span>AI 简讯 · 大模型榜单</span>'
        '<img class="footer-logo" src="logo.png" alt="招商金融科技">'
        f'<span>{page_no} / {total_pages}</span>'
        '</div>'
        '</div>'
    )


def render_report(payload: dict) -> str:
    template = REPORT_TEMPLATE.read_text(encoding="utf-8")
    # PDF 每维度页最多 4 条（共 12 条），4 条完美嵌入一页 A4；
    # curate 阶段按重要度填多少展示多少，少于 4 条也允许。
    grouped = _group_items(payload["items"], per_dim=4)
    counts = {d: len(grouped[d]) for d in DIM_ORDER}
    total = sum(counts.values()) or 1
    pcts = {d: f"{counts[d] * 100 / total:.0f}%" for d in DIM_ORDER}

    # 封面(1) + 3 维度页(2-4) + 榜单页(5) = 5 页
    total_pages = 5
    dim_pages = "\n".join(
        _report_dim_page(i + 1, d, list(grouped[d]), total_pages=total_pages)
        for i, d in enumerate(DIM_ORDER)
    )
    leaderboard_page = _leaderboard_page(
        payload.get("leaderboard") or [], page_no=5, total_pages=total_pages
    )

    action_items_html = "\n".join(
        f"<li>{_esc(a)}</li>"
        for a in (payload.get("action_items") or [])
    ) or '<li style="opacity:0.5">（今日无行动建议）</li>'

    now_cn = datetime.now(tz=CN_TZ)
    date_full = now_cn.strftime("%Y年%m月%d日 %A")
    for en, cn in [("Monday","周一"),("Tuesday","周二"),("Wednesday","周三"),
                   ("Thursday","周四"),("Friday","周五"),("Saturday","周六"),("Sunday","周日")]:
        date_full = date_full.replace(en, cn)

    return (
        template
        .replace("{{DATE}}", now_cn.strftime("%Y%m%d"))
        .replace("{{DATE_FULL}}", date_full)
        .replace("{{GENERATED_AT_FULL}}",
                 now_cn.strftime("%Y-%m-%d %H:%M:%S (UTC+8)"))
        .replace("{{TOTAL_SCANNED}}", str(payload.get("total_scanned", 0)))
        .replace("{{SOURCE_COUNT}}", str(payload.get("source_count", 0)))
        .replace("{{N_TOTAL}}", str(total))
        .replace("{{N_STRATEGY}}", str(counts["strategy"]))
        .replace("{{N_INDUSTRY}}", str(counts["industry"]))
        .replace("{{N_PRACTICE}}", str(counts["practice"]))
        .replace("{{PCT_STRATEGY}}", pcts["strategy"])
        .replace("{{PCT_INDUSTRY}}", pcts["industry"])
        .replace("{{PCT_PRACTICE}}", pcts["practice"])
        .replace("{{EXECUTIVE_SUMMARY}}",
                 _esc(payload.get("executive_summary") or "今日无执行摘要。"))
        .replace("{{PIE_SVG_LARGE}}", _pie_svg_pdf(counts, size=180))
        .replace("{{DIMENSION_PAGES}}", dim_pages)
        .replace("{{LEADERBOARD_PAGE}}", leaderboard_page)
        .replace("{{ACTION_ITEMS_PDF}}", action_items_html)
    )


# ---------- export ----------

LIB_PATHS = "/home/node/.local/lib:/tmp/libs/lib/x86_64-linux-gnu:/tmp/libs/usr/lib/x86_64-linux-gnu"

def _chrome_env() -> dict:
    """Inject LD_LIBRARY_PATH for Chromium in containers missing system libs."""
    import os
    env = os.environ.copy()
    existing = env.get("LD_LIBRARY_PATH", "")
    if LIB_PATHS not in existing:
        env["LD_LIBRARY_PATH"] = f"{LIB_PATHS}:{existing}" if existing else LIB_PATHS
    return env


def export_png(html_path: Path, png_path: Path, scale: int = 2) -> bool:
    if not Path(CHROME_PATH).exists():
        print(f"[warn] Chrome missing; skip PNG", file=sys.stderr)
        return False
    cmd = [
        CHROME_PATH, "--headless", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
        "--window-size=1920,1080", "--virtual-time-budget=3000",
        f"--force-device-scale-factor={scale}",
        f"--screenshot={png_path}",
        f"file://{html_path.resolve()}",
    ]
    subprocess.run(cmd, capture_output=True, timeout=60, check=False, env=_chrome_env())
    return png_path.exists()


def export_pdf(html_path: Path, pdf_path: Path) -> bool:
    """A4 多页 PDF。"""
    if not Path(CHROME_PATH).exists():
        print(f"[warn] Chrome missing; skip PDF", file=sys.stderr)
        return False
    cmd = [
        CHROME_PATH, "--headless", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
        "--no-pdf-header-footer",
        f"--print-to-pdf={pdf_path}",
        "--virtual-time-budget=3000",
        f"file://{html_path.resolve()}",
    ]
    subprocess.run(cmd, capture_output=True, timeout=60, check=False, env=_chrome_env())
    return pdf_path.exists()


# ---------- main ----------

def render_all(args) -> int:
    """渲染产物到用户工作目录：
      · AI简讯 · YYYYMMDD.html —— 最终网页报告（链接可点，微信/浏览器直接跳转）
      · AI简讯 · YYYYMMDD.pdf  —— A4 打印/存档（--no-pdf 可跳过）
      · AI简讯 · YYYYMMDD.png  —— 16:9 仪表盘
    dashboard 中间渲染文件用后即删；HTML 报告保留为主交付物。
    """
    payload = json.loads(args.json_path.read_text(encoding="utf-8"))
    base = args.json_path.with_suffix("")
    date_compact = datetime.now(tz=CN_TZ).strftime("%Y%m%d")
    out_stem = f"AI简讯 · {date_compact}"

    dashboard_path = base.with_name(out_stem + ".dashboard.html")  # 中间，用后删
    html_out = base.with_name(out_stem + ".html")                  # 最终网页交付

    # 1. Dashboard HTML → PNG（16:9 仪表盘）
    png_out = None
    if not args.no_png:
        dashboard_path.write_text(render_dashboard(payload), encoding="utf-8")
        png_out = base.with_name(out_stem + ".png")
        if export_png(dashboard_path, png_out, scale=args.png_scale):
            print(f"[ok] wrote {png_out}")
        else:
            png_out = None
        if not args.keep_html:
            dashboard_path.unlink(missing_ok=True)

    # 2. Report HTML —— 最终交付（自包含、链接可点、屏幕/打印两用）
    html_out.write_text(render_report(payload), encoding="utf-8")
    print(f"[ok] wrote {html_out}")

    # 3. 同源渲染 PDF（A4 打印/存档）
    pdf_out = None
    if not args.no_pdf:
        pdf_out = base.with_name(out_stem + ".pdf")
        if export_pdf(html_out, pdf_out):
            print(f"[ok] wrote {pdf_out}")
        else:
            pdf_out = None

    # 4. 打开：HTML 为主交付，始终打开
    if args.open_png and png_out:
        subprocess.run(["open", str(png_out)], check=False)
    if args.open_pdf and pdf_out:
        subprocess.run(["open", str(pdf_out)], check=False)
    if (args.open_pdf or args.open_png) and html_out.exists():
        subprocess.run(["open", str(html_out)], check=False)
    return 0

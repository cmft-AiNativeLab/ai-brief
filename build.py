#!/usr/bin/env python3
"""每日构建：抓取 → 自动提炼 → 渲染 HTML → 写入 docs/ →（可选）git push。

用法:
  python build.py            # 生成到 docs/，不提交
  python build.py --push     # 生成并 git commit & push（触发 GitHub Pages 更新）

依赖 .env（不进仓库）：AI_BRIEF_API_KEY / AI_BRIEF_BASE_URL / AI_BRIEF_MODEL
"""
import os
import re
import sys
import json
import shutil
import hashlib
import datetime
import subprocess
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent
SCRIPTS = ROOT / "scripts"
DOCS = ROOT / "docs"
BUILD = ROOT / "build"
PY = sys.executable


def load_env():
    envf = ROOT / ".env"
    if envf.exists():
        for line in envf.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def run(cmd):
    print("+", " ".join(str(c) for c in cmd))
    subprocess.run([str(c) for c in cmd], check=True)


def build_archive():
    dates = sorted([p.stem for p in DOCS.glob("20*.html") if p.stem.isdigit()], reverse=True)
    def _fmt(d):
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else d
    # href 用无后缀（/20260601），GitHub Pages 自动命中 20260601.html
    lis = "\n".join(f'  <li><a href="{d}">{_fmt(d)}</a></li>' for d in dates)
    html = (
        "<!doctype html><html lang=zh><head><meta charset=utf-8>"
        "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
        "<title>AI 简讯 · 往期</title><style>"
        "body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;"
        "background:#1b1e25;color:#e8e8e8;max-width:680px;margin:0 auto;padding:28px 20px}"
        "h1{color:#d4a373;font-size:22px}a{color:#4a9eff;text-decoration:none}"
        "li{margin:11px 0;font-size:17px;list-style:none}"
        "ul{padding:0}.t{color:#888;font-size:13px;margin-bottom:18px}"
        ".brand{height:32px;width:auto;display:block;margin-bottom:16px}"
        ".foot{color:#5a6480;font-size:12px;margin-top:26px;border-top:1px solid #2a2f3a;padding-top:14px}"
        "</style></head><body>"
        "<img class=brand src=\"logo.png\" alt=\"招商金融科技 · CMG Fintech\">"
        "<h1>AI 简讯 · 往期</h1><div class=t>点任意日期查看当日简报</div><ul>\n"
        f"{lis}\n</ul>"
        "<div class=foot>由 招商金科 出品</div></body></html>"
    )
    (DOCS / "archive.html").write_text(html, encoding="utf-8")
    print(f"[ok] wrote docs/archive.html ({len(dates)} 期)")


def _screenshot(html_path, png_path, w, h, scale=2):
    """Chrome 无头截图（卡片用方形窗口）。"""
    from render import CHROME_PATH
    if not pathlib.Path(CHROME_PATH).exists():
        print("[warn] Chrome 缺失，跳过卡片截图", file=sys.stderr)
        return False
    cmd = [CHROME_PATH, "--headless", "--disable-gpu", "--hide-scrollbars",
           f"--window-size={w},{h}", "--virtual-time-budget=2500",
           f"--force-device-scale-factor={scale}",
           f"--screenshot={png_path}", f"file://{html_path.resolve()}"]
    subprocess.run(cmd, capture_output=True, timeout=60, check=False)
    return png_path.exists()


def _prune_downloads(dl, keep_days=7):
    """只保留近 keep_days 天的带日期产物，控制仓库体积。"""
    today = datetime.date.today()
    for p in dl.glob("ai-brief-*"):
        m = re.search(r"(\d{8})", p.name)
        if not m:
            continue
        try:
            d = datetime.datetime.strptime(m.group(1), "%Y%m%d").date()
        except ValueError:
            continue
        if (today - d).days > keep_days:
            p.unlink(missing_ok=True)


def _download_index(dl):
    """生成 docs/download/index.html —— 按日期列出全部可下载文件（永久保留）。"""
    dates = set()
    for p in dl.glob("ai-brief-*"):
        m = re.search(r"(\d{8})", p.name)
        if m:
            dates.add(m.group(1))
    dates = sorted(dates, reverse=True)

    def ver(name):
        # 内容哈希作为版本号：文件一变，链接就变，破微信/浏览器旧缓存
        f = dl / name
        return hashlib.md5(f.read_bytes()).hexdigest()[:8] if f.exists() else ""

    rows = []
    for d in dates:
        links = []
        n = f"ai-brief-{d}.pdf"
        if (dl / n).exists():
            links.append(f'<a download="AI简讯 · {d}.pdf" href="{n}?v={ver(n)}">📄 日报 PDF</a>')
        n = f"ai-brief-overview-{d}.png"
        if (dl / n).exists():
            links.append(f'<a download="AI简讯-总览 · {d}.png" href="{n}?v={ver(n)}">🖼️ 总览大图</a>')
        n = f"ai-brief-card-{d}.png"
        if (dl / n).exists():
            links.append(f'<a download="AI简讯-卡片 · {d}.png" href="{n}?v={ver(n)}">📇 分享卡片</a>')
        if links:
            dt = f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            rows.append(f'<div class="day"><div class="dt">{dt}</div>'
                        f'<div class="lk">{"".join(links)}</div></div>')
    wk = dl / "ai-brief-7days.pdf"
    weekly = ""
    if wk.exists():
        weekly = ('<div class="day feat"><div class="dt">📚 近 7 天 AI 资讯报告 · 合辑</div>'
                  '<div class="lk">'
                  f'<a class="full" download="AI简讯-近7天合辑.pdf" '
                  f'href="ai-brief-7days.pdf?v={ver("ai-brief-7days.pdf")}">📦 下载合辑 PDF（近 7 天全部日报）</a>'
                  '</div></div>')
    body = weekly + ("\n".join(rows) or '<div class="day">暂无可下载文件</div>')
    html = (
        '<!doctype html><html lang="zh"><head><meta charset="utf-8">'
        '<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">'
        '<meta http-equiv="Pragma" content="no-cache"><meta http-equiv="Expires" content="0">'
        '<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">'
        '<title>AI 简讯 · 下载</title><style>'
        ':root{--ink:#26303f;--grey:#6a7488;--line:#e2e7f0;--blue:#3a63b8}'
        '*{box-sizing:border-box;margin:0;padding:0}'
        'body{font-family:"PingFang SC","Microsoft YaHei",sans-serif;color:var(--ink);'
        'background:linear-gradient(160deg,#eef1f7,#e7ebf3);min-height:100vh;padding:26px 16px}'
        '.wrap{max-width:560px;margin:0 auto}'
        'h1{font-size:21px;font-weight:800;letter-spacing:1px}'
        '.sub{color:var(--grey);font-size:13px;margin:7px 0 20px;line-height:1.6}'
        '.day{background:#fff;border:1px solid var(--line);border-radius:14px;padding:14px 16px;'
        'margin-bottom:12px;box-shadow:0 6px 18px rgba(40,55,90,.06)}'
        '.dt{font-size:15px;font-weight:700;margin-bottom:10px}'
        '.lk{display:flex;flex-wrap:wrap;gap:9px}'
        '.lk a{flex:1 1 30%;min-width:126px;text-align:center;text-decoration:none;color:var(--blue);'
        'background:#f3f6fc;border:1px solid var(--line);border-radius:10px;padding:10px 8px;'
        'font-size:13.5px;font-weight:600;transition:.15s}'
        '.lk a:hover{background:#e8effb;border-color:var(--blue)}'
        '.lk a.full{flex:1 1 100%;background:var(--blue);color:#fff;border-color:var(--blue)}'
        '.lk a.full:hover{background:#2f56a8}'
        '.day.feat{border-color:#9fbef0;background:#eef4ff}'
        '.day.feat .dt{color:var(--blue)}'
        '.back{display:inline-block;margin-bottom:10px;color:var(--blue);text-decoration:none;font-size:13px}'
        '.brand{height:32px;width:auto;display:block;margin:2px 0 14px}'
        '.foot{color:var(--grey);font-size:11.5px;margin-top:16px;line-height:1.6;text-align:center}'
        '</style></head><body><div class="wrap">'
        '<a class="back" href="../card">‹ 返回 AI 简讯</a>'
        '<img class="brand" src="../logo.png" alt="招商金融科技 · CMG Fintech">'
        '<h1>AI 简讯 · 资料下载</h1>'
        '<div class="sub">每日 7:30 自动生成 · 日报 PDF / 总览大图 / 分享卡片 · 往期全部永久保留</div>'
        f'{body}'
        '<div class="foot">由 招商金科 出品 · 数据来源 量子位 / 新智元 / 36氪 / 华尔街见闻 等 ＋ artificialanalysis.ai</div>'
        '</div></body></html>'
    )
    (dl / "index.html").write_text(html, encoding="utf-8")


def build_weekly(date):
    """合并近 7 天日报 PDF 为「近七天 AI 资讯报告」合辑（最新在前）。"""
    from render import export_pdf
    from pypdf import PdfWriter
    dl = DOCS / "download"
    today = datetime.date(int(date[:4]), int(date[4:6]), int(date[6:8]))
    # 近 7 天内（含今天）有日报 HTML 的日期，最新在前
    dates = []
    for p in sorted(DOCS.glob("20*.html"), key=lambda x: x.stem, reverse=True):
        if not p.stem.isdigit():
            continue
        try:
            d = datetime.datetime.strptime(p.stem, "%Y%m%d").date()
        except ValueError:
            continue
        if 0 <= (today - d).days < 7:
            dates.append(p.stem)
    if not dates:
        return None
    # 取已有的当期 PDF，缺的从对应 HTML 临时渲染
    pdfs, tmps = [], []
    for ds in dates:
        dated = dl / f"ai-brief-{ds}.pdf"
        if dated.exists():
            pdfs.append(dated)
        else:
            t = BUILD / f"wk-{ds}.pdf"
            if export_pdf(DOCS / f"{ds}.html", t):
                pdfs.append(t)
                tmps.append(t)
    if not pdfs:
        return None
    out = dl / "ai-brief-7days.pdf"
    writer = PdfWriter()
    for pf in pdfs:
        writer.append(str(pf))
    with open(out, "wb") as f:
        writer.write(f)
    writer.close()
    for t in tmps:
        t.unlink(missing_ok=True)
    print(f"[ok] 近 7 天合辑：{len(pdfs)} 期 -> {out.name}")
    return out


def build_downloads(payload, date):
    """生成可下载产物到 docs/download/：日报 PDF、总览 PNG、卡片 PNG、近 7 天合辑（+ latest.* 固定链接）。"""
    from render import render_dashboard, export_pdf, export_png
    dl = DOCS / "download"
    dl.mkdir(exist_ok=True)
    report_html = DOCS / f"{date}.html"
    made = []

    # 1) 日报 PDF（A4 多页，从报告 HTML 同源渲染）
    pdf_path = dl / f"ai-brief-{date}.pdf"
    if report_html.exists() and export_pdf(report_html, pdf_path):
        shutil.copyfile(pdf_path, dl / "latest.pdf")
        made.append("PDF")

    # 2) 总览 PNG（16:9 仪表盘）
    dash_html = BUILD / f"dashboard-{date}.html"
    dash_html.write_text(render_dashboard(payload), encoding="utf-8")
    overview_png = dl / f"ai-brief-overview-{date}.png"
    if export_png(dash_html, overview_png, scale=2):
        shutil.copyfile(overview_png, dl / "latest-overview.png")
        made.append("总览PNG")
    dash_html.unlink(missing_ok=True)

    # 3) 卡片 PNG（正方形分享卡，520×520 窗口）
    card_png = dl / f"ai-brief-card-{date}.png"
    if _screenshot(DOCS / "card.html", card_png, 520, 520, scale=2):
        shutil.copyfile(card_png, dl / "latest-card.png")
        made.append("卡片PNG")

    # 4) 近 7 天合辑 PDF
    try:
        if build_weekly(date):
            made.append("近7天合辑")
    except Exception as e:
        print(f"[warn] 近 7 天合辑生成失败：{e}", file=sys.stderr)

    # 往期全部永久保留，不做清理
    _download_index(dl)
    print(f"[ok] downloads -> docs/download/ [{', '.join(made) or '空'}]")


def main():
    load_env()
    push = "--push" in sys.argv
    BUILD.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    # 旁路：--from-curated <path> 跳过抓取+提炼，直接用现成 curated JSON 渲染发布
    if "--from-curated" in sys.argv:
        curated_json = pathlib.Path(sys.argv[sys.argv.index("--from-curated") + 1])
        print(f"[i] 跳过抓取+提炼，直接渲染：{curated_json}")
    else:
        fetch_json = BUILD / "fetch.json"
        curated_json = BUILD / "curated.json"
        # 1. 抓取 10 源 + 榜单
        run([PY, SCRIPTS / "brief.py", "--curate", "--json-out", fetch_json, "--hours", "24"])
        # 2. Claude 自动提炼（选 12 条 + 打标 + 摘要/行动）
        run([PY, SCRIPTS / "curate_auto.py", fetch_json, curated_json])
    # 3. 渲染 HTML（直接拿字符串，写入 docs/，链接可点）
    sys.path.insert(0, str(SCRIPTS))
    from render import render_report
    payload = json.loads(curated_json.read_text(encoding="utf-8"))
    html = render_report(payload)
    date_iso = (payload.get("generated_at") or "")[:10] or datetime.date.today().isoformat()
    date = date_iso.replace("-", "")  # 紧凑日期 YYYYMMDD → URL 形如 /ai-brief/20260601
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    (DOCS / f"{date}.html").write_text(html, encoding="utf-8")
    print(f"[ok] wrote docs/index.html + docs/{date}.html")
    # 4. 往期归档页
    build_archive()
    # 5. 可下载产物（日报 PDF / 总览 PNG / 卡片 PNG）→ docs/download/
    try:
        build_downloads(payload, date)
    except Exception as e:
        print(f"[warn] 生成下载产物失败（不影响网页发布）：{e}", file=sys.stderr)
    # 6. 推送（Pages 从 docs/ 自动发布）
    if push:
        run(["git", "-C", ROOT, "add", "-A", "docs"])
        run(["git", "-C", ROOT, "commit", "-m", f"AI 简讯 {date}"])
        run(["git", "-C", ROOT, "push"])
        print("[ok] pushed — 稍等 1 分钟 GitHub Pages 会更新")


if __name__ == "__main__":
    main()

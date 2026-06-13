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


def _analytics_snippet(prefix=""):
    """百度统计埋点 + 下载事件追踪"""
    return '''<script>
var _hmt = _hmt || [];
(function() {
 var hm = document.createElement("script");
 hm.src = "https://hm.baidu.com/hm.js?5b3142c3d7836775b91647439de7a663";
 var s = document.getElementsByTagName("script")[0];
 s.parentNode.insertBefore(hm, s);
})();
</script>
<script>
(function(){
  function classify(href){
    var p=(new URL(href,location.href)).pathname.split('/').pop()||'';
    if(/7days\\.pdf$/i.test(p)) return 'weekly_pdf';
    if(/latest\\.pdf$/i.test(p)||/ai-brief-20\\d{6}\\.pdf$/i.test(p)) return 'daily_pdf';
    if(/overview.*\\.png$/i.test(p)) return 'overview_png';
    if(/card.*\\.png$/i.test(p)) return 'card_png';
    if(/\\.pdf$/i.test(p)) return 'other_pdf';
    if(/\\.png$/i.test(p)) return 'other_png';
    return '';
  }
  document.addEventListener('click',function(ev){
    var a=ev.target.closest&&ev.target.closest('a[href]');
    if(!a)return;
    var href=a.getAttribute('href')||'';
    var isDl=a.hasAttribute('download')||/\\.(pdf|png)(\\?|#|$)/i.test(href);
    if(!isDl)return;
    var type=classify(href);
    if(type){
      _hmt.push(['_trackEvent','download',type,a.textContent.trim().slice(0,60)]);
    }
  },true);
})();
</script>'''


def _inject_analytics(html, prefix=""):
    snippet = _analytics_snippet(prefix)
    if "hm.baidu.com" in html:
        return html
    if "</body>" in html:
        return html.replace("</body>", snippet + "</body>", 1)
    return html + snippet


def write_analytics_js():
    # 已切换百度统计，无需写入自定义 analytics.js
    pass


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
    (DOCS / "archive.html").write_text(_inject_analytics(html), encoding="utf-8")
    print(f"[ok] wrote docs/archive.html ({len(dates)} 期)")


_LIB_PATHS = "/home/node/.local/lib:/tmp/libs/lib/x86_64-linux-gnu:/tmp/libs/usr/lib/x86_64-linux-gnu"
def _chrome_env():
    import os
    env = os.environ.copy()
    existing = env.get("LD_LIBRARY_PATH", "")
    if _LIB_PATHS not in existing:
        env["LD_LIBRARY_PATH"] = f"{_LIB_PATHS}:{existing}" if existing else _LIB_PATHS
    return env


def _valid_file(path, min_size=100):
    path = pathlib.Path(path)
    return path.exists() and path.stat().st_size > min_size


def _prepare_output(path):
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.unlink(missing_ok=True)


def _screenshot(html_path, png_path, w, h, scale=2):
    """Chrome 无头截图（卡片用方形窗口）。Try Chrome CLI, fallback to pw-render.js card mode."""
    from render import CHROME_PATH, _pw_render
    png_path = pathlib.Path(png_path)
    _prepare_output(png_path)
    if pathlib.Path(CHROME_PATH).exists():
        cmd = [CHROME_PATH, "--headless", "--disable-gpu", "--hide-scrollbars", "--no-sandbox",
               f"--window-size={w},{h}", "--virtual-time-budget=5000",
               f"--force-device-scale-factor={scale}",
               f"--screenshot={png_path}", f"file://{html_path.resolve()}"]
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=90, check=False, env=_chrome_env())
            if _valid_file(png_path):
                return True
            if r.stderr:
                print(f"[warn] Chrome card screenshot failed: {r.stderr.decode(errors='replace')[:240]}", file=sys.stderr)
        except subprocess.TimeoutExpired:
            print("[warn] Chrome card screenshot timeout, trying Playwright fallback", file=sys.stderr)
    # Fallback to Playwright Node.js card mode
    return _pw_render("card", pathlib.Path(html_path), png_path)


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
    (dl / "index.html").write_text(_inject_analytics(html, "../"), encoding="utf-8")


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


def _render_card(payload, date):
    """从 assets/card*.html 模板渲染分享卡到 docs/card*.html：
    自动注入当日日期与「今日精选」（取 importance 最高一条的 headline + briefing + so what）。
    card.html      —— 标准版（精选标题 + 引文 + 来源）
    card-pro.html  —— 深度版（追加 SO WHAT 影响价值点评）
    """
    import html as _html
    items = [it for it in payload.get("items", []) if it.get("dimension")]
    if not items:
        print("[warn] curated 无条目，跳过卡片更新", file=sys.stderr)
        return False
    # 优先取战略动向第一条作为 BREAKING NEWS；若无战略条目则 fallback 到全局 importance 最高
    strategy = [it for it in items if it.get("dimension") == "strategy"]
    if strategy:
        top = sorted(strategy, key=lambda x: (-(x.get("importance") or 0), x.get("id") or 0))[0]
    else:
        top = sorted(items, key=lambda x: (-(x.get("importance") or 0), x.get("id") or 0))[0]
    headline = top.get("headline") or top.get("title") or ""
    briefing = top.get("briefing") or top.get("summary") or top.get("exec_meaning") or ""
    meaning = top.get("exec_meaning") or top.get("briefing") or ""
    source = top.get("source") or "—"
    imp = int(top.get("importance") or 0)
    stars = "★" * imp + "☆" * (5 - imp) if imp else "—"
    date_dot = date  # 紧凑 YYYYMMDD：20260605（按需求去掉点分隔）

    def _fill(text):
        return (text
                .replace("{{DATE_DOT}}", _html.escape(date_dot))
                .replace("{{HOT_HEADLINE}}", _html.escape(headline))
                .replace("{{HOT_QUOTE}}", _html.escape(briefing))
                .replace("{{HOT_MEANING}}", _html.escape(meaning))
                .replace("{{HOT_SOURCE}}", _html.escape(source))
                .replace("{{HOT_STARS}}", stars))

    # 暂定 card-pro 为日卡设计：同一模板渲染到 /card 和 /card-pro
    primary = ROOT / "assets" / "card-pro.html"
    if not primary.exists():
        print("[warn] assets/card-pro.html 模板缺失，跳过卡片更新", file=sys.stderr)
        return False
    filled = _fill(primary.read_text(encoding="utf-8"))
    rendered = 0
    for out_name in ("card.html", "card-pro.html"):
        (DOCS / out_name).write_text(_inject_analytics(filled), encoding="utf-8")
        rendered += 1
    print(f"[ok] wrote docs/card*.html × {rendered} (card-pro 模板) · 今日精选：{headline[:24]}…")
    return True


def build_downloads(payload, date):
    """生成可下载产物到 docs/download/：日报 PDF、总览 PNG、卡片 PNG、近 7 天合辑（+ latest.* 固定链接）。"""
    from render import render_dashboard, export_pdf, export_png
    dl = DOCS / "download"
    dl.mkdir(exist_ok=True)
    report_html = DOCS / f"{date}.html"
    made = []
    missing = []

    # 0) 先按当日数据刷新分享卡片（注入日期 + 今日爆款），随后才截图
    if _render_card(payload, date):
        made.append("卡片HTML")
    else:
        missing.append("卡片HTML")

    # 1) 日报 PDF（A4 多页，从报告 HTML 同源渲染）
    pdf_path = dl / f"ai-brief-{date}.pdf"
    if report_html.exists() and export_pdf(report_html, pdf_path) and _valid_file(pdf_path):
        shutil.copyfile(pdf_path, dl / "latest.pdf")
        made.append("PDF")
    else:
        missing.append("PDF")

    # 2) 总览 PNG（16:9 仪表盘）
    dash_html = BUILD / f"dashboard-{date}.html"
    dash_html.write_text(render_dashboard(payload), encoding="utf-8")
    overview_png = dl / f"ai-brief-overview-{date}.png"
    try:
        if export_png(dash_html, overview_png, scale=2) and _valid_file(overview_png):
            shutil.copyfile(overview_png, dl / "latest-overview.png")
            made.append("总览PNG")
        else:
            missing.append("总览PNG")
    finally:
        dash_html.unlink(missing_ok=True)

    # 3) 卡片 PNG（card 改为 min-height 模式可自由生长，窗口加高到 900 确保不裁切）
    card_png = dl / f"ai-brief-card-{date}.png"
    if _screenshot(DOCS / "card.html", card_png, 580, 900, scale=2) and _valid_file(card_png):
        shutil.copyfile(card_png, dl / "latest-card.png")
        made.append("卡片PNG")
    else:
        missing.append("卡片PNG")

    # 4) 近 7 天合辑 PDF
    try:
        weekly = build_weekly(date)
        if weekly and _valid_file(weekly):
            made.append("近7天合辑")
        else:
            missing.append("近7天合辑")
    except Exception as e:
        missing.append("近7天合辑")
        print(f"[warn] 近 7 天合辑生成失败：{e}", file=sys.stderr)

    # 往期全部永久保留，不做清理
    _download_index(dl)
    print(f"[ok] downloads -> docs/download/ [{', '.join(made) or '空'}]")
    if missing:
        print(f"[warn] downloads missing: {', '.join(missing)}", file=sys.stderr)
    return made, missing


def git_commit_push(date):
    """Commit and push generated outputs/scripts. Treat no-op commit as success for cron."""
    run(["git", "-C", ROOT, "add", "-A", "docs", "build.py", "scripts"])
    status = subprocess.run(
        ["git", "-C", ROOT, "status", "--porcelain"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if not status:
        print("[ok] no changes to commit")
        return
    msg = f"AI 简讯 {date}"
    subprocess.run(["git", "-C", ROOT, "commit", "-m", msg], check=True)
    subprocess.run(["git", "-C", ROOT, "push"], check=True)
    print("[ok] pushed — 稍等 1 分钟 GitHub Pages 会更新")


def verify_downloads(date):
    """验证当日所有关键下载产物是否存在且有效。
    返回 (ok: bool, missing: list[str])。
    """
    dl = DOCS / "download"
    required = [
        (f"ai-brief-{date}.pdf", 50_000),       # PDF 至少 50KB
        (f"ai-brief-overview-{date}.png", 100_000),  # 总览至少 100KB
        (f"ai-brief-card-{date}.png", 50_000),   # 卡片至少 50KB
    ]
    missing = []
    for name, min_size in required:
        p = dl / name
        if not p.exists():
            missing.append(f"{name} (不存在)")
        elif p.stat().st_size < min_size:
            missing.append(f"{name} (仅 {p.stat().st_size} bytes，需 >{min_size})")
    # 检查 latest.* 固定链接
    for alias in ("latest.pdf", "latest-overview.png", "latest-card.png"):
        p = dl / alias
        if not p.exists() or p.stat().st_size < 100:
            missing.append(f"{alias} (缺失或过小)")
    # 检查 7 天合辑
    wk = dl / "ai-brief-7days.pdf"
    if not wk.exists() or wk.stat().st_size < 100_000:
        missing.append("ai-brief-7days.pdf (缺失或过小)")
    # 检查下载索引
    idx = dl / "index.html"
    if not idx.exists():
        missing.append("download/index.html (缺失)")
    return (len(missing) == 0, missing)


def retry_missing_downloads(payload, date, max_retries=2):
    """验证产物，缺失的尝试重新渲染（最多 max_retries 次）。
    返回最终 (ok, missing)。
    """
    from render import render_dashboard, export_pdf, export_png
    for attempt in range(1, max_retries + 1):
        ok, missing = verify_downloads(date)
        if ok:
            return True, []
        print(f"[retry #{attempt}] 缺失产物: {', '.join(missing)}")
        dl = DOCS / "download"
        dl.mkdir(exist_ok=True)
        report_html = DOCS / f"{date}.html"
        # 逐个尝试补渲染
        pdf_name = f"ai-brief-{date}.pdf"
        if any(pdf_name in m for m in missing) and report_html.exists():
            pdf_path = dl / pdf_name
            print(f"  重试 PDF: {pdf_name}")
            try:
                if export_pdf(report_html, pdf_path) and _valid_file(pdf_path):
                    shutil.copyfile(pdf_path, dl / "latest.pdf")
                    print(f"  ✓ PDF 重试成功 ({pdf_path.stat().st_size} bytes)")
            except Exception as e:
                print(f"  ✗ PDF 重试失败: {e}", file=sys.stderr)
        overview_name = f"ai-brief-overview-{date}.png"
        if any(overview_name in m for m in missing):
            dash_html = BUILD / f"dashboard-{date}.html"
            overview_png = dl / overview_name
            print(f"  重试总览 PNG: {overview_name}")
            try:
                dash_html.write_text(render_dashboard(payload), encoding="utf-8")
                if export_png(dash_html, overview_png, scale=2) and _valid_file(overview_png):
                    shutil.copyfile(overview_png, dl / "latest-overview.png")
                    print(f"  ✓ 总览 PNG 重试成功 ({overview_png.stat().st_size} bytes)")
            except Exception as e:
                print(f"  ✗ 总览 PNG 重试失败: {e}", file=sys.stderr)
            finally:
                dash_html.unlink(missing_ok=True)
        card_name = f"ai-brief-card-{date}.png"
        if any(card_name in m for m in missing):
            card_png = dl / card_name
            print(f"  重试卡片 PNG: {card_name}")
            try:
                if _screenshot(DOCS / "card.html", card_png, 580, 900, scale=2) and _valid_file(card_png):
                    shutil.copyfile(card_png, dl / "latest-card.png")
                    print(f"  ✓ 卡片 PNG 重试成功 ({card_png.stat().st_size} bytes)")
            except Exception as e:
                print(f"  ✗ 卡片 PNG 重试失败: {e}", file=sys.stderr)
        # 7 天合辑
        if any("7days" in m for m in missing):
            try:
                build_weekly(date)
                print(f"  ✓ 7 天合辑重试完成")
            except Exception as e:
                print(f"  ✗ 7 天合辑重试失败: {e}", file=sys.stderr)
        # 下载索引
        if any("index.html" in m for m in missing):
            try:
                _download_index(dl)
                print(f"  ✓ 下载索引重试完成")
            except Exception as e:
                print(f"  ✗ 下载索引重试失败: {e}", file=sys.stderr)
    # 最终验证
    ok, missing = verify_downloads(date)
    if not ok:
        print(f"[error] 重试 {max_retries} 次后仍有 {len(missing)} 个产物缺失：", file=sys.stderr)
        for m in missing:
            print(f"  - {m}", file=sys.stderr)
    return ok, missing


def main():
    load_env()
    push = "--push" in sys.argv
    verify_only = "--verify-only" in sys.argv
    BUILD.mkdir(exist_ok=True)
    DOCS.mkdir(exist_ok=True)
    # --verify-only: 仅验证产物完整性，不重新构建
    if verify_only:
        # 取最新的日期 HTML
        dates = sorted([p.stem for p in DOCS.glob("20*.html") if p.stem.isdigit()], reverse=True)
        if not dates:
            print("[error] 没有找到任何日期 HTML", file=sys.stderr)
            sys.exit(1)
        date = dates[0]
        ok, missing = verify_downloads(date)
        if ok:
            print(f"[ok] {date} 全部产物完整 ✓")
        else:
            print(f"[fail] {date} 缺失 {len(missing)} 个产物:")
            for m in missing:
                print(f"  - {m}")
            sys.exit(1)
        return
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
    html = _inject_analytics(render_report(payload))
    write_analytics_js()
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
        print(f"[warn] 生成下载产物异常（将进入验证+重试）：{e}", file=sys.stderr)
    # 6. 验证产物完整性，缺失则自动重试
    ok, missing = retry_missing_downloads(payload, date, max_retries=2)
    if not ok:
        print(f"[error] 产物验证失败，放弃推送！缺失: {missing}", file=sys.stderr)
        sys.exit(1)
    print(f"[ok] 产物验证通过 ✓ (PDF + 总览PNG + 卡片PNG + 7天合辑 + 下载索引)")
    # 7. 推送（Pages 从 docs/ 自动发布）
    if push:
        git_commit_push(date)


if __name__ == "__main__":
    main()

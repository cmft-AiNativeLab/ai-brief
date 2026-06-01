#!/usr/bin/env python3
"""每日构建：抓取 → 自动提炼 → 渲染 HTML → 写入 docs/ →（可选）git push。

用法:
  python build.py            # 生成到 docs/，不提交
  python build.py --push     # 生成并 git commit & push（触发 GitHub Pages 更新）

依赖 .env（不进仓库）：AI_BRIEF_API_KEY / AI_BRIEF_BASE_URL / AI_BRIEF_MODEL
"""
import os
import sys
import json
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
    dates = sorted([p.stem for p in DOCS.glob("20*.html")], reverse=True)
    lis = "\n".join(f'  <li><a href="{d}.html">{d}</a></li>' for d in dates)
    html = (
        "<!doctype html><html lang=zh><head><meta charset=utf-8>"
        "<meta name=viewport content=\"width=device-width,initial-scale=1\">"
        "<title>AI 简讯 · 往期</title><style>"
        "body{font-family:-apple-system,'PingFang SC','Microsoft YaHei',sans-serif;"
        "background:#1b1e25;color:#e8e8e8;max-width:680px;margin:0 auto;padding:28px 20px}"
        "h1{color:#d4a373;font-size:22px}a{color:#4a9eff;text-decoration:none}"
        "li{margin:11px 0;font-size:17px;list-style:none}"
        "ul{padding:0}.t{color:#888;font-size:13px;margin-bottom:18px}</style></head><body>"
        "<h1>AI 简讯 · 往期</h1><div class=t>点任意日期查看当日简报</div><ul>\n"
        f"{lis}\n</ul></body></html>"
    )
    (DOCS / "archive.html").write_text(html, encoding="utf-8")
    print(f"[ok] wrote docs/archive.html ({len(dates)} 期)")


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
    date = (payload.get("generated_at") or "")[:10] or datetime.date.today().isoformat()
    (DOCS / "index.html").write_text(html, encoding="utf-8")
    (DOCS / f"{date}.html").write_text(html, encoding="utf-8")
    print(f"[ok] wrote docs/index.html + docs/{date}.html")
    # 4. 往期归档页
    build_archive()
    # 5. 推送（Pages 从 docs/ 自动发布）
    if push:
        run(["git", "-C", ROOT, "add", "docs"])
        run(["git", "-C", ROOT, "commit", "-m", f"AI 简讯 {date}"])
        run(["git", "-C", ROOT, "push"])
        print("[ok] pushed — 稍等 1 分钟 GitHub Pages 会更新")


if __name__ == "__main__":
    main()

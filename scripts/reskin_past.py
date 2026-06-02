#!/usr/bin/env python3
"""把往期日报 HTML 就地适配到最新模板。

往期数据已不可复原（每日覆盖），故只更新「外观」而不重渲染正文：
  1. 修正封面日期与 <title>（按文件名 YYYYMMDD 推算，原先是回填日期，错误）
  2. 删除封面底部长脚注（数据来源 / 生成时间 / 方法论）
  3. 每页底部居中加 logo（封面底部 + 各页页脚中间）
  4. 页脚改 grid 三栏，使 logo 真正居中
正文条目、榜单内容保持原样（忠于当时发布的版本）。

用法: python reskin_past.py docs/20260526.html docs/20260530.html ...
"""
import re
import sys
import datetime
import pathlib

WEEK = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
FOOTER_LOGO = '<img class="footer-logo" src="logo.png" alt="招商金融科技">'
COVER_FOOT = ('<div class="cover-foot">'
              '<img class="footer-logo" src="logo.png" alt="招商金融科技 · CMG Fintech">'
              '</div>')
CSS_PATCH = (
    "\n  /* —— 适配最新模板：页脚 logo / 去脚注 / 居中 —— */\n"
    "  .footer-logo{ height:6mm; width:auto; flex-shrink:0; }\n"
    "  .cover-foot{ margin-top:auto; padding-top:3mm; border-top:1px solid var(--line);"
    " display:flex; justify-content:center; }\n"
    "  .page-footer{ display:grid; grid-template-columns:1fr auto 1fr; align-items:center; }\n"
    "  .page-footer > span:last-child{ text-align:right; }\n"
)


def reskin(path):
    p = pathlib.Path(path)
    ds = p.stem  # YYYYMMDD
    d = datetime.date(int(ds[:4]), int(ds[4:6]), int(ds[6:8]))
    date_full = f"{d.year}年{d.month:02d}月{d.day:02d}日 {WEEK[d.weekday()]}"
    html = p.read_text(encoding="utf-8")

    if ".footer-logo{" in html:
        print(f"[skip] {path} 已是最新模板")
        return

    # 1) <title> 紧凑日期
    html = re.sub(r'(<title>AI 简讯 · )\d{8}(</title>)', rf'\g<1>{ds}\g<2>', html)
    # 2) 封面副标题日期（原为回填日期）
    html = re.sub(r'(<div class="cover-subtitle">)\d{4}年\d{2}月\d{2}日 [周一二三四五六日]+',
                  rf'\g<1>{date_full}', html)
    # 3) 删长脚注 -> 底部居中 logo
    html = re.sub(r'<div class="cover-footnote">.*?</div>',
                  COVER_FOOT, html, count=1, flags=re.S)
    # 4) 各页脚两个 span 间插入居中 logo
    html = re.sub(r'(<div class="page-footer">\s*<span>[^<]*</span>)(\s*<span>)',
                  rf'\g<1>\n        {FOOTER_LOGO}\g<2>', html)
    # 5) 注入最新 CSS（覆盖旧 page-footer 的 flex 写法）
    html = html.replace("</style>", CSS_PATCH + "</style>", 1)

    p.write_text(html, encoding="utf-8")
    n = html.count('class="footer-logo"')
    print(f"[ok] {path} -> {date_full}（logo×{n}）")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("用法: python reskin_past.py <html> [<html> ...]")
    for f in sys.argv[1:]:
        reskin(f)

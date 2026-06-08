# 模板自定义

技能内置三套 HTML 模板，每天用最新数据填充。要改样式只动模板，逻辑不用碰。

## 文件对应

| 文件 | 渲染出 | 用途 |
|---|---|---|
| `assets/report.html` | `docs/{YYYYMMDD}.html` + PDF | A4 多页深度报告，封面 / 战略 / 行业 / 实践 / 大模型榜 |
| `assets/dashboard.html` | `docs/download/ai-brief-overview-{date}.png` | 1920×1080 16:9 总览大图（仪表盘） |
| `assets/card.html` | `docs/card.html` | 「分享到微信」的分享卡（标准） |
| `assets/card-pro.html` | `docs/card-pro.html` 与 `docs/card.html`（当前 build 配置） | 含 SO WHAT 影响价值点评的深度卡 |

## 占位符

`_render_card()` 替换：

```
{{DATE_DOT}}       → YYYYMMDD（钢印日期）
{{HOT_HEADLINE}}   → 当日 importance 最高一条的 headline
{{HOT_QUOTE}}      → 该条的 briefing 正文
{{HOT_MEANING}}    → 该条的 exec_meaning（SO WHAT 内容）
{{HOT_SOURCE}}     → 来源名（如 "华尔街见闻"）
{{HOT_STARS}}      → 重要度星级（★★★★★）
```

`render_report()` 和 `render_dashboard()` 用的占位符见 `scripts/render.py` 顶部。

## 卡片设计要点（当前稳定版）

| 元素 | 设计选择 |
|---|---|
| 形状 | 4:5 竖版，**用 `min-height` 而非严格 `aspect-ratio`** 避免长引文挤压 row-2 |
| 调色板 | 冷调灰蓝 + 钢蓝强调色（`--steel:#3a5a8c` / `--steel-soft:#7287a8`） |
| 字体栈 | 标题用 Didot / Bodoni 杂志衬线，中文回落 Songti SC；正文用 PingFang SC |
| 头部 | 「AI 简讯」标题左上 / 日期"钢印"右上（Bodoni + 三层 text-shadow）/ 副标 + 出品方一行 |
| 中心 | hot-box 毛玻璃面板（rgba(255,255,255,.5) + backdrop-filter:blur(14px)），含 BREAKING NEWS 标签 / 头条标题 / 引文（钢蓝高光横贯背景，上下羽化）/ 来源胶囊 |
| SO WHAT | 左侧 3px 钢蓝竖条 + 渐变底，编辑视角点评 |
| 底部 | 双码（今日资讯 + 往期下载）左下；logo 钉到右下角对角呼应日期 |
| 二维码 | 透明底（白格 alpha=0）让 QR "融入"卡片背景；ERROR_CORRECT_M、box_size 12 |

## 改字号 / 改色一行修改

```css
/* 卡片调色板（card-pro.html 顶部 :root） */
--steel: #3a5a8c;       /* 主强调色 */
--steel-soft: #7287a8;  /* 次强调 */
--ink: #1c2433;         /* 主文本 */
--bronze: #a38660;      /* 可选暖色点缀（早期用过；当前未启用） */

/* 标题字号 */
.title { font-size: 36px; }     /* 默认 36px，杂志感建议 32-40 */
```

## 改头条 / 标签文案

`assets/card-pro.html` 里直接搜索改：

```html
<div class="label">BREAKING NEWS</div>     <!-- 头条标签 -->
<div class="sw-label">SO WHAT</div>        <!-- 影响价值标签 -->
<div class="tagline">每日 AI 行业关键动向 · 战略 / 行业 / 实践</div>
<div class="by">由 招商金科 出品</div>
```

## 改二维码指向（必做之一）

二维码内嵌指向你站点的具体 URL。换站点必须重生成（不然扫码会跳到原作者）：

```bash
python3 -c "
import qrcode
from qrcode.constants import ERROR_CORRECT_M
def make(url, out):
    qr = qrcode.QRCode(error_correction=ERROR_CORRECT_M, box_size=12, border=2)
    qr.add_data(url); qr.make(fit=True)
    img = qr.make_image(fill_color='#1c2740', back_color='white').convert('RGBA')
    px = img.load(); w,h = img.size
    for y in range(h):
        for x in range(w):
            r,g,b,a = px[x,y]
            if r>235 and g>235 and b>235: px[x,y]=(r,g,b,0)
    img.save(out)
make('https://你账号.github.io/你repo/',           'docs/qr.png')
make('https://你账号.github.io/你repo/archive',    'docs/qr-archive.png')
make('https://你账号.github.io/你repo/download/',  'docs/qr-download.png')
"
```

> `.gitignore` 已放行 `docs/{logo,qr,qr-archive,qr-download}.png` 这几个特例。

## 截图分辨率

`build.py` 里：

| 产物 | 窗口尺寸 | DPR | 输出 PNG 像素 |
|---|---|---|---|
| 总览大图 | 1920×1080 | 2 | 3840×2160 |
| 卡片 | 580×900 | 2 | 1160×1800 |

调更大可改 `_screenshot` 的参数。卡片用 `min-height` 后高度会按内容生长，**窗口高度必须 ≥ 实际内容**否则会截掉底部。900 对当前模板留有余量。

## 改报告页脚 logo 位置

`assets/report.html` 的 `.page-footer`：

```css
.page-footer {
  display: grid;
  grid-template-columns: 1fr auto 1fr;  /* 关键：让中间 logo 真正居中，不被左/右文本宽度推偏 */
  align-items: center;
  ...
}
```

## 改卡片日期"钢印"效果强弱

```css
.date {
  font-family: "Bodoni 72","Didot","Playfair Display",Georgia,serif;
  font-size: 11.5px;             /* 字号——越小越像小印章 */
  letter-spacing: 1.5px;          /* 字距——印章感的关键 */
  color: rgba(58,90,140,.85);     /* 半透明让"印"轻一点 */
  text-shadow:
    0 1px 0 rgba(255,255,255,.75),   /* 顶部高光 */
    0 -1px 0 rgba(28,36,55,.12),     /* 底部暗影 */
    1px 1px 1px rgba(28,36,55,.08);  /* 1px 偏移阴影 */
}
```

三层 `text-shadow` 顺序决定"压"或"凸"——上白下黑 = 凸起，上黑下白 = 凹陷。

## 改卡片引文背景（钢蓝晕染带）

```css
.quote::before {
  position: absolute;
  top: -6px; bottom: -6px;
  left: -120px; right: -120px;        /* 横向延展，被 .card overflow:hidden 裁到卡片边 */
  background: linear-gradient(90deg,
    transparent 0%,
    rgba(58,90,140,.06) 8%,
    rgba(58,90,140,.16) 35%,           /* ← 峰值透明度，调强弱 */
    rgba(58,90,140,.16) 65%,
    rgba(58,90,140,.06) 92%,
    transparent 100%);
  mask: linear-gradient(180deg,       /* 上下羽化 */
    transparent 0%, #000 25%, #000 75%, transparent 100%);
}
```

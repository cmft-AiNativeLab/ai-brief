---
name: ai-brief-daily
description: 每日 AI 行业简讯生成与发布的完整流水线（抓取 → Claude 提炼 → 渲染 → GitHub Pages 发布）。当用户说「跑今日的 AI 简讯 / 日报」「生成 AI 简报」「更新分享卡片 / 总览图 / 7 天合辑」「自动每天 7:30 出 AI 日报」「让 cron 跑 AI 简讯」「调整卡片样式 / 模板」「回填历史卡片版式」「为高管做一份 AI 行业简报」「招商金科 AI 简讯」等表达时立即触发——即使用户只说「跑下日报」「更新卡片」上下文与 AI 行业资讯相关也应优先使用本技能。抓取 10 个中英文 AI 媒体 + artificialanalysis 大模型榜单近 24 小时内容，由 Claude/Qwen 按战略·行业·实践三维度精选 12 条（每源硬约束 ≤3 条），渲染 A4 多页 PDF 报告 + 16:9 总览大图 + 杂志竖版分享卡片（标准版 + 含 SO WHAT 影响价值点评的深度版），加近 7 天合辑 PDF 与下载主页，可选 git push 到 GitHub Pages 触发线上发布。
---

# AI 简讯 · 每日生成与发布技能

## 一句话

抓 10 个中英文 AI 来源 → Claude 提炼 12 条 + 摘要 + 行动建议 + 大模型榜 → 渲染网页/PDF/总览图/分享卡片 → 推 GitHub Pages → 落地 cron 每日 7:30 自动出报。

## 何时触发

- "跑下今天的 AI 简讯 / 日报"
- "生成今日 AI 简报 / AI 高管简报"
- "更新分享卡片 / 总览图 / 近 7 天合辑"
- "为领导做一份 AI 行业速递"
- "招商金科 AI 简讯 / 凯总日报"
- "AI 简讯 cron 没跑 / 每日 7:30 自动"
- "调整卡片样式 / 字体 / 配色 / 二维码"
- "回填历史卡片版式"
- 任何关于 AI 行业新闻汇总 + 自动发布的请求

## 核心工作流

```
                  ┌──────────────────────────────────────────┐
                  │  cron 7:30  →  run_daily.sh              │
                  │   ├─ 等代理 / 网络就绪                    │
                  │   ├─ python3 build.py --push              │
                  │   │    ├─ scripts/brief.py  抓取 10 源    │
                  │   │    │     + 大模型榜单                 │
                  │   │    ├─ scripts/curate_auto.py  Claude  │
                  │   │    │     精选 12 条 + 行动建议        │
                  │   │    └─ render.py + build.py 渲染:      │
                  │   │         · docs/{YYYYMMDD}.html        │
                  │   │         · docs/card{,-pro}.html       │
                  │   │         · docs/download/*.pdf/png     │
                  │   │         · docs/download/ai-brief-7days.pdf │
                  │   │         · docs/archive.html (往期列表)│
                  │   │         · docs/download/index.html    │
                  │   └─ git commit & push → GitHub Pages    │
                  └──────────────────────────────────────────┘
```

## 立即使用（已部署好的项目）

```bash
# 一次性手动跑（生成 + 推送）
python3 build.py --push

# 仅生成不推送（看完再决定）
python3 build.py

# 用已抓取的数据重新渲染（不重新抓取/不重新调 LLM）
python3 build.py --from-curated build/curated.json

# 回填历史卡片版式（统一到最新模板）
python3 scripts/backfill_cards.py            # 所有历史日期
python3 scripts/backfill_cards.py 20260607   # 仅指定日

# 历史日报 HTML 套用新模板（只换日期/logo/页脚，不重渲染正文）
python3 scripts/reskin_past.py docs/20260526.html docs/20260530.html
```

## 仓库初始化（首次使用）

详见 `references/publishing.md`。最简步骤：

1. `pip install -r requirements.txt`
2. 复制 `.env.example` → `.env`，填入 `AI_BRIEF_API_KEY`（中转或原生），`AI_BRIEF_MODEL`（推荐 `aly-qwen3.7-max` / `deepseek-v4-pro` / `claude-sonnet-4-7`，按中转可用渠道选）
3. `git remote add origin https://github.com/<你>/<repo>.git`
4. `git config --global credential.helper store` + 首次手动 push 把 PAT 落到 `~/.git-credentials`（cron 才能免交互推）
5. GitHub Pages 设置：从 `main` 分支 `/docs` 目录发布
6. 加 cron：`30 7 * * * /绝对路径/run_daily.sh`

## 模板与样式定制

详见 `references/customization.md`。要点：

- **报告（PDF/网页）**：`assets/report.html` —— A4 多页，封面 + 三维度 + 大模型榜单页，底部居中 logo
- **总览大图（PNG）**：`assets/dashboard.html` —— 1920×1080 16:9 仪表盘
- **分享卡片**：`assets/card-pro.html` —— 4:5 竖版杂志风（米杏纸感→冷调灰蓝、Didot 字体、BREAKING NEWS hot-box、SO WHAT 模块、双二维码、钢印日期、毛玻璃 + 内容居中）
- **标准卡片**：`assets/card.html` —— 同模板的另一份输出（当前 build.py 配置成两个 URL 都用 card-pro 模板）

技能内置的 `assets/card-pro.html` 是经过多次迭代的稳定版本：4:5 最小高度 + 内容自由生长（避免长引文挤压 row-2 副标）、引文带钢蓝晕染底色（横向延展到卡片边、上下羽化）、QR 双码（今日资讯 + 往期下载）、SO WHAT 影响价值点评（取自 `exec_meaning` 字段）。

## 关键设计决策

| 决策 | 说明 |
|---|---|
| 每源 ≤3 条 | `curate_auto.py` 的 `PER_SRC_CAP=6` 候选限流 + 提示词硬约束，避免单源（尤其 Hacker News）刷屏 |
| 中转模型 fallback | `aly-qwen3.7-max` / `qwen3.7-max` / `deepseek-v4-pro` / `aly-glm-5.1`；claude-* 视中转可用渠道决定，可用 `GET /v1/models` 查 |
| 流式 + 重试 | 大请求触发中转 504 时改流式 stream=True + retries=3 + 直连不走系统代理 |
| 卡片 min-height 而非严格 aspect-ratio | 严格 4:5 在长引文时挤压 row-3 致 hot-box 上溢覆盖 row-2 副标，改为最低 4:5、内容多时自由生长 |
| 卡片二维码透明底 | 用 PIL 把白格转 alpha=0，让二维码"融"进毛玻璃卡片（仍可扫） |
| 下载链接加 `?v=<md5前8位>` | 文件一变链接版本号即变，破微信/浏览器旧缓存 |
| 卡片日期"钢印"效果 | Bodoni/Didot + letter-spacing + 三层 text-shadow（上白高光 / 下暗影 / 1px 偏移）模拟金属印章压入纸面 |
| 报告每页底部居中 logo | 用 `grid 1fr/auto/1fr` 实现真正居中，左标题/中 logo/右页码 |
| 近 7 天合辑 PDF | `pypdf` 合并最近 7 天日报，往期缺的从 HTML 临时渲染补齐 |
| 历史卡片回填 | `scripts/backfill_cards.py` 反解 HTML 重建 curated 数据 → 套新模板重新生成 PNG，让所有历史卡视觉统一 |

## 文件结构

```
ai-brief-daily/
├── SKILL.md                          # 本文件
├── build.py                          # 主流水线编排
├── run_daily.sh                      # cron 调用入口（带网络等待+代理）
├── requirements.txt                  # python 依赖
├── .env.example                      # 配置示例（不进仓库的真实 .env）
├── scripts/
│   ├── brief.py                      # 抓取入口
│   ├── fetchers.py                   # 10 源 + 大模型榜抓取器
│   ├── curate_auto.py                # Claude/Qwen 提炼成 curated.json
│   ├── render.py                     # report/dashboard HTML 渲染 + PDF/PNG 导出
│   ├── gen_md.py                     # 可选：把 curated.json 转 Markdown
│   ├── reskin_past.py                # 一次性给历史 HTML 套最新模板
│   └── backfill_cards.py             # 反解历史 HTML，回填卡片 PNG
├── assets/
│   ├── report.html                   # A4 多页报告模板
│   ├── dashboard.html                # 16:9 总览模板
│   ├── card.html                     # 分享卡（标准/备用）
│   └── card-pro.html                 # 分享卡（深度版 + SO WHAT，当前主用）
├── docs/                             # 种子资源（运行时会写入更多）
│   ├── logo.png                      # 招商金科品牌（透明底 PNG）
│   ├── qr.png                        # 今日资讯二维码（透明底）
│   ├── qr-archive.png                # 往期列表二维码
│   └── qr-download.png               # 资料下载二维码
└── references/
    ├── publishing.md                 # 部署 / 凭据 / cron / 多账号
    └── customization.md              # 模板自定义 / 卡片样式 / 颜色 / 字体
```

## 触发示例

**Example 1** — 用户：「跑下今天的 AI 简讯」
→ `python3 build.py --push`，等 1–3 分钟，回报头条 + 来源分布，给出线上 URL

**Example 2** — 用户：「卡片字体换成 Didot 杂志封面风」
→ 改 `assets/card-pro.html` 的 `--display` 字体栈和 `.title` `.date` 字体；`_render_card` 用最新数据重渲染 → 截图 → push

**Example 3** — 用户：「20260607 的卡片不在下载页」
→ `scripts/backfill_cards.py 20260607` 反解 06-07 HTML，套最新模板重渲染卡片 + dashboard PNG + 用现有 HTML 直接 export_pdf；`_download_index` 重生成

**Example 4** — 用户：「调整每页底部 logo 居中位置」
→ 改 `assets/report.html` 的 `.page-footer` 用 `grid 1fr/auto/1fr` 让 logo 真正居中；`build.py --from-curated` 用已有数据快速重渲染验证

## 安全与隐私

- **绝不写 API key 到任何会 push 的文件**——`.env` 已被 `.gitignore`，只在本地
- `.env.example` 用占位值，提交可见
- `curate_auto.py` 启动会校验 key 必须是 ASCII（防中文占位泄漏 latin-1 错误）
- git push 凭据用 `credential.helper store`（明文 `~/.git-credentials`），仅本地，cron 可读
- 多账号场景：用 `git remote set-url origin https://<user>@github.com/<user>/<repo>.git` 内嵌用户名 → 推送时按 user 查 `~/.git-credentials`

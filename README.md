# AI 简讯 · 每日自动日报（本地生成 + GitHub Pages 发布）

每天本地抓取 10 个 AI 信息源 + 大模型榜单 → Claude 自动提炼成「战略/行业/实践」三维度 12 条简报 → 生成网页 → push 到 GitHub，GitHub Pages 自动更新。领导收藏一个固定链接，每天点开看最新一期、链接可点。

## 🔐 安全（务必先看）

- API key **只放 `.env`**（已被 `.gitignore`，不会进仓库）。**绝不要**把 key 写进任何会 push 的文件——公开仓库带 key 会被扫描盗刷。
- 本仓库可公开（GitHub Pages 免费版要求公开仓库）；公开的只是 `docs/` 里的网页，`.env` 不公开。

## 一、目录结构

```
ai-brief/
├─ scripts/        fetchers.py(抓取) · render.py(渲染) · brief.py(抓取CLI) · curate_auto.py(AI提炼)
├─ assets/         report.html(商务模板，HTML/PDF 共用)
├─ docs/           ← GitHub Pages 发布目录（index.html=最新, 日期.html=归档, archive.html=往期）
├─ build/          中间产物（已 gitignore）
├─ build.py        一键：抓取→提炼→渲染→写docs→push
├─ .env            你的密钥（不入库，自己建）
└─ requirements.txt
```

## 二、首次部署

```bash
cd ai-brief
# 1) 依赖
pip3 install -r requirements.txt
# 2) 密钥
cp .env.example .env        # 然后编辑 .env 填入真实 key
# 3) 关联到你的 GitHub 仓库（公开）
git init && git add . && git commit -m "init"
git branch -M main
git remote add origin https://github.com/<你的用户名>/<仓库名>.git
git push -u origin main
```

**配置 GitHub Pages**：仓库 → Settings → Pages → Build and deployment → Source 选 **Deploy from a branch** → Branch 选 **main**、目录选 **/docs** → Save。

约 1 分钟后链接生效：`https://<你的用户名>.github.io/<仓库名>/`（领导收藏这个）。

## 三、每天出一期

```bash
python3 build.py --push     # 抓取+提炼+渲染+推送，一条命令
```
推送后 GitHub Pages 自动更新，`index.html` 永远是最新一期，`archive.html` 是往期列表。

## 四、设成每天自动（本地定时）

**macOS（cron，最简）**：`crontab -e` 加一行（每天 08:30）：
```
30 8 * * * cd /绝对路径/ai-brief && /usr/bin/python3 build.py --push >> build.log 2>&1
```
> 用本地定时是因为：你的电脑在国内，抓国内源（量子位/虎嗅/新浪等）最全；GitHub 海外服务器抓国内源命中率低。需要电脑当天开机联网。

## 五、说明

- **提炼协议**：`curate_auto.py` 默认按 OpenAI 兼容 `/v1/chat/completions` 调用（new-api 中转标配）。若你的中转是 Anthropic 原生 `/v1/messages`，改 `call_llm` 即可。
- **不需要 Chrome**：发布走 HTML，`build.py` 只生成网页字符串；PNG/PDF 是另一套（需 Chrome），本流程用不到。
- **链接可点**：网页里每条标题与 URL 都是 `<a>`，浏览器/微信内置浏览器点击直接跳转。

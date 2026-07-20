# 部署与自动化（固定域名 + GitHub Pages + OpenClaw cron）

技能通过 `run_daily.sh` 统一完成生成、验证、固定域名原子发布、GitHub 推送和两端在线校验。

正式地址：`https://brief.ai-native-lab.com/`

GitHub Pages 备份：`https://cmft-AiNativeLab.github.io/ai-brief/`

## 1. GitHub Pages 站点

| 项 | 推荐配置 |
|---|---|
| 仓库 | `<你的账号>/<repo>`，建议公开仓便于他人无登录访问 |
| 分支 / 路径 | `main` 分支的 `/docs` 目录（Settings → Pages） |
| 站点地址 | `https://<account>.github.io/<repo>/` |
| 入口 URL | `/`（今日）`/<YYYYMMDD>`（指定日）`/archive`（往期）`/card`/`/card-pro`（分享卡）`/download/`（下载页） |

> GitHub Pages 默认支持无后缀 URL 解析（`/20260607` 自动命中 `20260607.html`）。

## 2. 多账号 / 凭据（让 cron 免交互推送）

### 单账号

```bash
git config --global credential.helper store
git push        # 首次交互输入 GitHub username + PAT，落入 ~/.git-credentials
```

之后 cron 调 `git push` 时会从 `~/.git-credentials` 自动读凭据（明文文件，仅本地保留，不入仓）。

### 多账号（推荐——避免污染默认账号）

```bash
git remote set-url origin https://<这个仓所属账号>@github.com/<同账号>/<repo>.git
```

URL 里内嵌 username。`credential.helper store` 会按 `(host, username)` 索引 PAT。这样不同仓可用不同 GitHub 账号推送，互不影响。

### 注意

- **不要**把 PAT 写到代码或 `.env` 任何 push 进仓的文件里
- `gh auth login` 用的是 keychain，cron **读不到**——必须用 `credential.helper store`

## 3. OpenClaw 定时任务

```bash
crontab -e
# 加这一行（改成你的绝对路径）：
30 7 * * * cd /绝对路径/ai-brief && bash run_daily.sh build
```

`run_daily.sh` 已经完成：
1. 互斥执行，防止主任务和看门狗并发覆盖；
2. 生成并强制验证上海时区当天产物；
3. 原子切换 `.deploy/current`，发布固定域名；
4. 提交并重试推送 GitHub；
5. 比对两个线上渠道的日期和 `latest.pdf` SHA-256。

08:15 看门狗调用 `bash run_daily.sh repair`。如果当天文件已完整，它只补发缺失渠道，不重复抓取或调用模型。

> 苹果电脑只在亮屏时执行 cron——长期运行需 caffeinate / 不睡眠 + 接电源。

## 4. 中转 API（LLM）配置

`.env` 里填：

```
AI_BRIEF_API_KEY=sk-xxxxxx
AI_BRIEF_BASE_URL=https://newapi.ai-native-lab.com    # 或其他兼容 OpenAI Chat 协议的中转
AI_BRIEF_MODEL=aly-qwen3.7-max                         # 注释里有更多候选
```

模型必须是中转「有可用渠道」的——用以下命令查可用列表：

```bash
curl -H "Authorization: Bearer $AI_BRIEF_API_KEY" $AI_BRIEF_BASE_URL/v1/models | jq '.data[].id'
```

如果遇到 **「分组 default 下模型 xxx 无可用渠道」** 503，说明配置的模型在中转上已下线，换个可用模型即可。`curate_auto.py` 默认会重试 3 次。

## 5. 故障排查

| 症状 | 排查 |
|---|---|
| cron 早间没出报 | `tail -50 build/daily.log` 看错误；常见原因：代理未就绪 / API 渠道下线 / 网络抖断 SSL_ERROR_SYSCALL |
| 微信打开 PDF/卡片是旧版 | 文件已更新但客户端缓存——下载链接已加 `?v=<md5前8位>` 自动破缓存；微信用「在浏览器打开」或退出重进 |
| push 被 reject | 远端有新提交（OpenClaw Bot/另一台机器）；`git fetch && git rebase origin/main`，冲突用 `git checkout --theirs` 偏向本地新版，再 `git push -c http.postBuffer=524288000` |
| 来源严重偏科（HN 占一半） | 已通过 `curate_auto.py PER_SRC_CAP=6` + 提示词硬约束修；如仍偏科，调小 PER_SRC_CAP 或在 fetchers 里调权 |

## 6. 验证清单（推送后 1 分钟）

```bash
for P in https://brief.ai-native-lab.com https://cmft-AiNativeLab.github.io/ai-brief; do
  for u in "" "20260608" "card" "card-pro" "archive" "download/" "download/latest.pdf"; do
  echo "$(curl -s -o /dev/null -w '%{http_code}' "$P/$u?v=$RANDOM")  /$u"
  done
done
```

所有都该返回 200。如果首页（`/`）日期不是今天，等 30s 再试（GitHub Pages 构建延迟）。

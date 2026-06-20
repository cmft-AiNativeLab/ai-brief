# AI Brief Analytics - 轻量埋点采集端点

Cloudflare Worker 实现，零成本、全球 CDN、自带 KV 存储。

## 采集事件

| 事件 | 触发时机 |
|------|----------|
| `page_view` | 每次打开页面 |
| `download_click` | 点击 PDF/PNG 下载链接 |
| `link_click` | 点击其他链接 |

## 部署步骤（5 分钟）

### 1. 安装 Wrangler CLI

```bash
npm install -g wrangler
```

### 2. 登录 Cloudflare

```bash
wrangler login
```

### 3. 创建 KV 命名空间

```bash
cd ~/.openclaw/workspace/skills/ai-brief-daily/analytics
wrangler kv:namespace create ANALYTICS
```

输出类似：
```
🌀 Creating namespace with title "ai-brief-analytics-ANALYTICS"
✨ Success!
Add the following to your configuration file in your kv_namespaces array:
{ binding = "ANALYTICS", id = "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx" }
```

把输出的 `id` 填入 `wrangler.toml` 中。

### 4. 设置 API Key（可选，用于查询统计）

```bash
wrangler secret put API_KEY
# 输入一个强密码
```

### 5. 部署

```bash
wrangler deploy
```

部署成功后会得到一个 URL，如：
```
https://ai-brief-analytics.xxx.workers.dev
```

### 6. 配置前端端点

编辑 `build.py`，把 `https://...` 替换为你的 Worker URL + `/track`：

```python
# build.py 第 31 行附近
window.AI_BRIEF_ANALYTICS_ENDPOINT = "https://ai-brief-analytics.xxx.workers.dev/track"
```

重新构建即可生效：
```bash
cd ~/.openclaw/workspace/skills/ai-brief-daily
python3 build.py --push
```

## 查询统计

```bash
# 查询最近 7 天
curl -H "Authorization: Bearer YOUR_API_KEY" \
  https://ai-brief-analytics.xxx.workers.dev/stats

# 查询特定日期
curl -H "Authorization: Bearer YOUR_API_KEY" \
  "https://ai-brief-analytics.xxx.workers.dev/stats?date=20260611"
```

## 自定义域名（可选）

如果想用自己的域名（如 `analytics.yourdomain.com`）：
1. 在 Cloudflare Dashboard → Workers → 你的 Worker → Settings → Domains & Routes
2. 添加自定义域名（需要域名 DNS 托管在 Cloudflare）

## 数据保留

- 原始事件：90 天自动过期
- 聚合计数：365 天自动过期

## 免费额度

Cloudflare Workers 免费版：
- 10 万次请求/天
- 1 GB KV 存储
- 足够日均几千 PV 的场景

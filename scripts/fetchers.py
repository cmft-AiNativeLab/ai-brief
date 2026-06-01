"""
10 个 AI 资讯源 + 1 个大模型榜单的抓取函数。

统一返回的条目结构：
{
    "source":       str,            # 媒体名 (e.g. "量子位")
    "title":        str,            # 标题
    "url":          str,            # 原文链接
    "published_at": datetime,       # UTC-aware
    "summary":      str,            # 摘要 (可空字符串)
    "image":        str | None,     # 封面图 URL
    "metrics": {                    # 各源原始热度信号（可能缺失）
        "views":     int | None,
        "comments":  int | None,
        "points":    int | None,    # 仅 HN
        "likes":     int | None,
    }
}

设计原则：
- 单源失败抛 RuntimeError，由 daily.py 捕获 + 打 warning + 继续其他源
- 时间统一转 UTC-aware
- 摘要做 HTML 标签剥离与长度截断（240 字以内）
"""
from __future__ import annotations

import json
import re
import time
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from typing import Any
from urllib.parse import urljoin

import feedparser
import requests
from bs4 import BeautifulSoup

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
)
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"}
TIMEOUT = 12


# ---------- utilities ----------

def _strip_html(s: str, max_len: int = 240) -> str:
    if not s:
        return ""
    text = BeautifulSoup(s, "lxml").get_text(" ", strip=True)
    text = re.sub(r"\s+", " ", unescape(text)).strip()
    if len(text) > max_len:
        text = text[: max_len - 1].rstrip() + "…"
    return text


def _to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _ts_ms_to_utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


# ---------- 1. 量子位 (RSS, 最稳) ----------

def fetch_qbitai() -> list[dict[str, Any]]:
    r = requests.get("https://www.qbitai.com/feed", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    feed = feedparser.parse(r.content)
    out = []
    for e in feed.entries[:30]:
        pub = None
        if getattr(e, "published_parsed", None):
            pub = _to_utc(datetime.fromtimestamp(time.mktime(e.published_parsed), tz=timezone.utc))
        elif getattr(e, "published", None):
            try:
                pub = _to_utc(parsedate_to_datetime(e.published))
            except Exception:
                pass
        if not pub:
            continue
        out.append({
            "source": "量子位",
            "title": e.title.strip(),
            "url": e.link,
            "published_at": pub,
            "summary": _strip_html(getattr(e, "summary", "")),
            "image": None,
            "metrics": {"views": None, "comments": None, "points": None, "likes": None},
        })
    return out


# ---------- 2. InfoQ (多 topic 扫描 + AI 关键词过滤) ----------
# InfoQ 没有专门的 AI 频道 topic_id，调研验证后选取这些 AI 内容浓度最高的 topic
INFOQ_TOPICS = [19, 147, 17, 120, 21, 15, 106, 125, 155, 8, 11, 108, 119]

AI_KEYWORDS = (
    "ai", "llm", "gpt", "claude", "anthropic", "openai", "deepseek", "qwen",
    "大模型", "智能体", "agent", "深度学习", "机器学习", "通义", "豆包", "kimi",
    "rag", "transformer", "向量", "扩散", "diffusion", "多模态", "推理模型",
    "embedding", "微调", "fine-tune", "agi", "humanoid", "具身",
)


def fetch_infoq() -> list[dict[str, Any]]:
    seen_aid = set()
    out = []
    for tid in INFOQ_TOPICS:
        try:
            r = requests.post(
                "https://www.infoq.cn/public/v1/article/getList",
                json={"size": 30, "type": 0, "id": tid},
                headers={**HEADERS, "Referer": "https://www.infoq.cn/topic/AI",
                         "Content-Type": "application/json"},
                timeout=TIMEOUT,
            )
            r.raise_for_status()
            for a in r.json().get("data") or []:
                aid = a.get("aid")
                if aid in seen_aid:
                    continue
                title = (a.get("article_title") or "").strip()
                summary = a.get("article_summary") or ""
                blob = (title + " " + summary).lower()
                if not any(k in blob for k in AI_KEYWORDS):
                    continue
                pub_ms = a.get("publish_time")
                if not pub_ms:
                    continue
                seen_aid.add(aid)
                uuid = a.get("uuid") or a.get("aid")
                out.append({
                    "source": "InfoQ",
                    "title": title,
                    "url": f"https://www.infoq.cn/article/{uuid}",
                    "published_at": _ts_ms_to_utc(int(pub_ms)),
                    "summary": _strip_html(summary),
                    "image": a.get("article_cover"),
                    "metrics": {
                        "views": a.get("views"),
                        "comments": a.get("comment_count"),
                        "points": None,
                        "likes": None,
                    },
                })
        except Exception:
            continue  # 单 topic 失败不影响其他
    return out


# ---------- 4. 新智元 (WP REST API) ----------

def fetch_xinzhiyuan() -> list[dict[str, Any]]:
    r = requests.get(
        "https://www.aiera.com.cn/wp-json/wp/v2/posts",
        params={"per_page": 20, "_embed": "wp:featuredmedia"},
        headers=HEADERS,
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for p in r.json():
        pub_raw = p.get("date_gmt") or p.get("date")
        if not pub_raw:
            continue
        try:
            pub = _to_utc(datetime.fromisoformat(pub_raw))
        except Exception:
            continue
        title = _strip_html(p.get("title", {}).get("rendered", ""))
        summary = _strip_html(p.get("excerpt", {}).get("rendered", ""))
        image = None
        try:
            media = (p.get("_embedded") or {}).get("wp:featuredmedia") or []
            if media:
                image = media[0].get("source_url")
        except Exception:
            pass
        out.append({
            "source": "新智元",
            "title": title,
            "url": p.get("link", ""),
            "published_at": pub,
            "summary": summary,
            "image": image,
            "metrics": {"views": None, "comments": None, "points": None, "likes": None},
        })
    return out


# ---------- 5. 36氪 AI 频道 (HTML 内嵌 JSON) ----------

def fetch_36kr() -> list[dict[str, Any]]:
    r = requests.get("https://36kr.com/information/AI/", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    m = re.search(r"window\.initialState\s*=\s*(\{.+?\})\s*;?\s*</script>", r.text, re.DOTALL)
    if not m:
        raise RuntimeError("36kr initialState JSON not found")
    data = json.loads(m.group(1))
    # 兼容路径：information.informationList.itemList / informationList
    item_list = (
        data.get("information", {}).get("informationList", {}).get("itemList")
        or data.get("informationList", {}).get("itemList")
        or []
    )
    out = []
    for it in item_list[:30]:
        tm = it.get("templateMaterial") or {}
        title = tm.get("widgetTitle") or it.get("title") or ""
        if not title:
            continue
        item_id = it.get("itemId") or tm.get("itemId")
        if not item_id:
            continue
        url = f"https://36kr.com/p/{item_id}"
        pub_ms = tm.get("publishTime") or it.get("publishTime")
        if not pub_ms:
            continue
        pub = _ts_ms_to_utc(int(pub_ms))
        out.append({
            "source": "36氪",
            "title": title.strip(),
            "url": url,
            "published_at": pub,
            "summary": _strip_html(tm.get("summary", "")),
            "image": tm.get("widgetImage"),
            "metrics": {
                "views": tm.get("statRead"),
                "comments": tm.get("statComment"),
                "points": None,
                "likes": tm.get("statPraise"),
            },
        })
    return out


# ---------- 6. Hacker News (Algolia API) ----------

def fetch_hackernews() -> list[dict[str, Any]]:
    # 近 24h 内、tag=story、查询 AI 相关关键词
    cutoff = int(time.time()) - 24 * 3600
    queries = ["AI", "LLM", "GPT", "Claude", "Anthropic", "OpenAI"]
    seen_ids = set()
    out = []
    for q in queries:
        # 单 query 重试 2 次（Algolia 偶发超时）
        r = None
        for attempt in range(2):
            try:
                r = requests.get(
                    "https://hn.algolia.com/api/v1/search",
                    params={
                        "tags": "story",
                        "query": q,
                        "hitsPerPage": 30,
                        "numericFilters": f"created_at_i>{cutoff}",
                    },
                    headers=HEADERS,
                    timeout=TIMEOUT,
                )
                r.raise_for_status()
                break
            except Exception:
                if attempt == 1:
                    r = None
                continue
        if r is None:
            continue  # 该 query 跳过，不让单次失败拖垮整源
        for h in r.json().get("hits", []):
            oid = h.get("objectID")
            if oid in seen_ids:
                continue
            seen_ids.add(oid)
            pub = datetime.fromtimestamp(h["created_at_i"], tz=timezone.utc)
            # 优先用原始 URL，没有就回退到 HN 讨论页
            url = h.get("url") or f"https://news.ycombinator.com/item?id={oid}"
            out.append({
                "source": "Hacker News",
                "title": (h.get("title") or "").strip(),
                "url": url,
                "published_at": pub,
                "summary": _strip_html(h.get("story_text") or ""),
                "image": None,
                "metrics": {
                    "views": None,
                    "comments": h.get("num_comments"),
                    "points": h.get("points"),
                    "likes": None,
                },
            })
    return out


# ---------- 7. 虎嗅 (内部 API + AI 关键词过滤) ----------

# 用于「商业/产业」中文媒体（虎嗅、IT之家、woshipm 等）的关键词过滤。
# 与 InfoQ 的 AI_KEYWORDS 区别：这里包括算力/机器人/智驾等产业延伸主题。
AI_BIZ_KEYWORDS = (
    "llm", "gpt", "claude", "anthropic", "openai", "deepseek", "qwen",
    "大模型", "智能体", "agent", "深度学习", "机器学习", "通义", "豆包", "kimi",
    "英伟达", "nvidia", "算力", "推理", "机器人", "humanoid", "具身",
    "自动驾驶", "数字人",
    "rag", "transformer", "多模态", "agi", "微调", "fine-tune",
)

# 单独的 AI 词根：因为 "ai" 子串会误命中 main / matebook / train 等，
# 用正则带词边界匹配，保留 "AI 时代"、"AI应用"、"AI公司" 等场景。
_AI_TOKEN_RE = re.compile(r"(?<![a-z])ai(?![a-z])", re.IGNORECASE)


def _ai_related(blob: str) -> bool:
    """命中 AI 关键词或带边界的 ai 词根。blob 必须 lower。"""
    if _AI_TOKEN_RE.search(blob):
        return True
    return any(k in blob for k in AI_BIZ_KEYWORDS)


def _safe_int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except Exception:
        return None


def fetch_huxiu() -> list[dict[str, Any]]:
    r = requests.post(
        "https://api-article.huxiu.com/web/article/articleList",
        data={"platform": "www", "pageSize": 30, "recommendTime": 0},
        headers={**HEADERS, "Origin": "https://www.huxiu.com",
                 "Referer": "https://www.huxiu.com/"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for a in (r.json().get("data") or {}).get("dataList") or []:
        title = (a.get("title") or "").strip()
        summary = (a.get("summary") or "").strip()
        blob = (title + " " + summary).lower()
        if not _ai_related(blob):
            continue
        ts = a.get("dateline")
        if not ts:
            continue
        try:
            pub = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except Exception:
            continue
        ci = a.get("count_info") or {}
        out.append({
            "source": "虎嗅",
            "title": title,
            "url": a.get("share_url") or f"https://m.huxiu.com/article/{a.get('aid')}.html",
            "published_at": pub,
            "summary": _strip_html(summary),
            "image": a.get("pic_path"),
            "metrics": {
                "views": _safe_int(ci.get("viewnum")),
                "comments": _safe_int(ci.get("commentnum")),
                "points": None,
                "likes": _safe_int(ci.get("agree")),
            },
        })
    return out


# ---------- 8. 钛媒体 (人工智能 tag 页 SSR HTML 解析) ----------

def fetch_tmtpost() -> list[dict[str, Any]]:
    r = requests.get(
        "https://www.tmtpost.com/tag/topic/299106",
        headers={**HEADERS, "Referer": "https://www.tmtpost.com/"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    text = r.text
    out = []
    # 标题链接用 <a class="_tit" href=...>title</a>
    title_pat = re.compile(
        r'<a class="_tit"[^>]*href="https://www\.tmtpost\.com/(\d{7,9})\.html"[^>]*>([^<]+)</a>'
    )
    # 时间戳藏在文章 cover img URL：/YYYY/MM/YYYYMMDDHHMMSSxxx.jpg
    ts_pat = re.compile(r'/\d{4}/\d{2}/(\d{14})\d*\.(?:jpg|jpeg|png|webp)')
    cn_tz = timezone(timedelta(hours=8))
    seen_ids: set[str] = set()
    matches = list(title_pat.finditer(text))
    for i, m in enumerate(matches):
        aid, title = m.group(1), m.group(2).strip()
        if aid in seen_ids:
            continue
        seen_ids.add(aid)
        # 块范围：从上一个标题之后到下一个标题之前
        block_start = matches[i - 1].end() if i > 0 else max(0, m.start() - 800)
        block_end = matches[i + 1].start() if i + 1 < len(matches) else m.end() + 800
        block = text[block_start:block_end]
        ts_m = ts_pat.search(block)
        if not ts_m:
            continue
        try:
            pub = datetime.strptime(ts_m.group(1), "%Y%m%d%H%M%S").replace(tzinfo=cn_tz).astimezone(timezone.utc)
        except Exception:
            continue
        out.append({
            "source": "钛媒体",
            "title": _strip_html(title),
            "url": f"https://www.tmtpost.com/{aid}.html",
            "published_at": pub,
            "summary": "",  # 列表页不带详细摘要；让 Claude 在 curate 阶段从标题推断
            "image": None,
            "metrics": {"views": None, "comments": None, "points": None, "likes": None},
        })
        if len(out) >= 25:
            break
    return out


def _parse_relative_cn_time(s: str, now: datetime) -> datetime | None:
    m = re.search(r"(\d+)\s*分钟前", s)
    if m:
        return now - timedelta(minutes=int(m.group(1)))
    m = re.search(r"(\d+)\s*小时前", s)
    if m:
        return now - timedelta(hours=int(m.group(1)))
    m = re.search(r"(\d+)\s*天前", s)
    if m:
        return now - timedelta(days=int(m.group(1)))
    return None


# ---------- 9. AIbase (首页 NUXT payload：a 标签取 id+标题，payload 取时间) ----------
# NUXT3 dedup payload 标题与 id/time 不顺序对应，故只取「有内联标题的 <a>」+ id→time 映射，
# 拿到 URL/时间精确的优质条目（每次约 5–9 条）。

def fetch_aibase() -> list[dict[str, Any]]:
    r = requests.get("https://www.aibase.cn/", headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    html = r.text
    cn_tz = timezone(timedelta(hours=8))
    # id -> 时间（payload 内 28481,"2026-05-29 17:01:15"）
    time_map: dict[str, str] = {}
    for nid, tm in re.findall(r'(\d{5,7}),"(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"', html):
        time_map.setdefault(nid, tm)
    out, seen = [], set()
    # <a href="...news.aibase.cn/news/ID" ...>标题</a>
    for nid, title in re.findall(
        r'news\.aibase\.cn/news/(\d+)"[^>]*>([^<]{6,100})</a>', html
    ):
        if nid in seen:
            continue
        seen.add(nid)
        tm = time_map.get(nid)
        if not tm:
            continue
        try:
            pub = datetime.strptime(tm, "%Y-%m-%d %H:%M:%S").replace(tzinfo=cn_tz).astimezone(timezone.utc)
        except Exception:
            continue
        title = unescape(title).strip()
        if not _ai_related(title.lower()) and "AI" not in title:
            # aibase 全站 AI 媒体，标题多不含关键词也属 AI，这里放宽：默认收
            pass
        out.append({
            "source": "AIbase",
            "title": title,
            "url": f"https://news.aibase.cn/news/{nid}",
            "published_at": pub,
            "summary": "",
            "image": None,
            "metrics": {"views": None, "comments": None, "points": None, "likes": None},
        })
    return out


# ---------- 10. 新浪财经·科技 (roll API + AI 过滤) ----------
# 替代财联社（财联社 50101 风控难稳定）。财经/科技/A股视角，老牌稳定。

def fetch_sina() -> list[dict[str, Any]]:
    r = requests.get(
        "https://feed.mix.sina.com.cn/api/roll/get",
        params={"pageid": "153", "lid": "2515", "num": "50", "page": "1"},
        headers=HEADERS, timeout=TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for d in (r.json().get("result") or {}).get("data") or []:
        title = (d.get("title") or "").strip()
        intro = (d.get("intro") or d.get("summary") or "").strip()
        blob = (title + " " + intro).lower()
        if not _ai_related(blob):
            continue
        ct = d.get("ctime")
        if not ct:
            continue
        try:
            pub = datetime.fromtimestamp(int(ct), tz=timezone.utc)
        except Exception:
            continue
        out.append({
            "source": "新浪财经",
            "title": title,
            "url": d.get("url") or d.get("wapurl") or "",
            "published_at": pub,
            "summary": _strip_html(intro),
            "image": None,
            "metrics": {"views": None, "comments": None, "points": None, "likes": None},
        })
    return out


# ---------- 11. 华尔街见闻 (7x24 快讯 API + AI 过滤) ----------
# 财经/政策/A股视角，补「管理者最关心的钱与政策」。快讯多无标题，用正文兜底。

def fetch_wallstreetcn() -> list[dict[str, Any]]:
    r = requests.get(
        "https://api-one-wscn.awtmt.com/apiv1/content/lives",
        params={"channel": "global-channel", "limit": 100},
        headers={**HEADERS, "Referer": "https://wallstreetcn.com/"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    out = []
    for it in (r.json().get("data") or {}).get("items") or []:
        title = (it.get("title") or "").strip()
        content = (it.get("content_text") or "").strip()
        blob = (title + " " + content).lower()
        if not _ai_related(blob):
            continue
        ts = it.get("display_time")
        if not ts:
            continue
        try:
            pub = datetime.fromtimestamp(int(ts), tz=timezone.utc)
        except Exception:
            continue
        out.append({
            "source": "华尔街见闻",
            "title": title or content[:40],
            "url": it.get("uri") or f"https://wallstreetcn.com/livenews/{it.get('id')}",
            "published_at": pub,
            "summary": _strip_html(content),
            "image": None,
            "metrics": {"views": None, "comments": _safe_int(it.get("comment_count")),
                        "points": None, "likes": None},
        })
    return out


# ---------- 大模型榜单 (artificialanalysis.ai，独立于新闻源) ----------
# 不进 SOURCES（非新闻），由 brief.py 单独调用，附在报告最后一页。
# 数据在页面 Next.js RSC payload 的 "models":[...] 数组里（含 intelligenceIndex）。

def fetch_model_leaderboard(top_n: int = 20) -> list[dict[str, Any]]:
    r = requests.get(
        "https://artificialanalysis.ai/leaderboards/models",
        headers={**HEADERS, "Accept": "text/html"}, timeout=TIMEOUT + 6,
    )
    r.raise_for_status()
    html = r.text
    # 定位含 intelligenceIndex 的那个 models 数组（页面里另有一个精简版无 II）
    ii_pos = html.find("intelligenceIndex")
    if ii_pos < 0:
        raise RuntimeError("intelligenceIndex not found in AA page")
    mstart = html.rfind('\\"models\\":[', 0, ii_pos)
    if mstart < 0:
        raise RuntimeError("models array not found")
    start = html.find("[", mstart)
    depth, end = 0, start
    for j in range(start, len(html)):
        c = html[j]
        if c == "[":
            depth += 1
        elif c == "]":
            depth -= 1
            if depth == 0:
                end = j + 1
                break
    arr = json.loads(html[start:end].replace('\\"', '"').replace("\\\\", "\\"))
    active = [
        x for x in arr
        if not x.get("deprecated") and x.get("intelligenceIndex") is not None
    ]
    active.sort(key=lambda x: -x["intelligenceIndex"])
    out = []
    for rank, x in enumerate(active[:top_n], 1):
        out.append({
            "rank": rank,
            "name": x.get("name") or x.get("shortName") or "?",
            "creator": x.get("modelCreatorName") or "",
            "country": (x.get("modelCreatorCountry") or "").upper(),
            "intelligence": round(float(x["intelligenceIndex"]), 1),
            "reasoning": bool(x.get("isReasoning") or x.get("reasoningModel")),
            # 每百万 token 价格（美元）：输入 / 输出
            "price_in": x.get("price1mInputTokens"),
            "price_out": x.get("price1mOutputTokens"),
        })
    return out


# ---------- registry ----------
# 用户指定 10 源（2026-05）：aibase + 量子位 + InfoQ + 新智元 + 36氪 + HN
#   + 虎嗅 + 钛媒体 + 新浪财经(替代财联社风控) + 华尔街见闻。
# 另含独立的 fetch_model_leaderboard（大模型榜单，不在 SOURCES）。

SOURCES: dict[str, Any] = {
    "aibase":       fetch_aibase,
    "qbitai":       fetch_qbitai,
    "infoq":        fetch_infoq,
    "xinzhiyuan":   fetch_xinzhiyuan,
    "kr36":         fetch_36kr,
    "hackernews":   fetch_hackernews,
    "huxiu":        fetch_huxiu,
    "tmtpost":      fetch_tmtpost,
    "sina":         fetch_sina,
    "wallstreetcn": fetch_wallstreetcn,
}

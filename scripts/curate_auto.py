#!/usr/bin/env python3
"""自动提炼：读 fetch JSON → 调 LLM → 写 curated JSON（替代人工 curate）。

选 12 条（每维度 4）、打分、写 headline/briefing/exec_meaning + 顶层摘要与行动建议。
保留 leaderboard 原样。

环境变量：
  AI_BRIEF_API_KEY   (必需) 中转 / Anthropic key
  AI_BRIEF_BASE_URL  (默认 https://newapi.ai-native-lab.com)
  AI_BRIEF_MODEL     (默认 claude-opus-4-7)

用法: python curate_auto.py <fetch.json> <curated.json>

注：默认按 OpenAI 兼容协议 /v1/chat/completions 调用（new-api 中转标配）。
若你的中转是 Anthropic 原生 /v1/messages，把 call_llm 换成对应格式即可。
"""
import os
import re
import sys
import json
import time
import requests
from collections import Counter

BASE_URL = os.environ.get("AI_BRIEF_BASE_URL", "https://newapi.ai-native-lab.com").rstrip("/")
API_KEY = os.environ.get("AI_BRIEF_API_KEY", "")
MODEL = os.environ.get("AI_BRIEF_MODEL", "claude-opus-4-7")
MAX_CAND = 50  # 传给 LLM 的候选上限（太多会让单次生成过久、触发中转 504）
PER_SRC_CAP = 6  # 候选阶段每来源最多 N 条：避免高频源（如 Hacker News）淹没候选池导致选稿偏科

SYSTEM = (
    "你是面向企业高层管理者的 AI 资讯主编。从候选 AI 资讯中，以「管理者视角」精选并加工成每日简报。"
    "判断标准：对行业格局 / 战略决策 / 经营管理有实际意义；剔除纯技术细节、营销软文、重复事件。"
    "务必只输出 JSON，不要任何解释，不要 markdown 代码块标记。"
)

USER_TMPL = """今天的候选 AI 资讯（JSON 数组，每条含 id/source/title/summary）：

{candidates}

请完成：
1. 精选 12 条，分到三个维度，每维度 4 条：
   - strategy 战略动向（巨头 / 融资并购 / 模型发布 / 技术路线）
   - industry 行业影响（颠覆某行业 / 岗位与招聘 / 市场格局 / 政策监管）
   - practice 管理实践（企业部署 / ROI / 团队协作 / AI 工具落地 / 安全治理）
2. 源分布必须均衡：任一 source 最多 3 条（硬性约束，务必遵守），并尽量覆盖更多不同来源（理想 ≥6 个源）。
3. 每条写：
   - importance：1-5 整数（5 = 高管必看：影响格局 / 重大金额 / 政策级）
   - headline：中文 12-22 字，讲清"发生了什么"，不标题党，英文源必须翻译成中文
   - briefing：中文 40-80 字，"发生了什么 + 关键数据"
   - exec_meaning：中文 30-60 字，回答"对管理者意味着什么（So What）"——会改变什么格局、要警惕什么风险或抓住什么机会，忌空话
4. 顶层：
   - executive_summary：中文 80-150 字，概括"今天对管理者最值得关注的 3 件事"
   - action_items：3-4 条，每条中文 20-40 字、可立即执行，忌"关注 AI / 保持学习"这类空话

只输出如下 JSON（不要 markdown、不要解释）：
{{"picks":[{{"id":<int>,"dimension":"strategy|industry|practice","importance":<int>,"headline":"...","briefing":"...","exec_meaning":"..."}}],"executive_summary":"...","action_items":["...","..."]}}
"""


def call_llm(candidates, retries=3):
    """流式调用：边收边拼，避免大请求触发中转网关 504；失败自动重试。"""
    body = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": USER_TMPL.format(
                candidates=json.dumps(candidates, ensure_ascii=False))},
        ],
        "temperature": 0.4,
        "max_tokens": 4096,
        "stream": True,
    }
    # 中转 API 直连：不走系统代理（fetch 海外源才需代理，二者分开，互不干扰）
    session = requests.Session()
    session.trust_env = False
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    last_err = None
    for attempt in range(1, retries + 2):
        try:
            print(f"[i] 正在调用 Claude 提炼…（第 {attempt} 次 · 约 1–3 分钟，请勿按 Ctrl+C 中断）",
                  file=sys.stderr, flush=True)
            r = session.post(f"{BASE_URL}/v1/chat/completions",
                             headers=headers, json=body, timeout=(20, 100), stream=True)
            r.raise_for_status()
            parts = []
            for raw in r.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8", "ignore").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                    if delta:
                        parts.append(delta)
                except Exception:
                    continue
            text = "".join(parts).strip()
            if text:
                return text
            last_err = "空响应"
        except Exception as e:
            last_err = e
        print(f"[warn] LLM 第 {attempt} 次失败，重试…（{str(last_err)[:100]}）", file=sys.stderr)
        if attempt <= retries:
            time.sleep(2)
    raise RuntimeError(f"LLM 调用失败（已重试 {retries} 次）: {last_err}")


def extract_json(text):
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.S)
    i, j = text.find("{"), text.rfind("}")
    if i < 0 or j < 0:
        raise ValueError("LLM 未返回 JSON：" + text[:200])
    return json.loads(text[i:j + 1])


def main():
    if not API_KEY:
        sys.exit("ERROR: 未设置 AI_BRIEF_API_KEY（请配 .env 或环境变量）")
    if not API_KEY.isascii() or "你的" in API_KEY or "填" in API_KEY:
        sys.exit("ERROR: AI_BRIEF_API_KEY 还是占位值或含中文——请在 .env 里把它改成真实 key"
                 "（纯英文 / 数字，整行不要有中文）。")
    if len(sys.argv) < 3:
        sys.exit("用法: python curate_auto.py <fetch.json> <curated.json>")
    src, dst = sys.argv[1], sys.argv[2]
    data = json.loads(open(src, encoding="utf-8").read())
    items = data["items"]

    # 候选池按来源限流，保证多样性（items 已按时间倒序，每来源取最新若干）
    per_src, cand = {}, []
    for it in items:
        s = it.get("source", "")
        if per_src.get(s, 0) >= PER_SRC_CAP:
            continue
        per_src[s] = per_src.get(s, 0) + 1
        cand.append({"id": it["id"], "source": s, "title": it["title"],
                     "summary": (it.get("summary") or "")[:140]})
        if len(cand) >= MAX_CAND:
            break
    result = extract_json(call_llm(cand))

    for it in items:
        it["dimension"] = None
        it["importance"] = it.get("importance") or 1
    by_id = {it["id"]: it for it in items}
    for p in result.get("picks", []):
        it = by_id.get(p.get("id"))
        if not it:
            continue
        it["dimension"] = p.get("dimension")
        it["importance"] = int(p.get("importance") or 3)
        it["headline"] = p.get("headline") or it["title"]
        it["briefing"] = p.get("briefing") or ""
        it["exec_meaning"] = p.get("exec_meaning") or ""
    data["executive_summary"] = result.get("executive_summary", "")
    data["action_items"] = result.get("action_items", [])

    with open(dst, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    picked = [it for it in items if it["dimension"]]
    print(f"[ok] curated {len(picked)} items -> {dst}")
    print("  dims:", dict(Counter(it["dimension"] for it in picked)))
    print("  sources:", dict(Counter(it["source"] for it in picked)))


if __name__ == "__main__":
    main()

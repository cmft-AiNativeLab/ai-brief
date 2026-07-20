#!/usr/bin/env python3
"""验证固定域名与 GitHub Pages 都已发布当天同一份日报。"""

import argparse
import datetime
import hashlib
import os
from pathlib import Path
import ssl
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def china_today():
    tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz).strftime("%Y%m%d")


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fetch(base, path):
    separator = "&" if "?" in path else "?"
    url = f"{base.rstrip('/')}/{path.lstrip('/')}{separator}v={time.time_ns()}"
    request = Request(url, headers={"User-Agent": "ai-brief-publish-check/1.0"})
    with urlopen(request, timeout=25, context=ssl.create_default_context()) as response:
        if response.status != 200:
            raise RuntimeError(f"{url} HTTP {response.status}")
        return response.read()


def verify_once(base, date):
    home = fetch(base, "/")
    if date.encode("ascii") not in home:
        raise RuntimeError(f"首页未包含 {date}")
    dated = fetch(base, f"/{date}")
    if date.encode("ascii") not in dated:
        raise RuntimeError(f"/{date} 未包含当天日期")
    download = fetch(base, "/download/")
    if date.encode("ascii") not in download:
        raise RuntimeError(f"下载页未包含 {date}")
    local_pdf = (DOCS / "download" / "latest.pdf").read_bytes()
    remote_pdf = fetch(base, "/download/latest.pdf")
    if sha256(remote_pdf) != sha256(local_pdf):
        raise RuntimeError("latest.pdf 与本地产物 SHA-256 不一致")


def verify_channel(name, base, date, attempts, interval):
    error = None
    for attempt in range(1, attempts + 1):
        try:
            verify_once(base, date)
            print(f"[ok] {name}: {base} 已发布 {date}，latest.pdf 一致")
            return True
        except (HTTPError, URLError, TimeoutError, OSError, RuntimeError) as exc:
            error = exc
            print(f"[wait] {name} 第 {attempt}/{attempts} 次未就绪：{exc}", file=sys.stderr)
            if attempt < attempts:
                time.sleep(interval)
    print(f"[fail] {name}: {error}", file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--channel", choices=("fixed", "github", "all"), default="all")
    parser.add_argument("--date", default=china_today())
    parser.add_argument("--attempts", type=int, default=1)
    parser.add_argument("--interval", type=int, default=5)
    args = parser.parse_args()
    channels = {
        "fixed": os.environ.get("AI_BRIEF_SITE_URL", "https://brief.ai-native-lab.com"),
        "github": os.environ.get(
            "AI_BRIEF_GITHUB_PAGES_URL",
            "https://cmft-AiNativeLab.github.io/ai-brief",
        ),
    }
    selected = channels.items() if args.channel == "all" else [(args.channel, channels[args.channel])]
    ok = True
    for name, base in selected:
        ok = verify_channel(name, base, args.date, max(1, args.attempts), max(1, args.interval)) and ok
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""为固定域名生成首页、归档和下载中心二维码。"""

import os
from pathlib import Path

import qrcode


ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def make(url, output):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=4,
    )
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color="#172033", back_color="white").convert("RGB")
    image.save(output, optimize=True)
    print(f"[ok] {output.relative_to(ROOT)} -> {url}")


def main():
    load_env()
    base = os.environ.get("AI_BRIEF_SITE_URL", "https://brief.ai-native-lab.com").rstrip("/")
    make(f"{base}/", DOCS / "qr.png")
    make(f"{base}/archive", DOCS / "qr-archive.png")
    make(f"{base}/download/", DOCS / "qr-download.png")


if __name__ == "__main__":
    main()

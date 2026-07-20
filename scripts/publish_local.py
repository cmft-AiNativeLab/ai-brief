#!/usr/bin/env python3
"""把已验证的 docs 原子发布到固定域名静态目录。"""

import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"


def china_today():
    tz = datetime.timezone(datetime.timedelta(hours=8))
    return datetime.datetime.now(tz).strftime("%Y%m%d")


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_fingerprint(root):
    digest = hashlib.sha256()
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_hash(path).encode("ascii"))
        digest.update(b"\0")
    return digest.hexdigest()


def verify_source(date):
    required = {
        DOCS / "index.html": 500,
        DOCS / f"{date}.html": 500,
        DOCS / "download" / f"ai-brief-{date}.pdf": 50_000,
        DOCS / "download" / f"ai-brief-overview-{date}.png": 100_000,
        DOCS / "download" / f"ai-brief-card-{date}.png": 50_000,
        DOCS / "download" / "latest.pdf": 50_000,
        DOCS / "download" / "latest-overview.png": 100_000,
        DOCS / "download" / "latest-card.png": 50_000,
        DOCS / "download" / "ai-brief-7days.pdf": 100_000,
        DOCS / "download" / "index.html": 500,
    }
    bad = [
        f"{path.relative_to(ROOT)}（缺失或小于 {minimum} bytes）"
        for path, minimum in required.items()
        if not path.exists() or path.stat().st_size < minimum
    ]
    if (DOCS / "index.html").exists():
        text = (DOCS / "index.html").read_text(encoding="utf-8", errors="ignore")
        if date not in text:
            bad.append(f"docs/index.html（未包含 {date}）")
    aliases = {
        "latest.pdf": f"ai-brief-{date}.pdf",
        "latest-overview.png": f"ai-brief-overview-{date}.png",
        "latest-card.png": f"ai-brief-card-{date}.png",
    }
    for alias, dated in aliases.items():
        latest_path = DOCS / "download" / alias
        dated_path = DOCS / "download" / dated
        if latest_path.exists() and dated_path.exists() and file_hash(latest_path) != file_hash(dated_path):
            bad.append(f"docs/download/{alias}（与 {dated} 内容不一致）")
    if bad:
        raise RuntimeError("拒绝发布不完整产物：\n- " + "\n- ".join(bad))


def current_fingerprint(current):
    manifest = current / ".release.json"
    if current.is_dir() and manifest.exists():
        try:
            return json.loads(manifest.read_text(encoding="utf-8")).get("fingerprint")
        except (OSError, ValueError):
            return None
    return None


def publish(date, deploy_root, keep):
    verify_source(date)
    deploy_root.mkdir(parents=True, exist_ok=True)
    releases = deploy_root / "releases"
    releases.mkdir(exist_ok=True)
    lock_path = deploy_root / ".publish.lock"
    with lock_path.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        fingerprint = tree_fingerprint(DOCS)
        current = deploy_root / "current"
        if current_fingerprint(current) == fingerprint:
            print(f"[ok] 固定域名发布目录已是 {date} / {fingerprint[:12]}，无需切换")
            return

        stamp = datetime.datetime.now().strftime("%H%M%S")
        name = f"{date}-{stamp}-{os.getpid()}"
        staging = releases / f".{name}.tmp"
        release = releases / name
        try:
            shutil.copytree(DOCS, staging)
            copied_fingerprint = tree_fingerprint(staging)
            if copied_fingerprint != fingerprint:
                raise RuntimeError("复制后的目录指纹不一致")
            manifest = {
                "date": date,
                "fingerprint": fingerprint,
                "published_at": datetime.datetime.now(
                    datetime.timezone(datetime.timedelta(hours=8))
                ).isoformat(),
            }
            (staging / ".release.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            os.replace(staging, release)

            next_link = deploy_root / ".current.next"
            next_link.unlink(missing_ok=True)
            os.symlink(Path("releases") / name, next_link)
            if current.exists() and not current.is_symlink():
                raise RuntimeError(f"{current} 已存在且不是符号链接")
            os.replace(next_link, current)
            print(f"[ok] 固定域名已原子切换到 {name} / {fingerprint[:12]}")
        finally:
            if staging.exists():
                shutil.rmtree(staging)

        targets = sorted(
            (path for path in releases.iterdir() if path.is_dir() and not path.name.startswith(".")),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for old in targets[keep:]:
            if current.resolve() != old.resolve():
                shutil.rmtree(old)
                print(f"[ok] 清理旧版本 {old.name}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", default=china_today())
    parser.add_argument(
        "--deploy-root",
        type=Path,
        default=Path(os.environ.get("AI_BRIEF_DEPLOY_ROOT", ROOT / ".deploy")),
    )
    parser.add_argument("--keep", type=int, default=7)
    args = parser.parse_args()
    if not (len(args.date) == 8 and args.date.isdigit()):
        raise SystemExit("--date 必须是 YYYYMMDD")
    publish(args.date, args.deploy_root.resolve(), max(2, args.keep))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[fail] 本地固定域名发布失败：{exc}", file=sys.stderr)
        raise SystemExit(1)

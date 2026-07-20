#!/usr/bin/env bash
# AI 简讯 · OpenClaw 双渠道每日发布入口
set -u
set -o pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || exit 1
mkdir -p build .deploy

LOG="$ROOT/build/daily.log"
exec > >(tee -a "$LOG") 2>&1

MODE="${1:-build}"
case "$MODE" in
  build|repair|publish) ;;
  *) echo "[fatal] 用法: $0 [build|repair|publish]"; exit 2 ;;
esac

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
TODAY="$(TZ=Asia/Shanghai date +%Y%m%d)"

exec 9>".deploy/run.lock"
if ! flock -w 900 9; then
  echo "[fatal] 等待另一个日报任务结束超时"
  exit 1
fi

echo "===== $(date '+%F %T') 开始 mode=$MODE date=$TODAY ====="

curated_is_today() {
  [ -f build/curated.json ] && "$PYTHON_BIN" - "$TODAY" <<'PY'
import json
import sys
from pathlib import Path
date = sys.argv[1]
try:
    value = json.loads(Path("build/curated.json").read_text(encoding="utf-8"))
    generated = (value.get("generated_at") or "")[:10].replace("-", "")
except Exception:
    raise SystemExit(1)
raise SystemExit(0 if generated == date else 1)
PY
}

verify_today() {
  "$PYTHON_BIN" build.py --verify-only --date "$TODAY"
}

render_or_build() {
  if [ "$MODE" = "repair" ] && verify_today; then
    echo "[ok] 当天构建产物已存在，repair 不重复抓取或调用模型"
    return 0
  fi
  bash scripts/ensure_chrome_deps.sh || return 1
  if [ "$MODE" = "repair" ] && curated_is_today; then
    echo "[repair] 使用当天 curated.json 补渲染"
    "$PYTHON_BIN" build.py --from-curated build/curated.json
    return $?
  fi
  echo "[build] 开始抓取、提炼和渲染"
  if "$PYTHON_BIN" build.py; then
    return 0
  fi
  echo "[warn] 完整构建失败，尝试恢复"
  if curated_is_today; then
    "$PYTHON_BIN" build.py --from-curated build/curated.json
  else
    sleep 30
    "$PYTHON_BIN" build.py
  fi
}

if [ "$MODE" != "publish" ]; then
  if ! render_or_build; then
    echo "[fatal] 日报生成失败"
    exit 1
  fi
fi

if ! verify_today; then
  echo "[fatal] 当天产物验证失败，两个渠道均不发布"
  exit 1
fi

STATUS=0
if "$PYTHON_BIN" scripts/publish_local.py --date "$TODAY"; then
  "$PYTHON_BIN" scripts/verify_channels.py \
    --channel fixed --date "$TODAY" --attempts 12 --interval 5 || STATUS=1
else
  STATUS=1
fi

if "$PYTHON_BIN" build.py --push-only --date "$TODAY"; then
  "$PYTHON_BIN" scripts/verify_channels.py \
    --channel github --date "$TODAY" --attempts 20 --interval 15 || STATUS=1
else
  STATUS=1
fi

if [ "$STATUS" -eq 0 ]; then
  echo "===== $(date '+%F %T') 结束 ✓ 固定域名与 GitHub Pages 均已更新 ====="
else
  echo "===== $(date '+%F %T') 结束 ✗ 至少一个发布渠道未通过，请由 watchdog 补发 ====="
fi
exit "$STATUS"

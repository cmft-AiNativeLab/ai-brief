#!/bin/bash
# AI 简讯 · 每日自动构建 + 发布（供 cron 调用）
# 关键：cron 环境不继承交互终端，这里显式补上 PATH 和代理。
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"
export HTTP_PROXY="http://127.0.0.1:7897"
export HTTPS_PROXY="http://127.0.0.1:7897"
# 中转 API（newapi）若在国内、走代理反而不通，可解除下一行注释让它直连：
# export NO_PROXY="newapi.ai-native-lab.com"

cd "$(dirname "$0")" || exit 1
mkdir -p build
echo "===== $(date '+%F %T') 开始 =====" >> build/daily.log

# ── Step 0: 确保 Chrome 渲染依赖存在 ──
# 容器重启后 /tmp/libs 可能被清空，此脚本自动检测并恢复
echo "$(date '+%F %T') [Step 0] 检查 Chrome 依赖..." >> build/daily.log
bash scripts/ensure_chrome_deps.sh >> build/daily.log 2>&1
if [ $? -ne 0 ]; then
    echo "$(date '+%F %T') [error] Chrome 依赖安装失败，中止构建！" >> build/daily.log
    exit 1
fi

# 等网络/代理就绪（电脑睡眠唤醒后 Clash 自启需时间），最多等 ~5 分钟
for i in $(seq 1 20); do
  if /usr/bin/curl -s --max-time 8 -o /dev/null https://github.com; then
    echo "$(date '+%F %T') 网络就绪（第 $i 次探测）" >> build/daily.log; break
  fi
  echo "$(date '+%F %T') 网络/代理未就绪，等待…($i)" >> build/daily.log
  sleep 15
done

# ── Step 1: 构建（含自动重试和产物验证） ──
echo "$(date '+%F %T') [Step 1] 开始构建..." >> build/daily.log
/usr/local/bin/python3 build.py --push >> build/daily.log 2>&1
BUILD_EXIT=$?

if [ $BUILD_EXIT -ne 0 ]; then
    echo "$(date '+%F %T') [error] build.py 失败 (exit=$BUILD_EXIT)，进入重试..." >> build/daily.log
    # 等待 30 秒后重试一次
    sleep 30
    /usr/local/bin/python3 build.py --push >> build/daily.log 2>&1
    BUILD_EXIT=$?
fi

if [ $BUILD_EXIT -ne 0 ]; then
    echo "$(date '+%F %T') [FATAL] 构建最终失败 (exit=$BUILD_EXIT)！请检查 build/daily.log" >> build/daily.log
    exit 1
fi

# ── Step 2: 最终产物验证 ──
echo "$(date '+%F %T') [Step 2] 最终产物验证..." >> build/daily.log
/usr/local/bin/python3 build.py --verify-only >> build/daily.log 2>&1
VERIFY_EXIT=$?

if [ $VERIFY_EXIT -ne 0 ]; then
    echo "$(date '+%F %T') [error] 产物验证失败！尝试补渲染..." >> build/daily.log
    # 用 --from-curated 重新渲染下载产物
    if [ -f build/curated.json ]; then
        /usr/local/bin/python3 build.py --from-curated build/curated.json --push >> build/daily.log 2>&1
        # 再次验证
        /usr/local/bin/python3 build.py --verify-only >> build/daily.log 2>&1
        VERIFY_EXIT=$?
    fi
fi

if [ $VERIFY_EXIT -ne 0 ]; then
    echo "$(date '+%F %T') [FATAL] 产物验证最终失败！请检查 build/daily.log" >> build/daily.log
    exit 1
fi

echo "===== $(date '+%F %T') 结束 ✓ (全部产物验证通过) =====" >> build/daily.log

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

# 等网络/代理就绪（电脑睡眠唤醒后 Clash 自启需时间），最多等 ~5 分钟
for i in $(seq 1 20); do
  if /usr/bin/curl -s --max-time 8 -o /dev/null https://github.com; then
    echo "$(date '+%F %T') 网络就绪（第 $i 次探测）" >> build/daily.log; break
  fi
  echo "$(date '+%F %T') 网络/代理未就绪，等待…($i)" >> build/daily.log
  sleep 15
done

/usr/local/bin/python3 build.py --push >> build/daily.log 2>&1
echo "===== $(date '+%F %T') 结束 (exit=$?) =====" >> build/daily.log

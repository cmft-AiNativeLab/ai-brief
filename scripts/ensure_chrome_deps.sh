#!/bin/bash
# ensure_chrome_deps.sh — 确保 /tmp/libs 中有 Chrome 运行所需的共享库
# 容器重启后 /tmp 可能被清空，此脚本自动恢复依赖。
set -euo pipefail

CHROME_BIN="/home/node/.cache/ms-playwright/chromium-1223/chrome-linux64/chrome"
LIB_DIR="/tmp/libs"
DEB_DIR="/tmp/debs"
LD_PATH="${LIB_DIR}/lib/x86_64-linux-gnu:${LIB_DIR}/usr/lib/x86_64-linux-gnu"

log() { echo "[chrome-deps] $(date '+%H:%M:%S') $*"; }

# 快速检测：Chrome 能否启动
if LD_LIBRARY_PATH="$LD_PATH:${LD_LIBRARY_PATH:-}" "$CHROME_BIN" --version &>/dev/null 2>&1; then
    log "✓ Chrome 依赖完整，无需安装"
    exit 0
fi

log "Chrome 依赖缺失，开始下载安装..."
mkdir -p "$LIB_DIR" "$DEB_DIR"

# 从 Debian bookworm 包索引提取所有 Chrome 依赖
PACKAGES_URL="https://deb.debian.org/debian/dists/bookworm/main/binary-amd64/Packages.gz"
PACKAGES_FILE="/tmp/Packages.txt"

# 仅在索引不存在时下载（~30MB 压缩，解压后约 100MB）
if [ ! -f "$PACKAGES_FILE" ]; then
    log "下载 Debian 包索引..."
    curl -sSf "$PACKAGES_URL" | gunzip > "$PACKAGES_FILE" 2>/dev/null || {
        log "✗ 下载包索引失败"
        exit 1
    }
fi

# Chrome 需要的所有库（含递归依赖）
NEEDED_PKGS="
libglib2.0-0 libnspr4 libnss3 libatk1.0-0 libdbus-1-3 libcups2
libxcb1 libxkbcommon0 libasound2 libgbm1 libx11-6 libxext6
libcairo2 libpango-1.0-0 libxcomposite1 libatk-bridge2.0-0
libgobject-2.0-0 libgio-2.0-0 libnssutil3 libsmime3
libxrandr2 libxdamage1 libxfixes3 libxshmfence1 libdrm2
libwayland-server0 libpangocairo-1.0-0 libpangoft2-1.0-0
libharfbuzz0b libfontconfig1 libfreetype6 libpixman-1-0
libexpat1 libffi8 libpcre2-8-0 libselinux1 libmount1
libblkid1 libzstd1 zlib1g libpng16-16 libxau6 libxdmcp6
libatspi2.0-0 libavahi-common3 libavahi-client3
libxcb-shm0 libxcb-render0 libxrender1 libfribidi0
libthai0 libxi6 libbsd0 libgraphite2-3 libdatrie1
"

cd "$DEB_DIR"

# 从 Packages 索引提取下载 URL
log "解析包下载链接..."
python3 -c "
pkgs = '''$NEEDED_PKGS'''.split()
with open('$PACKAGES_FILE') as f:
    content = f.read()
sections = content.split('\n\n')
found = set()
for section in sections:
    lines = section.split('\n')
    pkg_name = filename = None
    for line in lines:
        if line.startswith('Package: '): pkg_name = line.split(': ', 1)[1]
        elif line.startswith('Filename: '): filename = line.split(': ', 1)[1]
    if pkg_name in pkgs and filename:
        found.add(pkg_name)
        print(f'https://deb.debian.org/debian/{filename}')
missing = set(pkgs) - found
if missing:
    import sys
    print(f'WARNING: packages not found: {missing}', file=sys.stderr)
" > urls.txt

TOTAL=$(wc -l < urls.txt)
log "需要下载 $TOTAL 个包"

# 下载所有 deb 包
DOWNLOADED=0
while IFS= read -r url; do
    fname=$(basename "$url")
    if [ ! -f "$fname" ]; then
        curl -sSfL -o "$fname" "$url" 2>/dev/null || {
            log "  ✗ 下载失败: $fname"
            continue
        }
    fi
    DOWNLOADED=$((DOWNLOADED + 1))
done < urls.txt
log "已下载 $DOWNLOADED/$TOTAL 个包"

# 解压到 /tmp/libs
log "解压库文件..."
for f in *.deb; do
    [ -f "$f" ] && dpkg -x "$f" "$LIB_DIR/" 2>/dev/null
done

# 最终验证
if LD_LIBRARY_PATH="$LD_PATH:${LD_LIBRARY_PATH:-}" "$CHROME_BIN" --version &>/dev/null 2>&1; then
    log "✓ Chrome 依赖安装成功"
    # 清理临时 deb 文件节省空间
    rm -f "$DEB_DIR"/*.deb
    exit 0
else
    # 检查还缺什么
    MISSING=$(LD_LIBRARY_PATH="$LD_PATH:${LD_LIBRARY_PATH:-}" ldd "$CHROME_BIN" 2>&1 | grep "not found" | awk '{print $1}')
    log "✗ 仍有缺失库: $MISSING"
    exit 1
fi

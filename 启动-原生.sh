#!/usr/bin/env bash
# Coopanion · 原生身体版（PySide6 + QPainter，**不用 Chromium/Electron**）
#
# 跟 启动.sh 的差别只有一个：把「宠物窗口」换成 原生/原生身体.py。
# 核心（Node 那边）一个字节没改，它照样按 CORTICO_DESKTOP_PET_HOST 把宿主拉起来。
#
# 实测（2026-09-28）：内存 629 MB → 约 64 MB，进程 2 → 2，画质与动作由 Python 重写。
# 想回到 Chromium 版：跑 ./启动.sh 就行（两条路互不影响，源码是同一份）。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HERE/app"
export PATH="$HOME/.local/node/bin:$PATH"
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
export CORTICO_HOME="${CORTICO_HOME:-$APP/build/home}"
export CORTICO_COMPANION_ROOT="$APP/build/cortico"
export ELECTRON_SKIP_BINARY_DOWNLOAD=1
# 原生身体的参数：帧率（闲时自动减半）、大小、网格抽稀（2 最稳，3 更快）
export COOP_FPS="${COOP_FPS:-24}"
export COOP_FPS_IDLE="${COOP_FPS_IDLE:-12}"
export COOP_SCALE="${COOP_SCALE:-0.62}"
export COOP_GRID="${COOP_GRID:-3}"
# 宠物窗口交给 World（作者设计的嵌入点）
export CORTICO_DESKTOP_PET_HOST="[\"$HOME/dsh-pet-opt/.venv/bin/python\",\"$HERE/原生/原生身体.py\"]"
[ -f "$HERE/外挂/应用.sh" ] && bash "$HERE/外挂/应用.sh" >> "$HERE/logs/外挂.log" 2>&1

mkdir -p "$HERE/logs"
echo $$ > "$HERE/logs/核心.pid"
cd "$APP"
exec node --max-old-space-size=96 --max-semi-space-size=4 --import tsx --require "$HERE/兜异常.cjs" "$APP/core/boot.ts" \
  >> "$HERE/logs/核心.log" 2>&1

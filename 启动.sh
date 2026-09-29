#!/usr/bin/env bash
# Coopanion · Linux 版（轻量外壳）一键启动
# 依赖：Node（核心）+ Python3/PySide6（外壳，本机已有）—— 不需要 Electron
#
# 内存/CPU 瘦身在沙盒里逐项量过（细节见 docs/瘦身实测.md）：
#   ① 直接 node 跑核心，不要中间那个只负责 fork 的启动器   省 47 MB / 1 个进程
#      （依据：core/companion.ts 只有 process.send?.() 和 disconnect 兜底，没有 IPC 握手）
#   ② --single-process      渲染进程并进主进程（省内存第一名）
#   ③ --enable-low-end-device-mode + js-flags 压 V8 堆和缓存
#   ④ --use-angle=swiftshader  软件 GL 换 SwiftShader，比默认 Vulkan 回退省 ~25% CPU
#   ⑤ COOP_FPS=24           帧率上限（弹簧按 dt 积分，降帧只影响顺滑度，不影响动作）
# ⚠️ 千万别加 --disable-gpu：鲸鱼的骨骼是 WebGL2 合成的，关了就只剩空画布、人直接消失，
#    而 rAF 帧率照样 48fps —— 光看指标发现不了。验收必须看画面或读 canvas 像素。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
APP="$HERE/app"
export PATH="$HOME/.local/node/bin:$PATH"
export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
export CORTICO_HOME="${CORTICO_HOME:-$APP/build/home}"
export CORTICO_COMPANION_ROOT="$APP/build/cortico"
export ELECTRON_SKIP_BINARY_DOWNLOAD=1
export QTWEBENGINE_DISABLE_SANDBOX=1
export QTWEBENGINE_CHROMIUM_FLAGS="--single-process --no-sandbox --enable-low-end-device-mode \
--js-flags=--max-old-space-size=32 --max-semi-space-size=2 --use-angle=swiftshader --use-gl=angle \
--disable-dev-shm-usage --disk-cache-size=1 --media-cache-size=1 \
--disable-features=Translate,BackForwardCache,MediaRouter,OptimizationHints,AcceptCHFrame,AudioServiceOutOfProcess,CalculateNativeWinOcclusion \
--disable-background-networking --disable-breakpad --disable-crash-reporter --disable-extensions \
--disable-sync --disable-default-apps --no-first-run --disable-component-update --disable-domain-reliability"
export COOP_FPS="${COOP_FPS:-24}"
# 外壳命令交给 World（作者设计的嵌入点 CORTICO_DESKTOP_PET_HOST）
export CORTICO_DESKTOP_PET_HOST="[\"$HOME/dsh-pet-opt/.venv/bin/python\",\"$HERE/外壳.py\"]"
# 按 外挂/启用.json 把外挂同步成该有的样子（开着的应用、关着的还原）。
# 想彻底不要外挂：把这一行删掉即可，主干其它部分不受影响。
[ -f "$HERE/外挂/应用.sh" ] && bash "$HERE/外挂/应用.sh" >> "$HERE/logs/外挂.log" 2>&1

mkdir -p "$HERE/logs"
echo $$ > "$HERE/logs/核心.pid"
cd "$APP"
exec node --max-old-space-size=96 --max-semi-space-size=4 --import tsx --require "$HERE/兜异常.cjs" "$APP/core/boot.ts" \
  >> "$HERE/logs/核心.log" 2>&1

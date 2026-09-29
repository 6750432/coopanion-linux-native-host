#!/usr/bin/env bash
# 起一个不需要 root 的 Wayland 合成器测试床（本机原本是纯 X11，没装任何合成器）
#
# English: Boot a rootless Wayland compositor testbed on a machine that only had X11.
# 中文：本机原本一个合成器都没有。这里把 weston 的 deb 解到 $HOME 下直接跑，
#       不装包、不要 root。两个后端的用法：
#         bash 起合成器.sh headless    # 无头，跑性能测试用
#         bash 起合成器.sh x11         # 嵌进当前 X 桌面开个窗口，能截图能点
#
# ⚠️ 三个必须知道的坑：
#   1) 【本脚本自己踩过】bash 里**变量名必须纯 ASCII**，locale 是 C，中文名会报
#      "command not found / not a valid identifier"。注释里用中文没问题，标识符不行。
#   2) weston 的模块路径是**编译期写死**的（/usr/lib/x86_64-linux-gnu/libweston-13），
#      要用 WESTON_MODULE_MAP 覆盖；格式是「模块名=路径」，多条用 ; 隔开，
#      而且值太长会被静默丢弃（内部有长度上限），所以这里用 ~/wlm、~/wsh 两个短符号链接。
#   3) kiosk 外壳不需要拉起 /usr/libexec/weston-* 辅助客户端，desktop 外壳需要
#      而这些辅助客户端的路径同样写死、WESTON_MODULE_MAP 管不着 —— 所以测试床用 kiosk。

set -u
# 测试床根目录，可用环境变量覆盖
BASE="${WAYLAND_TESTBED:-$HOME/wayland-test}"
R="$BASE/root"
BACKEND="${1:-headless}"

export XDG_RUNTIME_DIR="$BASE/rt"
mkdir -p "$XDG_RUNTIME_DIR" && chmod 700 "$XDG_RUNTIME_DIR"
export LD_LIBRARY_PATH="$R/usr/lib/x86_64-linux-gnu:$R/usr/lib/x86_64-linux-gnu/weston:$R/usr/lib/x86_64-linux-gnu/libweston-13"

# 短路径符号链接（避免模块映射值超长被丢掉）
ln -sfn "$R/usr/lib/x86_64-linux-gnu/libweston-13" "$HOME/wlm"
ln -sfn "$R/usr/lib/x86_64-linux-gnu/weston" "$HOME/wsh"

if [ "$BACKEND" = "x11" ]; then
  export DISPLAY="${DISPLAY:-:0}"
  export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
  MODULES="x11-backend.so=$HOME/wlm/x11-backend.so"
  SOCKET="wayland-x11"
  SIZE="--width=900 --height=560"
  LOG="$BASE/weston-x11.log"
else
  MODULES="headless-backend.so=$HOME/wlm/headless-backend.so"
  SOCKET="wayland-test"
  SIZE="--width=1920 --height=1080"
  LOG="$BASE/weston.log"
fi
export WESTON_MODULE_MAP="$MODULES;kiosk-shell.so=$HOME/wsh/kiosk-shell.so"
BACKEND_NAME=$(echo "$MODULES" | cut -d= -f1)

rm -f "$XDG_RUNTIME_DIR/$SOCKET"
setsid nohup "$R/usr/bin/weston" --backend="$BACKEND_NAME" \
    --renderer=pixman --shell=kiosk --socket="$SOCKET" $SIZE > "$LOG" 2>&1 &
sleep 3

if [ -S "$XDG_RUNTIME_DIR/$SOCKET" ]; then
  PID=$(pgrep -x weston | head -1)
  echo "$PID" > "$BASE/weston.pid"
  echo "✅ 合成器起来了：socket=$SOCKET  pid=$PID"
  echo "   客户端用法： export XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR"
  echo "                export WAYLAND_DISPLAY=$SOCKET"
  echo "                export WESTON_PID=$PID   # 让客户端能量到合成器 CPU"
else
  echo "❌ 没起来，看日志： $LOG"
  tail -15 "$LOG"
  exit 1
fi

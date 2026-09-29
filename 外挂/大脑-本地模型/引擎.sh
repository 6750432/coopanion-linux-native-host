#!/usr/bin/env bash
# 外挂：大脑-本地模型 · 本地引擎
# 用 Jan 自带的 llama-server 直接跑 Qwen3-8B（绕开 Jan 的 UI 和 API Key —— 那版 Jan 的本地服务要钥匙，
# 而且模型列表是从它自己的库里生成的，改 INI 会被它重写）。
#
# ⚠️ 本脚本会起一个进程（llama-server），pid 写在 运行中/llama.pid，用 引擎停.sh 停。
# ⚠️ bash 变量名一律 ASCII（本机 locale 是 C）。
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
RUN="$HERE/运行中"
mkdir -p "$RUN"

BIN_DIR="$HOME/.var/app/ai.jan.Jan/data/Jan/data/llamacpp/backends/b9967/linux-cuda-13-common_cpus-x64/build/bin"
MODEL="${1:-$HOME/models/DeepSeek-R1-0528-Qwen3-8B-IQ4_XS.gguf}"
PORT="${2:-8123}"
CTX="${3:-8192}"

[ -x "$BIN_DIR/llama-server" ] || { echo "  找不到 Jan 自带的 llama-server：$BIN_DIR"; exit 1; }
[ -f "$MODEL" ] || { echo "  找不到模型：$MODEL"; exit 1; }

if [ -f "$RUN/llama.pid" ] && kill -0 "$(cat "$RUN/llama.pid")" 2>/dev/null; then
  echo "  本地引擎已经在跑（pid $(cat "$RUN/llama.pid")）"
  exit 0
fi

echo "── 起本地引擎 ──"
echo "   模型 $(basename "$MODEL")"
echo "   端口 $PORT  上下文 $CTX  KV cache 量化 q8_0  全部层上显卡"
cd "$BIN_DIR"
setsid nohup ./llama-server -m "$MODEL" --jinja --host 127.0.0.1 --port "$PORT" \
  -c "$CTX" --cache-type-k q8_0 --cache-type-v q8_0 -ngl 99 --no-webui \
  > "$RUN/llama.log" 2>&1 &
echo $! > "$RUN/llama.pid"

for i in $(seq 1 40); do
  sleep 3
  if curl -s -m 3 -o /dev/null "http://127.0.0.1:$PORT/v1/models"; then
    echo "   ✓ 起来了（pid $(cat "$RUN/llama.pid")），显存占用："
    nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null | sed 's/^/     /'
    exit 0
  fi
done
echo "   ✗ 120 秒还没起来，看 $RUN/llama.log"
tail -5 "$RUN/llama.log" | sed 's/^/     /'
exit 1

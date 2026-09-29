#!/usr/bin/env bash
# 外挂：大脑-本地模型 · 停本地引擎
# ⚠️ bash 变量名一律 ASCII（本机 locale 是 C）。
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
RUN="$HERE/运行中"

echo "── 停本地引擎 ──"
if [ -f "$RUN/llama.pid" ]; then
  PID="$(cat "$RUN/llama.pid")"
  if kill -0 "$PID" 2>/dev/null; then kill "$PID"; sleep 2; kill -9 "$PID" 2>/dev/null || true; fi
  rm -f "$RUN/llama.pid"
  echo "   已停 llama-server（pid $PID）"
else
  echo "   没有 pid 文件；保险起见按名字找一遍"
  python3 - <<'PY'
import os, signal
me = os.getpid(); 祖 = set(); p = me
while p > 1:
    祖.add(p)
    try: p = int(open(f"/proc/{p}/stat").read().split()[3])
    except Exception: break
n = 0
for d in os.listdir("/proc"):
    if not d.isdigit() or int(d) in 祖: continue
    try: l = " ".join(open(f"/proc/{d}/cmdline","rb").read().decode(errors="ignore").split("\0"))
    except Exception: continue
    if "llama-server" in l and "python3" not in l:
        try: os.kill(int(d), signal.SIGKILL); n += 1
        except Exception: pass
print(f"   按名字停了 {n} 个")
PY
fi
nvidia-smi --query-gpu=memory.used,memory.total --format=csv,noheader 2>/dev/null | sed 's/^/   显存现在: /'
echo "── 提示：引擎停了以后她还能动、还能自己散步，但不会说话了（要么再起引擎，要么装回假模型）──"

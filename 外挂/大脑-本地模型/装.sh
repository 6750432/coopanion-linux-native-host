#!/usr/bin/env bash
# 外挂：大脑-本地模型 · 安装
# 把她的 provider 指向本地（默认本地 Jan；加 --假模型 就指向自带的假模型，用于零成本自测）。
#
# ⚠️ 本外挂会**起两个进程**（代理 + 可选假模型），这是「别偷偷起进程」那条规矩的显式例外：
#    卸.sh 会把它们停掉；进程 pid 写在 运行中/ 目录里。
# ⚠️ bash 变量名一律 ASCII（locale 为 C 时中文变量名非法 —— 已踩三次）。
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
APP="$ROOT/app"
PROV="$APP/build/home/providers/deepseek"
CONF="$PROV/config.json"
ENVF="$PROV/.env"
RUN="$HERE/运行中"

USE_MOCK=0
[ "${1:-}" = "--假模型" ] && USE_MOCK=1
UPSTREAM="${2:-http://127.0.0.1:1337/v1}"
MODEL="${3:-deepseek-r1-0528-qwen3-8b}"   # ⚠️ 别用 R1-Distill-Qwen-7B：它的模板不支持 tools

mkdir -p "$RUN"
echo "── 装：大脑-本地模型 ──"

# ① 备份 provider 配置
if [ ! -f "$CONF.原版备份" ]; then
  cp "$CONF" "$CONF.原版备份"; echo "   备份 → providers/deepseek/config.json.原版备份"
fi

# ② 起假模型（可选）
if [ "$USE_MOCK" = "1" ]; then
  if [ ! -f "$RUN/mock.pid" ]; then
    setsid nohup python3 "$HERE/mock.py" --端口 8111 > "$RUN/mock.log" 2>&1 &
    echo $! > "$RUN/mock.pid"; sleep 1.2
    echo "   假模型 → http://127.0.0.1:8111/v1（pid $(cat "$RUN/mock.pid")）"
  fi
  UPSTREAM="http://127.0.0.1:8111/v1"; MODEL="假模型"
fi

# ③ 起代理
if [ -f "$RUN/proxy.pid" ]; then
  kill "$(cat "$RUN/proxy.pid")" 2>/dev/null || true; sleep 0.5
fi
setsid nohup python3 "$HERE/proxy.py" --端口 8899 --上游 "$UPSTREAM" --模型 "$MODEL" > "$RUN/proxy.log" 2>&1 &
echo $! > "$RUN/proxy.pid"; sleep 1.2
echo "   代理 → http://127.0.0.1:8899/v1  ⇒  $UPSTREAM（pid $(cat "$RUN/proxy.pid")）"

# ④ 改 provider：baseUrl 指向代理，密钥用占位（本地不需要真 key）
python3 - "$CONF" "$MODEL" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); 模型 = sys.argv[2]
d = json.loads(p.read_text(encoding="utf-8"))
d["baseUrl"] = "http://127.0.0.1:8899/v1"
d["spec"] = {"model": 模型}
d["multimodal"] = False
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print(f"   provider baseUrl → 代理，模型 → {模型}")
PY

# ⑤ 密钥文件：核心从 endpoint 的 .env 读密钥，本地随便给个占位
if [ ! -f "$ENVF" ]; then
  printf 'DEEPSEEK_API_KEY=local-no-key-needed\n' > "$ENVF"
  echo "   写了 providers/deepseek/.env（占位密钥，本地用不上）"
fi

echo "── 装好了。重启才生效：bash $ROOT/停.sh && bash $ROOT/开.sh ──"

#!/usr/bin/env bash
# 外挂：大脑-本地模型 · 卸载：停进程、还原 provider 配置和 .env。
# ⚠️ bash 变量名一律 ASCII（本机 locale 是 C）。
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
APP="$ROOT/app"
PROV="$APP/build/home/providers/deepseek"
CONF="$PROV/config.json"
ENVF="$PROV/.env"
RUN="$HERE/运行中"

echo "── 卸：大脑-本地模型 ──"

for NAME in proxy mock; do
  if [ -f "$RUN/$NAME.pid" ]; then
    kill "$(cat "$RUN/$NAME.pid")" 2>/dev/null || true
    rm -f "$RUN/$NAME.pid"
    echo "   已停：$NAME"
  fi
done

if [ -f "$CONF.原版备份" ]; then
  cp "$CONF.原版备份" "$CONF"; rm -f "$CONF.原版备份"
  echo "   provider 配置 → 还原（baseUrl 回 DeepSeek）"
else
  echo "   provider 配置：没备份，跳过"
fi

if [ -f "$ENVF" ]; then
  rm -f "$ENVF"; echo "   删掉占位 .env"
fi

echo "── 卸好了。重启才生效 ──"

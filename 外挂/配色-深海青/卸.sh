#!/usr/bin/env bash
# 外挂：配色-深海青 · 卸载
# 删掉 schemes/deepsea，还原 model.json 和配置里的配色选择。
# ⚠️ bash 变量名一律 ASCII（本机 locale 是 C）。
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
APP="$ROOT/app"
WHALE="$APP/packages/cortico-world-desktop-pet/web/whale"
MODEL="$WHALE/model.json"
CONF="$APP/build/home/companion/config.json"

echo "── 卸：配色-深海青 ──"

# ① 贴图：挪到外挂目录里留着（不直接删，万一想再装回来）
if [ -d "$WHALE/schemes/deepsea" ]; then
  rm -rf "$HERE/生成过的贴图"
  mv "$WHALE/schemes/deepsea" "$HERE/生成过的贴图"
  echo "   贴图 -> 挪回外挂目录（生成过的贴图/）"
fi

# ② model.json
if [ -f "$MODEL.原版备份" ]; then
  cp "$MODEL.原版备份" "$MODEL"; rm -f "$MODEL.原版备份"
  echo "   model.json -> 还原（deepsea 条目已去掉）"
else
  echo "   model.json：没备份，跳过"
fi

# ③ 配色选择
if [ -f "$CONF.原版备份" ]; then
  cp "$CONF.原版备份" "$CONF"; rm -f "$CONF.原版备份"
  echo "   配置 -> 还原（配色回到原来那套）"
else
  echo "   配置：没备份，跳过"
fi

echo "── 卸好了。重启才生效 ──"

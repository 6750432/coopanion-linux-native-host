#!/usr/bin/env bash
# 外挂：persona-whale-maid · 卸载
# 把人格卡、环境提示、名字都还原成装之前的样子。
# ⚠️ bash 变量名一律 ASCII（本机 locale 是 C）。
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
APP="$ROOT/app"
CONST="$APP/build/home/companion/workspace/CONSTITUTION.md"
ENVP="$APP/packages/cortico-world-desktop-pet/src/ENV_PROMPT.md"
CONF="$APP/build/home/companion/config.json"

echo "── 卸：persona-whale-maid（鲸鱼女仆）──"

if [ -f "$CONST.原版备份" ]; then
  cp "$CONST.原版备份" "$CONST"; rm -f "$CONST.原版备份"
  echo "   人格卡 → 还原成原版 Coo"
else
  echo "   人格卡：没备份，跳过"
fi

if [ -f "$ENVP.原版备份" ]; then
  cp "$ENVP.原版备份" "$ENVP"; rm -f "$ENVP.原版备份"
  echo "   环境提示 → 还原"
else
  echo "   环境提示：没备份，跳过"
fi

if [ -f "$CONF.原版备份" ]; then
  cp "$CONF.原版备份" "$CONF"; rm -f "$CONF.原版备份"
  echo "   配置 → 还原（名字回 Coo）"
else
  python3 - "$CONF" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text(encoding="utf-8"))
d["displayName"] = "Coo"
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("   配置：没备份，只把名字改回 Coo")
PY
fi

echo "── 卸好了。重启才生效 ──"

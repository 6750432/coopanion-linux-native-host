#!/usr/bin/env bash
# 外挂：persona-whale-maid
# 把角色换成鲸鱼女仆（whale-maid）。改两个文件 + 一个配置项，覆盖前都先备份。
# 可重复跑；卸.sh 从备份还原。
# ⚠️ bash 里不能用中文变量名（本机 locale 是 C），所以变量一律 ASCII，只有注释和输出用中文。
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
APP="$ROOT/app"
CONST="$APP/build/home/companion/workspace/CONSTITUTION.md"
ENVP="$APP/packages/cortico-world-desktop-pet/src/ENV_PROMPT.md"
CONF="$APP/build/home/companion/config.json"

echo "── 装：persona-whale-maid ──"

# ① 人格卡（每开一个新 session 会放进系统前缀）
if [ ! -f "$CONST.原版备份" ]; then
  cp "$CONST" "$CONST.原版备份"
  echo "   备份人格卡 → CONSTITUTION.md.原版备份"
fi
cp "$HERE/CONSTITUTION.md" "$CONST"
echo "   人格卡 → 鲸鱼女仆（$(wc -m < "$CONST" | tr -d ' ') 字）"

# ② 环境提示（讲身体长什么样、有哪些工具）
if [ ! -f "$ENVP.原版备份" ]; then
  cp "$ENVP" "$ENVP.原版备份"
  echo "   备份环境提示 → ENV_PROMPT.md.原版备份"
fi
cp "$HERE/ENV_PROMPT.md" "$ENVP"
echo "   环境提示 → 鲸鱼女仆的身体描述"

# ③ 名字
if [ ! -f "$CONF.原版备份" ]; then
  cp "$CONF" "$CONF.原版备份"
  echo "   备份配置 → config.json.原版备份"
fi
python3 - "$CONF" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
d["displayName"] = "鲸鱼女仆"
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("   名字 displayName → 鲸鱼女仆")
PY

echo "── 装好了。重启才生效：bash $ROOT/停.sh && bash $ROOT/开.sh ──"

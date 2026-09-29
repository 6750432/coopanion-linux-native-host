#!/usr/bin/env bash
# 外挂：配色-深海青
# 给鲸鱼娘加一套自己的配色（蓝 → 深海青），并把她切过去。
# ⚠️ bash 变量名一律 ASCII（本机 locale 是 C，中文变量名会报错）。
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
APP="$ROOT/app"
WHALE="$APP/packages/cortico-world-desktop-pet/web/whale"
MODEL="$WHALE/model.json"
CONF="$APP/build/home/companion/config.json"
PY="$HOME/dsh-pet-opt/.venv/bin/python"

echo "── 装：配色-深海青 ──"

# ① 染色：从基准贴图生成 schemes/deepsea/（tex + feat）
"$PY" "$HERE/染色.py" "$WHALE/schemes/deepsea"
echo "   贴图 → $WHALE/schemes/deepsea"

# ② 注册到 model.json（先备份）
if [ ! -f "$MODEL.原版备份" ]; then
  cp "$MODEL" "$MODEL.原版备份"
  echo "   备份 → model.json.原版备份"
fi
python3 - "$MODEL" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
条目 = {"id": "deepsea", "brand": "Coopanion Native Host", "label": "深海青", "accent": "#2AD4C8", "ready": True}
方案 = d.setdefault("schemes", [])
if not any(s.get("id") == "deepsea" for s in 方案):
    方案.append(条目)
    print("   注册配色 deepsea（现在共 %d 套）" % len(方案))
else:
    print("   配色 deepsea 已经注册过了")
p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
PY

# ③ 把她切到这套配色
if [ ! -f "$CONF.原版备份" ]; then
  cp "$CONF" "$CONF.原版备份"
fi
python3 - "$CONF" <<'PY'
import json, sys, pathlib
p = pathlib.Path(sys.argv[1])
d = json.loads(p.read_text(encoding="utf-8"))
d.setdefault("worlds", {}).setdefault("desktop-pet", {}).setdefault("skin", {})["scheme"] = "deepsea"
p.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")
print("   当前配色 skin.scheme → deepsea")
PY

echo "── 装好了。重启才生效：bash $ROOT/停.sh && bash $ROOT/开.sh ──"

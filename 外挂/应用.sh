#!/usr/bin/env bash
# 外挂同步：照 启用.json 把每个外挂调成该有的样子 ——
#   开着的 → 跑一次它的 装.sh（装过的会跳过）
#   关着的 → 跑一次它的 卸.sh（没装的会跳过）
# 可以反复跑，不会重复折腾（用每个目录里的 .已启用 当记号）。
#
# 用法：bash 应用.sh          # 只同步
#       bash 应用.sh --重启   # 同步完再重启桌宠
# ⚠️ bash 变量名一律 ASCII（本机 locale 是 C）。
set -u
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
STATE="$HERE/启用.json"

echo "── 同步外挂 ──"
python3 - "$STATE" "$HERE" <<'PY'
import json, pathlib, subprocess, sys
状态文件, 目录 = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
try:
    状态 = json.loads(状态文件.read_text(encoding="utf-8"))
except Exception:
    状态 = {}

变了 = 0
for d in sorted(p for p in 目录.iterdir() if p.is_dir()):
    if not (d / "装.sh").exists():
        continue
    名 = d.name
    想开 = bool(状态.get(名, False))
    记号 = d / ".已启用"
    现在开 = 记号.exists()
    if 想开 and not 现在开:
        print(f"   开 → {名}")
        if subprocess.run(["bash", str(d / "装.sh")], cwd=str(d)).returncode == 0:
            记号.write_text("1", encoding="utf-8"); 变了 += 1
        else:
            print(f"     ⚠ {名} 装失败")
    elif not 想开 and 现在开:
        print(f"   关 → {名}")
        subprocess.run(["bash", str(d / "卸.sh")], cwd=str(d))
        记号.unlink(missing_ok=True); 变了 += 1
    else:
        print(f"   {'开' if 想开 else '关'} → {名}（已经是这样）")
print(f"   一共动了 {变了} 个")
PY

if [ "${1:-}" = "--重启" ]; then
  echo "── 重启桌宠 ──"
  bash "$ROOT/停.sh" | tail -1
  rm -f "$ROOT/logs/核心.log"
  setsid nohup bash "$ROOT/启动.sh" >/dev/null 2>&1 &
  echo "   已拉起（约 30 秒后才能看到效果）"
fi

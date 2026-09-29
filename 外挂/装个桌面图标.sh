#!/usr/bin/env bash
# 在桌面生成「外挂管理器」图标（Thunar 双击 .sh 只会打开编辑器，所以必须用绝对路径的 .desktop）
set -eu
HERE="$(cd "$(dirname "$0")" && pwd)"
ICON="applications-system"
DESK="$HOME/Desktop/外挂管理器.desktop"
cat > "$DESK" <<EOF
[Desktop Entry]
Type=Application
Name=外挂管理器
Comment=开关Coopanion 桌宠的外挂
Exec=$HERE/管理器.sh
Path=$HERE
Icon=$ICON
Terminal=false
Categories=Utility;
EOF
chmod +x "$DESK"
gio set "$DESK" metadata::trusted true 2>/dev/null || true
echo "  ✓ 桌面图标：$DESK"

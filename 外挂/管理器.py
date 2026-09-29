#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""外挂管理器：一个窗口，勾上想要的外挂，点「应用」就生效。

设计约束：外挂摆在外挂/ 文件夹里**不用动**，只用开关控制开不开；
想加新外挂 = 往文件夹里丢一个目录（里面有 装.sh / 卸.sh / 说明.txt），窗口里自动出现。

用法：python3 管理器.py     （或者双击 管理器.sh）
"""
import json
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QVBoxLayout, QWidget)

BASE = Path(__file__).resolve().parent
ROOT = BASE.parent
状态文件 = BASE / "启用.json"
PRIMARY = "#2AD4C8"


def 读状态() -> dict:
    try:
        return json.loads(状态文件.read_text(encoding="utf-8"))
    except Exception:
        return {}


def 写状态(d: dict) -> None:
    状态文件.write_text(json.dumps(d, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def 扫外挂() -> list:
    """返回 [(名字, 一句话说明, 现在已经开着吗)]"""
    出 = []
    for d in sorted(p for p in BASE.iterdir() if p.is_dir()):
        if not (d / "装.sh").exists():
            continue
        说明 = ""
        f = d / "说明.txt"
        if f.exists():
            行s = [x.strip() for x in f.read_text(encoding="utf-8").splitlines()]
            行s = [x for x in 行s if x and not x.startswith(("外挂：", "====", "状态："))]
            for i, x in enumerate(行s):
                if x in ("作用", "作用："):
                    说明 = 行s[i + 1] if i + 1 < len(行s) else ""   # 「作用」下面那行才是真正的说明
                    break
            else:
                说明 = 行s[0] if 行s else ""
        说明 = 说明.replace("**", "")
        出.append((d.name, 说明[:40], (d / ".已启用").exists()))
    return 出


def 进程在跑(关键字: str) -> bool:
    import os
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            行 = " ".join(open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="ignore").split("\0"))
        except Exception:
            continue
        if 关键字 in 行:
            return True
    return False


class 窗口(QWidget):
    """Plugin manager window: lists the directories under `外挂/` and toggles each one through its own `装.sh` / `卸.sh`.
    
    外挂管理器窗口：列出 `外挂/` 下的目录，用各自的 `装.sh` / `卸.sh` 开关。
    """
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("外挂管理器 · Coopanion Native Host")
        self.setStyleSheet(f"""
            QWidget {{ background:#1b1f27; color:#e8eaf0; font-size:13px; }}
            QLabel#标题 {{ font-size:15px; font-weight:600; color:{PRIMARY}; }}
            QLabel#小字 {{ color:#8b93a7; font-size:11px; }}
            QCheckBox {{ padding:6px 2px; }}
            QCheckBox::indicator {{ width:16px; height:16px; }}
            QPushButton {{ background:#2a3140; border:1px solid #39415a; border-radius:6px;
                           padding:7px 14px; }}
            QPushButton:hover {{ background:#333c4e; }}
            QPushButton#主 {{ background:{PRIMARY}; color:#10222b; border:none; font-weight:600; }}
            QFrame#线 {{ background:#2a3140; max-height:1px; }}
        """)
        self.setMinimumWidth(460)
        self.框s = {}

        竖 = QVBoxLayout(self)
        竖.setContentsMargins(18, 16, 18, 16)
        竖.setSpacing(10)

        标题 = QLabel("外挂管理器")
        标题.setObjectName("标题")
        竖.addWidget(标题)
        提示 = QLabel("外挂摆在外挂/ 文件夹里不用动，勾上就开、取消就关。改完点「应用」。")
        提示.setObjectName("小字")
        提示.setWordWrap(True)
        竖.addWidget(提示)

        线 = QFrame(); 线.setObjectName("线"); 竖.addWidget(线)

        self.状态 = 读状态()
        for 名, 说明, 开着 in 扫外挂():
            行 = QHBoxLayout()
            勾 = QCheckBox(名)
            勾.setChecked(bool(self.状态.get(名, 开着)))
            self.框s[名] = 勾
            行.addWidget(勾, 1)
            小 = QLabel(说明)
            小.setObjectName("小字")
            行.addWidget(小, 2)
            竖.addLayout(行)

        线2 = QFrame(); 线2.setObjectName("线"); 竖.addWidget(线2)

        self.自检 = QLabel()
        self.自检.setObjectName("小字")
        竖.addWidget(self.自检)

        按钮行 = QHBoxLayout()
        self.日志 = QLabel("")
        self.日志.setObjectName("小字")
        self.日志.setWordWrap(True)
        按钮行.addWidget(self.日志, 1)
        用 = QPushButton("应用")
        用.clicked.connect(lambda: self.跑(重启=False))
        重 = QPushButton("应用并重启桌宠")
        重.setObjectName("主")
        重.clicked.connect(lambda: self.跑(重启=True))
        按钮行.addWidget(用)
        按钮行.addWidget(重)
        竖.addLayout(按钮行)

        self.刷新自检()

    def 刷新自检(self) -> None:
        桌宠 = "在跑 ✓" if 进程在跑("core/boot.ts") else "没跑"
        引擎 = "在跑 ✓" if 进程在跑("llama-server") else "没跑"
        self.自检.setText(f"桌宠：{桌宠}　｜　本地引擎：{引擎}")

    def 跑(self, 重启: bool) -> None:
        for 名, 勾 in self.框s.items():
            self.状态[名] = 勾.isChecked()
        写状态(self.状态)
        命令 = ["bash", str(BASE / "应用.sh")] + (["--重启"] if 重启 else [])
        出 = subprocess.run(命令, capture_output=True, text=True, timeout=600)
        末尾 = [l for l in 出.stdout.strip().splitlines() if l.strip()][-3:]
        self.日志.setText(" / ".join(l.strip() for l in 末尾)[:160])
        self.刷新自检()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = 窗口()
    w.show()
    sys.exit(app.exec())

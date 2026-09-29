#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""面板与演示 —— 给「黑盒交付」用的两块小东西。

    面板.HUD        左上角一个小牌子：实时显示 内存 / 渲染帧率 / CPU，外加一个退出按钮。
    面板.演示核心   不用连任何外部程序，自己按剧本让她说话、走动、坐下睡觉。

只有 AppImage 演示模式（没给 --pet-url）才会用到它们；接自己的核心时一切照旧。
"""
from __future__ import annotations

import json
import os
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget


def 读内存MB(pid: int | None = None) -> float:
    pid = pid or os.getpid()
    try:
        for 行 in open(f"/proc/{pid}/status"):
            if 行.startswith("VmRSS"):
                return int(行.split()[1]) / 1024
    except Exception:
        pass
    return 0.0


class CPU表:
    """Measures this process's CPU usage (utime+stime delta over wall-clock time).
    
    量「这个进程」的 CPU 占用（utime+stime 增量 ÷ 真实流逝时间）。
    """

    def __init__(self, pid: int | None = None):
        self.pid = pid or os.getpid()
        self.上 = self._取()
        self.时 = time.perf_counter()

    def _取(self) -> float:
        try:
            字段 = open(f"/proc/{self.pid}/stat").read().split(") ", 1)[1].split()
            return (int(字段[11]) + int(字段[12])) / os.sysconf("SC_CLK_TCK")
        except Exception:
            return 0.0

    def 取值(self) -> float:
        现在, 时 = self._取(), time.perf_counter()
        出 = (现在 - self.上) / max(1e-6, 时 - self.时) * 100
        self.上, self.时 = 现在, 时
        return 出


class HUD(QWidget):
    """The small badge in the top-left corner — deliberately plain: black background, white text, one ✕.
    
    左上角那块小牌子。故意做得很朴素：黑底、白字、一个 ✕。
    """

    边距 = 14

    def __init__(self, 宠):
        super().__init__(None)
        self.宠 = 宠
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                            Qt.WindowType.Tool | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.字体 = QFont()
        for 名 in ("Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "Sans Serif"):
            self.字体.setFamily(名)
            if QFontMetrics(self.字体).horizontalAdvance("汉字") > 0:
                break
        self.字体.setPointSizeF(10.0)
        self.行 = ["Coopanion Native Host (no Chromium)", "…"]
        self.提示 = "戳她 / 拖她试试 · 点右边 ✕ 退出"
        self.setFixedSize(340, 86)
        屏 = QApplication.primaryScreen().availableGeometry()
        self.move(屏.left() + 18, 屏.top() + 18)
        self._上次 = time.perf_counter()
        self._关 = False

    def 每秒刷新(self):
        现在 = time.perf_counter()
        宠 = self.宠
        fps = 宠.画帧累计 / max(.001, 现在 - self._上次)
        宠.画帧累计 = 0      # 用独立计数器：帧数 是每 5 秒那条统计在用的
        self._上次 = 现在
        内存 = 读内存MB()
        cpu = self.宠.CPU表.取值()
        self.行 = ["Coopanion Native Host (Python + Qt, no Chromium)",
                   f"内存 {内存:.0f} MB  ｜  渲染 {fps:.0f} fps  ｜  CPU {cpu:.0f}%"]
        self.update()

    def paintEvent(self, ev):
        笔 = QPainter(self)
        try:
            笔.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            路 = QPainterPath()
            路.addRoundedRect(2, 2, self.width() - 4, self.height() - 4, 12, 12)
            笔.setBrush(QColor(12, 16, 22, 214))
            笔.setPen(QPen(QColor("#4dd6a1"), 1.6))
            笔.drawPath(路)
            笔.setPen(QColor("#E9EDF2"))
            笔.setFont(self.字体)
            y = 24
            for 行 in self.行:
                笔.drawText(14, y, 行)
                y += 20
            笔.setPen(QColor("#8C95A3"))
            小 = QFont(self.字体)
            小.setPointSizeF(8.5)
            笔.setFont(小)
            笔.drawText(14, self.height() - 12, self.提示)
            # ✕
            笔.setPen(QPen(QColor("#8C95A3"), 1.6))
            笔.drawLine(self.width() - 26, 14, self.width() - 14, 26)
            笔.drawLine(self.width() - 14, 14, self.width() - 26, 26)
        finally:
            笔.end()

    def mousePressEvent(self, ev):
        if ev.position().x() > self.width() - 40 and ev.position().y() < 40:
            self.宠.app.quit()
            return
        super().mousePressEvent(ev)


class 演示核心:
    """Scripted core: feeds lines itself, using exactly the same message format as the real core.
    
    不连外部程序，自己按剧本喂台词（走的是和真核心一模一样的消息格式）。
    """

    剧本 = [
        {"t": "thinking", "on": True},
        {"t": "say", "id": "s1", "beats": [
            {"actions": ["happy"], "text": "你好呀～", "anchors": []},
            {"actions": [], "text": "现在这个身体是【原生渲染】的：Python + Qt 的 QPainter，没有 Chromium。",
             "anchors": [{"at": 9, "actions": ["wink"]}]},
            {"actions": [], "text": "所以内存只要一百多兆，Electron 那套要六百兆起步。", "anchors": []},
        ]},
        {"t": "thinking", "on": False},
        {"t": "act", "id": "a1", "actions": ["look"]},
        {"t": "walk", "id": "w1", "to": 0.3, "run": False},
        {"t": "say", "id": "s2", "beats": [
            {"actions": ["love"], "text": "戳一下、或者拎起来试试？", "anchors": []},
        ]},
        {"t": "act", "id": "a2", "actions": ["jump"]},
        {"t": "walk", "id": "w2", "to": 0.72, "run": True},
        {"t": "say", "id": "s3", "beats": [
            {"actions": ["sleepy"], "text": "……有点困了。", "anchors": []},
            {"actions": ["sleep"], "text": "", "anchors": []},
        ]},
    ]

    def __init__(self, 宠):
        self.宠 = 宠
        self.第 = 0
        self.时刻 = time.perf_counter() + 2.0
        self.一轮 = 0

    def 步(self, dt: float):
        if time.perf_counter() < self.时刻:
            return
        if self.第 >= len(self.剧本):
            self.第 = 0
            self.一轮 += 1
            if self.一轮 >= 1:          # 剧本跑完一遍就安静下来，别再复读
                self.时刻 = time.perf_counter() + 9999
                return
        m = self.剧本[self.第]
        self.第 += 1
        try:
            self.宠.电台._收(json.dumps(m, ensure_ascii=False))
        except Exception as exc:
            self.宠.记("演示剧本出错：", exc)
        self.时刻 = time.perf_counter() + 6.0

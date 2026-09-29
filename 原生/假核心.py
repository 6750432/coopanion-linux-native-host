#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""假核心 —— 用来单独试「接线 + 气泡 + 念台词」，不用真的开 Coopanion。

它只做三件事：
    1. 起一个 WebSocket 服务（模仿核心的 /socket?role=pet&host=window）；
    2. 连上后按核心的格式发一串 say / act / walk / listen / thinking；
    3. 把她回上来的消息（hello / touch / mode / arrived）打印出来。

用法：QT_QPA_PLATFORM=offscreen python3 假核心.py 7899
"""
from __future__ import annotations

import json
import os
import sys

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWebSockets import QWebSocketServer

剧本 = [
    {"t": "thinking", "on": True},
    {"t": "say", "id": "s1", "beats": [
        {"actions": ["happy"], "text": "欢迎回来！【开心】", "anchors": []},
        {"actions": [], "text": "身体已经换成原生渲染，一兆字节的 Chromium 都没用。", "anchors": [
            {"at": 6, "actions": ["wink"]}]},
        {"actions": ["sit"], "text": "坐一会儿。", "anchors": []},
    ]},
    {"t": "thinking", "on": False},
    {"t": "act", "id": "a1", "actions": ["stand", "jump"]},
    {"t": "walk", "id": "w1", "to": 0.25, "run": False},
    {"t": "listen", "phase": "start"},
    {"t": "listen", "phase": "heard", "text": "（听见你在说话）"},
]


class 假核心(QObject):
    """A stand-in core that speaks the real WebSocket protocol, so the host can be tested without the Node process.
    
    假核心：说真核心那套 WebSocket 协议，用来在没有 Node 进程时脱机测试宿主。
    """
    def __init__(self, 端口: int):
        super().__init__()
        self.服 = QWebSocketServer("假核心", QWebSocketServer.SslMode.NonSecureMode)
        if not self.服.listen(port=端口):
            print(f"端口 {端口} 起不来：{self.服.errorString()}")
            sys.exit(1)
        print(f"假核心在 ws://127.0.0.1:{端口}/socket 上等宠物…")
        self.服.newConnection.connect(self._有人来)
        self.客人 = None
        self.第 = 0

    def _有人来(self):
        ws = self.服.nextPendingConnection()
        self.客人 = ws
        print(f"有人连上了：{ws.requestUrl().toString()}")
        ws.textMessageReceived.connect(lambda s: print("  她 →", s))
        ws.disconnected.connect(lambda: print("断了"))
        QTimer.singleShot(1200, self._下一条)

    def _下一条(self):
        if os.environ.get("FAKE_SLEEP"):
            if self.客人:
                self.客人.sendTextMessage(json.dumps({"t": "act", "id": f"a{self.第}", "actions": ["sleep"]}, ensure_ascii=False))
                self.第 += 1
                QTimer.singleShot(6000, self._下一条)
            return
        if not self.客人 or self.第 >= len(剧本):
            print("剧本发完，5 秒后退出")
            QTimer.singleShot(5000, lambda: sys.exit(0))
            return
        m = 剧本[self.第]
        self.第 += 1
        self.客人.sendTextMessage(json.dumps(m, ensure_ascii=False))
        print(f"  核心 → {m['t']}")
        QTimer.singleShot(6000, self._下一条)


if os.environ.get("FAKE_SLEEP"):      # 只让她睡觉：量「最闲的时候吃多少 CPU」
    剧本 = [{"t": "act", "id": "a0", "actions": ["sleep"]}]

if __name__ == "__main__":
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication(sys.argv)
    核心 = 假核心(int(sys.argv[1]) if len(sys.argv) > 1 else 7899)   # 得留个引用，不然被回收
    sys.exit(app.exec())

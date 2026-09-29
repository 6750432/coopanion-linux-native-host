#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""接线 —— 跟核心（Node 那边）通话 + 念台词。

网页那边这两件事分别在 pet-app.js 的 connect()/onOrder() 和 stepDialog()/typeText() 里。
这里按同样的节奏重写：

    核心 → 她： init / say / act / walk / listen / thinking / prefs / ask / dialog / confirm
    她 → 核心： hello / touch / mode / arrived / interrupted / answer / control

念台词的节奏照抄 pet-app：
    · 每个 beat 先跑动作，留 .45 秒「起手」，再开始打字；
    · 打字 20 字/秒，遇到标点停 5 个字的时间；标点/空白不出声；
    · 打完停一下（最后一句停久一点），然后下一句；
    · 空文字的 beat 只停顿 .8 秒。
"""
from __future__ import annotations

import json
import re

from PySide6.QtCore import QObject, QUrl
from PySide6.QtWebSockets import QWebSocket

标点 = re.compile(r"[,。!?…、,.!?]")
静音 = re.compile(r"[\s,。!?…、,.!?「」:()]")
表情词 = {"neutral", "happy", "wink", "love", "shy", "surprised", "angry", "sad",
          "sleepy", "thinking", "sleep", "dizzy", "dragged", "content", "waking",
          "squeeze", "listening", "run"}
动作词 = {"stand", "jump", "hop", "look", "turn", "nod", "shake", "spin", "sit",
          "sleep", "walk", "run", "dizzy"}


class 台词:
    """Replays a list of beats (port of pet-app.js `stepDialog` + `typeText`).
    
    把一串 beats 念出来（pet-app.js 的 stepDialog + typeText）。
    """

    def __init__(self, 身体, 气泡):
        self.身体 = 身体
        self.气泡 = 气泡
        self.队: list[dict] = []
        self.条: dict | None = None

    def 推(self, beats, 种类="say"):
        self.队.append({"beats": list(beats or []), "种类": 种类})

    def 清(self):
        self.队.clear()
        self.条 = None
        self.气泡.收()

    def 忙(self):
        return self.条 is not None or bool(self.队)

    def 步(self, dt: float):
        T = self.身体.时间
        if self.条 is None:
            if not self.队 or self.身体.忙():
                return
            self.条 = {"beats": self.队.pop(0)["beats"], "i": -1, "shown": 0, "acc": 0.0,
                       "fired": 0, "startAt": 0.0, "beatDone": False, "holdUntil": 0.0,
                       "种类": "say", "空": ""}
        it = self.条
        beats = it["beats"]
        if it["i"] < 0 or it["beatDone"]:
            if it["beatDone"] and T < it["holdUntil"]:
                return
            it["i"] += 1
            it["beatDone"] = False
            if it["i"] >= len(beats):
                self.气泡.收()
                self.条 = None
                return
            b = beats[it["i"]] or {}
            lead = 0.0
            for a in (b.get("actions") or []):
                self._做(a)
                lead = .45
            it["shown"] = 0
            it["acc"] = 0.0
            it["fired"] = 0
            it["startAt"] = T + lead
            it["空"] = b.get("text") or ""
            if it["空"]:
                self.气泡.设(it["空"], 0, "say")
                self.身体.说话()
            else:
                self.气泡.收()
            return
        b = beats[it["i"]] or {}
        文 = b.get("text") or ""
        if T < it["startAt"]:
            return
        if not 文:
            it["beatDone"] = True
            it["holdUntil"] = T + .8
            return
        # 打字
        it["acc"] += dt * 20
        while it["acc"] >= 1 and it["shown"] < len(文):
            ch = 文[it["shown"]]
            it["shown"] += 1
            it["acc"] -= 5 if 标点.match(ch) else 1
            if not 静音.match(ch):
                self.身体.说话()
            for i in range(it["fired"], len(b.get("anchors") or [])):
                锚 = b["anchors"][i]
                if 锚.get("at", 0) <= it["shown"]:
                    for a in (锚.get("actions") or []):
                        self._做(a)
                    it["fired"] = i + 1
                else:
                    break
        self.气泡.设(文, it["shown"], "say")
        if it["shown"] >= len(文) and not it["beatDone"]:
            it["beatDone"] = True
            末 = it["i"] == len(beats) - 1
            it["holdUntil"] = T + ((1.6 + len(文) * .07) if 末 else (.9 + len(文) * .03))

    def _做(self, a: str):
        if not a:
            return
        if a in 动作词:
            self.身体.动作(a)
        elif a in 表情词:
            self.身体.设表情(a)


class 电台(QObject):
    """WebSocket link to the core (the web side is just `new WebSocket(...)`).
    
    跟核心的 WebSocket 连线（网页那边就是 new WebSocket(...)）。
    """

    def __init__(self, 宠):
        super().__init__()
        self.宠 = 宠
        self.地址 = None
        self.断开次数 = 0
        self.在线 = False
        self.听写中 = None
        self.sock = QWebSocket()
        self.sock.textMessageReceived.connect(self._收)
        self.sock.connected.connect(self._连上)
        self.sock.disconnected.connect(self._断了)
        self.等重连 = None

    # ── 连接 ───────────────────────────────────────────────
    def 接(self, pet_url: str):
        """pet_url 是核心给的 http://127.0.0.1:端口/pet，换成它的 ws 地址。"""
        if not pet_url:
            return
        u = QUrl(pet_url)
        根 = f"ws://{u.host()}:{u.port()}"
        self.地址 = f"{根}/socket?role=pet&host=window"
        self.sock.open(QUrl(self.地址))
        self.宠.记(f"连核心：{self.地址}")

    def _连上(self):
        self.在线 = True
        self.断开次数 = 0
        屏 = self.宠.屏幕
        self.发({"t": "hello", "screen": {"w": 屏.width(), "h": 屏.height()}, "host": "window"})
        self.宠.记("核心连上了")

    def _断了(self):
        self.在线 = False
        self.断开次数 += 1
        等 = min(8.0, .5 * self.断开次数)
        self.宠.记(f"核心断了，{等:.1f} 秒后重连")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(int(等 * 1000), lambda: self.sock.open(QUrl(self.地址)) if self.地址 else None)

    def 发(self, 字典: dict):
        if self.在线:
            try:
                self.sock.sendTextMessage(json.dumps(字典, ensure_ascii=False))
            except Exception as exc:
                self.宠.记("发不出去：", exc)

    # ── 收 ────────────────────────────────────────────────
    def _收(self, 文本: str):
        try:
            m = json.loads(文本)
        except Exception:
            return
        t = m.get("t")
        身 = self.宠.身体
        if t == "init":
            self.宠.收到快照(m)
        elif t == "say":
            self.宠.台词.推(m.get("beats") or [])
        elif t == "act":
            for a in (m.get("actions") or []):
                self.宠.台词._做(a)
        elif t == "walk":
            to = m.get("to")
            if isinstance(to, (int, float)):
                身.走过去(to * self.宠.屏幕.width(), bool(m.get("run")), m.get("id") or 0)
        elif t == "listen":
            self._听(m)
        elif t == "thinking":
            身.设思考(bool(m.get("on")))
        elif t == "prefs":
            self.宠.收到偏好(m)
        elif t in ("ask", "confirm", "dialog"):
            self.宠.收到提问(m)
        elif t == "dialog-update":
            self.宠.收到对话更新(m)
        elif t == "dialog-close":
            self.宠.气泡.收()

    def _听(self, m: dict):
        相 = m.get("phase")
        self.听写中 = 相
        if 相 in ("ready", "start"):
            self.宠.身体.设倾听(True)
            self.宠.气泡.设("（在听你说…）", 99, "heard")
        elif 相 == "partial":
            self.宠.气泡.设(m.get("text") or "…", 999, "heard")
        elif 相 == "transcribing":
            self.宠.气泡.设(m.get("text") or "（在听你说…）", 999, "heard")
        elif 相 == "heard":
            self.宠.气泡.设(m.get("text") or "", 999, "heard")
        elif 相 == "none":
            self.宠.身体.设倾听(False)
            self.宠.气泡.收()

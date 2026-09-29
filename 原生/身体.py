#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""身体 —— pet-core.js 里 createPet() 的 Python 版（网页桌宠的「身体模拟」）。

职责一模一样：管她的姿势和表情。
  · 模式机：idle / walk / run / look / sit / sleep / wake / crouch / air / land / dizzy / drag
  · 弹簧与缓动：走路起伏、跳跃压缩拉长、被拎起来的摆荡、转头
  · 眼睛：眨眼、视线跟随鼠标、换表情时先用一次眨眼盖过去
  · 交互：戳一下 → 随机表情 + 小跳；按住拖动 → 拎起来；快速甩动 → 扔出去
  · 小粒子：睡觉的 z、开心的爱心、跑步的扬尘、难过的眼泪

坐标同网页：logo 单位，脚底 y=256，面朝右；舞台用
translate(AX AY) rotate(rot) scale(kx ky) translate(-ax -ay) 摆放。
"""
from __future__ import annotations

import math
import random

# ── 几何常数（pet-core.js）────────────────────────────────
髋 = [[104, 212], [150, 212]]
腿宽 = 30
脚底y = 256 - 腿宽 / 2          # 241：圆头脚掌正好踩地
站立 = [[h[0], h[1], h[0], 脚底y] for h in 髋]

# 网页里给的锚点（鲸鱼自己在 figure.js 里覆盖了这五个）
默认锚点 = {"gaze": [140, 117], "tear": [166, 136], "z": [196, 40], "hearts": [90, 175, 34], "bubble": [146, 0]}


def _夹(v, a, b):
    return max(a, min(b, v))


def _插(a, b, k):
    return a + (b - a) * k


def _随(a, b):
    return a + random.random() * (b - a)


def _缓(rate, dt):
    return 1 - math.exp(-rate * dt)


def _顺(k):
    return k * k * (3 - 2 * k)


def _环(**o):
    出 = {"shape": "ring", "rx": 16, "ry": 16}
    出.update(o)
    return 出


def _哈欠(t):
    p = (t % 4.2) / 1.6
    return math.sin(math.pi * p) ** 2 if p < 1 else 0.0


# ── 脸表（pet-core.js 的 FACES）─────────────────────────────
脸表 = {
    "neutral":   {"标签": "平静", "f": lambda t, p: {"gap": [50, 50], "eyes": [_环(), _环()]}},
    "happy":     {"标签": "开心", "f": lambda t, p: {"gap": [58, 58], "eyes": [{"shape": "up"}, {"shape": "up"}], "blush": .45}},
    "wink":      {"标签": "眨眼", "f": lambda t, p: {"gap": [56, 52], "eyes": [_环(), {"shape": "up"}]}},
    "love":      {"标签": "喜欢", "f": lambda t, p: {"gap": [56, 56], "blush": .7, "emit": "heart",
                                                     "eyes": [{"shape": "heart", "s": .8 + .08 * math.sin(t * 9), "sw": 8}] * 2}},
    "shy":       {"标签": "害羞", "f": lambda t, p: {"gap": [40, 40], "blush": 1, "lookLock": True,
                                                     "eyes": [_环(rx=13, ry=12, dx=-3, dy=5)] * 2}},
    "surprised": {"标签": "惊讶", "f": lambda t, p: {"gap": [62, 62], "bang": True,
                                                     "eyes": [_环(rx=20, ry=21)] * 2}},
    "angry":     {"标签": "生气", "f": lambda t, p: {"gap": [36, 36], "brows": "angry", "anger": True, "shake": True,
                                                     "eyes": [_环(ry=11, dy=4)] * 2}},
    "sad":       {"标签": "难过", "f": lambda t, p: {"gap": [34, 40], "brows": "sad", "emit": "tear",
                                                     "eyes": [_环(ry=14, dy=4)] * 2}},
    "sleepy":    {"标签": "犯困", "f": lambda t, p: (lambda y: {"gap": [50 + 14 * y] * 2,
                                                                "eyes": [{"shape": "lid", "ry": 9 - 7 * y}] * 2})(_哈欠(t))},
    "sleep":     {"标签": "睡着", "f": lambda t, p: (lambda b: {"gap": [b, b], "emit": "z",
                                                                "eyes": [{"shape": "down"}] * 2})(40 + 6 * math.sin(t * 1.7))},
    "dizzy":     {"标签": "晕乎", "f": lambda t, p: {"gap": [54 + 5 * math.sin(t * 5), 48], "orbit": True,
                                                     "eyes": [{"shape": "spiral", "rot": t * 7}, {"shape": "spiral", "rot": t * 7 + 1.4}]}},
    "dragged":   {"标签": "被拎起", "f": lambda t, p: (lambda g: {"gap": [g, g], "sweat": True,
                                                                  "eyes": [{"shape": "gt"}, {"shape": "lt"}]})(55 + 3 * math.sin(t * 22))},
    "content":   {"标签": "惬意", "f": lambda t, p: (lambda r: {"gap": [46, 46], "eyes": [{"shape": "lid", "ry": r}] * 2})(11 - 9 * (p["drowse"] or 0))},
    "waking":    {"标签": "醒来", "f": lambda t, p: (lambda mt, k, y: {
        "gap": [50 + 12 * y] * 2,
        "eyes": [{"shape": "lid", "ry": max(0.0, 10 * k * (1 - .7 * y))}] * 2})(p["modeT"], _夹(p["modeT"] / .5, 0, 1),
                                                                              math.sin(_夹((p["modeT"] - .5) / .9, 0, 1) * math.pi) if p["modeT"] > .5 else 0)},
    "squeeze":   {"标签": "回神", "f": lambda t, p: {"gap": [44, 44], "eyes": [{"shape": "lid", "ry": 0}] * 2}},
    "listening": {"标签": "倾听", "f": lambda t, p: {"gap": [44, 44], "listen": True,
                                                     "eyes": [_环(rx=17, ry=18, dy=-1)] * 2}},
    "thinking":  {"标签": "思考", "f": lambda t, p: {"gap": [46, 46], "think": True,
                                                     "eyes": [_环(rx=14, ry=15, dx=3, dy=-4)] * 2}},
    "run":       {"标签": "冲刺", "f": lambda t, p: (lambda g: {"gap": [g, g], "sweat": True,
                                                                "eyes": [_环(), _环()]})(55 + 4 * math.sin(t * 16))},
}

# 动作时长（pet-app.js 的 DUR）
动作时长 = {"stand": 1.2, "jump": 1.2, "hop": .9, "look": 2.7, "turn": .4, "nod": .8,
           "shake": .8, "spin": .8, "sit": .8, "sleep": .8, "dizzy": 3.2}


class 身体:
    """A desktop pet's body. External surface: `步(dt)` → render info, pointer events, and a few commands.
    
    一只桌宠的身体。外部只需要：步(dt) → 渲染信息、指针事件、几个命令。
    """

    def __init__(self, 锚点=None, 边界=None, 漫游="calm", 进场="drop", 起始x=None,
                 事件=None, 对话打开=None, 音效=None):
        self.宠物 = {
            "x": 260.0, "fy": 0.0, "vx": 0.0, "vy": 0.0, "facing": 1, "faceVis": 1.0,
            "mode": "idle", "modeT": 0.0, "dur": 0.0, "target": 0.0,
            "speed": 0.0, "stride": 0.0, "lift": 0.0, "bob": 0.0, "phase": 0.0, "lastHalf": 0,
            "lean": 0.0, "tilt": 0.0, "tiltV": 0.0, "sq": 0.0, "sqv": 0.0, "sitK": 0.0,
            "stretch": 0.0, "low": 0.0, "gap": [50, 50], "look": [0, 0], "drowse": 0.0,
            "feet": [list(f) for f in 站立], "blinkT": 1.5, "blinkAge": 9, "expr": None, "exprUntil": 0,
            "nextAt": 1.2, "emitAt": 0, "airKind": "jump", "turned": False, "startle": False,
            "lastAct": "", "turnAcc": 0, "dx": 0.0, "dy": 0.0, "jumpV": 700, "jumpVx": 0, "xf": None,
            "blushK": 0.0, "eyeSig": "", "eyeCur": None, "eyePrev": None,
            "eyeDims": [[16, 16, 0, 0], [16, 16, 0, 0]], "swapAge": 9,
            "glance": [0, 0], "glanceAt": 0, "swing": 0.0, "swingV": 0.0, "prevA": None,
            "velX": 0.0, "talkK": 0.0, "sfxAt": 0, "skid": False, "cue": 0,
            "pulse": None, "walkId": 0, "listening": False, "thinking": False, "placed": False,
        }
        self.指针 = {"x": -1e4, "y": -1e4, "inside": False, "vx": 0.0, "samples": []}
        self.按下 = None
        self.笔画累积 = 0.0
        self.摸冷却 = 0.0
        self.粒子 = []
        self.W = 0.0
        self.H = 0.0
        self.地面 = 0.0
        self.S = .42
        self.T = 0.0
        self.漫游 = 漫游
        self.保持到 = 0.0
        self.事件 = 事件 or (lambda kind, d=None: None)
        self.对话打开 = 对话打开 or (lambda: False)
        self.音效 = 音效 or type("哑音效", (), {k: (lambda *a, **k2: None) for k in
                                              ("tick", "nod", "shake", "spin", "whoosh", "jump", "skid", "step",
                                               "hmm", "yawn", "chirps", "squeak", "grab", "purr", "poke",
                                               "surprised", "land", "snore", "expr")})()
        self.锚 = dict(默认锚点)
        if 锚点:
            self.锚.update(锚点)
        self._边界 = 边界 or (lambda: (self.W, self.H, self.地面, self.S))
        self.进场 = 进场
        self.起始x = 起始x
        self.调整尺寸()

    # ── 尺寸与坐标 ──────────────────────────────────────────
    def 调整尺寸(self):
        Wb, Hb, 地, S = self._边界()
        self.W, self.H, self.地面, self.S = Wb, Hb, 地, S
        p = self.宠物
        if not p["placed"] and self.W > 0:
            p["x"] = self.起始x if self.起始x is not None else self.W * .7
            p["placed"] = True
            if self.进场 == "drop":
                p["fy"] = -8; p["vy"] = 0; p["vx"] = 0; p["airKind"] = "drop"
                self.设模式("air")
        p["x"] = _夹(p["x"], self.最小x(), self.最大x())
        p["target"] = _夹(p["target"], self.最小x(), self.最大x())
        if p["mode"] not in ("air", "drag"):
            p["fy"] = self.地面

    def 最小x(self):
        return 104 * self.S + 8

    def 最大x(self):
        return self.W - 104 * self.S - 8

    def 到舞台(self, lx, ly):
        c = self.宠物["xf"]
        if not c:
            return self.宠物["x"], self.地面
        x = (lx - c["ax"]) * c["kx"]
        y = (ly - c["ay"]) * c["ky"]
        r = math.radians(c["rot"])
        return c["AX"] + x * math.cos(r) - y * math.sin(r), c["AY"] + x * math.sin(r) + y * math.cos(r)

    def 打到她(self, x, y):
        cx, cy = self.到舞台(128, 128)
        return math.hypot(x - cx, y - cy) < 108 * self.S

    # ── 命令 ───────────────────────────────────────────────
    def 设模式(self, m, **o):
        p = self.宠物
        prev = p["mode"]
        if prev in ("walk", "run") and m != "idle" and p["walkId"]:
            self.事件("interrupted", {"walkId": p["walkId"], "x": round(p["x"]), "by": m})
            p["walkId"] = 0
        p["mode"] = m; p["modeT"] = 0.0; p["turned"] = False; p["startle"] = False
        p["skid"] = False; p["cue"] = 0
        p.update(o)
        if prev != m:
            self.事件("mode", {"mode": m})

    def 忙(self):
        return self.宠物["mode"] in ("drag", "air", "crouch")

    def 挑目标(self, 最小距):
        for _ in range(12):
            x = _随(self.最小x(), self.最大x())
            if abs(x - self.宠物["x"]) > 最小距:
                return x
        p = self.宠物
        return self.最小x() if (p["x"] - self.最小x()) > (self.最大x() - p["x"]) else self.最大x()

    def 动作(self, a):
        """跑一个动作；身体现在做不了（在空中、被拎着）就返回 False。"""
        if self.忙():
            return False
        p = self.宠物
        p["expr"] = None; p["lastAct"] = a
        坐睡 = p["mode"] in ("sleep", "sit")
        if a == "stand":
            self.设模式("wake" if 坐睡 else "idle", startle=False)
            p["nextAt"] = self.T + 3
        elif a == "walk":
            self.设模式("walk", target=self.挑目标(160))
        elif a == "run":
            self.设模式("run", target=self.最大x() - _随(0, 30) if p["x"] < self.W / 2 else self.最小x() + _随(0, 30))
        elif a == "jump":
            self.设模式("crouch", jumpV=720, jumpVx=p["facing"] * 40)
        elif a == "hop":
            self.设模式("crouch", jumpV=480, jumpVx=0)
        elif a == "look":
            self.设模式("look")
        elif a == "turn":
            if not 坐睡:
                self.设模式("idle")
            p["facing"] *= -1; self.音效.tick()
        elif a == "nod":
            self.脉冲("nod", .7); self.音效.nod()
        elif a == "shake":
            self.脉冲("shake", .7); self.音效.shake()
        elif a == "spin":
            if not 坐睡:
                self.设模式("idle")
            self.脉冲("spin", .6); self.音效.spin()
        elif a == "sit":
            self.设模式("sit", dur=1e9)
        elif a == "sleep":
            self.设模式("sleep", dur=1e9)
        elif a == "dizzy":
            self.设模式("dizzy")
        else:
            return False
        return True

    def 脉冲(self, kind, dur):
        self.宠物["pulse"] = {"kind": kind, "t0": self.T, "dur": dur}

    def 设表情(self, n, seconds=None):
        p = self.宠物
        if n == "sleep":
            self.动作("sleep"); return
        if self.忙():
            return
        if n == "dragged":                      # 被扔掉
            p["expr"] = None
            p["vy"] = -1150; p["vx"] = _随(-120, 120); p["airKind"] = "throw"; p["sqv"] -= 3
            self.音效.whoosh(); self.音效.jump()
            self.设模式("air"); return
        if n == "dizzy":
            p["expr"] = None; self.设模式("dizzy"); return
        if p["mode"] in ("look", "land"):
            self.设模式("idle")
        p["expr"] = n
        p["exprUntil"] = self.T + (seconds if seconds is not None else (4.4 if n == "sleepy" else 3.2))
        p["nextAt"] = max(p["nextAt"], p["exprUntil"] + .6)
        p["sqv"] += -2.2 if n == "surprised" else .8
        self.音效.expr(n)
        if n == "love":
            for _ in range(4):
                self.冒爱心()

    def 走过去(self, x, 跑=False, walkId=0):
        p = self.宠物
        if self.忙():
            return False
        if p["mode"] in ("sleep", "sit"):
            self.设模式("wake", startle=True)
        目标 = _夹(x, self.最小x(), self.最大x())
        p["expr"] = None
        if abs(目标 - p["x"]) < 2:
            self.事件("arrived", {"walkId": walkId, "x": round(p["x"])})
            return True
        self.设模式("run" if 跑 else "walk", target=目标, walkId=walkId)
        return True

    def 表情名(self):
        p = self.宠物
        m = p["mode"]
        if m == "drag":
            return "dragged"
        if m == "air" and p["airKind"] == "throw":
            return "dragged" if p["vy"] < 0 else "surprised"
        if m == "air" and p["airKind"] == "drop":
            return "surprised"
        if m == "dizzy":
            return "dizzy" if p["modeT"] < 2.4 else "squeeze"
        if m == "wake":
            return "surprised" if p["startle"] else "waking"
        if p["listening"] and m != "sleep":
            return "listening"
        if m == "sleep":
            return "sleep"
        if p["expr"] and self.T < p["exprUntil"]:
            return p["expr"]
        if p["thinking"]:
            return "thinking"
        if m == "sit":
            return "content"
        if m == "run":
            return "run"
        return "neutral"

    def 自己决定(self):
        p = self.宠物
        静 = self.漫游 == "calm"
        选项 = [("walk", 10 if 静 else 28), ("run", 0 if 静 else 12), ("look", 14),
                ("jump", 2 if 静 else 8), ("sit", 16), ("expr", 12), ("wait", 30 if 静 else 10)]
        选项 = [o for o in 选项 if o[1] > 0 and (o[0] != p["lastAct"] or o[0] == "wait")]
        总 = sum(o[1] for o in 选项)
        r = random.random() * 总
        挑 = "wait"
        for o in 选项:
            r -= o[1]
            if r < 0:
                挑 = o[0]; break
        if 挑 == "look":
            self.设模式("look"); p["lastAct"] = "look"
        elif 挑 == "expr":
            self.设表情(random.choice(["happy", "wink", "love", "sleepy", "surprised", "shy"]))
            p["lastAct"] = "expr"
        elif 挑 == "sit":
            self.设模式("sit", dur=_随(6, 9)); p["lastAct"] = "sit"
        elif 挑 != "wait":
            self.动作(挑)
        if p["mode"] == "idle" and self.T >= p["nextAt"]:
            p["nextAt"] = self.T + _随(2, 4)

    # ── 粒子 ───────────────────────────────────────────────
    def 冒(self, 类型, x, y, **o):
        项 = {"type": 类型, "x": x, "y": y, "vx": 0.0, "vy": 0.0, "age": 0.0, "life": 1.0}
        项.update(o)
        self.粒子.append(项)

    def 冒爱心(self):
        p = self.宠物
        a = self.锚["hearts"]
        x, y = self.到舞台(_随(a[0], a[1]), a[2] + p["low"])
        self.冒("heart", x, y, vx=_随(-20, 20), vy=_随(-70, -45), life=1.6)

    def 扬尘(self, lx, n, spread):
        p = self.宠物
        for _ in range(n):
            x, y = self.到舞台(lx, 250)
            self.冒("dust", x, y, vx=_随(-spread, spread) - p["facing"] * _随(10, 40),
                    vy=_随(-30, -8), life=_随(.4, .65))

    # ── 每帧 ───────────────────────────────────────────────
    def 步(self, dt: float):
        p = self.宠物
        self.T += dt
        p["modeT"] += dt
        m, mt = p["mode"], p["modeT"]
        sqT = strideT = liftT = leanT = sitT = bobT = 0.0
        rate = 0.0
        lookT = [0.0, 0.0]
        tiltT = 0.0
        tk, tc = 160.0, 12.0
        drowseT = 0.0
        自由 = self.漫游 != "off" and self.T > self.保持到 and not self.对话打开()

        p["blinkT"] -= dt
        p["blinkAge"] += dt
        if p["blinkT"] <= 0:
            p["blinkAge"] = 0
            p["blinkT"] = .28 if random.random() < .2 else _随(2.2, 5.2)

        指 = self.指针
        头 = self.到舞台(self.锚["gaze"][0], self.锚["gaze"][1])
        pdx = 指["x"] - 头[0]
        pdy = 指["y"] - 头[1]
        pm = math.hypot(pdx, pdy) or 1

        def 追视():
            if not 指["inside"]:
                if self.T > p["glanceAt"]:
                    p["glance"] = [0, 0] if random.random() < .45 else [_随(-3, 5), _随(-3, 3)]
                    p["glanceAt"] = self.T + _随(1.2, 3)
                return p["glance"]
            k = min(1.0, pm / 120)
            return [pdx * p["facing"] / pm * 5 * k, pdy / pm * 4 * k]

        if m == "idle":
            lookT = 追视()
            if 指["inside"] and not self.按下 and pdx * p["facing"] < -50 and pm < 600:
                p["turnAcc"] += dt
                if p["turnAcc"] > .9:
                    p["facing"] *= -1; p["turnAcc"] = 0
            else:
                p["turnAcc"] = 0
            if p["listening"]:
                lookT = [3, -4]; tiltT = -7; leanT = -2
            if 自由 and not p["listening"] and self.T > p["nextAt"] and not (p["expr"] and self.T < p["exprUntil"]):
                self.自己决定()
        elif m in ("walk", "run"):
            跑 = m == "run"
            d = p["target"] - p["x"]
            距 = abs(d)
            方向 = (1 if d > 0 else (-1 if d < 0 else 0)) or p["facing"]
            p["facing"] = 方向
            vMax = 250 if 跑 else 78
            vT = min(vMax, 距 * 4 + 20 if 跑 else 距 * 3 + 14)
            strideT = 17 if 跑 else 10
            liftT = 15 if 跑 else 8
            bobT = 7 if 跑 else 3
            rate = 4.4 if 跑 else 2.1
            leanT = (11 if not (距 < 50 and p["speed"] > 120) else -6) if 跑 else 4
            if leanT < 0 and not p["skid"]:
                p["skid"] = True; self.音效.skid()
            ramp = min(1.0, mt / (.35 if 跑 else .25))
            p["speed"] = _插(p["speed"], vT * _顺(ramp), _缓(6 if 跑 else 9, dt))
            p["x"] += 方向 * min(距, p["speed"] * dt)
            k = _夹(p["speed"] / vMax, 0, 1)
            strideT *= .4 + .6 * k
            liftT *= .4 + .6 * k
            p["phase"] += math.pi * 2 * rate * dt * max(.35, k)
            lookT = [4 if 跑 else 3, 1 if 跑 else 0]
            half = int(p["phase"] // math.pi)
            if half != p["lastHalf"]:
                self.音效.step(跑, half & 1)
                if 跑 and p["speed"] > 120:
                    self.扬尘(128, 3 if 距 < 50 else 1, 20)
            p["lastHalf"] = half
            if 距 < 1.5:
                p["speed"] = 0
                wid = p["walkId"]; p["walkId"] = 0
                self.设模式("idle"); p["nextAt"] = self.T + _随(1.2, 3.2)
                if wid:
                    self.事件("arrived", {"walkId": wid, "x": round(p["x"])})
        elif m == "look":
            if not p["cue"]:
                p["cue"] = 1; self.音效.hmm()
            if mt < .9:
                lookT = [4, -4]
            elif mt < 1.8:
                if not p["turned"]:
                    p["turned"] = True; p["facing"] *= -1
                lookT = [5, 0]
            elif mt < 2.6:
                lookT = [1, 4]
            else:
                self.设模式("idle"); p["nextAt"] = self.T + _随(1, 2.5)
        elif m == "sit":
            sitT = 1
            lookT = [v * (1 - p["drowse"]) for v in 追视()]
            if p["listening"]:
                lookT = [3, -4]; tiltT = -7
            drowseT = _夹((mt - 1.5) / max(1, min(p["dur"], 60) - 1.5), 0, 1 if 自由 else .45)
            if p["drowse"] > .5:
                leanT = 7 * p["drowse"] * max(0.0, math.sin(self.T * 1.3)) ** 6
            if 自由 and mt > p["dur"]:
                if random.random() < .6:
                    self.设模式("sleep", dur=_随(8, 12))
                else:
                    self.设模式("idle"); p["sqv"] -= 1.2; p["nextAt"] = self.T + _随(1.5, 3)
        elif m == "sleep":
            sitT = 1; drowseT = 1; leanT = 5
            if 自由 and mt > p["dur"]:
                self.设模式("wake")
        elif m == "wake":
            if p["startle"]:
                sitT = 0; lookT = [3, -2]
                if mt > .9:
                    self.设模式("idle"); p["nextAt"] = self.T + _随(1.5, 3)
            else:
                sitT = 1 if mt < 1.1 else 0
                if mt > .5 and not p["cue"]:
                    p["cue"] = 1; self.音效.yawn()
                sqT = -.1 if .5 < mt < 1.3 else 0
                leanT = 5 if mt < .5 else (-5 if mt < 1.2 else 0)
                lookT = 追视() if mt > 1.2 else [0, 0]
                if mt > 1.8:
                    self.设模式("idle"); p["nextAt"] = self.T + _随(1, 2)
        elif m == "crouch":
            sqT = .24; sitT = .3
            if mt > .16:
                p["vy"] = -p["jumpV"]; p["vx"] = p["jumpVx"]; p["airKind"] = "jump"; p["sqv"] -= 2.6
                self.音效.jump()
                self.设模式("air")
        elif m == "air":
            p["vy"] += 2300 * dt
            p["vx"] *= math.exp(-dt * .4)
            p["x"] += p["vx"] * dt
            p["fy"] += p["vy"] * dt
            if p["x"] < self.最小x():
                p["x"] = self.最小x(); p["vx"] = abs(p["vx"]) * .55; p["sqv"] += .6
            if p["x"] > self.最大x():
                p["x"] = self.最大x(); p["vx"] = -abs(p["vx"]) * .55; p["sqv"] += .6
            if p["fy"] - 250 * self.S < 0 and p["vy"] < 0:
                p["fy"] = 250 * self.S; p["vy"] = abs(p["vy"]) * .3
            sqT = -min(.12, abs(p["vy"]) / 6000)
            tiltT = _夹(p["vx"] * .025, -30, 30)
            tk, tc = 70, 8
            if p["fy"] >= self.地面 and p["vy"] > 0:
                self.落地()
        elif m == "land":
            sitT = .35 * (1 - _顺(_夹(mt / .35, 0, 1)))
            lookT = [2, 2]
            if mt > .4:
                self.设模式("idle")
        elif m == "dizzy":
            sitT = 1 if mt < 2.6 else 0
            if mt < 2.4 and self.T > p["sfxAt"]:
                self.音效.chirps(); p["sfxAt"] = self.T + .9
            if mt >= 2.4 and not p["cue"]:
                p["cue"] = 1; self.音效.shake()
            if mt < 2.4:
                tiltT = 8 * math.sin(self.T * 4.5) * min(1.0, mt * 2)
            elif mt < 3:
                k = (mt - 2.4) / .6
                tiltT = 12 * math.sin(mt * 34) * (1 - k)
            else:
                self.设模式("idle"); p["sqv"] -= 1; p["nextAt"] = self.T + _随(1.5, 3)
        elif m == "drag":
            p["dx"] = _插(p["dx"], 指["x"], _缓(28, dt))
            p["dy"] = _插(p["dy"], min(指["y"], self.地面 - 245 * self.S), _缓(28, dt))
            tiltT = _夹(指["vx"] * .035, -40, 40)
            tk, tc = 90, 5
            if abs(指["vx"]) > 500 and self.T > p["sfxAt"]:
                self.音效.squeak(); p["sfxAt"] = self.T + _随(.4, .7)

        # 叠在姿势上的小动作
        if p["pulse"]:
            k = (self.T - p["pulse"]["t0"]) / p["pulse"]["dur"]
            if k >= 1:
                p["pulse"] = None
            elif p["pulse"]["kind"] == "nod":
                leanT += 9 * abs(math.sin(k * math.pi * 2))
            elif p["pulse"]["kind"] == "shake":
                tiltT += 10 * math.sin(k * math.pi * 6) * (1 - k)
            elif p["pulse"]["kind"] == "spin" and k > .5 and not p["pulse"].get("flipped"):
                p["pulse"]["flipped"] = True; p["facing"] *= -1
            elif p["pulse"]["kind"] == "spin" and k < .5 and not p["pulse"].get("first"):
                p["pulse"]["first"] = True; p["facing"] *= -1; p["sqv"] -= 1

        名 = self.表情名()
        fc = 脸表[名]["f"](self.T, p)
        if fc.get("lookLock") or m in ("sleep", "drag"):
            lookT = [0, 0]

        # 换眼型时用一次快速眨眼盖过去；同形状的尺寸变化则缓缓插值
        sig = ",".join(e["shape"] for e in fc["eyes"])
        if sig != p["eyeSig"]:
            if p["eyeCur"]:
                p["eyePrev"] = p["eyeCur"]; p["swapAge"] = 0
            p["eyeSig"] = sig
            for i, e in enumerate(fc["eyes"]):
                p["eyeDims"][i] = [e.get("rx", 16), e.get("ry", 16), e.get("dx", 0), e.get("dy", 0)]
        p["swapAge"] += dt
        新眼 = []
        for i, e in enumerate(fc["eyes"]):
            if e["shape"] not in ("ring", "lid"):
                新眼.append(e); continue
            d = p["eyeDims"][i]
            tgt = [e.get("rx", 16), e.get("ry", 16), e.get("dx", 0), e.get("dy", 0)]
            for j in range(4):
                d[j] = _插(d[j], tgt[j], _缓(16, dt))
            新眼.append({**e, "rx": d[0], "ry": d[1], "dx": d[2], "dy": d[3]})
        p["eyeCur"] = 新眼
        p["blushK"] = _插(p["blushK"], fc.get("blush", 0) or 0, _缓(6, dt))

        # 弹簧与缓动
        p["sqv"] += ((sqT - p["sq"]) * 280 - p["sqv"] * 14) * dt
        p["sq"] = _夹(p["sq"] + p["sqv"] * dt, -.35, .45)
        p["tiltV"] += ((tiltT - p["tilt"]) * tk - p["tiltV"] * tc) * dt
        p["tilt"] += p["tiltV"] * dt
        p["lean"] = _插(p["lean"], leanT, _缓(7, dt))
        p["sitK"] = _插(p["sitK"], sitT, _缓(18 if m == "land" else 6, dt))
        p["drowse"] = _插(p["drowse"], drowseT, _缓(1.5 if m in ("sit", "sleep") else 6, dt))
        p["stretch"] = _插(p["stretch"], 1 if m == "drag" else 0, _缓(8, dt))
        p["stride"] = _插(p["stride"], strideT, _缓(10, dt))
        p["lift"] = _插(p["lift"], liftT, _缓(10, dt))
        p["bob"] = _插(p["bob"], bobT, _缓(10, dt))
        p["look"][0] = _插(p["look"][0], lookT[0], _缓(9, dt))
        p["look"][1] = _插(p["look"][1], lookT[1], _缓(9, dt))
        p["gap"][0] = _插(p["gap"][0], fc["gap"][0], _缓(8, dt))
        p["gap"][1] = _插(p["gap"][1], fc["gap"][1], _缓(8, dt))
        p["faceVis"] = _插(p["faceVis"], p["facing"], _缓(15, dt))
        if m not in ("walk", "run"):
            p["phase"] = _插(p["phase"], round(p["phase"] / math.pi) * math.pi, _缓(6, dt))
        指["vx"] *= math.exp(-dt * 6)

        # 耳朵/呆毛/围巾这类次级运动：比身体慢半拍
        AX = p["dx"] if m == "drag" else p["x"]
        if p["prevA"] is not None:
            p["velX"] = _插(p["velX"], (AX - p["prevA"]) / dt, .25)
        p["prevA"] = AX
        swingT = _夹(-p["velX"] * .06 * (1 if (p["faceVis"] or 1) >= 0 else -1), -28, 28)
        p["swingV"] += ((swingT - p["swing"]) * 110 - p["swingV"] * 7) * dt
        p["swing"] = _夹(p["swing"] + p["swingV"] * dt, -40, 40)

        p["low"] = p["sitK"] * 29 + p["bob"] * abs(math.sin(p["phase"]))
        for i, ft in enumerate(p["feet"]):
            hx, hy = 髋[i][0], 髋[i][1] + p["low"]
            if m == "drag":
                tx = hx + 7 * math.sin(self.T * 11 + i * 2.2); ty = hy + 36
            elif m == "air":
                tx = hx + (9 if i else -9); ty = hy + 33
            else:
                ph = p["phase"] + i * math.pi
                sx = hx + p["stride"] * math.sin(ph)
                sy = 脚底y - p["lift"] * max(0.0, math.cos(ph))
                tx = _插(sx, hx + 26, p["sitK"]); ty = _插(sy, 脚底y, p["sitK"])
            r = 14 if m in ("drag", "air") else 40
            ft[0] = _插(ft[0], tx, _缓(r, dt))
            ft[1] = _插(ft[1], ty, _缓(r, dt))

        if fc.get("emit") and self.T > p["emitAt"]:
            if fc["emit"] == "heart":
                self.冒爱心(); p["emitAt"] = self.T + .45
            elif fc["emit"] == "z":
                x, y = self.到舞台(self.锚["z"][0], self.锚["z"][1] + p["low"])
                self.冒("z", x, y, vx=p["facing"] * 16, vy=-26, life=2.4)
                p["emitAt"] = self.T + 1.3; self.音效.snore()
            elif fc["emit"] == "tear":
                x, y = self.到舞台(self.锚["tear"][0] + p["look"][0], self.锚["tear"][1] + p["low"])
                self.冒("drop", x, y, vx=p["facing"] * _随(10, 30), vy=-20, life=3)
                p["emitAt"] = self.T + .8

        self.笔画累积 *= math.exp(-dt * 1.5)
        self.摸冷却 -= dt
        for i in range(len(self.粒子) - 1, -1, -1):
            q = self.粒子[i]
            q["age"] += dt
            q["x"] += q["vx"] * dt
            q["y"] += q["vy"] * dt
            if q["type"] == "drop":
                q["vy"] += 900 * dt
                if q["y"] > self.地面:
                    q["age"] = q["life"]
            if q["type"] == "dust":
                q["vx"] *= math.exp(-dt * 4)
            if q["age"] >= q["life"]:
                self.粒子.pop(i)
        p["talkK"] *= math.exp(-dt * 12)
        p["_fc"] = fc
        p["_fname"] = 名

    def 落地(self):
        p = self.宠物
        impact, kind = p["vy"], p["airKind"]
        p["fy"] = self.地面; p["vy"] = 0; p["vx"] = 0
        p["sqv"] += _夹(impact * .0024, .8, 4.5)
        self.音效.land(kind != "jump" and impact > 1000)
        self.扬尘(128, 7 if impact > 900 else 3, 70)
        if kind == "throw" and impact > 1000:
            self.设模式("dizzy"); self.事件("touch", {"kind": "crash"}); return
        self.设模式("land")
        if kind == "throw":
            p["expr"] = "surprised"; p["exprUntil"] = self.T + .9; p["nextAt"] = self.T + 2
        elif kind == "drop":
            p["expr"] = "happy"; p["exprUntil"] = self.T + 1.6; p["nextAt"] = self.T + 2.6
        else:
            p["nextAt"] = self.T + _随(.8, 2)

    # ── 出帧：交给小鱼画 ────────────────────────────────────
    def 出帧(self):
        """对照 pet-core 的 render()：算好舞台变换、脸、和喂给 figure 的那一份。"""
        p = self.宠物
        fc = p.get("_fc") or 脸表["neutral"]["f"](0, p)
        名 = p.get("_fname") or "neutral"
        拖 = p["mode"] == "drag"
        br = math.sin(self.T * (1.7 if p["mode"] == "sleep" else 2.4))
        sx = (1 + p["sq"] * .7) * (1 - .05 * p["stretch"]) * (1 - .009 * br)
        sy = (1 - p["sq"]) * (1 + .09 * p["stretch"]) * (1 + .016 * br)
        ax, ay = 128, (36 if 拖 else 256)
        AX = p["dx"] if 拖 else p["x"]
        AY = p["dy"] if 拖 else p["fy"]
        if fc.get("shake"):
            AX += math.sin(self.T * 60) * 1.4
        kx = self.S * p["faceVis"] * sx
        ky = self.S * sy
        lean = p["lean"] * p["faceVis"]
        rot = p["tilt"] + lean
        p["xf"] = {"AX": AX, "AY": AY, "ax": ax, "ay": ay, "kx": kx, "ky": ky, "rot": rot}

        legs = [[髋[i][0], 髋[i][1] + p["low"], p["feet"][i][0], p["feet"][i][1]] for i in range(2)]
        blink = math.sin(math.pi * p["blinkAge"] / .16) if p["blinkAge"] < .16 else 0.0
        eyes = p["eyeCur"] or fc["eyes"]
        eyeClose = 0.0
        if p["swapAge"] < .07 and p["eyePrev"]:
            eyes = p["eyePrev"]; eyeClose = p["swapAge"] / .07
        elif p["swapAge"] < .16:
            eyeClose = 1 - (p["swapAge"] - .07) / .09
        脸 = {**fc, "eyes": eyes, "gap": [min(64, g + p["talkK"] * 12) for g in p["gap"]], "blush": p["blushK"]}
        帧 = {"look": list(p["look"]), "legs": legs, "low": p["low"], "t": self.T, "blink": blink,
              "eyeClose": eyeClose, "swing": p["swing"], "face": 名, "mode": p["mode"],
              "modeT": p["modeT"], "talk": p["talkK"], "drowse": p["drowse"], "sit": p["sitK"],
              "facing": p["faceVis"], "tilt": p["tilt"], "lean": lean, "groupRot": rot}
        return 脸, 帧

    # ── 指针 ───────────────────────────────────────────────
    def 指针按下(self, x, y):
        self.指针.update({"x": x, "y": y, "inside": True})
        if not self.打到她(x, y) or self.宠物["mode"] == "air":
            return False
        self.按下 = {"x": x, "y": y, "t": self.T * 1000}
        self.指针["samples"] = [{"t": self.T * 1000, "x": x, "y": y}]
        return True

    def _速度(self):
        s = self.指针["samples"]
        if len(s) < 2:
            return 0.0, 0.0
        a, b = s[0], s[-1]
        dt = max(.016, (b["t"] - a["t"]) / 1000)
        return (b["x"] - a["x"]) / dt, (b["y"] - a["y"]) / dt

    def 指针移动(self, x, y):
        """返回舞台该显示的光标：'' / 'grab' / 'grabbing'"""
        p, 指 = self.宠物, self.指针
        now = self.T * 1000
        ddx, ddy = x - 指["x"], y - 指["y"]
        指.update({"x": x, "y": y, "inside": True})
        指["samples"].append({"t": now, "x": x, "y": y})
        while len(指["samples"]) > 2 and now - 指["samples"][0]["t"] > 110:
            指["samples"].pop(0)
        vx, _vy = self._速度()
        指["vx"] = _插(指["vx"], vx, .35)
        if self.按下 and p["mode"] != "drag" and math.hypot(x - self.按下["x"], y - self.按下["y"]) > 6:
            scruff = self.到舞台(128, 36)
            p["expr"] = None
            self.设模式("drag", dx=scruff[0], dy=scruff[1])
            self.音效.grab()
            p["sqv"] -= 1.2; p["tiltV"] = 0
            self.事件("touch", {"kind": "grab"})
        if self.按下:
            return "grabbing"
        over = self.打到她(x, y)
        if over and p["mode"] in ("idle", "look", "sit", "sleep"):
            self.笔画累积 += math.hypot(ddx, ddy)
            if self.笔画累积 > 320 and self.摸冷却 <= 0:
                self.笔画累积 = 0; self.摸冷却 = 2.5
                self.音效.purr()
                if p["mode"] == "sleep":
                    self.冒爱心()
                else:
                    self.设表情("love" if random.random() < .5 else "shy")
                self.事件("touch", {"kind": "pet", "asleep": p["mode"] == "sleep"})
        return "grab" if over else ""

    def 指针松开(self):
        p = self.宠物
        if not self.按下:
            return
        if p["mode"] == "drag":
            # 从后颈锚点交到脚底锚点，画面不跳
            foot = self.到舞台(128, 256)
            vx, vy = self._速度()
            p["x"] = _夹(foot[0], self.最小x(), self.最大x())
            p["fy"] = min(self.地面, foot[1])
            p["vx"] = _夹(vx, -1800, 1800)
            p["vy"] = _夹(vy, -1800, 1400)
            p["airKind"] = "throw"
            speed = math.hypot(vx, vy)
            if speed > 700:
                self.音效.whoosh()
            self.设模式("air")
            self.事件("touch", {"kind": "throw" if speed > 700 else "drop", "x": round(p["x"])})
        elif self.T * 1000 - self.按下["t"] < 400:
            if p["mode"] in ("sleep", "sit"):
                睡着的 = p["mode"] == "sleep"
                self.设模式("wake", startle=True); p["sqv"] -= 2.2; p["nextAt"] = self.T + 2.4
                self.音效.surprised()
                self.事件("touch", {"kind": "poke", "woke": 睡着的})
            elif p["mode"] != "dizzy":
                self.音效.poke()
                self.设表情(random.choice(["happy", "wink", "surprised", "love", "angry"]))
                if random.random() < .5 and p["mode"] == "idle":
                    self.设模式("crouch", jumpV=480, jumpVx=0)
                self.事件("touch", {"kind": "poke"})
        self.按下 = None

    def 指针离开(self):
        if not self.按下:
            self.指针["inside"] = False

    # ── 小接口 ─────────────────────────────────────────────
    @property
    def 时间(self):
        return self.T

    def 抱一下(self, 秒):
        self.保持到 = max(self.保持到, self.T + 秒)

    def 说话(self):
        self.宠物["talkK"] = 1.0

    def 设倾听(self, 开):
        p = self.宠物
        p["listening"] = 开
        if 开 and p["mode"] in ("walk", "run"):
            self.设模式("idle")

    def 设思考(self, 开):
        self.宠物["thinking"] = 开

    def 气泡锚点(self):
        p = self.宠物
        return self.到舞台(self.锚["bubble"][0], self.锚["bubble"][1] + p["low"])

    def 边界(self):
        return {"W": self.W, "H": self.H, "floorY": self.地面, "S": self.S,
                "minX": self.最小x(), "maxX": self.最大x()}

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""小鱼 —— figure.js 的 Python 版：把「身体一帧」翻译成绑骨参数。

网页那边这份代码（web/whale/figure.js）干三件事：
  1. 一堆弹簧（头发、刘海、裙子、尾鳍、呆毛、头）算出本帧的摇摆量；
  2. 把身体给的姿势（走路、跳、被拎、坐、睡…）翻译成每个变形器的状态；
  3. 顺手把脸画出来、把心/眼泪/问号这些小花样画在人物上方。

这里按同样的顺序算，只是输出给「网格渲染器」而不是 WebGL。
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen

from 模型 import FACE, HEAD, 鲸鱼模型
from 网格 import 网格渲染器
from 脸 import 脸画师


def _夹(v, a, b):
    return max(a, min(b, v))


def _插(a, b, k):
    return a + (b - a) * k


def _缓(rate, dt):
    return 1 - math.exp(-rate * dt)


def _鼓(u):
    return math.sin(math.pi * _夹(u, 0, 1))


def _顺(a, b, x):
    k = _夹((x - a) / (b - a), 0, 1)
    return k * k * (3 - 2 * k)


def _圆整(n):
    return round(n * 100) / 100


class 弹簧:
    """Spring integrator ported from figure.js; the `lim` clamp stops hair from folding through itself.
    
    figure.js 的 spring()：不限位时会过冲，头发不能折过来，所以给了 lim。
    """

    __slots__ = ("x", "v", "k", "c", "lim")

    def __init__(self, k: float, c: float, lim: float = float("inf")):
        self.x = 0.0
        self.v = 0.0
        self.k, self.c, self.lim = k, c, lim

    def 步(self, 目标: float, dt: float) -> float:
        self.v += ((目标 - self.x) * self.k - self.v * self.c) * dt
        self.x += self.v * dt
        if abs(self.x) > self.lim:
            self.x = math.copysign(self.lim, self.x)
            self.v = 0.0
        return self.x


# 脸的鳍/尾巴情绪：鳍扬起（+）还是垂下（-），尾巴摆多大
情绪 = {
    "happy": (.8, 1), "love": (.9, 1), "wink": (.5, .7), "surprised": (1, .2), "angry": (.9, .15),
    "sad": (-1, 0), "shy": (-.5, .3), "sleepy": (-.7, 0), "sleep": (-.9, 0), "dizzy": (-.3, 0),
    "dragged": (.6, .6), "content": (-.2, .25), "listening": (.6, .2), "thinking": (.1, .15),
    "run": (.2, .4), "waking": (-.4, 0), "squeeze": (-.3, 0), "neutral": (0, .25),
}
# 身体倾斜分配给整个人物组还是留给脖子（figure.js 的 GROUP）
组倾 = {"air": (1, 1), "drag": (1, 1), "crouch": (1, 1), "land": (1, 1), "walk": (1, .5), "run": (1, .5)}


class 小鱼:
    """The fish's renderer. The body calls `画()` every frame and receives the deformer state and the face image back.
    
    一只小鱼的「画法」。身体（身体.py）每帧调 画()，拿回变形器状态和脸图。
    """

    def __init__(self, 模型: 鲸鱼模型, 渲染器: 网格渲染器):
        self.模型 = 模型
        self.渲染器 = 渲染器
        self.脸画师 = 脸画师(模型)
        self.配色名 = 模型.配色
        项 = next((s for s in 模型.配色表 if s["id"] == 模型.配色), {})
        self.强调色 = QColor(项.get("accent") or "#4d6bfe")
        self.弹簧 = {
            "hair": 弹簧(55, 7, 1.8), "hairY": 弹簧(50, 8, 1.2), "bangs": 弹簧(110, 10, 1.6),
            "skirt": 弹簧(100, 9, 1.6), "skirtY": 弹簧(90, 10, 1.1), "tail": 弹簧(40, 5, 32),
            "fins": 弹簧(90, 9, 30), "ahoge": 弹簧(140, 6, 38), "head": 弹簧(70, 10, 16),
            "armN": 弹簧(60, 9, 95), "armF": 弹簧(60, 9, 95),
        }
        self.重置()

    def 重置(self):
        for s in self.弹簧.values():
            s.x = s.v = 0.0
        self.上次t = None
        self.上次倾 = 0.0
        self.上次低 = 0.0
        self.头倾 = 0.0
        self.组w倾 = 0.0
        self.组w靠 = 0.0
        self.鳍情绪 = 0.0
        self.尾情绪 = 0.0
        self.摆幅 = 0.0
        self.坐k = 0.0

    def 组倾角(self, 模式: str, 倾: float, 靠: float) -> float:
        """身体本来想给整个人物组的倾斜；组没拿走的那部分，figure 会还给脖子。"""
        return 倾 * self.组w倾 + 靠 * self.组w靠

    # ── 主循环 ──────────────────────────────────────────────
    def 画(self, 脸: dict, 帧: dict) -> dict:
        """脸 = pet-core 算好的这张脸；帧 = 身体本帧的状态（照 render() 那份喂）。"""
        t = 帧.get("t", 0.0)
        dt = 1 / 60 if self.上次t is None else _夹(t - self.上次t, 0, .05)
        self.上次t = t
        模式 = 帧.get("mode", "idle")
        名 = 帧.get("face", "neutral")
        走 = 模式 in ("walk", "run")
        拎 = 模式 == "drag"
        空中 = 模式 == "air"

        sp = self.弹簧
        # 身体：pet-core 的 low 是胯下沉了多少（坐着、走路的起伏）
        self.坐k = _插(self.坐k, _夹(帧.get("sit", 0) or 0, 0, 1), _缓(12, dt))
        低 = 帧.get("low", 0) or 0
        低速 = (低 - self.上次低) / max(dt, 1e-3)
        self.上次低 = 低
        呼吸 = math.sin(t * (1.7 if 模式 == "sleep" else 2.4))

        视线 = 帧.get("look", [0, 0])
        摆 = 帧.get("swing", 0) or 0
        # 头：看向哪儿就往哪儿偏，睡着点一点，晕了摇一摇
        倾目 = 视线[0] * .7 + math.sin(t * .9) * 1.2 - 视线[1] * .4
        if 模式 == "sleep":
            倾目 += 6
        if 名 == "shy":
            倾目 += 7
        if 名 == "thinking":
            倾目 -= 8
        if 名 == "dizzy":
            倾目 += 3 * math.sin(t * 4.5)
        if 拎:
            倾目 += 摆 * .25
        self.头倾 = sp["head"].步(倾目, dt)
        gT, gL = 组倾.get(模式, (0, 0))
        弯 = (帧.get("tilt", 0) or 0) * (1 - self.组w倾) + (帧.get("lean", 0) or 0) * \
            (1 if (帧.get("facing", 1) or 1) >= 0 else -1) * (1 - self.组w靠)
        self.组w倾 = _插(self.组w倾, gT, _缓(10, dt))
        self.组w靠 = _插(self.组w靠, gL, _缓(10, dt))
        倾速 = (self.头倾 - self.上次倾) / max(dt, 1e-3)
        self.上次倾 = self.头倾
        角X = _夹(视线[0] / 5, -1, 1) * .9
        角Y = _夹(-视线[1] / 4, -1, 1) * .7 + (-.8 if 模式 == "sleep" else 0) + (-.35 if 名 == "sad" else 0)

        # 弹簧们
        甩 = _夹(摆 / 26, -1.6, 1.6)
        上 = 1 if (空中 or 拎) else 0
        hair = sp["hair"].步(甩 * 1.1 - 倾速 * .004 + (-.25 if 走 else 0), dt)
        hairY = sp["hairY"].步(上 * -1 + 低速 * .006, dt)
        bangs = sp["bangs"].步(甩 * .7 - 倾速 * .004, dt)
        skirt = sp["skirt"].步(甩 * .8 + (-.2 if 走 else 0), dt)
        flare = sp["skirtY"].步(上 * .8 + self.坐k * .6 + _夹(-低速 * .01, -.3, .6), dt)
        fm, wg = 情绪.get(名, 情绪["neutral"])
        self.鳍情绪 = _插(self.鳍情绪, fm, _缓(6, dt))
        self.摆幅 = _插(self.摆幅, wg, _缓(3, dt))
        self.尾情绪 = _插(self.尾情绪, -1 if (模式 == "sleep" or 名 == "sad") else 0, _缓(3, dt))
        fins = sp["fins"].步(self.鳍情绪 * 14 + 甩 * 10 + (3 * math.sin(t * 40) if 名 == "angry" else 0), dt)
        ahoge = sp["ahoge"].步(-倾速 * .12 + 甩 * 18 + (-16 if 名 == "surprised" else 0)
                              + (22 if 模式 == "sleep" else 0) - hairY * 12, dt)
        tail = sp["tail"].步(甩 * 14 + self.尾情绪 * 12, dt) + \
            self.摆幅 * 13 * math.sin(t * (4 + 5 * self.摆幅)) + math.sin(t * 1.3) * 3

        # 腿：pet-core 交上来的是胯→脚的两段，保持它的角度（脚在右边为正）
        腿 = 帧.get("legs") or [[104, 212, 104, 241], [150, 212, 150, 241]]
        腿角 = [-math.atan2(l[2] - l[0], max(4, l[3] - l[1])) * 180 / math.pi for l in 腿]
        抬 = [_夹(29 - math.hypot(l[2] - l[0], l[3] - l[1]), -8, 20) for l in 腿]
        坐进 = _顺(.44, .54, self.坐k)
        扑通 = math.sin(math.pi * _顺(.3, .8, self.坐k))

        # 手：走路时和腿反着甩，空中张开，被拎着乱挥
        aN, aF = 4, -2
        if 走:
            aN = -腿角[0] * 1.3 + 4
            aF = -腿角[1] * 1.3 - 2
        if 空中:
            aN, aF = 40, -30
        if 拎:
            aN = 70 + 16 * math.sin(t * 13)
            aF = -45 - 12 * math.sin(t * 13 + 1.3)
        if self.坐k > .5 and not 走:
            aN = _插(aN, -4, self.坐k)
            aF = _插(aF, -6, self.坐k)
        if 名 in ("happy", "love"):
            aN += 12 + 5 * math.sin(t * 8)
            aF -= 8 + 4 * math.sin(t * 8)
        if 名 == "angry":
            aN = 20 + 3 * math.sin(t * 30)
            aF = -18 - 3 * math.sin(t * 30)
        armN = sp["armN"].步(aN, dt)
        armF = sp["armF"].步(aF, dt)

        # ── 变形器状态 ──
        st: dict = {"z": {}, "alpha": {}}
        # pet-core 坐着时胯下沉 29；坐姿画最低点在脚底上方 19.4
        st["body"] = {"a": -甩 * 1.2 + (摆 * .15 if 拎 else 0), "ty": 低 - 9.6 * self.坐k,
                      "sx": 1 + .006 * 呼吸 + .04 * 扑通, "sy": 1 - .012 * 呼吸 - .06 * 扑通}
        sk, fl, sit = skirt, flare, self.坐k

        def 裙摆(u, v, x=0, y=0):
            k = v * v
            return [sk * 4 * k + fl * (u - .45) * 9 * v + sit * (u - .45) * 10 * v, -fl * k * 3 - sit * k * 8]

        st["skirt"] = {"fn": 裙摆}
        st["skirtSit"] = {"fn": lambda u, v, x=0, y=0: [sk * 1.5 * v * v, -max(0.0, 呼吸) * .4 * v]}
        st["alpha"]["skirt"] = 1 - 坐进
        st["alpha"]["leg_back"] = st["alpha"]["leg_front"] = 1 - _顺(.42, .52, self.坐k)
        st["alpha"]["skirt_sit"] = 坐进
        st["armNear"] = {"a": armN}
        st["armFar"] = {"a": armF}
        st["legBack"] = {"a": _插(腿角[0], -55, self.坐k), "ty": -抬[0] * .9 * (1 - self.坐k)}
        st["legFront"] = {"a": _插(腿角[1], -60, self.坐k), "ty": -抬[1] * .9 * (1 - self.坐k)}
        st["tail"] = {"a": tail - 10 * self.坐k}
        st["tailBend"] = {"fn": lambda u, v=0, x=0, y=0: [0, -tail * .5 * u * u]}
        st["neck"] = {"a": self.头倾 + _夹(弯 * .8, -10, 12),
                      "ty": (2.5 if 模式 == "sleep" else 0) + 呼吸 * .35}

        def 视差(k, ky):
            return lambda u, v, x=0, y=0: [角X * k * _鼓(u) * (.4 + .6 * _鼓(v)),
                                          角Y * ky * _鼓(v) * (.4 + .6 * _鼓(u))]

        st["headFront"] = {"fn": 视差(4.2, 2.8)}
        st["headFeat"] = {"fn": 视差(2, 1.4)}
        st["headMid"] = {"fn": 视差(2, 1.4)}
        st["headBack"] = {"fn": 视差(-1.4, -1)}
        # 长发挂在头上，但下半截跟着身体
        nk = self.模型.pivots["neck"]
        na = math.radians(self.头倾)

        def 发摆(u, v, x, y):
            w = _顺(.3, .8, v)
            a = -na * w
            c, s = math.cos(a), math.sin(a)
            dx, dy = x - nk[0], y - nk[1]
            wv = v ** 1.6
            return [nk[0] + dx * c - dy * s - x + hair * 8 * wv + math.sin(t * 1.6 + v * 3) * wv,
                    nk[1] + dx * s + dy * c - y + hairY * 12 * wv * wv - abs(hair) * 1.5 * wv]

        st["hairSway"] = {"fn": 发摆}
        st["bangsSway"] = {"fn": lambda u, v, x=0, y=0: [bangs * 3.2 * v * v + math.sin(t * 1.9 + u * 2) * .5 * v * v,
                                                        hairY * 3 * v * v]}
        st["ahoge"] = {"a": ahoge * .5 + math.sin(t * 2.1) * 2}
        st["finNear"] = {"a": fins + math.sin(t * 1.4) * 1.5}
        st["finFar"] = {"a": -fins * .8 - math.sin(t * 1.4) * 1.2}
        st["mix"] = 0
        st["图"] = {"faceFx": self.脸画师.画(脸, 帧)}
        return st

    # ── 特效（声音弧、思考泡泡、汗滴、怒气、感叹号、小星星）──────
    def 画特效(self, 笔: QPainter, 脸: dict, 帧: dict, st: dict):
        t = 帧.get("t", 0.0)
        k = self.渲染器.比例
        v0, v1 = self.渲染器.视口[0], self.渲染器.视口[1]

        def 点(变形器, x, y):
            mx, my = self.渲染器.求点(self.模型.链(变形器), st, x, y)
            return QPointF((mx - v0) * k, (my - v1) * k)

        笔.save()
        笔.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        顶 = 点("neck", 124, 34)
        侧 = 点("neck", 204, 52)
        比例 = k       # rig 单位 → 设备像素
        if 脸.get("orbit"):
            for i in range(3):
                a = t * 3.2 + i * 2.094
                sn = math.sin(a)
                笔.save()
                笔.translate(顶.x() + 56 * 比例 * math.cos(a), 顶.y() + (-4 + 10 * sn) * 比例)
                笔.scale(比例 * (0.7 if sn < 0 else 1), 比例 * (0.7 if sn < 0 else 1))
                路 = QPainterPath(QPointF(0, -7))
                for p in [(2, -2), (7, -2), (3, 1), (4.5, 6.5), (0, 3.3), (-4.5, 6.5), (-3, 1), (-7, -2), (-2, -2)]:
                    路.lineTo(*p)
                路.closeSubpath()
                笔.setBrush(QColor("#ffd23f"))
                笔.setPen(QPen(QColor("#3a2f7a"), 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
                笔.setOpacity(.55 if sn < 0 else 1)
                笔.drawPath(路)
                笔.restore()
        if 脸.get("listen"):
            c = 点("neck", 214, 116)
            for i in range(3):
                p = (t * .9 + i / 3) % 1
                r = (36 - 24 * p) * 比例
                笔.setBrush(Qt.BrushStyle.NoBrush)
                色 = QColor(self.强调色); 色.setAlphaF(_夹(math.sin(math.pi * p), 0, 1))
                笔.setPen(QPen(色, 5 * 比例, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
                路 = QPainterPath(QPointF(c.x() + r * math.cos(-.55), c.y() + r * math.sin(-.55)))
                路.arcTo(c.x() - r, c.y() - r, 2 * r, 2 * r, 31.5, 63)
                笔.drawPath(路)
        if 脸.get("think"):
            for i in range(3):
                kk = (t * .8 + i / 3) % 1
                色 = QColor(self.强调色); 色.setAlphaF(_夹(.4 + .6 * math.sin(math.pi * kk), 0, 1))
                笔.setBrush(QColor("#e8f0ff"))
                笔.setPen(QPen(色, 3 * 比例))
                笔.drawEllipse(QPointF(侧.x() + 10 * i * 比例, 侧.y() + (-20 * i - 6 * kk) * 比例), (4 + 3 * i) * 比例, (4 + 3 * i) * 比例)
        if 脸.get("sweat"):
            c = 点("neck", 196, 88 + 3 * math.sin(t * 7))
            笔.save()
            笔.translate(c)
            笔.scale(1.4 * 比例, 1.4 * 比例)
            路 = QPainterPath(QPointF(0, -9))
            路.cubicTo(QPointF(4, -3), QPointF(6, 0), QPointF(6, 3.5))
            路.arcTo(0, -2.5, 12, 12, 0, -180)
            路.cubicTo(QPointF(-6, 0), QPointF(-4, -3), QPointF(0, -9))
            路.closeSubpath()
            笔.setBrush(QColor("#8fd0ff"))
            笔.setPen(QPen(QColor("#2f5fae"), 1.4))
            笔.drawPath(路)
            笔.restore()
        if 脸.get("anger"):
            c = 点("neck", 190, 62)
            kk = 1 + .12 * math.sin(t * 10)
            # 四个小折线拼成的怒气符号，分开画，省得拼路径
            笔.save()
            笔.translate(c)
            笔.scale(kk * 比例, kk * 比例)
            笔.setBrush(Qt.BrushStyle.NoBrush)
            笔.setPen(QPen(QColor("#e5484d"), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            for (x1, y1, cx, cy, x2, y2) in [(-11, -3, -3, -3, -3, -11), (3, -11, 3, -3, 11, -3),
                                             (11, 3, 3, 3, 3, 11), (-3, 11, -3, 3, -11, 3)]:
                路 = QPainterPath(QPointF(x1, y1))
                路.quadTo(QPointF(cx, cy), QPointF(x2, y2))
                笔.drawPath(路)
            笔.restore()
        if 脸.get("bang"):
            c = 点("neck", 206, 36)
            笔.save()
            笔.translate(c)
            笔.scale(比例, 比例)
            笔.setPen(QPen(QColor("#252049"), 8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            笔.drawLine(QPointF(0, -16), QPointF(0, 3))
            笔.setPen(Qt.PenStyle.NoPen)
            笔.setBrush(QColor("#252049"))
            笔.drawEllipse(QPointF(0, 14), 4.5, 4.5)
            笔.restore()
        笔.restore()

    # 眼睛、眼泪、z、爱心、气泡的锚点（figure.js 的 anchors，绑骨单位）
    @property
    def 锚点(self):
        m = self.模型
        return {"gaze": [m.U(745), m.V(690)], "tear": [m.U(640), m.V(752)], "z": [196, 44],
                "hearts": [96, 176, 62], "bubble": [128, 18]}

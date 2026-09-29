#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""脸的画笔 —— figure.js 里 paintFace / paintOpenEye / sprite 那一段的 QPainter 版。

做的事和网页一模一样：在一张 390×252（母图像素）的图上，用一张张零件贴图拼出
眼睛、睫毛、嘴、腮红，再用「destination-out」把眼皮以上擦掉，做出睁眼／闭眼。
每帧重画一张，交给网格渲染器当 faceFx 部件贴上去。
"""
from __future__ import annotations

import math
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QImage, QPainter, QPainterPath, QPen,
                           QRadialGradient)

from 模型 import FACE, 鲸鱼模型

INK = QColor("#5a2330")
眼序 = ["eyeL", "eyeR"]          # 近眼（左）、远眼（右）

# 哪张脸用哪个嘴贴图；负数是手画的小嘴（figure.js 的 MOUTH）
嘴表 = {
    "neutral": "neutral_mouth", "happy": "happy_mouth", "wink": ("happy_mouth", .8),
    "love": "love_mouth", "shy": ("drag_mouth", .7), "surprised": "surprised_mouth",
    "sleepy": "sleep_mouth", "sleep": "sleep_mouth", "dizzy": "dizzy_mouth",
    "dragged": "drag_mouth", "content": "neutral_mouth", "waking": ("surprised_mouth", .6),
    "squeeze": "sleep_mouth", "listening": "neutral_mouth", "thinking": "sleep_mouth",
    "run": ("happy_mouth", .7), "angry": -1, "sad": -1.2,
}
腮红点 = [(618, 770, 40, 20), (852, 762, 22, 15)]


def _夹(v, a, b):
    return max(a, min(b, v))


def _二(c, x):
    return c[0] * x * x + c[1] * x + c[2]


class 脸画师:
    """One face per frame: `img = 画师.画(脸, 帧参数)`, then use it as the faceFx texture.
    
    一帧一张脸。用法：图 = 画师.画(脸, 帧参数)，然后把它当 faceFx 的贴图。
    """

    def __init__(self, 模型: 鲸鱼模型):
        self.模型 = 模型
        self.feat = 模型.feat
        self.图 = QImage(FACE["w"], FACE["h"], QImage.Format.Format_ARGB32_Premultiplied)
        self.眼图 = QImage(64, 64, QImage.Format.Format_ARGB32_Premultiplied)
        self._笔: QPainter | None = None
        # 眼睛的常数：眼皮要走多远才闭上、虹膜中心、中心处眼皮的高度
        self.眼 = {}
        for k in 眼序:
            e = self.feat["eyes"][k]
            bx0, _, bx1, _ = e["ball"]
            h = 0.0
            x = bx0 + 4
            while x < bx1 - 4:
                h = max(h, _二(e["rimFit"], x) - _二(e["lidFit"], x))
                x += 2
            cx = (e["iris"][0] + e["iris"][2]) / 2
            self.眼[k] = {**e, "travel": h + 2, "cx": cx, "cy": _二(e["lidFit"], cx)}

    # ── 零件 ────────────────────────────────────────────────
    def _图(self, 名: str) -> QImage | None:
        return self.模型.脸图.get(名)

    def _画零件(self, 笔: QPainter, 名: str, x: float, y: float):
        im = self._图(名)
        if im is None:
            return
        笔.drawImage(QPointF(x, y), im)

    def _精灵(self, 笔: QPainter, 名: str, **o):
        """figure.js 的 sprite()：把一张表情贴图摆到它该在的位置，可选缩放/旋转/透明度。"""
        b = self.feat["sprites"].get(名)
        if not b:
            return
        cx = (b[0] + b[2]) / 2 + o.get("dx", 0)
        cy = (b[1] + b[3]) / 2 + o.get("dy", 0)
        顶 = o.get("anchorTop", False)
        笔.save()
        笔.setOpacity(o.get("alpha", 1))
        笔.translate(cx - FACE["x"], (b[1] if 顶 else cy) - FACE["y"])
        if o.get("rot"):
            笔.rotate(math.degrees(o["rot"]))
        s = o.get("s", 1)
        笔.scale(o.get("sx", s), o.get("sy", s))
        self._画零件(笔, 名, b[0] - cx, (0 if 顶 else b[1] - cy))
        笔.restore()

    def _腮红(self, 笔: QPainter, a: float):
        if a < .02:
            return
        for (x, y, rx, ry) in 腮红点:
            笔.save()
            笔.translate(x - FACE["x"], y - FACE["y"])
            笔.scale(1, ry / rx)
            渐 = QRadialGradient(QPointF(0, 0), rx)
            内侧 = QColor(255, 120, 140); 内侧.setAlphaF(_夹(.55 * a, 0, 1))
            外侧 = QColor(255, 120, 140, 0)
            渐.setColorAt(0.0, 内侧)
            渐.setColorAt(1.0, 外侧)
            笔.setBrush(渐)
            笔.setPen(Qt.PenStyle.NoPen)
            笔.drawEllipse(QPointF(0, 0), rx, rx)
            笔.restore()

    def _线嘴(self, 笔: QPainter, form: float, w: float = 1):
        cx, cy = 766 - FACE["x"], 772 - FACE["y"]
        路 = QPainterPath(QPointF(cx - 9 * w, cy - form * 3))
        路.quadTo(QPointF(cx, cy + form * 5), QPointF(cx + 9 * w, cy - form * 3))
        笔.save()
        笔.setBrush(Qt.BrushStyle.NoBrush)
        笔.setPen(QPen(INK, 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        笔.drawPath(路)
        笔.restore()

    # ── 睁眼 ────────────────────────────────────────────────
    def _睁眼(self, 笔: QPainter, k: str, open_: float, ix: float, iy: float, tilt: float):
        """把一只睁着的眼画到脸上：眼白 + 虹膜 + 眼眶描边，再用眼皮擦掉上面一截。"""
        e = self.眼[k]
        bx0, by0, bx1, by1 = e["ball"]
        w, h = bx1 - bx0, by1 - by0
        if self.眼图.width() != w + 40 or self.眼图.height() != h + 40:
            self.眼图 = QImage(int(w + 40), int(h + 40), QImage.Format.Format_ARGB32_Premultiplied)
        self.眼图.fill(0)
        眼笔 = QPainter(self.眼图)
        眼笔.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        眼笔.translate(20 - bx0, 20 - by0)
        眼笔.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        self._画零件(眼笔, f"{k}_ball", bx0, by0)
        眼笔.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
        self._画零件(眼笔, f"{k}_iris", e["iris"][0] + ix, e["iris"][1] + iy)
        if e.get("rim"):
            眼笔.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            self._画零件(眼笔, f"{k}_rim", e["rim"][0], e["rim"][1])
        # 眼皮：一条从 lidFit 走的折线，往上整片擦掉
        d = (1 - _夹(open_, 0, 1)) * e["travel"]
        tn = math.tan(tilt)
        路 = QPainterPath(QPointF(bx0 - 20, by0 - 20))
        x = bx0 - 20
        while x <= bx1 + 20:
            路.lineTo(QPointF(x, _二(e["lidFit"], _夹(x, bx0, bx1)) + d + tn * (x - e["cx"]) - 1))
            x += 3
        路.lineTo(QPointF(bx1 + 20, by0 - 20))
        路.closeSubpath()
        眼笔.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationOut)
        眼笔.setPen(Qt.PenStyle.NoPen)
        眼笔.setBrush(QColor(0, 0, 0, 255))
        眼笔.drawPath(路)
        眼笔.end()
        笔.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        笔.drawImage(QPointF(bx0 - 20 - FACE["x"], by0 - 20 - FACE["y"]), self.眼图)
        # 睫毛跟着眼皮下来，越闭越扁
        L = e["lash"]
        sy = .55 + .45 * _夹(open_, 0, 1)
        笔.save()
        笔.translate(e["cx"] - FACE["x"], e["cy"] + d - FACE["y"])
        笔.rotate(math.degrees(tilt))
        笔.scale(1, sy)
        self._画零件(笔, f"{k}_lash", L[0] - e["cx"], L[1] - e["cy"])
        笔.restore()

    # ── 整张脸 ──────────────────────────────────────────────
    def 画(self, 脸: dict, 帧: dict) -> QImage:
        t = 帧.get("t", 0)
        名 = 帧.get("face", "neutral")
        self.图.fill(0)
        笔 = QPainter(self.图)
        笔.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        笔.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self._腮红(笔, 脸.get("blush", 0) or 0)
        闭 = max(帧.get("blink", 0) or 0, 帧.get("eyeClose", 0) or 0)
        视线 = 帧.get("look", [0, 0])
        lx = _夹(视线[0], -6, 6)
        ly = _夹(视线[1], -5, 5)
        眉 = 脸.get("brows")
        tilt = .2 if 眉 == "angry" else (-.16 if 眉 == "sad" else 0)
        for i, e in enumerate(脸.get("eyes", [])):
            k = 眼序[i] if i < 2 else 眼序[-1]
            side = 1 if k == "eyeL" else -1
            squash = {"sy": 1 - .85 * (帧.get("eyeClose", 0) or 0)}
            if 名 == "surprised" and e.get("shape") == "ring":
                self._精灵(笔, f"surprised_{k}", **squash)
                continue
            形状 = e.get("shape")
            if 形状 in ("ring", "lid"):
                if 形状 == "ring":
                    ry, rx = e.get("ry", 16), e.get("rx", 16) or 16
                    open_ = _夹(ry / rx, 0, 1) * (.8 if tilt else 1)
                else:
                    open_ = _夹(e.get("ry", 16) / 16, 0, 1)
                open_ *= (1 - 闭)
                gx = 1 if k == "eyeL" else .35
                ix = _夹((lx + (e.get("dx", 0) or 0)) * gx, -6 * gx, 6 * gx)
                iy = _夹(ly * .7 + (e.get("dy", 0) or 0) * .7, -3.5, 3.5)
                self._睁眼(笔, k, open_, ix, iy + (3 if 形状 == "lid" else 0), tilt * side)
            elif 形状 == "up":
                self._精灵(笔, f"happy_{k}", **squash)
            elif 形状 == "down":
                self._精灵(笔, f"sleep_{k}", **squash)
            elif 形状 in ("gt", "lt"):
                self._精灵(笔, f"drag_{k}", s=1 + .03 * math.sin(t * 22 + i))
            elif 形状 == "heart":
                self._精灵(笔, f"love_{k}", s=.94 + .06 * (e.get("s") or 1) / .8)
            elif 形状 == "spiral":
                self._精灵(笔, f"dizzy_{k}", rot=(e.get("rot", 0) or 0) * .6)
        # 嘴：说话时把 happy 嘴从顶边撑开；否则用这张脸自己的嘴
        talk = 帧.get("talk", 0) or 0
        gap = 脸.get("gap", [50, 50])
        gapOpen = _夹((max(gap[0], gap[1]) - 50) / 14, 0, 1)
        m = 嘴表.get(名, "neutral_mouth")
        open_ = max(talk * (.45 + .45 * abs(math.sin(t * 17))),
                    0 if 名 not in ("sleepy", "waking") else gapOpen)
        if open_ > .12:
            self._精灵(笔, "surprised_mouth" if 名 == "surprised" else "happy_mouth",
                       anchorTop=True, sy=.35 + .65 * open_, sx=.85 + .15 * open_)
        elif isinstance(m, (int, float)) and not isinstance(m, bool):
            self._线嘴(笔, float(m))
        elif isinstance(m, (tuple, list)):
            self._精灵(笔, m[0], s=m[1])
        else:
            self._精灵(笔, m)
        笔.end()
        return self.图


if __name__ == "__main__":
    import sys
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication(sys.argv)
    m = 鲸鱼模型(Path(__file__).resolve().parent.parent / "app/packages/cortico-world-desktop-pet/web")
    画师 = 脸画师(m)
    # 试着画几张脸
    脸表 = [("neutral", {"eyes": [{"shape": "ring"}, {"shape": "ring"}], "gap": [50, 50]}),
            ("happy", {"eyes": [{"shape": "up"}, {"shape": "up"}], "gap": [58, 58], "blush": .45}),
            ("sleep", {"eyes": [{"shape": "down"}, {"shape": "down"}], "gap": [40, 40]})]
    出 = QImage(FACE["w"] * 3, FACE["h"], QImage.Format.Format_ARGB32_Premultiplied)
    出.fill(0)
    q = QPainter(出)
    for i, (名, 脸) in enumerate(脸表):
        im = 画师.画(脸, {"t": 0.3, "face": 名, "blink": 0, "look": [0, 0]})
        q.drawImage(i * FACE["w"], 0, im)
    q.end()
    出.save("/tmp/原生-脸.png")
    print("三张脸 → /tmp/原生-脸.png")

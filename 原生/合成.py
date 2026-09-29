#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""合成 —— 把「身体一帧 + 小鱼一帧」画到画布上（网页那边是 SVG 组 + canvas + 粒子三合）。

画法照 pet-core 的 render()：
    影子 → 人物组（translate/rotate/scale 摆放）→ 组里的鲸鱼画布 + 人物自己的特效
    → 再回到舞台像素画粒子（爱心、z、泪、扬尘）
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

from 身体 import 身体, 脚底y
from 小鱼 import 小鱼
from 模型 import 鲸鱼模型
from 网格 import 网格渲染器

# 粗略计时表（调性能用）：{'网格': [秒, 次数], '其余': [...]}
计时表: dict[str, list] = {}


def _计时(名: str, 秒: float):
    it = 计时表.get(名)
    if it is None:
        计时表[名] = [秒, 1]
    else:
        it[0] += 秒
        it[1] += 1


def 取计时():
    出 = {k: (v[0] / max(1, v[1]) * 1000, v[1]) for k, v in 计时表.items()}
    计时表.clear()
    return 出


class 合成器:
    """Frame composer: turns one body state into one painted frame (mesh + face + effects + particles).
    
    每帧的合成器：把一个身体状态画成一帧（网格 + 脸 + 特效 + 粒子）。
    """
    def __init__(self, 模型: 鲸鱼模型, 身体: 身体, 小鱼: 小鱼, 网格: 网格渲染器, 查比例=None):
        """查比例：返回「窗口像素 / 绑骨单位」的可调用对象（默认问身体）。"""
        self.模型 = 模型
        self.身体 = 身体
        self.小鱼 = 小鱼
        self.网格 = 网格
        self._查比例 = 查比例 or (lambda: 身体.S)

    def 渲染骨架(self, 状态: dict) -> QImage:
        """把这一帧的鲸鱼骨架先渲染成一张小图（在计时器里做，别在 paintEvent 里做）。

        实测：在 paintEvent 里做这件事会慢一倍（widget 上已经有一个活动的 QPainter），
        所以拆成「先渲染、再贴图」两步。
        """
        return self.网格.出图(状态)

    def 画(self, 笔: QPainter, 宽: int, 高: int, 状态: dict, 帧: dict, 脸: dict):
        笔.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        笔.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        p = self.身体.宠物
        xf = p["xf"]
        S = self.身体.S
        # ── 影子 ──
        脚y = (p["dy"] + 220 * S * 1.09) if p["mode"] == "drag" else p["fy"]
        k = max(.3, min(1.0, 1 - (self.身体.地面 - 脚y) / 420))
        笔.save()
        笔.setPen(Qt.PenStyle.NoPen)
        笔.setBrush(QColor(0, 0, 0, int(255 * .16 * k)))
        笔.drawEllipse(QPointF(xf["AX"], self.身体.地面 - 2), 72 * S * k * (1 + p["sq"] * .5), 10 * S * k + 1)
        笔.restore()
        # ── 人物组 ──
        笔.save()
        笔.translate(xf["AX"], xf["AY"])
        笔.rotate(xf["rot"])
        笔.scale(xf["kx"], xf["ky"])
        笔.translate(-xf["ax"], -xf["ay"])
        # 鲸鱼画布：在绑骨空间里占 view 那个矩形
        v = self.网格.视口
        t1 = time.perf_counter()
        c1 = time.thread_time()
        图 = 状态.get("_画布") or self.网格.出图(状态)
        c2 = time.thread_time()
        t2 = time.perf_counter()
        _计时("贴骨架", c2 - c1)
        笔.drawImage(QRectF(v[0], v[1], v[2] - v[0], v[3] - v[1]), 图)
        self.小鱼.画特效(笔, 脸, 帧, 状态)
        t3 = time.perf_counter()
        笔.restore()
        # ── 粒子（舞台像素）──
        self._画粒子(笔)
        _计时("网格出图", t2 - t1)
        _计时("贴图+特效+粒子", time.perf_counter() - t3)

    def _画粒子(self, 笔: QPainter):
        p = self.身体.宠物
        S = self.身体.S
        sc = S / .48
        笔.save()
        for q in self.身体.粒子:
            a = q["age"] / q["life"]
            if q["type"] == "z":
                op = a / .15 if a < .15 else 1 - (a - .15) / .85
                z = (.7 + .9 * a) * sc
                笔.save()
                笔.translate(q["x"] + math.sin(q["age"] * 2.5) * 6, q["y"])
                笔.scale(z, z)
                笔.setBrush(Qt.BrushStyle.NoBrush)
                笔.setPen(QPen(QColor(self.小鱼.强调色), 3, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                               Qt.PenJoinStyle.RoundJoin))
                笔.setOpacity(max(0.0, min(1.0, op)))
                路 = QPainterPath(QPointF(-6, -7))
                路.lineTo(6, -7); 路.lineTo(-6, 7); 路.lineTo(6, 7)
                笔.drawPath(路)
                笔.restore()
            elif q["type"] == "heart":
                笔.save()
                笔.translate(q["x"] + math.sin(q["age"] * 4) * 5, q["y"])
                笔.scale((.45 + .35 * a) * sc, (.45 + .35 * a) * sc)
                笔.setBrush(Qt.BrushStyle.NoBrush)
                笔.setPen(QPen(QColor(255, 110, 150), 5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                               Qt.PenJoinStyle.RoundJoin))
                笔.setOpacity(max(0.0, 1 - a * a))
                笔.drawPath(self._心(q["x"], q["y"], 1))
                笔.restore()
            elif q["type"] == "dust":
                笔.save()
                笔.setBrush(Qt.BrushStyle.NoBrush)
                笔.setPen(QPen(QColor(160, 160, 160), 2))
                笔.setOpacity(.7 * (1 - a))
                笔.drawEllipse(QPointF(q["x"], q["y"]), (3 + 8 * a) * sc, (3 + 8 * a) * sc)
                笔.restore()
            elif q["type"] == "drop":
                笔.save()
                笔.translate(q["x"], q["y"])
                笔.scale(.9 * sc, .9 * sc)
                笔.setBrush(QColor("#8fd0ff"))
                笔.setPen(QPen(QColor("#2f5fae"), 1.4))
                路 = QPainterPath(QPointF(0, -9))
                路.cubicTo(QPointF(4, -3), QPointF(6, 0), QPointF(6, 3.5))
                路.arcTo(0, -2.5, 12, 12, 0, -180)
                路.cubicTo(QPointF(-6, 0), QPointF(-4, -3), QPointF(0, -9))
                路.closeSubpath()
                笔.drawPath(路)
                笔.restore()
        笔.restore()

    @staticmethod
    def _心(cx, cy, s):
        """heartD(cx, cy, s)：粒子用的小爱心（局部坐标画，靠 translate 摆放）。"""
        路 = QPainterPath(QPointF(0 * s, 14 * s))
        路.cubicTo(QPointF(-7 * s, 8 * s), QPointF(-19 * s, 1 * s), QPointF(-19 * s, -6 * s))
        路.cubicTo(QPointF(-19 * s, -15 * s), QPointF(-8 * s, -18 * s), QPointF(0 * s, -9 * s))
        路.cubicTo(QPointF(8 * s, -18 * s), QPointF(19 * s, -15 * s), QPointF(19 * s, -6 * s))
        路.cubicTo(QPointF(19 * s, 1 * s), QPointF(7 * s, 8 * s), QPointF(0 * s, 14 * s))
        路.closeSubpath()
        return 路

    def 出图(self, 宽: int, 高: int, 状态: dict, 帧: dict, 脸: dict) -> QImage:
        净 = QImage(宽, 高, QImage.Format.Format_ARGB32_Premultiplied)
        净.fill(0)
        笔 = QPainter(净)
        try:
            self.画(笔, 宽, 高, 状态, 帧, 脸)
        finally:
            笔.end()
        return 净

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""网格变形渲染器 —— rig.js 的 QPainter 版（原生身体用，不碰 WebGL / Chromium）。

网页那边是一个 Live2D 风格的小渲染器：每块贴图（part）铺在一个网格上，顶点按变形器
链逐点搬运，再画成一堆小四边形。这里做的事一模一样，只是画布换成 QImage、画家换成
QPainter（用 QTransform.quadToQuad 把每个格子映射过去 + 裁切到格子）。

对应关系：
    rig.js  applyChain()  →  本文件 求点() / _编译() / _过链()
    rig.js  render()      →  本文件 画()

两个实测出来的性能坑（2026-09-28 量过）：
  1. 不给画家设裁切、直接 drawImage 走透视变换：**慢 7 倍**（Qt 会老老实实重采样整张
     贴图）。设了裁切它才肯只算格子那一小块。
  2. QPolygonF 里塞**已经存在的 QPointF 对象**比塞现造的快……不，是**反过来**：塞现造的
     QPointF(元组) 更快（30 µs/格 vs 105 µs/格）。所以下面一律现造。
"""
from __future__ import annotations

import math
import time

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QImage, QPainter, QPainterPath, QPolygonF, QTransform

from 模型 import 鲸鱼模型

# 画质开关（默认都开）：关掉能在低配上省一点
抗锯齿 = True
平滑缩放 = True

# 分段计时（默认关，调性能时打开）：{'求点': [秒, 次数], '建格': [...], '画格': [...]}
计时表: dict[str, list] = {}
计时开 = False


def _计(名: str, 秒: float):
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


class 网格渲染器:
    """A canvas plus a model; feed it a deformer state each frame and it renders one image.
    
    一块画布 + 一个模型；每帧喂一份「变形器状态」就出图。
    """

    def __init__(self, 模型: 鲸鱼模型, 每单位像素: float = 3.0, 格步: int = 1):
        self.模型 = 模型
        self.比例 = float(每单位像素)          # 画布像素 / 绑骨单位
        self.格步 = max(1, int(格步))          # 网格抽稀：2 = 每 2 格画一次（远处细小格子够用）
        v = 模型.view
        self.视口 = list(v)
        self.宽 = max(16, round((v[2] - v[0]) * self.比例))
        self.高 = max(16, round((v[3] - v[1]) * self.比例))
        self.画布 = QImage(self.宽, self.高, QImage.Format.Format_ARGB32_Premultiplied)
        self.格子: dict[str, list] = {}
        self.链缓存: dict[str, list[str]] = {}
        self.顺序 = sorted(模型.部件, key=lambda p: (p.get("z", 0), p["id"]))
        for p in 模型.部件:
            nx, ny = p.get("grid") or [6, 6]
            x, y, w, h = p["box"]
            u0, v0, u1, v1 = p.get("uvBox") or [0, 0, 1, 1]
            点 = []
            for j in range(ny + 1):
                for i in range(nx + 1):
                    点.append((x + w * i / nx, y + h * j / ny, u0 + (u1 - u0) * i / nx, v0 + (v1 - v0) * j / ny))
            self.格子[p["id"]] = (nx, ny, 点)
            self.链缓存[p["id"]] = 模型.链(p.get("parent"))

    # ── 坐标 ────────────────────────────────────────────────
    def 设备点(self, x: float, y: float):
        return ((x - self.视口[0]) * self.比例, (y - self.视口[1]) * self.比例)

    # ── 变形链 ──────────────────────────────────────────────
    def _编译(self, 链: list[str], 状态: dict):
        """把这一帧的变形器参数先算成元组，省得每个顶点都重复算 cos/sin。"""
        表 = self.模型.变形器
        出 = []
        for 号 in 链:
            d = 表.get(号)
            s = 状态.get(号)
            if not d or not s:
                continue
            if d["kind"] == "rot":
                px, py = d["pivot"]
                a = math.radians(s.get("a", 0) or 0)
                sx = s.get("sx", s.get("s", 1))
                sy = s.get("sy", s.get("s", 1))
                出.append(("r", px, py, math.cos(a), math.sin(a),
                           sx if sx is not None else 1, sy if sy is not None else 1,
                           s.get("tx", 0) or 0, s.get("ty", 0) or 0))
            elif d["kind"] == "warp" and s.get("fn"):
                x0, y0, x1, y1 = d["rect"]
                出.append(("w", x0, y0, x1 - x0, y1 - y0, s["fn"]))
            elif s.get("fn") is None and d["kind"] == "warp":
                continue
        return 出

    def 求点(self, 链: list[str], 状态: dict, x: float, y: float):
        """把一个 rest 点穿过整条变形器链，返回本帧落点（rig.js 的 applyChain）。"""
        return self._过链(self._编译(链, 状态), x, y)

    @staticmethod
    def _过链(编, x: float, y: float):
        for 项 in 编:
            if 项[0] == "r":
                _, px, py, c, sn, sx, sy, tx, ty = 项
                lx = (x - px) * sx
                ly = (y - py) * sy
                x = px + tx + lx * c - ly * sn
                y = py + ty + lx * sn + ly * c
            else:
                _, x0, y0, w, h, fn = 项
                u = (x - x0) / w
                v = (y - y0) / h
                u = 0.0 if u < 0 else (1.0 if u > 1 else u)
                v = 0.0 if v < 0 else (1.0 if v > 1 else v)
                dx, dy = fn(u, v, x, y)
                x += dx
                y += dy
        return x, y

    # ── 画 ─────────────────────────────────────────────────
    def 画(self, painter: QPainter, 状态: dict, 隐藏: set[str] | None = None):
        """画一帧。

        实测（2026-09-28，217×217 画布、约 140 格、动画姿势）：
            · 不给画家裁切、直接透视 drawImage   → 每个格子重采样一大片，慢到不能用
            · 每块部件只裁一次外圈              → 比逐格裁还慢（Qt 仍按整块面积重采样）
            · **逐格裁切（本实现）**            → 最快，且相邻格子不会留缝
        所以这里保持「逐格裁切 + 往外撑 0.35 像素」。
        """
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, 抗锯齿)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, 平滑缩放)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        隐藏 = 隐藏 or set()
        树 = 状态.get("z") or {}
        alpha表 = 状态.get("alpha") or {}
        图表 = 状态.get("图") or {}
        步 = self.格步
        视x, 视y = self.视口[0], self.视口[1]
        比例 = self.比例
        for p in sorted(self.顺序, key=lambda q: 树.get(q["id"], q.get("z", 0))):
            号 = p["id"]
            if 号 in 隐藏:
                continue
            alpha = alpha表.get(号, p.get("alpha", 1))
            if alpha is None or alpha <= 0.001:
                continue
            图 = 图表.get(p["tex"]) or self.模型.取图(p["tex"])
            if 图 is None or 图.isNull():
                continue
            nx, ny, 点 = self.格子[号]
            编 = self._编译(self.链缓存[号], 状态)
            过链 = self._过链
            变形后 = [过链(编, x, y) for (x, y, _, _) in 点]
            宽, 高 = 图.width(), 图.height()
            设备 = [((x - 视x) * 比例, (y - 视y) * 比例) for (x, y) in 变形后]
            if alpha < 0.999:
                painter.save()
                painter.setOpacity(alpha)
            for j in range(0, ny, 步):
                j2 = min(ny, j + 步)
                for i in range(0, nx, 步):
                    i2 = min(nx, i + 步)
                    a = j * (nx + 1) + i
                    b, c2, d2 = j * (nx + 1) + i2, j2 * (nx + 1) + i, j2 * (nx + 1) + i2
                    源 = QPolygonF([QPointF(宽 * 点[a][2], 高 * 点[a][3]),
                                    QPointF(宽 * 点[b][2], 高 * 点[b][3]),
                                    QPointF(宽 * 点[d2][2], 高 * 点[d2][3]),
                                    QPointF(宽 * 点[c2][2], 高 * 点[c2][3])])
                    目 = QPolygonF([QPointF(设备[a][0], 设备[a][1]),
                                    QPointF(设备[b][0], 设备[b][1]),
                                    QPointF(设备[d2][0], 设备[d2][1]),
                                    QPointF(设备[c2][0], 设备[c2][1])])
                    self._一格(painter, 图, 源, 目)
            if alpha < 0.999:
                painter.restore()

    @staticmethod
    def _外圈(设备, nx: int, ny: int) -> QPainterPath:
        """变形后网格的外圈多边形（往外撑 0.6 像素），用来给整块部件做一次裁切。"""
        序 = []
        序 += [j * (nx + 1) + i for j in (0,) for i in range(nx + 1)]
        序 += [j * (nx + 1) + nx for j in range(1, ny + 1)]
        序 += [ny * (nx + 1) + i for i in range(nx - 1, -1, -1)]
        序 += [j * (nx + 1) for j in range(ny - 1, 0, -1)]
        xs = [设备[k][0] for k in 序]
        ys = [设备[k][1] for k in 序]
        心x, 心y = sum(xs) / len(xs), sum(ys) / len(ys)
        路 = QPainterPath()
        for n, k in enumerate(序):
            x, y = 设备[k]
            dx, dy = x - 心x, y - 心y
            L = math.hypot(dx, dy)
            k2 = (L + .6) / L if L > .01 else 1.0
            if n == 0:
                路.moveTo(心x + dx * k2, 心y + dy * k2)
            else:
                路.lineTo(心x + dx * k2, 心y + dy * k2)
        路.closeSubpath()
        return 路


    @staticmethod
    def _一格(painter: QPainter, 图: QImage, 源: QPolygonF, 目: QPolygonF):
        """把贴图的一小块按四点映射铺到目标四边形上（裁切 + 透视变换 + 贴图）。

        裁切框要**往外撑一点点**：相邻格子各自抗锯齿描边，边对边贴会在中间留下一条
        发白的细缝（实测能看见一道竖线）。撑 0.35 像素让它们互相压住。
        """
        t = QTransform()
        if not QTransform.quadToQuad(源, 目, t):
            # 退化（格子被压成一条线）—— 拿外接矩形近似，别把小东西丢没了
            painter.drawImage(目.boundingRect(), 图, 源.boundingRect())
            return
        四 = [(目[i].x(), 目[i].y()) for i in range(4)]
        心x = sum(p[0] for p in 四) / 4
        心y = sum(p[1] for p in 四) / 4
        撑 = QPolygonF()
        for (x, y) in 四:
            dx, dy = x - 心x, y - 心y
            L = math.hypot(dx, dy)
            k = (L + .35) / L if L > .01 else 1.0
            撑.append(QPointF(心x + dx * k, 心y + dy * k))
        路 = QPainterPath()
        路.addPolygon(撑)
        路.closeSubpath()
        painter.save()
        painter.setClipPath(路, Qt.ClipOperation.ReplaceClip)
        painter.setTransform(t, True)
        painter.drawImage(0, 0, 图)
        painter.restore()

    # ── 便捷：出一张整图 ─────────────────────────────────────
    def 出图(self, 状态: dict, 隐藏: set[str] | None = None) -> QImage:
        净 = QImage(self.宽, self.高, QImage.Format.Format_ARGB32_Premultiplied)
        净.fill(0)
        p = QPainter(净)
        try:
            self.画(p, 状态, 隐藏)
        finally:
            p.end()
        return 净

    def 画进(self, 笔: QPainter, 状态: dict, 隐藏: set[str] | None = None):
        """画到别人的画布上（窗口重绘用），不自己开 QPainter。"""
        self.画(笔, 状态, 隐藏)

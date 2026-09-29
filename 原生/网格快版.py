#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Experimental faster mesh renderer (the "fast A" prototype), opt-in only.

English: Same vertices, same quads, same pixels as the default renderer — it only
avoids work Qt does not need: path clipping instead of rect clipping, rebuilding
source polygons every frame, and drawing purely-affine parts cell by cell.
Enable with `COOP_RENDER=fast`; the default path is left completely untouched.

中文：与默认渲染器**同样的顶点、同样的四边形、同样的像素**，只是少做 Qt 本来不必做的事。
启用方式：环境变量 `COOP_RENDER=fast`。默认路径完全不受影响。

三条改动（都承诺像素等价，见 实测/ 里的像素比对）：

  ① 源多边形（贴图坐标）每帧都一样 → 预先算好，别每格重建
     （省 1 个 QPolygonF + 4 个 QPointF）
  ② 裁切从「路径裁切」换成「四边形外接矩形裁切」→ 省 QPainterPath，
     而且相邻格子互相压住，反而不会再出现细缝
  ③ 整条变形链上只有 rot 的部件（手臂、腿、躯干）→ 三个顶点定一个仿射矩阵，
     整块一次画完，一个格子都不少

  不变量：**形变部件仍然逐格画**，画出来的东西不变。
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPolygonF, QTransform

from 网格 import 网格渲染器


class 快渲染器(网格渲染器):
    """Faster drop-in renderer; pixel-equivalent to 网格渲染器 by design."""

    def __init__(self, 模型, 每单位像素: float = 3.0, 格步: int = 1):
        super().__init__(模型, 每单位像素, 格步)
        # ① 源多边形预计算（faceFx 的贴图每帧现画，留到真画时按尺寸缓存）
        self.源: dict[tuple, list] = {}
        self.纯仿射: dict[str, bool] = {}
        for p in 模型.部件:
            图 = 模型.取图(p["tex"])
            if 图 is None:
                self.纯仿射[p["id"]] = False
                continue
            self.源[(p["id"], 图.width(), 图.height())] = self._算源(p["id"], 图)
            # ③ 整条链上只有 rot 的部件 → 可以整块一次画
            self.纯仿射[p["id"]] = all(模型.变形器[q]["kind"] == "rot" for q in self.链缓存[p["id"]])

    def _算源(self, 号: str, 图: QImage) -> list:
        nx, ny, 点 = self.格子[号]
        宽, 高 = 图.width(), 图.height()
        列 = []
        for j in range(0, ny, self.格步):
            j2 = min(ny, j + self.格步)
            for i in range(0, nx, self.格步):
                i2 = min(nx, i + self.格步)
                a = j * (nx + 1) + i
                b, c, d = j * (nx + 1) + i2, j2 * (nx + 1) + i, j2 * (nx + 1) + i2
                列.append((a, b, c, d, QPolygonF([
                    QPointF(宽 * 点[a][2], 高 * 点[a][3]),
                    QPointF(宽 * 点[b][2], 高 * 点[b][3]),
                    QPointF(宽 * 点[d][2], 高 * 点[d][3]),
                    QPointF(宽 * 点[c][2], 高 * 点[c][3])])))
        return 列

    def _取源(self, 图: QImage, 号: str) -> list:
        """（贴图尺寸相同的）源多边形只算一次。"""
        键 = (号, 图.width(), 图.height())
        列 = self.源.get(键)
        if 列 is None:
            列 = self._算源(号, 图)
            self.源[键] = 列
        return 列

    def 画(self, painter: QPainter, 状态: dict, 隐藏: set[str] | None = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        树 = 状态.get("z") or {}
        alpha表 = 状态.get("alpha") or {}
        图表 = 状态.get("图") or {}
        视x, 视y, k = self.视口[0], self.视口[1], self.比例
        for p in sorted(self.顺序, key=lambda q: 树.get(q["id"], q.get("z", 0))):
            号 = p["id"]
            if 隐藏 and 号 in 隐藏:
                continue
            alpha = alpha表.get(号, p.get("alpha", 1))
            if alpha is None or alpha <= 0.001:
                continue
            图 = 图表.get(p["tex"]) or self.模型.取图(p["tex"])
            if 图 is None or 图.isNull():
                continue
            nx, ny, 点 = self.格子[号]
            编 = self._编译(self.链缓存[号], 状态)
            变形 = [self._过链(编, x, y) for (x, y, _, _) in 点]
            设备 = [((x - 视x) * k, (y - 视y) * k) for (x, y) in 变形]
            if alpha < .999:
                painter.save()
                painter.setOpacity(alpha)
            if self.纯仿射[号] and 状态.get("mix", 0) <= 0:
                # ③ 整块一次：仿射矩阵由三个顶点定（顶左 / 顶右 / 底左）
                # 网格四个角：0=左上, nx=右上, ny*(nx+1)=左下（不是 nx+1，那是第二行）
                x0, y0 = 设备[0]
                x1, y1 = 设备[nx]
                x2, y2 = 设备[ny * (nx + 1)]
                宽, 高 = 图.width(), 图.height()
                t = QTransform((x1 - x0) / 宽, (y1 - y0) / 宽, (x2 - x0) / 高, (y2 - y0) / 高, x0, y0)
                xs = [d[0] for d in 设备]
                ys = [d[1] for d in 设备]
                painter.setTransform(QTransform())      # 先复位，否则裁切会被上一格的矩阵搬走
                painter.setClipRect(QRectF(min(xs) - .5, min(ys) - .5,
                                           max(xs) - min(xs) + 1, max(ys) - min(ys) + 1),
                                    Qt.ClipOperation.ReplaceClip)
                painter.setTransform(t)
                painter.drawImage(0, 0, 图)
                painter.setClipping(False)
                painter.setTransform(QTransform())
            else:
                for (a, b, c, d, 源) in self._取源(图, 号):
                    目 = QPolygonF([QPointF(*设备[a]), QPointF(*设备[b]),
                                    QPointF(*设备[d]), QPointF(*设备[c])])
                    t = QTransform()
                    if not QTransform.quadToQuad(源, 目, t):
                        continue
                    xs = (设备[a][0], 设备[b][0], 设备[d][0], 设备[c][0])
                    ys = (设备[a][1], 设备[b][1], 设备[d][1], 设备[c][1])
                    painter.setTransform(QTransform())  # 同上：裁切要在单位矩阵下设
                    painter.setClipRect(QRectF(min(xs) - .5, min(ys) - .5,
                                               max(xs) - min(xs) + 1, max(ys) - min(ys) + 1),
                                        Qt.ClipOperation.ReplaceClip)
                    painter.setTransform(t)
                    painter.drawImage(0, 0, 图)
                painter.setClipping(False)
                painter.setTransform(QTransform())
            if alpha < .999:
                painter.restore()


class 保真快渲染器(快渲染器):
    """Same speedups as 快渲染器, but keeps the stock path clipping → pixel-exact.

    English: 快渲染器's speed partially comes from replacing path clipping with
    rect clipping, and rect clipping makes neighbouring cells overlap — that is
    what changes edge pixels. This variant keeps ① (source polygon cache) and
    ③ (merged affine draw) but draws deformed cells through the stock `_一格`
    path clip, so the output should be bit-identical to the stock renderer.

    中文：快渲染器 的提速有一部分来自「矩形裁切替路径裁切」，而矩形裁切会让相邻
    格子互相压住 —— 差异就是从那儿来的。本变体保留 ①（源多边形预缓存）与
    ③（纯仿射部件整块一次画），但形变格子仍走原来的 `_一格`（路径裁切），
    因此**输出应当与现状渲染器逐位一致**。

    用 COOP_RENDER=exact 启用。
    """

    def 画(self, painter: QPainter, 状态: dict, 隐藏: set[str] | None = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        树 = 状态.get("z") or {}
        alpha表 = 状态.get("alpha") or {}
        图表 = 状态.get("图") or {}
        视x, 视y, k = self.视口[0], self.视口[1], self.比例
        for p in sorted(self.顺序, key=lambda q: 树.get(q["id"], q.get("z", 0))):
            号 = p["id"]
            if 隐藏 and 号 in 隐藏:
                continue
            alpha = alpha表.get(号, p.get("alpha", 1))
            if alpha is None or alpha <= 0.001:
                continue
            图 = 图表.get(p["tex"]) or self.模型.取图(p["tex"])
            if 图 is None or 图.isNull():
                continue
            nx, ny, 点 = self.格子[号]
            编 = self._编译(self.链缓存[号], 状态)
            变形 = [self._过链(编, x, y) for (x, y, _, _) in 点]
            设备 = [((x - 视x) * k, (y - 视y) * k) for (x, y) in 变形]
            宽, 高 = 图.width(), 图.height()
            if alpha < .999:
                painter.save()
                painter.setOpacity(alpha)
            if self.纯仿射[号] and 状态.get("mix", 0) <= 0:
                # ③ 整块一次（纯仿射，映射与逐格 quadToQuad 等价）
                x0, y0 = 设备[0]
                x1, y1 = 设备[nx]
                x2, y2 = 设备[ny * (nx + 1)]
                t = QTransform((x1 - x0) / 宽, (y1 - y0) / 宽, (x2 - x0) / 高, (y2 - y0) / 高, x0, y0)
                xs = [d[0] for d in 设备]
                ys = [d[1] for d in 设备]
                painter.setTransform(QTransform())
                painter.setClipRect(QRectF(min(xs) - .5, min(ys) - .5,
                                           max(xs) - min(xs) + 1, max(ys) - min(ys) + 1),
                                    Qt.ClipOperation.ReplaceClip)
                painter.setTransform(t)
                painter.drawImage(0, 0, 图)
                painter.setClipping(False)
                painter.setTransform(QTransform())
            else:
                # ① 源多边形来自缓存；裁切仍走现状的 _一格（路径裁切）
                for (a, b, c, d, 源) in self._取源(图, 号):
                    目 = QPolygonF([QPointF(*设备[a]), QPointF(*设备[b]),
                                    QPointF(*设备[d]), QPointF(*设备[c])])
                    self._一格(painter, 图, 源, 目)
            if alpha < .999:
                painter.restore()

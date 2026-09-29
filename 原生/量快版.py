#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量快版 —— 试试「不换画法、只去掉实现里的浪费」能快到什么程度。

和 网格.py 的现状比，只动三件事（都不改画出来的东西）：
  ① 源多边形（贴图坐标）是**每一帧都一样**的 → 预先算好，别每格重建（省 1 个 QPolygonF + 4 个 QPointF）
  ② 裁切从「路径裁切」换成「四边形外接矩形裁切」→ 省 QPainterPath、省往外撑那点浮点运算，
     而且相邻格子会互相压住（反而不会再出现细缝）
  ③ 只受旋转/缩放的部件（手臂、腿、躯干）整块用一个仿射变换一次画完 —— 这在数学上是**精确等价**的
     （形变部件仍然逐格画，一个格子都不少）

用法：QT_QPA_PLATFORM=offscreen python3 量快版.py
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QPointF, QRectF, Qt                        # noqa: E402
from PySide6.QtGui import QGuiApplication, QImage, QPainter, QPolygonF, QTransform  # noqa: E402

from 模型 import 鲸鱼模型                                              # noqa: E402
from 小鱼 import 小鱼                                                  # noqa: E402
from 网格 import 网格渲染器                                            # noqa: E402

网页 = Path.home() / "coop-linux/app/packages/cortico-world-desktop-pet/web"
比例 = 0.62 * 1.25
帧样本 = {"t": 1.0, "face": "neutral", "mode": "idle", "look": [2, 1], "swing": 8,
          "legs": [[104, 212, 104, 241], [150, 212, 150, 241]], "low": 0, "blink": 0,
          "eyeClose": 0, "sit": 0, "facing": 1, "tilt": 4, "lean": 2}
脸样本 = {"eyes": [{"shape": "ring"}, {"shape": "ring"}], "gap": [50, 50]}


class 快渲染器(网格渲染器):
    """网格渲染器的快版：同样的顶点、同样的四边形，只是少造对象、少设路径。"""

    def __init__(self, 模型, 每单位像素=比例, 格步=1):
        super().__init__(模型, 每单位像素, 格步)
        # ① 源多边形预计算
        self.源: dict[tuple, list] = {}
        self.纯仿射: dict[str, bool] = {}
        for p in 模型.部件:
            图 = 模型.取图(p["tex"])
            if 图 is None:
                # faceFx 的贴图是每帧现画的，等真画的时候再按尺寸缓存
                self.纯仿射[p["id"]] = False
                continue
            nx, ny, 点 = self.格子[p["id"]]
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
            self.源[(p["id"], 宽, 高)] = 列
            # ③ 整条链上只有 rot 的部件 → 可以整块一次画
            self.纯仿射[p["id"]] = all(模型.变形器[q]["kind"] == "rot" for q in self.链缓存[p["id"]])

    def _取源(self, 图, 号: str):
        """（贴图尺寸相同的）源多边形只算一次。"""
        键 = (号, 图.width(), 图.height())
        列 = self.源.get(键)
        if 列 is None:
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
                # 整块一次：仿射矩阵由三个顶点定（顶左 / 顶右 / 底左）
                # 网格的四个角：0=左上, nx=右上, ny*(nx+1)=左下（别写成 nx+1，那是第二行）
                x0, y0 = 设备[0]
                x1, y1 = 设备[nx]
                x2, y2 = 设备[ny * (nx + 1)]
                宽, 高 = 图.width(), 图.height()
                t = QTransform((x1 - x0) / 宽, (y1 - y0) / 宽, (x2 - x0) / 高, (y2 - y0) / 高, x0, y0)
                xs = [d[0] for d in 设备]
                ys = [d[1] for d in 设备]
                painter.setTransform(QTransform())      # 先复位，否则裁切矩形会被上一格的矩阵搬走
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


class 快渲染器2(快渲染器):
    """再进一步：每个小格用**仿射**近似（三个角定矩阵），连 QPolygonF/quadToQuad 都不用造。

    几何上会有亚像素误差（格子越小误差越小），所以要跟原版逐像素比过才敢用。
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
            if alpha < .999:
                painter.save()
                painter.setOpacity(alpha)
            if self.纯仿射[号] and 状态.get("mix", 0) <= 0:
                x0, y0 = 设备[0]; x1, y1 = 设备[nx]; x2, y2 = 设备[ny * (nx + 1)]
                宽, 高 = 图.width(), 图.height()
                painter.setTransform(QTransform())
                xs = [d[0] for d in 设备]; ys = [d[1] for d in 设备]
                painter.setClipRect(QRectF(min(xs) - .5, min(ys) - .5,
                                           max(xs) - min(xs) + 1, max(ys) - min(ys) + 1),
                                    Qt.ClipOperation.ReplaceClip)
                painter.setTransform(QTransform((x1 - x0) / 宽, (y1 - y0) / 宽,
                                                (x2 - x0) / 高, (y2 - y0) / 高, x0, y0))
                painter.drawImage(0, 0, 图)
            else:
                for j in range(0, ny, self.格步):
                    j2 = min(ny, j + self.格步)
                    for i in range(0, nx, self.格步):
                        i2 = min(nx, i + self.格步)
                        a = j * (nx + 1) + i
                        b, c, d = j * (nx + 1) + i2, j2 * (nx + 1) + i, j2 * (nx + 1) + i2
                        d0, d1, d3 = 设备[a], 设备[b], 设备[c]
                        sx0, sy0 = 图.width() * 点[a][2], 图.height() * 点[a][3]
                        sx1, sy1 = 图.width() * 点[c][2], 图.height() * 点[c][3]
                        kx = (sx1 - sx0) or 1e-6
                        ky = (sy1 - sy0) or 1e-6
                        m11 = (d1[0] - d0[0]) / kx; m12 = (d1[1] - d0[1]) / kx
                        m21 = (d3[0] - d0[0]) / ky; m22 = (d3[1] - d0[1]) / ky
                        t = QTransform(m11, m12, m21, m22,
                                       d0[0] - m11 * sx0 - m21 * sy0, d0[1] - m12 * sx0 - m22 * sy0)
                        xs = (d0[0], d1[0], 设备[d][0], d3[0])
                        ys = (d0[1], d1[1], 设备[d][1], d3[1])
                        painter.setTransform(QTransform())
                        painter.setClipRect(QRectF(min(xs) - .5, min(ys) - .5,
                                                   max(xs) - min(xs) + 1, max(ys) - min(ys) + 1),
                                            Qt.ClipOperation.ReplaceClip)
                        painter.setTransform(t)
                        painter.drawImage(0, 0, 图)
            painter.setClipping(False)
            painter.setTransform(QTransform())
            if alpha < .999:
                painter.restore()


def 主():
    模型 = 鲸鱼模型(网页)
    for 格步 in (1, 2, 3):
        鱼 = 小鱼(模型, 网格渲染器(模型, 比例, 格步))
        st = 鱼.画(脸样本, 帧样本)
        现 = 网格渲染器(模型, 比例, 格步)
        快 = 快渲染器(模型, 比例, 格步)
        快2 = 快渲染器2(模型, 比例, 格步)
        格数 = 0
        for p in 模型.部件:
            图 = st.get("图", {}).get(p["tex"]) or 模型.取图(p["tex"])
            if 图 is not None:
                格数 += len(快._取源(图, p["id"]))
        圈数 = sum(1 for v, f in 快.纯仿射.items() if f)
        def 计时(名, fn, 次=8):
            fn()
            t0 = time.thread_time()
            for _ in range(次):
                fn()
            ms = (time.thread_time() - t0) / 次 * 1000
            print(f"    {名:16s} {ms:6.2f} ms/帧   → 理论上限 {1000/ms:6.1f} fps")
            return ms
        print(f"── 格步 {格步}：{格数} 格（其中 {圈数} 块部件可整块一次画）──")
        慢 = 计时("现状（路径裁切）", lambda: 现.出图(st))
        快ms = 计时("快版 A（矩形裁切+源缓存+仿射合并）", lambda: 快.出图(st))
        快2ms = 计时("快版 B（A + 小格也走仿射）", lambda: 快2.出图(st))
        print(f"    → A 快了 {慢/快ms:.2f} 倍，B 快了 {慢/快2ms:.2f} 倍")
        # 逐像素比一比。注意：要跟「现状」比的是**快版 A**（承诺像素等价），
        # 不是快版 B —— B 把形变部件也塞进仿射，本来就不保像素，只能当参考。
        def 比一比(名, 参照, 候选):
            a = 参照.出图(st).convertToFormat(QImage.Format.Format_RGBA8888)
            b = 候选.出图(st).convertToFormat(QImage.Format.Format_RGBA8888)
            不同 = 严重 = 最大差 = 0
            pa = a.constBits().tobytes()
            pb = b.constBits().tobytes()
            for i in range(0, len(pa), 4):
                d = max(abs(pa[i] - pb[i]), abs(pa[i+1] - pb[i+1]),
                        abs(pa[i+2] - pb[i+2]), abs(pa[i+3] - pb[i+3]))
                if d:
                    不同 += 1
                    最大差 = max(最大差, d)
                    if d >= 65:
                        严重 += 1
            总 = a.width() * a.height()
            print(f"    像素对比 {名}：{不同}/{总} 不同（{不同/总*100:.3f}%），"
                  f"其中 ≥65 的 {严重} 个，最大通道差 {最大差}/255")
            return 严重
        严重A = 比一比("现状 vs 快版A（承诺等价）", 现, 快)
        比一比("现状 vs 快版B（仅参考）", 现, 快2)
        print(f"    → 快版 A 的差异像素里「肉眼可见级」的有 {严重A} 个"
              f"（{'等价成立' if 严重A == 0 else '需要复核'}）")
        现.出图(st).save(f"/tmp/快版-慢-步{格步}.png")
        快.出图(st).save(f"/tmp/快版-A-步{格步}.png")
        快2.出图(st).save(f"/tmp/快版-快-步{格步}.png")


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    主()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量理论 —— 原生 QPainter 这条路，理论上能跑到多少帧？

分三层量，逐层剥开：
    ① 光栅器本身有多快（纯填充 / 1:1 贴图 / 缩放贴图）→ 每秒能糊多少像素
    ② 「一次绘制调用」的固定开销（无裁切 / 矩形裁切 / 路径裁切 / 路径裁切+透视变换）
    ③ 把整块部件「一次画完」（合并绘制）要多久 → 这就是这条路的上限

    时间 = 调用次数 × 每次固定开销 + 像素数 ÷ 像素吞吐
    把 ①② 量出来，套上她真实的格子数/像素数，就能算出「理论值」。

用法：QT_QPA_PLATFORM=offscreen python3 量理论.py
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QPointF, QRectF, Qt                     # noqa: E402
from PySide6.QtGui import (QColor, QGuiApplication, QImage, QPainter,   # noqa: E402
                           QPainterPath, QPolygonF, QTransform)

from 模型 import 鲸鱼模型                                          # noqa: E402
from 网格 import 网格渲染器                                        # noqa: E402

网页 = _资源 if (_资源 := __import__("os").environ.get("COOP_ASSETS")) else Path.home() / "coop-linux/app/packages/cortico-world-desktop-pet/web"
画布边长 = 217          # 和实际用的画布一样（缩放 0.62 × 1.25）


def 计(名, fn, 次, 单位数, 单位名):
    fn()
    t0 = time.thread_time()
    for _ in range(次):
        fn()
    秒 = (time.thread_time() - t0) / 次
    print(f"  {名:38s} {秒*1000:8.3f} ms/次   {单位数/秒/1e6:9.2f} M{单位名}/秒")
    return 秒


def 主():
    画布 = QImage(画布边长, 画布边长, QImage.Format.Format_ARGB32_Premultiplied)
    大图 = QImage(512, 512, QImage.Format.Format_ARGB32_Premultiplied)
    大图.fill(QColor(80, 180, 160, 200))
    微图 = QImage(8, 8, QImage.Format.Format_ARGB32_Premultiplied)
    微图.fill(QColor(120, 200, 180, 180))

    笔 = QPainter(画布)
    笔.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    笔.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)

    print("══ ① 光栅器本身（QPainter 往 ARGB32 图上画）══")
    计("填充 217×217 矩形", lambda: 笔.fillRect(0, 0, 画布边长, 画布边长, QColor(20, 30, 40)),
       1000, 画布边长 ** 2, "像素")
    原尺寸 = 大图.scaled(画布边长, 画布边长)
    计("1:1 贴 217×217 图", lambda: 笔.drawImage(0, 0, 原尺寸),
       1000, 画布边长 ** 2, "像素")
    def 缩放贴():
        笔.drawImage(QRectF(0, 0, 画布边长, 画布边长), 大图, QRectF(0, 0, 512, 512))
    计("512×512 缩到 217×217（双线性）", 缩放贴, 1000, 画布边长 ** 2, "像素")
    def 放大贴():
        笔.drawImage(QRectF(0, 0, 画布边长, 画布边长), 大图, QRectF(0, 0, 64, 64))
    计("64×64 放大到 217×217（双线性）", 放大贴, 1000, 画布边长 ** 2, "像素")

    print("\n══ ② 一次绘制调用的固定开销 ══")
    仿射 = QTransform(1.3, .1, -.2, 1.1, 12, 9)          # 随便一个带旋转的仿射
    路 = QPainterPath()
    路.addPolygon(QPolygonF([QPointF(10, 10), QPointF(80, 14), QPointF(76, 70), QPointF(12, 66)]))
    路.closeSubpath()
    目 = QPolygonF([QPointF(10, 10), QPointF(80, 14), QPointF(76, 70), QPointF(12, 66)])
    def a():
        笔.setTransform(仿射); 笔.drawImage(0, 0, 微图); 笔.setTransform(QTransform())
    def b():
        笔.setClipRect(QRectF(9, 9, 72, 62), Qt.ClipOperation.ReplaceClip)
        笔.setTransform(仿射); 笔.drawImage(0, 0, 微图)
        笔.setClipping(False); 笔.setTransform(QTransform())
    def c():
        笔.setClipPath(路, Qt.ClipOperation.ReplaceClip)
        笔.setTransform(仿射); 笔.drawImage(0, 0, 微图)
        笔.setClipping(False); 笔.setTransform(QTransform())
    def d():
        笔.save(); 笔.setClipPath(路, Qt.ClipOperation.ReplaceClip)
        笔.setTransform(仿射, True); 笔.drawImage(0, 0, 微图); 笔.restore()
    def e():
        笔.save(); 笔.setClipPath(路, Qt.ClipOperation.ReplaceClip)
        t = QTransform(); QTransform.quadToQuad(目, 路.currentPosition() and 目 or 目, t)
        笔.setTransform(仿射, True); 笔.drawImage(0, 0, 微图); 笔.restore()
    计("a 只 setTransform + drawImage", a, 4000, 1, "次")
    计("b + 矩形裁切", b, 4000, 1, "次")
    计("c + 路径裁切（不存栈）", c, 4000, 1, "次")
    计("d + 路径裁切 + save/restore（现用）", d, 4000, 1, "次")
    计("e + 上面再算一次 quadToQuad", e, 4000, 1, "次")
    笔.end()

    print("\n══ ②b 纯 Python 那一侧：造一格要用的 Qt 对象 ══")
    def 造一格():
        s0 = QPolygonF([QPointF(1.0, 2.0), QPointF(30.0, 2.5), QPointF(31.0, 40.0), QPointF(2.0, 39.0)])
        s1 = QPolygonF([QPointF(11.0, 12.0), QPointF(40.0, 12.5), QPointF(41.0, 50.0), QPointF(12.0, 49.0)])
        t = QTransform()
        QTransform.quadToQuad(s0, s1, t)
        return t
    def 造一格带撑():
        t = 造一格()
        四 = [(1.0, 2.0), (30.0, 2.5), (31.0, 40.0), (2.0, 39.0)]
        心x = sum(p[0] for p in 四) / 4; 心y = sum(p[1] for p in 四) / 4
        路 = QPainterPath()
        for i, (x, y) in enumerate(四):
            dx, dy = x - 心x, y - 心y
            L = math.hypot(dx, dy)
            k = (L + .35) / L if L > .01 else 1.0
            if i == 0:
                路.moveTo(心x + dx * k, 心y + dy * k)
            else:
                路.lineTo(心x + dx * k, 心y + dy * k)
        路.closeSubpath()
        return t, 路
    计("造 2 个 QPolygonF（8 个 QPointF）+ quadToQuad", 造一格, 4000, 1, "次")
    计("再造 1 个 QPainterPath（含往外撑 0.35 像素）", 造一格带撑, 4000, 1, "次")

    print("\n══ ③ 整帧的画法对比（217×217 画布，动画姿势）══")
    import 网格
    网格.计时开 = False
    for 格步 in (1, 4):
        模型 = 鲸鱼模型(网页)
        网格器 = 网格渲染器(模型, 0.775, 格步)
        鱼 = None
        from 小鱼 import 小鱼 as 鱼类
        from 身体 import 身体 as 身类
        from 合成 import 合成器
        鱼 = 鱼类(模型, 网格器)
        身 = 身类(锚点=鱼.锚点, 边界=lambda: (1920, 1080, 1078, 0.62), 漫游="calm", 进场="none", 起始x=960)
        身.S = 0.62; 身.调整尺寸()
        帧 = {"t": 1.0, "face": "neutral", "mode": "idle", "look": [2, 1], "swing": 8,
              "legs": [[104, 212, 104, 241], [150, 212, 150, 241]], "low": 0, "blink": 0,
              "eyeClose": 0, "sit": 0, "facing": 1, "tilt": 4, "lean": 2}
        脸 = {"eyes": [{"shape": "ring"}, {"shape": "ring"}], "gap": [50, 50]}
        st = 鱼.画(脸, 帧)
        格数 = sum(((p["grid"][0] + 格步 - 1) // 格步) * ((p["grid"][1] + 格步 - 1) // 格步) for p in 模型.部件)
        秒 = 计(f"现状：逐格裁切（{格数} 格）", lambda: 网格器.出图(st), 8, 1, "帧")
        print(f"      → 理论上限 {1/秒:6.1f} fps")

        # 合成场景：每块部件「一次画完」——只裁外接矩形、整块用一个仿射变换。
        # 注意：这只量「一次绘制的价格」，形变（warp）在这里是忽略的；
        #      它回答的是「如果每块部件只发一次绘制调用，上限在哪」。
        部件计划 = []
        for p in 模型.部件:
            图 = (st.get("图") or {}).get(p["tex"]) or 模型.取图(p["tex"])
            if 图 is None or 图.isNull():
                continue
            nx, ny, 点 = 网格器.格子[p["id"]]
            编 = 网格器._编译(网格器.链缓存[p["id"]], st)
            变形 = [网格器._过链(编, x, y) for (x, y, _, _) in 点]
            设备 = [((x - 网格器.视口[0]) * 网格器.比例, (y - 网格器.视口[1]) * 网格器.比例) for (x, y) in 变形]
            xs = [d[0] for d in 设备]; ys = [d[1] for d in 设备]
            框 = QRectF(min(xs) - .5, min(ys) - .5, max(xs) - min(xs) + 1, max(ys) - min(ys) + 1)
            宽, 高 = 图.width(), 图.height()
            x0, y0 = 设备[0]                 # 网格左上角
            x1, y1 = 设备[nx]                # 网格右上角
            x2, y2 = 设备[nx + 1]            # 网格左下角
            m11, m12 = (x1 - x0) / 宽, (y1 - y0) / 宽
            m21, m22 = (x2 - x0) / 高, (y2 - y0) / 高
            变换 = QTransform(m11, m12, m21, m22, x0, y0)
            部件计划.append((图, 框, 变换))
        def 合并画():
            净 = QImage(网格器.宽, 网格器.高, QImage.Format.Format_ARGB32_Premultiplied)
            净.fill(0)
            p2 = QPainter(净)
            p2.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            p2.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            for 图, 框, 变换 in 部件计划:
                p2.setClipRect(框, Qt.ClipOperation.ReplaceClip)
                p2.setTransform(变换)
                p2.drawImage(0, 0, 图)
            p2.end()
            return 净
        秒2 = 计(f"合并：每块部件一次绘制（{len(部件计划)} 块）", 合并画, 8, 1, "帧")
        print(f"      → 理论上限 {1/秒2:6.1f} fps")


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    主()

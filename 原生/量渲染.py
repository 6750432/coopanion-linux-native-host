#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量渲染 —— 离线把每一段渲染拆开计时（可重复，不受桌面上别的东西打扰）。

量四件事：
    身体.步       状态机 + 弹簧（每帧必跑）
    小鱼.画       弹簧 + 把姿势翻成骨骼参数 + 画那张 390×252 的脸
    网格.出图     17 块贴图按网格变形画成一张小图（原来这是 WebGL2 干的活）
    合成.出图     影子 + 人物 + 粒子（离线时画进 1920×1080，实际程序里只画窗口那一块）

用法：python3 量渲染.py [缩放] [每单位像素]
"""
from __future__ import annotations

import math
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtGui import QGuiApplication   # noqa: E402

import 网格                                  # noqa: E402
from 模型 import 鲸鱼模型                    # noqa: E402
from 小鱼 import 小鱼                        # noqa: E402
from 网格 import 网格渲染器                  # noqa: E402
from 身体 import 身体                        # noqa: E402
from 合成 import 合成器                      # noqa: E402

网页 = Path.home() / "coop-linux/app/packages/cortico-world-desktop-pet/web"
宽, 高 = 1920, 1080


def 一帧样本(比例, 格步, 帧数=40):
    """造一条会动的轨迹（跟真的待机时差不多），后面所有计时都用它。"""
    模型 = 鲸鱼模型(网页)
    网格器 = 网格渲染器(模型, 比例 * 1.25, 格步)
    鱼 = 小鱼(模型, 网格器)
    身 = 身体(锚点=鱼.锚点, 边界=lambda: (宽, 高, 高 - 2, 比例), 漫游="calm", 进场="none", 起始x=960)
    身.S = 比例
    身.调整尺寸()
    合成 = 合成器(模型, 身, 鱼, 网格器)
    轨迹 = []
    for i in range(帧数):
        身.步(1 / 60)
        # 让她也有点动作：中途溜达一段
        if i == 8:
            身.动作("walk")
        if i == 24:
            身.设表情("happy")
        脸, 帧 = 身.出帧()
        轨迹.append((脸, 帧))
    return 身, 鱼, 网格器, 合成, 轨迹


def 计(名, fn, 次=12):
    fn()
    t0 = time.thread_time()
    for _ in range(次):
        fn()
    ms = (time.thread_time() - t0) / 次 * 1000
    print(f"  {名:34s} {ms:6.2f} ms/帧")
    return ms


def 主(比例=0.62, 单位像素=None):
    单位像素 = 单位像素 or 比例 * 1.25
    网格.抗锯齿 = True
    print(f"══ 离线基准：缩放 {比例}（画布每单位 {单位像素:.3f} 像素）══")
    for 格步 in (1, 2, 3, 4):
        身, 鱼, 网格器, 合成, 轨迹 = 一帧样本(比例, 格步)
        箱 = [0]
        print(f"── 格步 {格步}（画布 {网格器.宽}×{网格器.高}）──")

        def b_身体():
            身.步(1 / 60)
        def b_小鱼():
            脸, 帧 = 轨迹[箱[0] % len(轨迹)]
            箱[0] += 1
            鱼.画(脸, 帧)
        def b_网格():
            脸, 帧 = 轨迹[箱[0] % len(轨迹)]
            return 网格器.出图(鱼.画(脸, 帧))
        def b_整帧():
            脸, 帧 = 轨迹[箱[0] % len(轨迹)]
            箱[0] += 1
            st = 鱼.画(脸, 帧)
            return 合成.出图(宽, 高, st, 帧, 脸)
        a = 计("身体.步（状态机+弹簧）", b_身体, 40)
        b = 计("小鱼.画（含画脸）", b_小鱼, 20)
        c = 计("网格.出图（骨骼变形）", b_网格, 12)
        d = 计("合成.出图（含 1080p 大图）", b_整帧, 6)
        print(f"    ↳ 一帧渲染合计 ≈ {b + c:.1f} ms（身体步进另算 {a:.2f} ms）")
        print(f"    ↳ 按 24 fps 算 CPU ≈ {(b + c) * 24 / 10:.0f}%，按 12 fps 算 ≈ {(b + c) * 12 / 10:.0f}%")


if __name__ == "__main__":
    app = QGuiApplication(sys.argv)
    主(float(sys.argv[1]) if len(sys.argv) > 1 else 0.62,
        float(sys.argv[2]) if len(sys.argv) > 2 else None)

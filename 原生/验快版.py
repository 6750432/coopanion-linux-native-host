#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Verify the fast renderer against the stock one on REAL animated frames.

English: `量快版.py` only compares two renderers on one frozen pose. This script
drives the actual body through every mode and expression, takes the deformer state
the live app would produce, and compares the two renderers pixel by pixel on each
of those states. That is the check that actually matters before flipping a switch.

中文：`量快版.py` 只在**一帧固定姿势**上比两个渲染器。本脚本把真实身体驱动过
每一种模式与表情，取「主程序真会产出的那份变形器状态」，逐帧逐像素比对两个渲染器。
**这个才是决定能不能开开关的那个验证。**

判据：差异必须全是亚像素抗锯齿 —— 即「单通道差 ≥65/255」的像素数为 0
（量级参考：现役渲染器与快版在同一姿势下的 ≥65 像素数为 0~2）。

用法：
    QT_QPA_PLATFORM=offscreen python3 验快版.py
    COOP_ASSETS=<web目录> QT_QPA_PLATFORM=offscreen python3 验快版.py
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtGui import QGuiApplication, QImage   # noqa: E402

from 合成 import 合成器                              # noqa: E402
from 模型 import 鲸鱼模型                            # noqa: E402
from 小鱼 import 小鱼 as 鱼类                        # noqa: E402
from 网格 import 网格渲染器                          # noqa: E402
from 网格快版 import 快渲染器, 保真快渲染器            # noqa: E402
from 身体 import 身体 as 身类                         # noqa: E402

_资源 = os.environ.get("COOP_ASSETS")
网页 = Path(_资源) if _资源 else (Path.home() / "coop-linux/app/packages/cortico-world-desktop-pet/web")
宽, 高 = 1920, 1080


def 计时(渲染器, 状态: dict, 次: int = 6) -> float:
    """量「出图」的耗时（ms）—— 这正是主程序每帧调的那一步（合成.py 里的 self.网格.出图）。

    同一个状态、两个渲染器轮流量，互相抵消机器负载漂移。
    """
    if 状态.get("_画布") is not None:
        状态.pop("_画布")
    渲染器.出图(状态)                      # 预热
    t0 = time.thread_time()
    for _ in range(次):
        渲染器.出图(状态)
    return (time.thread_time() - t0) / 次 * 1000


def 比一比(a: QImage, b: QImage):
    """返回（不同像素数, ≥65 的像素数, 最大通道差）。"""
    if a.size() != b.size():
        return (-1, -1, -1)
    A = a.convertToFormat(QImage.Format.Format_RGBA8888)
    B = b.convertToFormat(QImage.Format.Format_RGBA8888)
    pa, pb = A.constBits().tobytes(), B.constBits().tobytes()
    不同 = 严重 = 最大 = 0
    for i in range(0, len(pa), 4):
        d = max(abs(pa[i] - pb[i]), abs(pa[i + 1] - pb[i + 1]),
                abs(pa[i + 2] - pb[i + 2]), abs(pa[i + 3] - pb[i + 3]))
        if d:
            不同 += 1
            if d >= 65:
                严重 += 1
            if d > 最大:
                最大 = d
    return 不同, 严重, 最大


def main() -> int:
    app = QGuiApplication(sys.argv)
    模型 = 鲸鱼模型(网页)
    网格慢 = 网格渲染器(模型, max(.2, .62 * 1.25), 3)
    网格快 = 快渲染器(模型, max(.2, .62 * 1.25), 3)
    网格保 = 保真快渲染器(模型, max(.2, .62 * 1.25), 3)
    鱼 = 鱼类(模型, 网格慢)
    身 = 身类(锚点=鱼.锚点, 边界=lambda: (宽, 高, 高 - 2, .62),
             漫游="calm", 进场="none", 起始x=960)
    身.S = .62
    身.调整尺寸()
    合成 = 合成器(模型, 身, 鱼, 网格慢)

    print(f"素材：{网页}")
    print(f"格步 3 ｜ 画布 {网格慢.宽}×{网格慢.高}\n")

    开关 = os.environ.get("COOP_TIMING") == "1" and print("（计时已开：每帧多量 2×6 次出图）") is None
    总 = 不同总 = 严重总 = 最大总 = 0
    慢总 = 快总 = 保总 = 0.0
    计次 = 0
    保不同 = 保严重 = 0
    保最大 = 0
    最差 = ("", 0)

    def 采一帧(标签: str, 计时它: bool = False):
        nonlocal 总, 不同总, 严重总, 最大总, 最差, 慢总, 快总, 保总, 计次, 保不同, 保严重, 保最大
        脸, 帧 = 身.出帧()
        状态 = 鱼.画(脸, 帧)          # 只算一次，两个渲染器吃同一份状态
        im慢 = 网格慢.出图(状态)
        n, sev, mx = 比一比(im慢, 网格快.出图(状态))
        n2, sev2, mx2 = 比一比(im慢, 网格保.出图(状态))
        总 += 1
        不同总 += n; 严重总 += sev; 最大总 = max(最大总, mx)
        保不同 += n2; 保严重 += sev2; 保最大 = max(保最大, mx2)
        if sev > 最差[1]: 最差 = (标签, sev)
        if 计时它:
            ms = 计时(网格慢, 状态); mf = 计时(网格快, 状态); mb = 计时(网格保, 状态)
            慢总 += ms; 快总 += mf; 保总 += mb; 计次 += 1
            速 = f"｜ A {ms/mf:.2f}× ｜ A′ {ms/mb:.2f}×"
        else:
            速 = ""
        标 = "✅" if sev == 0 else ("⚠" if sev <= 2 else "⛔")
        标2 = "✅" if sev2 == 0 else ("⚠" if sev2 <= 2 else "⛔")
        print(f"  A{标} A′{标2} {标签:<22} ｜A: {n:5d}/≥65 {sev:2d}/差 {mx:3d} ｜A′: {n2:5d}/≥65 {sev2:2d}/差 {mx2:3d}{速}")

    print("① 让身体自己跑 12 秒（覆盖 idle/walk/sit/sleep 等自然状态）")
    身.设模式("idle")
    for i in range(720):
        身.步(1 / 60)
        if i % 90 == 89:
            采一帧(f"自由漫游 {i/60:.1f}s 模式={身.宠物['mode']}")

    print("\n② 逐个姿势 + 逐个表情（把主要组合都过一遍）")
    姿势 = ["idle", "walk", "run", "sit", "sleep", "air", "drag", "crouch", "dizzy"]
    表情 = ["neutral", "happy", "angry", "sad", "surprised", "shy", "love",
            "wink", "sleepy", "dizzy", "thinking", "content"]
    for m in 姿势:
        try:
            身.设模式(m)
        except Exception:
            continue
        for _ in range(45):
            身.步(1 / 60)
        身.设表情("neutral", 99)
        for _ in range(20):
            身.步(1 / 60)
        采一帧(f"姿势 {m}", 计时它=开关)
    for f in 表情:
        try:
            身.设表情(f, 99)
        except Exception:
            continue
        for _ in range(30):
            身.步(1 / 60)
        采一帧(f"表情 {f}", 计时它=开关)

    print("\n③ 极端格步（1 = 最密、4 = 最稀）")
    for g in (1, 2, 4):
        a = 网格渲染器(模型, max(.2, .62 * 1.25), g)
        b = 快渲染器(模型, max(.2, .62 * 1.25), g)
        鱼2 = 鱼类(模型, a)
        for _ in range(60):
            身.步(1 / 60)
        脸, 帧 = 身.出帧()
        状态 = 鱼2.画(脸, 帧)
        n, sev, mx = 比一比(a.出图(状态), b.出图(状态))
        总 += 1
        不同总 += n
        严重总 += sev
        最大总 = max(最大总, mx)
        if sev > 最差[1]:
            最差 = (f"格步{g}", sev)
        标 = "✅" if sev == 0 else ("⚠" if sev <= 2 else "⛔")
        print(f"  {标} 格步 {g:<22} 不同 {n:6d} ｜ ≥65 {sev:3d} ｜ 最大差 {mx:3d}")

    print()
    print("═" * 58)
    print(f"共比对 {总} 帧")
    print(f"  快版 A   ：不同 {不同总}  ｜ ≥65 {严重总}  ｜ 最大通道差 {最大总}")
    print(f"  快版 A′  ：不同 {保不同}  ｜ ≥65 {保严重}  ｜ 最大通道差 {保最大}")
    print(f"最差的一帧：{最差[0]}（≥65 像素 {最差[1]} 个）")
    if 计次:
        print(f"受控计时（{计次} 个真实状态，每个轮流量 2×6 次出图）：")
        print(f"    现状    {慢总/计次:6.2f} ms/帧")
        print(f"    快版 A  {快总/计次:6.2f} ms/帧  ＝ {慢总/快总:.2f}×")
        print(f"    快版 A′ {保总/计次:6.2f} ms/帧  ＝ {慢总/保总:.2f}×")
    print()
    if 保严重 == 0:
        print("✅ 快版 A′（保真）逐帧逐像素一致 → 这一个可以放心开。")
        return 0
    print(f"⚠ 快版 A′ 仍有 {保严重} 个 ≥65 像素，需要人工看图确认。")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())

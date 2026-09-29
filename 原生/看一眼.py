#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""看一眼 —— 离线把身体跑起来，出几张图，看看姿势对不对（不碰屏幕、不碰核心）。"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtGui import QGuiApplication, QImage, QPainter   # noqa: E402

from 身体 import 身体 as 身类                                          # noqa: E402
from 合成 import 合成器                                        # noqa: E402
from 模型 import 鲸鱼模型                                      # noqa: E402
from 小鱼 import 小鱼 as 鱼类                                          # noqa: E402
from 网格 import 网格渲染器                                    # noqa: E402

_资源 = os.environ.get("COOP_ASSETS")
网页 = Path(_资源) if _资源 else (Path.home() / "coop-linux/app/packages/cortico-world-desktop-pet/web")
宽, 高 = 1920, 1080


def 搭舞台(比例=0.62, 格步=1):
    模型 = 鲸鱼模型(网页)
    网格 = 网格渲染器(模型, max(.2, 比例 * 1.25), 格步)
    鱼 = 鱼类(模型, 网格)
    身 = 身类(锚点=鱼.锚点,
              边界=lambda: (宽, 高, 高 - 2, 比例),
              漫游="calm", 进场="none", 起始x=960)
    身.S = 比例
    身.调整尺寸()
    合成 = 合成器(模型, 身, 鱼, 网格)
    return 模型, 网格, 鱼, 身, 合成


def 一帧(合成, 身体, 小鱼, 网格, 裁到人物=True):
    脸, 帧 = 身体.出帧()
    状态 = 小鱼.画(脸, 帧)
    图 = 合成.出图(宽, 高, 状态, 帧, 脸)
    if 裁到人物:
        p = 身体.宠物
        xf = p["xf"]
        cx, cy = xf["AX"], xf["AY"] - 140 * 身体.S
        r = 190 * 身体.S
        x0, y0 = max(0, int(cx - r)), max(0, int(cy - r))
        x1, y1 = min(宽, int(cx + r)), min(高, int(cy + r))
        图 = 图.copy(x0, y0, x1 - x0, y1 - y0)   # QImage.copy 收的是 (x, y, 宽, 高)
    return 图


def main():
    app = QGuiApplication(sys.argv)
    模型, 网格, 小鱼, 身体, 合成 = 搭舞台()
    出 = []
    print("① 空跑 10 秒，看看会不会炸")
    for i in range(600):
        身体.步(1 / 60)
    print(f"   T={身体.时间:.1f}s 模式={身体.宠物['mode']} 位置 x={身体.宠物['x']:.0f} 表情={身体.宠物['_fname']}")
    出.append(("空闲", 一帧(合成, 身体, 小鱼, 网格)))
    print("② 各种姿势")
    姿势 = [
        ("走路", lambda: 身体.动作("walk"), 40),
        ("起跳", lambda: 身体.动作("jump"), 22),
        ("坐着", lambda: 身体.动作("sit"), 90),
        ("睡着", lambda: 身体.动作("sleep"), 120),
        ("开心", lambda: 身体.设表情("happy"), 20),
        ("生气", lambda: 身体.设表情("angry"), 25),
        ("惊讶", lambda: 身体.设表情("surprised"), 12),
        ("晕乎", lambda: 身体.动作("dizzy"), 60),
    ]
    for 名, 做, 步数 in 姿势:
        身体.设模式("idle"); 身体.宠物["expr"] = None; 身体.宠物["durry"] if False else None
        做()
        for _ in range(步数):
            身体.步(1 / 60)
        出.append((名, 一帧(合成, 身体, 小鱼, 网格)))
        print(f"   {名:4s} → 模式={身体.宠物['mode']:8s} 表情={身体.宠物['_fname']}")
    print("③ 拖起来看看")
    身体.设模式("idle"); 身体.宠物["expr"] = None
    cx, cy = 身体.到舞台(128, 128)
    身体.指针按下(cx, cy)
    身体.指针移动(cx + 40, cy - 30)
    for _ in range(30):
        身体.步(1 / 60)
    出.append(("被拎起", 一帧(合成, 身体, 小鱼, 网格)))
    身体.指针松开()
    for _ in range(40):
        身体.步(1 / 60)
    出.append(("扔出去", 一帧(合成, 身体, 小鱼, 网格)))
    # 拼成一张对照图
    高最 = max(im.height() for _, im in 出)
    宽总 = sum(im.width() for _, im in 出)
    拼 = QImage(宽总, 高最, QImage.Format.Format_ARGB32_Premultiplied)
    拼.fill(0)
    q = QPainter(拼)
    x = 0
    for 名, im in 出:
        q.drawImage(x, 高最 - im.height(), im)
        x += im.width()
    q.end()
    拼.save("/tmp/原生-姿势表.png")
    print(f"→ /tmp/原生-姿势表.png  {拼.width()}×{拼.height()}")


if __name__ == "__main__":
    main()

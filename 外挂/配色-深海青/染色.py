#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""鲸鱼娘配色生成器：把基准配色（web/whale/tex + feat）重着色成一套新配色。

原理：母版几何完全共用，每套配色只是「同一批贴图换了颜色」。
这里只动蓝色那一段色相（头发/裙子/眼睛），皮肤、白色、灰色一概不碰，
所以在 HSV 里按「色相区间 + 饱和度」做掩膜，再做线性色相重映射。

用法：
    python3 染色.py <输出目录>        # 生成 tex/ 和 feat/ 到指定目录
"""
import sys
from pathlib import Path

from PIL import Image, ImageChops

# 色相在 PIL 里是 0-255（360° 映射到 256）
源色相段 = (140, 200)        # DeepSeek 蓝所在的那一段
目标色相段 = (100, 160)      # 深海青：整体 -40（约 -56°）
饱和度门槛 = 40              # 低于这个饱和度的（白、灰、黑）不动
饱和度增益 = 1.12            # 稍微提一点饱和，看起来更清爽


def 重映射(值: int) -> int:
    if 值 < 源色相段[0] or 值 > 源色相段[1]:
        return 值
    k = (值 - 源色相段[0]) / (源色相段[1] - 源色相段[0])
    return int(目标色相段[0] + k * (目标色相段[1] - 目标色相段[0])) % 256


def 染一张(源: Path, 目标: Path) -> None:
    im = Image.open(源).convert("RGBA")
    透明 = im.getchannel("A")
    h, s, v = im.convert("RGB").convert("HSV").split()

    蓝 = h.point(lambda x: 255 if 源色相段[0] <= x <= 源色相段[1] else 0)
    彩 = s.point(lambda x: 255 if x >= 饱和度门槛 else 0)
    掩膜 = ImageChops.multiply(蓝, 彩)

    h2 = h.point(重映射)
    s2 = s.point(lambda x: min(255, int(x * 饱和度增益)))

    出 = Image.merge("HSV", (Image.composite(h2, h, 掩膜), Image.composite(s2, s, 掩膜), v)).convert("RGB")
    出 = 出.convert("RGBA")
    出.putalpha(透明)
    目标.parent.mkdir(parents=True, exist_ok=True)
    出.save(目标)


def main() -> None:
    基准 = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else None
    if 基准 is None:
        sys.exit("用法：python3 染色.py <输出目录>")
    这里 = Path(__file__).resolve().parent
    源根 = 这里 / "基准贴图"          # 装外挂时把基准贴图复制过来，避免依赖 app 目录结构
    if not 源根.exists():
        sys.exit(f"找不到基准贴图目录：{源根}")

    数 = 0
    for 子 in ("tex", "feat"):
        for 图 in sorted((源根 / 子).glob("*.png")):
            染一张(图, 基准 / 子 / 图.name)
            数 += 1
    print(f"  染好 {数} 张贴图 → {基准}")


if __name__ == "__main__":
    main()

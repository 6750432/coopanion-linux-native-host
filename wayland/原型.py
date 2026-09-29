#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""底层探针：用纯 ctypes 的裸 Wayland 协议，把一张 CPU 画好的图送上屏并测代价。

English: A raw-protocol Wayland probe. It never touches Qt/GTK/SDL — it speaks
wl_shm + xdg-shell straight through ctypes, uploads a CPU-rasterised ARGB image,
carves its input region with the CORE `wl_surface.set_input_region` request, and
measures what the full-screen-layer architecture would actually cost.

中文：完全不碰 Qt/GTK/SDL，直接用 ctypes 说 wl_shm + xdg-shell 协议。它把 CPU 画好的
ARGB 图丢进共享内存送屏，用**核心协议**（不是扩展）的 set_input_region 挖出点击穿透区，
并实测「Wayland 上被迫改用全屏透明层」这条路到底要多少 CPU。

用法：
    python3 原型.py --模式=小窗          # 360×360 独立小窗
    python3 原型.py --模式=全屏          # 1920×1080 每帧整屏
    python3 原型.py --模式=全屏局部      # 1920×1080 但只提交宠物那一小块
    python3 原型.py --秒=8 --模式=全屏
"""

import argparse
import mmap
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wlraw

XDG_XML = wlraw.找协议xml("stable/xdg-shell/xdg-shell.xml")

宠物边长 = 360
格式_ARGB8888 = 0


# ------------------------------------------------------------------ 小工具

def 读CPU秒(pid):
    """读一个进程累计吃掉的 CPU 秒数（utime+stime）。"""
    try:
        with open(f"/proc/{pid}/stat") as f:
            数据 = f.read()
    except OSError:
        return None
    段 = 数据[数据.rindex(")") + 2:].split()
    return (int(段[11]) + int(段[12])) / os.sysconf("SC_CLK_TCK")


def 造鱼块(边长=宠物边长):
    """造一块带透明的 ARGB 图案（BGRA 字节序），模拟桌宠那一帧。"""
    R = 边长 / 2 - 6
    半 = 边长 / 2
    行表 = []
    for y in range(边长):
        dy = y - 半 + 0.5
        行 = bytearray(边长 * 4)
        for x in range(边长):
            dx = x - 半 + 0.5
            d = (dx * dx + dy * dy) ** 0.5
            i = x * 4
            if d <= R:
                行[i + 0] = 200 - int(d * 0.3)
                行[i + 1] = 120 + ((x // 16) % 2) * 60
                行[i + 2] = 40 + ((y // 16) % 2) * 80
                行[i + 3] = 255
        行表.append(bytes(行))
    return b"".join(行表)


def 贴块(大图, 跨距, 块, 块边长, x, y, 屏宽, 屏高):
    """把方块贴进大图，带边界裁剪。"""
    x0, y0 = max(x, 0), max(y, 0)
    x1, y1 = min(x + 块边长, 屏宽), min(y + 块边长, 屏高)
    if x0 >= x1 or y0 >= y1:
        return
    for 行号 in range(y0, y1):
        源起 = ((行号 - y) * 块边长 + (x0 - x)) * 4
        # 注意：块是整块 bytes，切片出来正好一行要的像素
        if x1 - x < 块边长:
            片段 = 块[源起:源起 + (x1 - x0) * 4]
        else:
            片段 = 块[源起:源起 + (x1 - x0) * 4]
        大图[行号 * 跨距 + x0 * 4: 行号 * 跨距 + x1 * 4] = 片段


# --------------------------------------------------------------- 探针本体

class 探针:
    def __init__(self, 宽, 高, 模式, 秒数, 显示名=None):
        self.屏宽, self.屏高 = 宽, 高
        self.模式, self.秒数 = 模式, 秒数
        self.连 = wlraw.连接(显示名)
        self.连.装扩展(xml路径=XDG_XML)
        self.帧次数 = 0
        self.回调时间戳 = []
        self.画耗时 = []
        self.送耗时 = []
        self.自检 = {}

    # ---- 能力普查：先问清楚这台合成器到底给什么
    def 普查(self):
        表 = {}
        for 号, 名, 版 in self.连.全局:
            表.setdefault(名, []).append(版)
        self.自检["全局"] = 表
        return 表

    # ---- 建窗
    def 建窗(self):
        连 = self.连
        自 = self.自检
        自["合成器"] = self.探针版本 = None
        self.合成器 = 连.绑("wl_compositor")
        self.shm = 连.绑("wl_shm")
        self.wm = 连.绑("xdg_wm_base")
        自["合成器版本"] = int(连.lib.wl_proxy_get_version(self.合成器.p))
        自["shm 格式"] = int(连.lib.wl_proxy_get_version(self.shm.p))
        # layer-shell 在不在？wlroots 系才有，weston/GNOME 没有
        自["有 layer-shell"] = any(g[1] == "zwlr_layer_shell_v1" for g in 连.全局)
        自["有 wl_seat"] = any(g[1] == "wl_seat" for g in 连.全局)

        面宽 = 宠物边长 if self.模式 == "小窗" else self.屏宽
        面高 = 宠物边长 if self.模式 == "小窗" else self.屏高
        self.面宽, self.面高 = 面宽, 面高

        self.面 = self.合成器.create_surface()
        self.xdg面 = self.wm.get_xdg_surface(self.面)
        self.顶 = self.xdg面.get_toplevel()
        self.顶.set_title(b"dafeiyu raw wayland probe")
        self.顶.set_app_id(b"dafeiyu-wayland-raw")
        self.xdg面.set_window_geometry(0, 0, 面宽, 面高)

        self.已配置 = False
        self.配置序号 = 0

        def 面配置(_d, _xs, 序号):
            self.配置序号 = int(序号)
            self.已配置 = True

        def 顶配置(_d, _t, w, h, _状态):
            # kiosk shell 会把它铺满，这里只记录合成器想给多大
            self.自检["合成器给的尺寸"] = (int(w), int(h))

        self.连.挂监听(self.xdg面, {"configure": 面配置})
        self.连.挂监听(self.顶, {"configure": 顶配置, "close": lambda *a: None})
        self.面.commit()

        # 等第一帧 configure，必须 ack 之后才能上缓冲
        截止 = time.time() + 3
        while not self.已配置 and time.time() < 截止:
            if not self.连.等一批(200):
                pass
        if not self.已配置:
            raise RuntimeError("等不到 xdg_surface.configure")
        self.xdg面.ack_configure(self.配置序号)
        self.自检["拿到 configure"] = True

    # ---- 共享内存
    def 建池(self):
        连 = self.连
        self.跨距 = self.面宽 * 4
        self.体积 = self.跨距 * self.面高
        self.fd = os.memfd_create("dafeiyu-wl-shm", 0)
        os.ftruncate(self.fd, self.体积)
        self.图 = mmap.mmap(self.fd, self.体积)
        self.池 = self.shm.create_pool(self.fd, self.体积)
        self.缓冲 = self.池.create_buffer(0, self.面宽, self.面高, self.跨距, 格式_ARGB8888)
        self.自检["共享内存 MB"] = round(self.体积 / 1024 / 1024, 2)
        self.鱼 = 造鱼块()
        # 全屏底色（模拟桌宠背后那层要被填满的透明层）
        self.底色 = bytes([0, 0, 0, 0]) * (self.面宽 * self.面高)

    # ---- 点击穿透：核心协议，不是扩展
    def 挖输入区(self, x, y, 宽, 高):
        if getattr(self, "区域", None) is None:
            self.区域 = self.合成器.create_region()
        self.区域.add(x, y, 宽, 高)
        self.面.set_input_region(self.区域)
        self.自检["输入区"] = (x, y, 宽, 高)

    # ---- 一帧
    def 画一帧(self, 宠物x, 宠物y, 旧x, 旧y):
        t0 = time.thread_time()
        if self.模式 == "小窗":
            self.图[:] = self.底色[:宠物边长 * 宠物边长 * 4]
            贴块(self.图, self.跨距, self.鱼, 宠物边长, 0, 0, 宠物边长, 宠物边长)
            伤害 = [(0, 0, 宠物边长, 宠物边长)]
        elif self.模式 == "全屏":
            self.图[:] = self.底色
            贴块(self.图, self.跨距, self.鱼, 宠物边长, 宠物x, 宠物y, self.面宽, self.面高)
            伤害 = [(0, 0, self.面宽, self.面高)]
        else:  # 全屏局部
            透明块 = self.底色[:宠物边长 * 4 * 宠物边长]
            贴块(self.图, self.跨距, 透明块, 宠物边长, 旧x, 旧y, self.面宽, self.面高)
            贴块(self.图, self.跨距, self.鱼, 宠物边长, 宠物x, 宠物y, self.面宽, self.面高)
            伤害 = [(旧x, 旧y, 宠物边长, 宠物边长), (宠物x, 宠物y, 宠物边长, 宠物边长)]
        self.画耗时.append((time.thread_time() - t0) * 1000)

        t1 = time.thread_time()
        self.面.attach(self.缓冲, 0, 0)
        for x, y, w, h in 伤害:
            self.面.damage(x, y, w, h)
        回调 = self.面.frame()
        self.连.挂监听(回调, {"done": self._帧回})
        self.面.commit()
        self.连.lib.wl_display_flush(self.连.d)
        self.送耗时.append((time.thread_time() - t1) * 1000)
        self.当前回调 = 回调

    def _帧回(self, _d, _cb, 时间戳):
        self.帧次数 += 1
        self.回调时间戳.append(int(时间戳))
        self.连.lib.wl_proxy_destroy(_cb)

    # ---- 主循环
    def 跑(self):
        自费0 = 读CPU秒(os.getpid())
        合费0 = 读CPU秒(int(os.environ.get("WESTON_PID", "0"))) if os.environ.get("WESTON_PID") else None

        宠物x = 宠物y = 0
        旧x = 旧y = 0
        self.画一帧(宠物x, 宠物y, 旧x, 旧y)
        t0 = time.perf_counter()
        步 = 0
        while time.perf_counter() - t0 < self.秒数:
            之前 = self.帧次数
            self.连.等一批(500)
            if self.帧次数 == 之前:
                continue        # 没等到 frame 回调就不画，免得把「空转」算进帧率里
            步 += 1
            if self.模式 == "小窗":
                宠物x = 宠物y = 0
            else:
                旧x, 旧y = 宠物x, 宠物y
                # 宠物在屏幕里走一圈，逼真地制造「旧位置要擦、新位置要画」
                宠物x = int((self.面宽 - 宠物边长) * (0.5 + 0.5 * __import__("math").sin(步 / 40)))
                宠物y = int((self.面高 - 宠物边长) * (0.5 + 0.5 * __import__("math").cos(步 / 33)))
            self.画一帧(宠物x, 宠物y, 旧x, 旧y)
        用时 = time.perf_counter() - t0
        自费1 = 读CPU秒(os.getpid())
        合费1 = 读CPU秒(int(os.environ["WESTON_PID"])) if os.environ.get("WESTON_PID") else None

        间隔 = [b - a for a, b in zip(self.回调时间戳, self.回调时间戳[1:])] or [0]
        结果 = {
            "模式": self.模式,
            "画面": f"{self.面宽}×{self.面高}",
            "用时秒": round(用时, 2),
            "帧数": self.帧次数,
            "帧率": round(self.帧次数 / 用时, 1),
            "帧间隔中位ms": round(statistics.median(间隔), 2) if len(间隔) > 1 else 0,
            "客户端CPU%": round(100 * (自费1 - 自费0) / 用时, 1),
            "画图中位ms": round(statistics.median(self.画耗时), 2),
            "提交中位ms": round(statistics.median(self.送耗时), 2),
        }
        if 合费0 is not None and 合费1 is not None:
            结果["合成器CPU%"] = round(100 * (合费1 - 合费0) / 用时, 1)
        return 结果

    def 收尾(self):
        try:
            if getattr(self, "当前回调", None):
                pass
            self.连.关()
        except Exception:
            pass


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--模式", default="小窗", choices=["小窗", "全屏", "全屏局部"])
    p.add_argument("--秒", type=float, default=6)
    p.add_argument("--宽", type=int, default=1920)
    p.add_argument("--高", type=int, default=1080)
    p.add_argument("--显示", default=None)
    Ａ = p.parse_args()

    t建 = time.perf_counter()
    探 = 探针(Ａ.宽, Ａ.高, Ａ.模式, Ａ.秒, Ａ.显示)
    普 = 探.普查()
    t连 = time.perf_counter() - t建

    print("=" * 70)
    print(f"合成器全局对象（{len(普)} 种）")
    print("=" * 70)
    for 名 in sorted(普):
        print(f"  {名:<34} v{max(普[名])}")

    探.建窗()
    探.建池()
    if Ａ.模式 == "小窗":
        探.挖输入区(40, 40, 宠物边长 - 80, 宠物边长 - 80)
    else:
        # 全屏层：整屏都不吃鼠标，只有宠物身上那个圈吃
        探.挖输入区(60, 60, 宠物边长 - 120, 宠物边长 - 120)

    print()
    print("=" * 70)
    print("协议能力自检")
    print("=" * 70)
    for k, v in 探.自检.items():
        if k == "全局":
            continue
        print(f"  {k:<16} {v}")
    print(f"  {'连接+建窗耗时s':<16} {t连:.3f}")

    结果 = 探.跑()
    探.收尾()
    print()
    print("=" * 70)
    print("实测结果")
    print("=" * 70)
    for k, v in 结果.items():
        print(f"  {k:<16} {v}")


if __name__ == "__main__":
    main()

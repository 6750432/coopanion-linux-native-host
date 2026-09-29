#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""子表面方案：让「全屏透明层」的代价降到小窗水平。

English: The subsurface trick. Without wlr-layer-shell (GNOME, plain xdg-shell
desktops) a pet is forced to live inside a full-screen transparent layer. Instead
of redrawing 1920x1080 every frame, keep the parent fully transparent and NEVER
touch it again, then put the pet on a `wl_subsurface` child that only ever uploads
360x360 pixels and is moved with `set_position`.

中文：GNOME 那边没有 layer-shell，桌宠只能塞进一个全屏透明层。但我们没必要每帧
重画那 1920×1080 —— 父面全透明、提交一次之后再也不碰；宠物挂在 wl_subsurface
子面上，永远只传 360×360，靠 set_position 自由挪位置。
关键点：父面必须用**空**输入区（不是 NULL —— NULL 会恢复成"整面吃鼠标"），
子面用 set_desync 独立提交（否则子面的改动要等父面 commit 才生效，而父面我们不动了）。
"""

import math
import mmap
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wlraw

XDG_XML = wlraw.找协议xml("stable/xdg-shell/xdg-shell.xml")

屏宽, 屏高 = int(os.environ.get("SW", 1920)), int(os.environ.get("SH", 1080))
宠物边长 = 360
秒数 = float(os.environ.get("SEC", 8))


def 读CPU秒(pid):
    try:
        with open(f"/proc/{pid}/stat") as f:
            数据 = f.read()
    except OSError:
        return None
    段 = 数据[数据.rindex(")") + 2:].split()
    return (int(段[11]) + int(段[12])) / os.sysconf("SC_CLK_TCK")


def 造鱼块(边长=宠物边长):
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
                行[i] = 200 - int(d * 0.3)
                行[i + 1] = 120 + ((x // 16) % 2) * 60
                行[i + 2] = 40 + ((y // 16) % 2) * 80
                行[i + 3] = 255
        行表.append(bytes(行))
    return b"".join(行表)


def 建共享图(shm, 宽, 高, 内容=b""):
    跨距 = 宽 * 4
    体积 = 跨距 * 高
    fd = os.memfd_create("sub-shm", 0)
    os.ftruncate(fd, 体积)
    池 = shm.create_pool(fd, 体积)
    缓 = 池.create_buffer(0, 宽, 高, 跨距, 0)      # 0 = ARGB8888
    图 = mmap.mmap(fd, 体积)
    if 内容:
        图[:] = 内容
    return 缓, 图, 跨距


连 = wlraw.连接(os.environ.get("WAYLAND_DISPLAY"))
连.装扩展(xml路径=XDG_XML)
全局 = {g[1]: g[2] for g in 连.全局}
print("有 wl_subcompositor 吗：", "wl_subcompositor" in 全局,
      "（这是核心协议，GNOME/KDE/wlroots 都有）", flush=True)

合成器 = 连.绑("wl_compositor")
shm = 连.绑("wl_shm")
wm = 连.绑("xdg_wm_base")
子合成器 = 连.绑("wl_subcompositor")

# ---------- 父面：全屏、全透明、提交一次之后再不动 ----------
父面 = 合成器.create_surface()
xs = wm.get_xdg_surface(父面)
顶 = xs.get_toplevel()
顶.set_title(b"subsurface parent")
顶.set_app_id(b"dafeiyu-sub")
xs.set_window_geometry(0, 0, 屏宽, 屏高)
已配 = []
连.挂监听(xs, {"configure": lambda d, x, s: 已配.append(int(s))})
连.挂监听(顶, {"configure": lambda *a: None, "close": lambda *a: None})
父面.commit()
截止 = time.time() + 3
while not 已配 and time.time() < 截止:
    连.等一批(200)
xs.ack_configure(已配[0])

透明 = bytes(屏宽 * 屏高 * 4)          # 全 0 = 全透明
父缓, 父图, 父跨距 = 建共享图(shm, 屏宽, 屏高, 透明)
# ⚠️ 空输入区（不是 NULL）才等于"整面不吃鼠标"；NULL 会恢复成整面吃鼠标
空区 = 合成器.create_region()
父面.set_input_region(空区)
父面.attach(父缓, 0, 0)
父面.damage(0, 0, 屏宽, 屏高)
父面.commit()
连.lib.wl_display_flush(连.d)
print(f"父面：{屏宽}×{屏高} 全透明，输入区=空（整屏穿透），已提交，之后不再碰", flush=True)

# ---------- 子面：只传 360×360，靠 set_position 挪 ----------
子面 = 合成器.create_surface()
子缓, 子图, 子跨距 = 建共享图(shm, 宠物边长, 宠物边长)
子表 = 子合成器.get_subsurface(子面, 父面)
子表.set_desync()          # 子面独立提交，不用等父面 commit
子表.place_above(父面)      # 排在父面内容之上（父面是透明的，纯粹为了保险）
宠物区 = 合成器.create_region()
宠物区.add(40, 40, 宠物边长 - 80, 宠物边长 - 80)
子面.set_input_region(宠物区)
子表.set_position(0, 0)
子面.attach(子缓, 0, 0)
子面.damage(0, 0, 宠物边长, 宠物边长)
子面.commit()
连.lib.wl_display_flush(连.d)
print("子面：360×360，输入区=中间一小块（其余穿透）", flush=True)

# ---------- 主循环 ----------
鱼 = 造鱼块()
帧次数 = 0
时间戳 = []
画耗时 = []
送耗时 = []


def 帧回(_d, cb, 时间戳值):
    global 帧次数
    帧次数 += 1
    时间戳.append(int(时间戳值))
    连.lib.wl_proxy_destroy(cb)


def 一帧(x, y):
    t0 = time.thread_time()
    子图[:] = 鱼
    画耗时.append((time.thread_time() - t0) * 1000)
    t1 = time.thread_time()
    子面.attach(子缓, 0, 0)
    子面.damage(0, 0, 宠物边长, 宠物边长)
    子表.set_position(x, y)
    回 = 子面.frame()
    连.挂监听(回, {"done": 帧回})
    子面.commit()
    连.lib.wl_display_flush(连.d)
    送耗时.append((time.thread_time() - t1) * 1000)


自费0 = 读CPU秒(os.getpid())
合费0 = 读CPU秒(int(os.environ["WESTON_PID"])) if os.environ.get("WESTON_PID") else None

步 = 0
一帧(0, 0)
t0 = time.perf_counter()
while time.perf_counter() - t0 < 秒数:
    之前 = 帧次数
    连.等一批(500)
    if 帧次数 == 之前:
        continue
    步 += 1
    x = int((屏宽 - 宠物边长) * (0.5 + 0.5 * math.sin(步 / 40)))
    y = int((屏高 - 宠物边长) * (0.5 + 0.5 * math.cos(步 / 33)))
    一帧(x, y)
用时 = time.perf_counter() - t0
自费1 = 读CPU秒(os.getpid())
合费1 = 读CPU秒(int(os.environ["WESTON_PID"])) if os.environ.get("WESTON_PID") else None

间隔 = [b - a for a, b in zip(时间戳, 时间戳[1:])] or [0]
print()
print("=" * 60)
print("  模式                子表面（父面全屏透明 + 宠物挂子是子面）")
print(f"  父面                 {屏宽}×{屏高}（提交一次，之后零更新）")
print(f"  每帧实际上传          {宠物边长}×{宠物边长} = "
      f"{宠物边长*宠物边长*4/1024:.0f} KB")
print(f"  用时秒               {用时:.2f}")
print(f"  帧数                 {帧次数}")
print(f"  帧率                 {帧次数/用时:.1f}")
print(f"  帧间隔中位ms          {statistics.median(间隔):.2f}" if len(间隔) > 1 else "")
print(f"  客户端CPU%           {100*(自费1-自费0)/用时:.1f}")
if 合费0 is not None and 合费1 is not None:
    print(f"  合成器CPU%           {100*(合费1-合费0)/用时:.1f}")
print(f"  画图中位ms            {statistics.median(画耗时):.2f}")
print(f"  提交中位ms            {statistics.median(送耗时):.2f}")

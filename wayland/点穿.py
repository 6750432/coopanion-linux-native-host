#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""点击穿透的真·端到端验证。

English: End-to-end click-through test. We carve a small input region out of a
full-screen surface with the CORE request `wl_surface.set_input_region`, then have
real X11 clicks injected into the nested compositor window. A click inside the
region must reach us; a click outside must not — that is the whole claim.

中文：证明「Wayland 上挖点击穿透区」不是纸上谈兵。我们用核心协议请求
set_input_region 在全屏面上挖一个 240×240 的小方块，然后往嵌套合成器窗口里
打真鼠标点击：方块内必须收到 wl_pointer 事件，方块外必须收不到。
"""

import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wlraw

XDG_XML = wlraw.找协议xml("stable/xdg-shell/xdg-shell.xml")

宽, 高 = int(os.environ.get("CT_W", 900)), int(os.environ.get("CT_H", 560))
区 = (60, 60, 240, 240)      # 只有这一块吃鼠标，其余整屏点击穿透

连 = wlraw.连接(os.environ.get("WAYLAND_DISPLAY"))
连.装扩展(xml路径=XDG_XML)

全局 = {g[1]: g[2] for g in 连.全局}
print("全局里有 wl_seat 吗：", "wl_seat" in 全局, flush=True)

合成器 = 连.绑("wl_compositor")
shm = 连.绑("wl_shm")
wm = 连.绑("xdg_wm_base")
座 = 连.绑("wl_seat") if "wl_seat" in 全局 else None

面 = 合成器.create_surface()
xs = wm.get_xdg_surface(面)
顶 = xs.get_toplevel()
顶.set_title(b"click-through test")
顶.set_app_id(b"dafeiyu-ct")
已配 = []
连.挂监听(xs, {"configure": lambda d, x, s: 已配.append(int(s))})
连.挂监听(顶, {"configure": lambda *a: None, "close": lambda *a: None})
面.commit()
截止 = time.time() + 3
while not 已配 and time.time() < 截止:
    连.等一批(200)
xs.ack_configure(已配[0])

# 共享内存 + 一块实心缓冲（看得见才知道位置）
跨距 = 宽 * 4
体积 = 跨距 * 高
fd = os.memfd_create("ct-shm", 0)
os.ftruncate(fd, 体积)
池 = shm.create_pool(fd, 体积)
缓 = 池.create_buffer(0, 宽, 高, 跨距, 0)
import mmap
图 = mmap.mmap(fd, 体积)
# 把输入区那一块涂成实心绿，其余全透明 —— 眼睛和协议对得上
for y in range(区[1], 区[1] + 区[3]):
    起 = y * 跨距 + 区[0] * 4
    图[起:起 + 区[2] * 4] = bytes([40, 200, 60, 255]) * 区[2]

区域 = 合成器.create_region()
区域.add(*区)
面.set_input_region(区域)
面.attach(缓, 0, 0)
面.damage(0, 0, 宽, 高)
面.commit()
连.lib.wl_display_flush(连.d)
print(f"输入区 = {区}（屏幕坐标里那块绿方块），其余整屏点击穿透", flush=True)

事件表 = []
def 进(d, 指针, 序号, 面指针, sx, sy):
    事件表.append(("enter", sx / 256.0, sy / 256.0))
    print(f"  ★ enter  面内坐标 ({sx/256.0:.1f}, {sy/256.0:.1f})", flush=True)
def 离(d, 指针, 序号, 面指针):
    事件表.append(("leave", 0, 0))
    print("  ★ leave", flush=True)

指针 = None
if 座:
    指针 = 座.get_pointer()
    连.挂监听(指针, {
        "enter": 进,
        "leave": 离,
        "motion": lambda d, p, t, sx, sy: 事件表.append(("motion", sx / 256.0, sy / 256.0)),
        "button": lambda d, p, s, t, b, st: (事件表.append(("button", b, st)),
                                             print(f"  ★ button {b} state={st}", flush=True))[-1],
    })
    连.lib.wl_display_flush(连.d)

时长 = float(os.environ.get("CT_SEC", 12))
print(f"→ 现在等 {时长:.0f} 秒，外部往窗口里打点击", flush=True)
t0 = time.time()
while time.time() - t0 < 时长:
    连.等一批(200)

进数 = sum(1 for e in 事件表 if e[0] == "enter")
离数 = sum(1 for e in 事件表 if e[0] == "leave")
按数 = sum(1 for e in 事件表 if e[0] == "button")
内 = [e for e in 事件表 if e[0] in ("enter", "motion")
      and 区[0] <= e[1] <= 区[0] + 区[2] and 区[1] <= e[2] <= 区[1] + 区[3]]
外 = [e for e in 事件表 if e[0] in ("enter", "motion")
      and not (区[0] <= e[1] <= 区[0] + 区[2] and 区[1] <= e[2] <= 区[1] + 区[3])]
print()
print("=" * 60)
print(f"  enter 次数 {进数}   leave 次数 {离数}   按键事件 {按数}")
print(f"  落在输入区内的指针事件：{len(内)}")
print(f"  落在输入区外的指针事件：{len(外)}   ← 必须为 0，否则就是没穿透")
print("  结论：", "✅ 点击穿透成立" if (内 and not 外) else
      ("⚠️ 有区外事件" if 外 else "❓ 没收到任何事件（是不是没打点击？）"))

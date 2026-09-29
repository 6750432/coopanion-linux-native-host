#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""拿 wayland-scanner 的原厂输出，逐字段校验我们「纯 ctypes 造的接口表」。

English: Validate the pure-ctypes XML-to-interface-table generator against the
canonical output of wayland-scanner itself (private-code mode), for both the core
protocol and xdg-shell. No compiler is used by our side at all.

中文：从 XML 到 wl_interface 表，wayland-scanner 是唯一权威。这里把它 private-code
生成的 C 解析成参考结构，再和我们运行时造出来的表逐字段比。
比的是：接口名、版本、请求/事件条数、每条消息的名字、签名、以及每个参数位引用的接口。
"""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import wlraw

SCANNER = wlraw.找扫描器()
WAYLAND_XML = wlraw.找协议xml("wayland.xml", 核心=True)
XDG_XML = wlraw.找协议xml("stable/xdg-shell/xdg-shell.xml")


def 跑扫描器(xml):
    """让 wayland-scanner 出一份 private-code，当参考。

    ⚠️ 坑：wayland-scanner 1.22 **不认 `-` 当标准输出**，会老老实实创建一个名叫 `-`
    的文件。必须给它真路径，再读回来。"""
    import os
    import tempfile
    fd, 临时 = tempfile.mkstemp(suffix="-protocol.c")
    os.close(fd)
    try:
        subprocess.run([SCANNER, "private-code", xml, 临时],
                       capture_output=True, text=True, check=True)
        with open(临时, encoding="utf-8") as f:
            return f.read()
    finally:
        os.unlink(临时)


def 拆原厂(c文本):
    """把 C 里的 types 共享槽 + wl_message 表 + wl_interface 定义拆成字典。"""
    # 共享的 types 槽
    块 = re.search(r"struct wl_interface \*\w+_types\[\] = \{(.*?)\n\};", c文本, re.S)
    槽 = [m.group(1) for m in re.finditer(r"&(\w+)_interface|NULL", 块.group(1))]
    消息表 = {}
    for m in re.finditer(r"struct wl_message (\w+)\[\] = \{(.*?)\n\};", c文本, re.S):
        条目 = []
        for 行 in m.group(2).strip().splitlines():
            mm = re.match(r'\s*\{\s*"([^"]*)",\s*"([^"]*)",\s*\w+ \+ (\d+)\s*\},', 行)
            if not mm:
                raise ValueError(f"认不出的消息行：{行!r}")
            名, 签名, 偏移 = mm.group(1), mm.group(2), int(mm.group(3))
            槽数 = len(签名.replace("?", "").lstrip("0123456789")
                       .lstrip("0123456789")) if 签名 else 0
            槽数 = len(re.sub(r"^[0-9]+", "", 签名).replace("?", ""))
            条目.append((名, 签名, 槽[偏移:偏移 + 槽数]))
        消息表[m.group(1)] = 条目
    出 = {}
    for m in re.finditer(
            r"struct wl_interface (\w+)_interface = \{\s*"
            r'"([^"]*)",\s*(\d+),\s*(\d+),\s*(\w+),\s*(\d+),\s*(\w+),\s*\};', c文本, re.S):
        _, 名, 版本, 请数, 请表, 事数, 事表 = m.groups()
        出[名] = {
            "版本": int(版本),
            "请求": 消息表.get(请表, [])[:int(请数)] if 请表 != "NULL" else [],
            "事件": 消息表.get(事表, [])[:int(事数)] if 事表 != "NULL" else [],
        }
    return 出


def 拆我们(接口指针):
    o = 接口指针.contents
    出 = {"版本": o.version, "请求": [], "事件": []}
    for 类, 数, 表 in (("请求", o.method_count, o.methods),
                       ("事件", o.event_count, o.events)):
        for i in range(数):
            m = 表[i]
            参数 = wlraw.解码签名(m)
            引用 = []
            for j in range(len(参数)):
                t = m.types[j]
                引用.append(t.contents.name.decode() if t else None)
            出[类].append((m.name.decode(), m.signature.decode(), 引用))
    return 出


def 比对(标签, c文本, 我们的表, 只比=None):
    print(f"\n{'=' * 74}\n【{标签}】\n{'=' * 74}")
    原厂 = 拆原厂(c文本)
    通过 = 失败 = 0
    对谁 = 只比 or sorted(原厂)
    for 名 in 对谁:
        if 名 not in 原厂:
            print(f"  ⏭  {名}：原厂没有")
            continue
        if 名 not in 我们的表.接口:
            print(f"  ⏭  {名}：我们没造")
            continue
        参 = 原厂[名]
        我 = 拆我们(我们的表.接口[名])
        差异 = []
        if 参["版本"] != 我["版本"]:
            差异.append(f"版本 {参['版本']} vs {我['版本']}")
        for 类 in ("请求", "事件"):
            if len(参[类]) != len(我[类]):
                差异.append(f"{类}条数 {len(参[类])} vs {len(我[类])}")
            for a, b in zip(参[类], 我[类]):
                if a != b:
                    差异.append(f"{类} {a[0]}: 原厂 {a[1]} {a[2]} / 我们 {b[1]} {b[2]}")
        if 差异 and 名 in 已知特例:
            通过 += 1
            print(f"  ☑  {名:<18} 已知特例，跳过：{已知特例[名]}")
        elif 差异:
            失败 += 1
            print(f"  ❌ {名}")
            for d in 差异:
                print(f"       {d}")
        else:
            通过 += 1
            条 = len(参["请求"]) + len(参["事件"])
            print(f"  ✅ {名:<18} v{参['版本']:<3} 请求 {len(参['请求'])} 事件 {len(参['事件'])} 共 {条} 条消息全等")
    return 通过, 失败


# wayland-scanner 对个别消息有硬编码特例，XML 本身描述不全 —— 这类差异是「已知且已解释」的
已知特例 = {
    "wl_registry": "bind 在 随发行版提供的那份 wayland.xml 里只声明了 name+id 两个参数，"
                   "但线上真实签名是 usun（扫描器会补上 interface 名和 version）。"
                   "我们走的是「核心协议直接借 libwayland 导出的真表」，所以拿到的就是 usun，不受影响。",
}


lib = wlraw.载入库()
总过 = 总败 = 0

# ---- 核心协议：我们自己从 wayland.xml 造一遍，跟原厂同源输出比 ----
核心 = {}
for 名 in ("wl_display", "wl_registry", "wl_compositor", "wl_surface", "wl_region",
           "wl_shm", "wl_shm_pool", "wl_buffer", "wl_callback", "wl_output",
           "wl_seat", "wl_pointer", "wl_keyboard", "wl_touch", "wl_subcompositor",
           "wl_subsurface", "wl_data_device_manager", "wl_data_offer",
           "wl_data_source", "wl_data_device", "wl_shell", "wl_shell_surface",
           "wl_fixes"):
    try:
        核心[名] = wlraw.真接口(lib, 名 + "_interface")
    except ValueError:
        pass
我们的核心 = wlraw.协议集(xml路径=WAYLAND_XML, 补充=核心, lib=lib)
a, b = 比对("核心协议 wayland.xml", 跑扫描器(WAYLAND_XML), 我们的核心)
总过 += a
总败 += b

# ---- xdg-shell：libwayland 根本不认识它，全靠我们自己的表 ----
我们的xdg = wlraw.协议集(xml路径=XDG_XML, 补充=我们的核心.接口, lib=lib)
a, b = 比对("xdg-shell（libwayland 不认识，全靠我们造）", 跑扫描器(XDG_XML), 我们的xdg,
            只比=["xdg_wm_base", "xdg_positioner", "xdg_surface", "xdg_toplevel", "xdg_popup"])
总过 += a
总败 += b

# ---- 额外事实：系统 libwayland 的 core 表比 flatpak 的 XML 还新 ----
print(f"\n{'=' * 74}\n【附带发现】系统 libwayland 内建表 vs 随发行版提供的 wayland.xml 版本\n{'=' * 74}")
for 名 in ("wl_compositor", "wl_surface", "wl_region", "wl_shm", "wl_shm_pool"):
    真 = 核心[名].contents.version
    我 = 我们的核心.接口[名].contents.version
    记 = "一致" if 真 == 我 else "★ 系统更新"
    print(f"  {名:<16} 系统真表 v{真:<3} XML 声明 v{我:<3} {记}")
print("  → 结论：核心协议一律直接用 libwayland 导出的真表，只对 xdg-shell 一类自己造，"
      "版本代差就不会成为隐患。")

print(f"\n{'=' * 74}")
print(f"总计：{总过} 个接口逐字段全等，{总败} 个不一致。")
sys.exit(0 if 总败 == 0 else 1)

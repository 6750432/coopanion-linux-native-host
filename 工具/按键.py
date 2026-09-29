#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""桌面按键/点击小工具（ctypes 直接调 X11 + XTest，不依赖 xdotool）。

用法：
    python3 按键.py 点击 <x> <y>            在屏幕绝对坐标点一下左键
    python3 按键.py 右键 <x> <y>            点右键
    python3 按键.py 键 <键名> [次数]        按某个键，如 Next(PageDown)/Prior/Home/End/Return/Escape/F5
    python3 按键.py 打字 "文本"             逐字键入（只支持 ASCII 普通可见字符）
    python3 按键.py 组合 ctrl+f             组合键（+ 连接，如 ctrl+shift+t）

⚠️ 两个必须的坑（都踩过）：
  1) XWarpPointer 的 dest_w 传 0 会把坐标当成「相对当前位置的偏移」，
     必须传 XDefaultRootWindow 才是屏幕绝对坐标；
  2) 坐标以截图为准，wmctrl -lG 报的位置和真实客户区差几十像素。
"""
import ctypes
import sys
import time

X11 = ctypes.CDLL("libX11.so.6")
XTST = ctypes.CDLL("libXtst.so.6")
X11.XOpenDisplay.restype = ctypes.c_void_p
X11.XOpenDisplay.argtypes = [ctypes.c_char_p]
X11.XDefaultRootWindow.restype = ctypes.c_ulong
X11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
X11.XWarpPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                             ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                             ctypes.c_int, ctypes.c_int]
X11.XFlush.argtypes = [ctypes.c_void_p]
X11.XStringToKeysym.restype = ctypes.c_ulong
X11.XStringToKeysym.argtypes = [ctypes.c_char_p]
X11.XKeysymToKeycode.restype = ctypes.c_ubyte
X11.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
XTST.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]
XTST.XTestFakeKeyEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]

d = X11.XOpenDisplay(None)
if not d:
    sys.exit("  打不开 X display（DISPLAY / XAUTHORITY 设了吗）")
根 = X11.XDefaultRootWindow(d)


def 点(x: int, y: int, 键: int = 1) -> None:
    X11.XWarpPointer(d, 0, 根, 0, 0, 0, 0, int(x), int(y))   # 坑 1：必须给 root
    X11.XFlush(d)
    time.sleep(0.25)
    XTST.XTestFakeButtonEvent(d, 键, 1, 0)
    XTST.XTestFakeButtonEvent(d, 键, 0, 0)
    X11.XFlush(d)
    time.sleep(0.35)


def 按(键名: str, 次数: int = 1) -> None:
    码 = X11.XKeysymToKeycode(d, X11.XStringToKeysym(键名.encode()))
    if not 码:
        sys.exit(f"  不认识这个键名: {键名}")
    for _ in range(次数):
        XTST.XTestFakeKeyEvent(d, 码, 1, 0)
        XTST.XTestFakeKeyEvent(d, 码, 0, 0)
        X11.XFlush(d)
        time.sleep(0.12)


def 组合(串: str) -> None:
    键s = [k.strip() for k in 串.split("+")]
    码s = [X11.XKeysymToKeycode(d, X11.XStringToKeysym(k.encode())) for k in 键s]
    for 码 in 码s:
        XTST.XTestFakeKeyEvent(d, 码, 1, 0)
    X11.XFlush(d)
    time.sleep(0.06)
    for 码 in reversed(码s):
        XTST.XTestFakeKeyEvent(d, 码, 0, 0)
    X11.XFlush(d)
    time.sleep(0.35)


def 打字(文本: str) -> None:
    for ch in 文本:
        名 = {" ": "space", ".": "period", ",": "comma", "-": "minus", "_": "underscore",
              "/": "slash", ":": "colon", "?": "question"}.get(ch, ch)
        需要shift = ch.isupper()
        if 需要shift:
            按("Shift_L")
            time.sleep(0.03)
        按(名)
        if 需要shift:
            time.sleep(0.03)


if __name__ == "__main__":
    什么 = sys.argv[1]
    if 什么 == "点击":
        点(int(sys.argv[2]), int(sys.argv[3]))
    elif 什么 == "右键":
        点(int(sys.argv[2]), int(sys.argv[3]), 3)
    elif 什么 == "键":
        按(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 1)
    elif 什么 == "组合":
        组合(sys.argv[2])
    elif 什么 == "打字":
        打字(sys.argv[2])
    else:
        sys.exit(__doc__)
    print(f"  ✓ 完成: {' '.join(sys.argv[1:])}")

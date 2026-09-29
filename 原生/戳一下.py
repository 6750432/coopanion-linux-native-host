#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""戳一下 —— 把鼠标挪到指定坐标点一下（X11 XTest），用来试桌宠的反应。

用法：python3 戳一下.py <x> <y> [次数]
"""
import ctypes
import sys
import time

x11 = ctypes.CDLL("libX11.so.6")
xtst = ctypes.CDLL("libXtst.so.6")
x11.XOpenDisplay.restype = ctypes.c_void_p
x11.XDefaultRootWindow.restype = ctypes.c_ulong
x11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
dpy = x11.XOpenDisplay(None)
root = x11.XDefaultRootWindow(dpy)
x11.XWarpPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
                             ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
                             ctypes.c_int, ctypes.c_int]
xtst.XTestFakeButtonEvent.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_int, ctypes.c_ulong]

x, y = int(sys.argv[1]), int(sys.argv[2])
次 = int(sys.argv[3]) if len(sys.argv) > 3 else 1
for i in range(次):
    x11.XWarpPointer(dpy, 0, root, 0, 0, 0, 0, x, y)
    x11.XFlush(dpy)
    time.sleep(.15)
    xtst.XTestFakeButtonEvent(dpy, 1, 1, 0)
    x11.XFlush(dpy)
    time.sleep(.06)
    xtst.XTestFakeButtonEvent(dpy, 1, 0, 0)
    x11.XFlush(dpy)
    time.sleep(.4)
print(f"点完了 ({x},{y}) ×{次}")

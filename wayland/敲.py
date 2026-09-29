#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把真鼠标点击打进指定屏幕坐标（ctypes 调 libXtst）。

English: Inject real pointer clicks at absolute screen coordinates via XTest.
中文：用 ctypes 调 libXtst 的 XTestFakeButtonEvent / XWarpPointer 打真点击。
⚠️ 坑：XWarpPointer 的 dest_w 必须给 XDefaultRootWindow，传 0 会被当成「相对偏移」。
"""
import ctypes as C
import sys
import time

x, y = int(sys.argv[1]), int(sys.argv[2])
按 = sys.argv[3] if len(sys.argv) > 3 else "左"

X11 = C.CDLL("libX11.so.6")
Xtst = C.CDLL("libXtst.so.6")
X11.XOpenDisplay.restype = C.c_void_p
X11.XDefaultRootWindow.restype = C.c_ulong
X11.XDefaultRootWindow.argtypes = [C.c_void_p]
d = X11.XOpenDisplay(None)
if not d:
    raise SystemExit("打不开 X 显示")
root = X11.XDefaultRootWindow(C.c_void_p(d))

X11.XWarpPointer.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong,
                             C.c_int, C.c_int, C.c_uint, C.c_uint, C.c_int, C.c_int]
X11.XWarpPointer(C.c_void_p(d), 0, C.c_ulong(root), 0, 0, 0, 0, x, y)
X11.XFlush(C.c_void_p(d))
time.sleep(0.35)

键 = 1 if 按 == "左" else 3
Xtst.XTestFakeButtonEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
Xtst.XTestFakeButtonEvent(C.c_void_p(d), 键, 1, 0)
X11.XFlush(C.c_void_p(d))
time.sleep(0.12)
Xtst.XTestFakeButtonEvent(C.c_void_p(d), 键, 0, 0)
X11.XFlush(C.c_void_p(d))
print(f"已在 ({x},{y}) 打了一次{按}键")

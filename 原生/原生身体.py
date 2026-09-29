#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""原生身体 —— 不借 Chromium 的桌宠外壳（PySide6 + QPainter）。

跟 ~/coop-linux/外壳.py 的分工：
    外壳.py      = 原来的路线：QtWebEngine 装下作者的整页网页，靠 window.petHost 垫片驱动窗口。
    原生身体.py  = 现在的路线：网页那套 JS（pet-core 的身体 + whale 的 figure）已经用 Python
                   重写（身体.py / 小鱼.py / 脸.py / 网格.py），窗口只用 QPainter 画，**没有
                   Chromium 那 380 MB 的地板**。

窗口手法照旧：全屏、透明、置顶、不进任务栏、不抢焦点；用 XShape 把「看得见的区域」和
「能点的区域」都收成她那一小块，剩下的地方鼠标随便穿过去，也不会让合成器白算一整屏。
"""
from __future__ import annotations

import ctypes
import math
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from PySide6.QtCore import QPoint, QRect, Qt, QTimer                              # noqa: E402
from PySide6.QtGui import QGuiApplication, QCursor, QPainter, QRegion             # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget                               # noqa: E402

import 面板
from 泡泡 import 气泡窗
from 接线 import 电台, 台词
from 合成 import 合成器, 取计时                                                            # noqa: E402
from 身体 import 身体                                                              # noqa: E402
from 模型 import 鲸鱼模型                                                          # noqa: E402
from 小鱼 import 小鱼                                                              # noqa: E402
from 网格 import 网格渲染器                                                        # noqa: E402

# 资源目录：本机开发时用仓库里那份；打包成 AppImage 时由 AppRun 用 COOP_ASSETS 指到包内
_资源 = os.environ.get("COOP_ASSETS")
网页目录 = Path(_资源) if _资源 else (Path.home() / "coop-linux/app/packages/cortico-world-desktop-pet/web")
帧率 = int(os.environ.get("COOP_FPS", "24"))          # 忙的时候（走、跳、被拎、说话）
闲帧率 = int(os.environ.get("COOP_FPS_IDLE", "12"))   # 闲着的时候（站着、坐着、睡）
缩放 = float(os.environ.get("COOP_SCALE", "0.62"))
格步 = int(os.environ.get("COOP_GRID", "2"))
日志 = Path(os.environ.get("COOP_LOG") or (Path.home() / "coop-linux/原生/logs"))
日志.mkdir(parents=True, exist_ok=True)


def 记(*a):
    行 = " ".join(str(x) for x in a)
    print(行, flush=True)
    try:
        with open(日志 / "原生.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%H:%M:%S')} {行}\n")
    except Exception:
        pass


# ── X11 小工具（照抄外壳.py，够用就行）─────────────────────────
class X光标本:
    """Minimal ctypes holder for the libX11 / libXext handles.
    
    libX11 / libXext 的 ctypes 句柄薄封装。库不在时 `ok=False`，调用方必须自行判断，别直接用它调 X 函数。
    """
    def __init__(self) -> None:
        self.ok = False
        try:
            self.x = ctypes.CDLL("libX11.so.6")
            self.x.XOpenDisplay.restype = ctypes.c_void_p
            self.x.XDefaultRootWindow.restype = ctypes.c_ulong
            self.x.XDefaultRootWindow.argtypes = [ctypes.c_void_p]
            self.dpy = self.x.XOpenDisplay(None)
            self.root = self.x.XDefaultRootWindow(self.dpy)
            self.ok = bool(self.dpy)
        except Exception as exc:
            记("X 打不开，光标功能关闭:", exc)

    def 取(self):
        if not self.ok:
            return None
        px, py = ctypes.c_int(), ctypes.c_int()
        wx, wy = ctypes.c_int(), ctypes.c_int()
        m = ctypes.c_uint()
        xr = ctypes.c_ulong()
        r = self.x.XQueryPointer(self.dpy, self.root, ctypes.byref(xr), ctypes.byref(xr),
                                 ctypes.byref(px), ctypes.byref(py),
                                 ctypes.byref(wx), ctypes.byref(wy), ctypes.byref(m))
        return (px.value, py.value) if r else None


class X矩形(ctypes.Structure):
    """The plain XRectangle struct that XShapeCombineRectangles expects.
    
    XShape 要的矩形结构（XRectangle）。
    """
    _fields_ = [("x", ctypes.c_short), ("y", ctypes.c_short),
                ("width", ctypes.c_ushort), ("height", ctypes.c_ushort)]


def _开Xext():
    try:
        库 = ctypes.CDLL("libXext.so.6")
        库.XShapeCombineRectangles.restype = None
        库.XShapeCombineRectangles.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_int,
                                               ctypes.c_int, ctypes.c_int, ctypes.POINTER(X矩形),
                                               ctypes.c_int, ctypes.c_int, ctypes.c_int]
        return 库
    except Exception as exc:
        记("libXext 打不开，形状区功能关闭:", exc)
        return None


XEXT = _开Xext()
形_外框 = 0      # ShapeBounding：看得见的区域
形_输入 = 2      # ShapeInput：能点的区域
形_设 = 0        # ShapeSet
形_并 = 1        # ShapeUnion


class 原生桌宠:
    """The application object: owns the QApplication, model, renderer, body and window, and wires their lifetimes together.
    
    应用主体：持有 QApplication、模型、渲染器、身体和窗口，并把它们的生命周期、每帧的调用顺序串在一起。
    """
    def __init__(self):
        self.app = QApplication(sys.argv)
        self.app.setQuitOnLastWindowClosed(True)
        self.模型 = 鲸鱼模型(网页目录)
        self.网格 = 网格渲染器(self.模型, max(.2, 缩放 * 1.25), 格步)
        self.鱼 = 小鱼(self.模型, self.网格)
        self.屏幕 = QGuiApplication.primaryScreen().availableGeometry()
        self.身体 = 身体(锚点=self.鱼.锚点,
                         边界=lambda: (self.屏幕.width(), self.屏幕.height(),
                                       self.屏幕.height() - 2, 缩放),
                         漫游="calm", 进场="drop",
                         事件=self._身体事件)
        self.身体.S = 缩放
        self.身体.调整尺寸()
        self.合成 = 合成器(self.模型, self.身体, self.鱼, self.网格)
        self.指针 = X光标本()
        self.窗口 = 桌宠窗口(self)
        self.气泡 = 气泡窗(self.鱼.强调色)
        self.台词 = 台词(self.身体, self.气泡)
        self.电台 = 电台(self)
        self.待问 = None
        self.父pid = 0
        self.演示模式 = False
        self.演示 = None
        self.HUD = None
        self.CPU表 = 面板.CPU表()
        self.画帧累计 = 0
        self.偏好 = {"roam": "calm", "scale": 1.0, "user": "伙伴", "theme": "dark"}
        self.上次矩形: QRect | None = None
        self.上次光标: str | None = None
        self.上次时间 = time.perf_counter()
        self.帧数 = 0
        self.累计ms = 0.0
        self.画次数 = 0
        self.画累计ms = 0.0
        self.上次报 = time.perf_counter()
        self.上次画 = 0.0
        self.计时器 = QTimer()
        self.计时器.setTimerType(Qt.TimerType.PreciseTimer)
        self.计时器.timeout.connect(self._打点)
        # 打点只管「光标 + 统计」，125~250 Hz；出画交给下面那个单发定时器（节奏准）
        滴答 = max(4, min(8, 1000 // max(1, 帧率), 1000 // max(1, 闲帧率)))
        self.计时器.start(滴答)
        self.画定时器 = QTimer()
        self.画定时器.setSingleShot(True)
        self.画定时器.setTimerType(Qt.TimerType.PreciseTimer)
        self.画定时器.timeout.connect(self._跳)
        self.画定时器.start(1)
        记(f"打点 {1000//滴答} Hz；目标 忙 {帧率} fps / 闲 {闲帧率} fps")
        记(f"原生身体起来了：窗口 {self.屏幕.width()}×{self.屏幕.height()} 缩放 {缩放} 帧率 {帧率} 格步 {格步}"
           f" 画布 {self.网格.宽}×{self.网格.高}")
        if os.environ.get("COOP_SELFCHECK"):
            self._自检()
        # 核心（World）按 CORTICO_DESKTOP_PET_HOST 拉起本宿主，并给一个 --pet-url
        秒后退出 = 0.0
        for a in sys.argv[1:]:
            if a.startswith("--pet-url="):
                self.电台.接(a.split("=", 1)[1])
            elif a.startswith("--parent-pid="):
                try:
                    self.父pid = int(a.split("=", 1)[1])
                except ValueError:
                    pass
            elif a.startswith("--秒="):
                秒后退出 = float(a.split("=", 1)[1])
            elif a == "--说明":
                print(说明文本())
                raise SystemExit(0)
        # 没有 --pet-url：说明没人把本宿主当宠物窗口用 → 进「演示模式」，
        # 自己带剧本演一段，并在左上角挂个牌子实时显示内存/帧率/CPU（黑盒交付用）。
        if not self.电台.地址:
            self.演示模式 = True
            self.HUD = 面板.HUD(self)
            self.HUD.show()
            self.演示 = 面板.演示核心(self)
            # ⚠️ 定时器必须留引用，否则被 GC 掉、牌子就永远停在「…」（这个坑今天踩过一次）
            self.HUD定时 = QTimer()
            self.HUD定时.timeout.connect(self.HUD.每秒刷新)
            self.HUD定时.start(1000)
            if 秒后退出 > 0:
                QTimer.singleShot(int(秒后退出 * 1000), self.app.quit)
            记("演示模式：自带剧本（没给 --pet-url）")

    def _自检(self):
        """开窗前先跑几轮渲染，量一下这个进程里网格到底多贵（排查「脚本里快、程序里慢」用）。"""
        脸 = {"eyes": [{"shape": "ring"}, {"shape": "ring"}], "gap": [50, 50]}
        帧 = {"t": 0.0, "face": "neutral", "mode": "idle", "look": [1, 0],
              "legs": [[104, 212, 104, 241], [150, 212, 150, 241]], "low": 0, "blink": 0,
              "eyeClose": 0, "swing": 6, "sit": 0, "facing": 1, "tilt": 3, "lean": 0}
        st = self.鱼.画(脸, 帧)
        self.网格.出图(st)
        t0 = time.thread_time()
        for i in range(8):
            帧2 = dict(帧); 帧2["t"] = i / 24; 帧2["look"] = [1 + (i % 3), 0]
            st = self.鱼.画(脸, 帧2)
            self.网格.出图(st)
        记(f"自检：开窗前网格 {(time.thread_time()-t0)/8*1000:.1f} ms/帧")

    def 记一笔画(self, 毫秒: float):
        self.画次数 += 1
        self.画累计ms += 毫秒

    def _看爸爸(self):
        """核心没了就把自己也收掉（不然窗口会孤零零挂着）。"""
        if self.父pid and not Path(f"/proc/{self.父pid}").exists():
            记("核心进程没了，原生身体跟着退出")
            self.app.quit()

    def _报表(self):
        """每 5 秒写一行：帧、每帧耗时、重绘次数与耗时（调性能用）。"""
        now = time.perf_counter()
        间隔 = now - self.上次报
        if 间隔 < 5 or not self.帧数:
            return
        细 = "｜".join(f"{k} {v[0]:.1f}×{v[1]}" for k, v in 取计时().items())
        记(f"统计：{间隔:.0f}s 内 {self.帧数} 帧（{self.帧数/间隔:.1f} fps）"
           f"｜每帧 {self.累计ms/max(1,self.帧数):.1f} ms"
           f"｜重绘 {self.画次数} 次，每次 {self.画累计ms/max(1,self.画次数):.1f} ms"
           + (f"｜{细}" if 细 else ""))
        self.上次报 = now
        self.帧数 = 0
        self.累计ms = 0.0
        self.画次数 = 0
        self.画累计ms = 0.0

    # ── 身体回调 ───────────────────────────────────────────
    def 记(self, *a):
        """给接线/泡泡用的日志口（它们只拿到「宠」这个对象）。"""
        记(*a)

    def _身体事件(self, kind: str, d=None):
        # 身体比电台先造出来（造身体时就要设一次模式），所以这里得防一手
        if kind == "touch":
            记(f"她被碰了：{(d or {}).get('kind')}")
        台 = getattr(self, "电台", None)
        if 台 is not None:
            台.发({"t": kind, **(d or {})})

    # ── 核心来的东西 ───────────────────────────────────────
    def 收到快照(self, m: dict):
        """init：核心把当前状态一股脑发过来（偏好、皮肤、机器人信息…）。"""
        p = {k: v for k, v in m.items() if k in ("roam", "scale", "user", "theme", "sound", "mic")}
        if p:
            self.收到偏好(p)
        skin = m.get("skin") or {}
        形象 = skin.get("figure") if isinstance(skin, dict) else None
        if 形象 and 形象 != "whale":
            self.记(f"核心说形象是 {形象}，原生身体只画鲸鱼，先照旧")

    def 收到偏好(self, p: dict):
        self.偏好.update(p)
        if isinstance(p.get("roam"), str):
            self.身体.漫游 = p["roam"]

    def 收到提问(self, m: dict):
        """ask / confirm / dialog：摆进气泡，用户点哪个就回哪个。"""
        self.待问 = dict(m)
        问 = m.get("question") or m.get("title") or ""
        选 = list(m.get("options") or [])
        if 选:
            import functools
            self.气泡.设(问 or "（请选一个）", 9999, "say")
            self.气泡.设选项(选, functools.partial(self._答问, m))
        else:
            self.气泡.设(问, 9999, "say")

    def _答问(self, m: dict, i: int):
        选 = list(m.get("options") or [])
        if m.get("t") == "confirm":
            self.电台.发({"t": "confirmed", "id": m.get("id"), "index": i})
        else:
            self.电台.发({"t": "answer", "askId": m.get("id"), "index": i,
                        "label": 选[i] if i < len(选) else ""})
        self.身体.设表情("happy")
        self.待问 = None

    def 收到对话更新(self, m: dict):
        if m.get("text"):
            self.气泡.设(str(m["text"]), 9999, "say")

    def _忙不忙(self) -> bool:
        """她现在算不算「忙」——忙用满帧率，闲用闲帧率。

        注意：**睡觉时冒的 z 不算「忙」** —— 它每 1.3 秒冒一个、飘 2.4 秒，等于永远有粒子，
        一开始就是这么写的，结果她睡着反而最费 CPU（实测 58%，比醒着还高）。z 飘得慢，
        12 fps 完全够看。
        """
        p = self.身体.宠物
        忙粒子 = any(q["type"] != "z" for q in self.身体.粒子)
        return (p["mode"] not in ("idle", "sit", "sleep", "look", "wake", "land")
                or 忙粒子 or p["talkK"] > .02 or p["listening"] or p["thinking"]
                or self.身体.按下 is not None)

    # ── 每帧 ───────────────────────────────────────────────
    def _打点(self):
        """高频小定时器：只做「问光标位置 + 看看核心还在不在 + 写统计」，不负责出画。"""
        xy = self.指针.取()
        if xy:
            x, y = xy[0] - self.屏幕.x(), xy[1] - self.屏幕.y()
            光标 = self.身体.指针移动(x, y)
            if 光标 != self.上次光标:
                self.上次光标 = 光标
                self.窗口.setCursor(Qt.CursorShape.OpenHandCursor if 光标 == "grab"
                                    else Qt.CursorShape.ClosedHandCursor if 光标 == "grabbing"
                                    else Qt.CursorShape.ArrowCursor)
        self._报表()
        self._看爸爸()

    def _跳(self):
        """出画这一帧；画完自己再排下一次（单发定时器，节奏准，不受打点粒度限制）。

        一开始是把「打点」和「出画」合在一个定时器里，结果打点粒度（8 毫秒）会把帧周期
        向上取整：目标 60 fps 实际只能到 41.7 fps（16.7 毫秒被抬到 24 毫秒）。拆开之后
        帧周期按「上一帧开始 + 目标间隔」算，误差不再累积。
        """
        now = time.perf_counter()
        dt = min(.1, max(.001, now - self.上次时间))
        self.上次时间 = now
        t0 = time.perf_counter()
        self.身体.步(dt)
        self.台词.步(dt)
        if self.演示 is not None:
            self.演示.步(dt)
        脸, 帧 = self.身体.出帧()
        状态 = self.鱼.画(脸, 帧)
        self.窗口.放帧(状态, 帧, 脸)
        if self.待问 is None:
            ax, ay = self.身体.气泡锚点()
            self.气泡.摆(ax, ay, self.屏幕)
        self.帧数 += 1
        self.画帧累计 += 1
        self.累计ms += (time.perf_counter() - t0) * 1000
        # 排下一帧：按「这一帧的开始 + 目标间隔」算，晚了就立刻画（不累积漂移）
        间隔 = 1.0 / (帧率 if self._忙不忙() else 闲帧率)
        下次 = self.上次画 + 间隔
        剩 = 下次 - time.perf_counter()
        if 剩 < 0:
            剩 = 0.0
            self.上次画 = time.perf_counter()
        else:
            self.上次画 = 下次
        self.画定时器.start(max(1, int(剩 * 1000)))

    def 跑(self):
        return self.app.exec()

    def 报(self):
        if self.帧数:
            记(f"跑了 {self.帧数} 帧，平均每帧 {self.累计ms / self.帧数:.1f} ms（{帧率} fps 上限）")


class 桌宠窗口(QWidget):
    """The small window she actually lives in (not a full-screen surface).
    
    装她的小窗口（不是全屏）。

    全屏透明窗口的办法（网页那套）实测每次重绘要 20~32 ms：Qt 得把整屏 ARGB 后备缓冲
    跟合成器来回倒。换成一块 360×360 的小窗口、她走到边上才挪一下窗口，重绘就只剩几个
    毫秒；顺便因为窗口本来就小，连「看得见的区域」都不用 XShape 了，只需把「能点的区域」
    收成她身上那一圈。
    """

    边长 = 360          # 窗口边长（像素）
    边距 = 56           # 她离窗口边这么近就重新摆窗口

    def __init__(self, host: 原生桌宠):
        super().__init__(None)
        self.host = host
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                            Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus |
                            Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setMouseTracking(True)
        self.setFixedSize(self.边长, self.边长)
        self.帧: tuple | None = None
        self.旧矩形 = QRect()
        self.形状输入 = QRect()
        self.窗口矩形 = QRect(0, 0, self.边长, self.边长)
        self._可施形状 = False
        方 = host.屏幕
        self.move(int(方.center().x() - self.边长 / 2), int(方.bottom() - self.边长 - 40))

    # ── 坐标 ───────────────────────────────────────────────
    def 到窗口(self, 人: QRect) -> QRect:
        return 人.translated(-self.x(), -self.y())

    def _人物矩形(self) -> QRect:
        p = self.host.身体.宠物
        if not p.get("xf"):
            return QRect(0, 0, 1, 1)
        视 = self.host.网格.视口
        角 = [self.host.身体.到舞台(x, y) for (x, y) in
              ((视[0], 视[1]), (视[2], 视[1]), (视[2], 视[3]), (视[0], 视[3]))]
        x0 = min(c[0] for c in 角); x1 = max(c[0] for c in 角)
        y0 = min(c[1] for c in 角); y1 = max(c[1] for c in 角)
        return QRect(int(x0) - 6, int(y0) - 6, int(x1 - x0) + 12, int(y1 - y0) + 12)

    def _身体矩形(self) -> QRect:
        cx, cy = self.host.身体.到舞台(128, 128)
        r = int(108 * self.host.身体.S) + 6
        return QRect(int(cx - r), int(cy - r), 2 * r, 2 * r)

    # ── 形状区（只收「能点的区域」）────────────────────────
    def _施形状(self):
        if XEXT is None or not self.host.指针.ok:
            return
        身 = self.到窗口(self._身体矩形())
        self.形状输入 = 身
        win = int(self.winId())
        r = (X矩形 * 1)(X矩形(身.x(), 身.y(), 身.width(), 身.height()))
        XEXT.XShapeCombineRectangles(self.host.指针.dpy, win, 形_输入, 0, 0, r, 1, 形_设, 0)

    def _摆窗口(self, 人: QRect):
        """她快走出窗口了就重新摆一下窗口（走动时一秒几次，站着时一次都不动）。"""
        窗 = self.窗口矩形
        if (人.left() >= 窗.left() + self.边距 and 人.right() <= 窗.right() - self.边距
                and 人.top() >= 窗.top() + self.边距 and 人.bottom() <= 窗.bottom() - self.边距):
            return
        新x = int(人.center().x() - self.边长 / 2)
        新y = int(人.center().y() - self.边长 / 2)
        方 = self.host.屏幕
        新x = max(方.left(), min(方.right() - self.边长, 新x))
        新y = max(方.top(), min(方.bottom() - self.边长, 新y))
        self.move(新x, 新y)
        self.窗口矩形 = QRect(新x, 新y, self.边长, self.边长)
        self.旧矩形 = QRect(0, 0, self.边长, self.边长)
        self.update()

    # ── 帧 ────────────────────────────────────────────────
    def 放帧(self, 状态: dict, 帧: dict, 脸: dict):
        self.帧 = (状态, 帧, 脸)
        人 = self._人物矩形()
        self._摆窗口(人)
        脏 = self.到窗口(人)
        脏 = 脏 if self.旧矩形.isNull() else 脏.united(self.旧矩形)
        self.旧矩形 = self.到窗口(人)
        self.update(脏)
        if not self._可施形状:
            self._可施形状 = True
            self._施形状()
        elif not self.形状输入.contains(self._身体矩形()):
            self._施形状()

    def paintEvent(self, ev):
        if not self.帧:
            return
        状态, 帧, 脸 = self.帧
        t0 = time.thread_time()
        笔 = QPainter(self)
        try:
            笔.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            笔.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            笔.fillRect(ev.rect(), Qt.GlobalColor.transparent)
            笔.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
            笔.translate(-self.x(), -self.y())      # 合成代码用的是屏幕坐标
            self.host.合成.画(笔, self.host.屏幕.width(), self.host.屏幕.height(), 状态, 帧, 脸)
        finally:
            笔.end()
            self.host.记一笔画((time.thread_time() - t0) * 1000)

    # ── 鼠标 ──────────────────────────────────────────────
    def mousePressEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            if self.host.身体.指针按下(ev.position().x() + self.x(), ev.position().y() + self.y()):
                ev.accept()

    def mouseMoveEvent(self, ev):
        self.host.身体.指针移动(ev.position().x() + self.x(), ev.position().y() + self.y())

    def mouseReleaseEvent(self, ev):
        if ev.button() == Qt.MouseButton.LeftButton:
            self.host.身体.指针松开()

    def showEvent(self, ev):
        super().showEvent(ev)
        self._可施形状 = False
        self.窗口矩形 = QRect(self.x(), self.y(), self.边长, self.边长)




def 说明文本() -> str:
    随包 = Path(__file__).resolve().parent / "README-quickstart.txt"
    if 随包.exists():
        return 随包.read_text(encoding="utf-8")
    return ("Coopanion Native Host\n"
            "  直接运行：桌面上出现她 + 左上角牌子显示 内存/帧率/CPU（演示模式）\n"
            "  接自己的核心：CORTICO_DESKTOP_PET_HOST='[\"<本文件路径>\"]' 启动 Coopanion\n")


def main() -> int:
    宠 = 原生桌宠()
    宠.窗口.show()
    import signal
    signal.signal(signal.SIGTERM, lambda *_: 宠.app.quit())
    signal.signal(signal.SIGINT, lambda *_: 宠.app.quit())
    try:
        return 宠.跑()
    finally:
        宠.报()


if __name__ == "__main__":
    sys.exit(main())

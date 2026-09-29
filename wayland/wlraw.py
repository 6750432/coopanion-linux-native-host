#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""纯 ctypes 的 Wayland 客户端底层库。

English: A raw Wayland client layer written purely with ctypes. It needs neither
gcc, wayland-scanner nor PyWayland, and it can turn any wayland-protocols XML
into live `wl_interface` tables at runtime.

中文：直接调 libwayland-client 的底层封装。不需要 gcc、wayland-scanner 或
pywayland —— 任何 wayland-protocols 的 XML 都能在运行时变成真的 wl_interface
表，交给 libwayland 自己用。这条路线和项目里既有的「ctypes 裸调 libX11」是一个思路。
"""

import ctypes as C
import os
import shutil
import xml.etree.ElementTree as ET
from ctypes import (
    CFUNCTYPE,
    POINTER,
    byref,
    c_char_p,
    c_int,
    c_int32,
    c_size_t,
    c_uint32,
    c_void_p,
    cast,
    pointer,
)

# ---------------------------------------------------------------- 核心结构体

class WlMessage(C.Structure):
    """English: One protocol message. / 中文：一条协议消息。"""


class WlInterface(C.Structure):
    """English: A protocol interface table. / 中文：一份协议接口表。"""


WlMessage._fields_ = [
    ("name", c_char_p),
    ("signature", c_char_p),
    ("types", POINTER(POINTER(WlInterface))),
]
WlInterface._fields_ = [
    ("name", c_char_p),
    ("version", c_int),
    ("method_count", c_int),
    ("methods", POINTER(WlMessage)),
    ("event_count", c_int),
    ("events", POINTER(WlMessage)),
]

# XML 里的类型名 -> 签名里的单字符
类型字符 = {
    "int": "i", "uint": "u", "fixed": "f", "string": "s",
    "object": "o", "new_id": "n", "array": "a", "fd": "h",
}
# 签名单字符 -> 回调函数该用什么 ctypes 类型接
回参类型 = {
    "i": c_int32, "u": c_uint32, "f": c_int32, "h": c_int32,
    "s": c_char_p, "o": c_void_p, "n": c_void_p, "a": c_void_p,
}


def 载入库(路径="libwayland-client.so.0"):
    """English: Load libwayland-client and pin every prototype.
    中文：载入 libwayland-client 并固定好每个函数的原型。"""
    lib = C.CDLL(路径)
    lib.wl_display_connect.restype = c_void_p
    lib.wl_display_connect.argtypes = [c_char_p]
    lib.wl_display_disconnect.argtypes = [c_void_p]
    lib.wl_display_get_fd.restype = c_int
    lib.wl_display_get_fd.argtypes = [c_void_p]
    lib.wl_display_roundtrip.restype = c_int
    lib.wl_display_roundtrip.argtypes = [c_void_p]
    lib.wl_display_dispatch.restype = c_int
    lib.wl_display_dispatch.argtypes = [c_void_p]
    lib.wl_display_dispatch_pending.restype = c_int
    lib.wl_display_dispatch_pending.argtypes = [c_void_p]
    lib.wl_display_flush.restype = c_int
    lib.wl_display_flush.argtypes = [c_void_p]
    lib.wl_display_prepare_read.restype = c_int
    lib.wl_display_prepare_read.argtypes = [c_void_p]
    lib.wl_display_read_events.restype = c_int
    lib.wl_display_read_events.argtypes = [c_void_p]
    lib.wl_display_cancel_read.argtypes = [c_void_p]
    # 变参函数：只固定前 5 个，后面按签名自己塞（这就是「底层」的全部秘密）
    lib.wl_proxy_marshal_flags.restype = c_void_p
    lib.wl_proxy_marshal_flags.argtypes = [
        c_void_p, c_uint32, POINTER(WlInterface), c_uint32, c_uint32,
    ]
    lib.wl_proxy_get_version.restype = c_uint32
    lib.wl_proxy_get_version.argtypes = [c_void_p]
    lib.wl_proxy_destroy.argtypes = [c_void_p]
    lib.wl_proxy_add_listener.restype = c_int
    lib.wl_proxy_add_listener.argtypes = [c_void_p, POINTER(c_void_p), c_void_p]
    return lib


def 真接口(lib, 符号名):
    """English: Borrow an interface table that libwayland-client already exports.
    中文：借用 libwayland-client 自己导出的接口表（wl_surface 之类的标准件）。"""
    return cast(pointer(WlInterface.in_dll(lib, 符号名)), POINTER(WlInterface))


# ------------------------------------------------------- XML -> 活接口表

class 协议集:
    """English: Turn a wayland-protocols XML into live `wl_interface` tables.
    中文：把一份 wayland-protocols XML 变成能被 libwayland 直接使用的活接口表。
    核心结论：wl_interface 就是三个数字加两张表，纯 ctypes 造得出来，不用编译器。"""

    def __init__(self, xml路径=None, xml文本=None, 补充=None, lib=None):
        self.接口 = {}      # 接口名 -> POINTER(WlInterface)
        self._活口 = []     # 防 GC：所有 ctypes 数组都挂在这里
        if 补充:
            self.接口.update(补充)
        if xml路径:
            根 = ET.parse(xml路径).getroot()
        elif xml文本:
            根 = ET.fromstring(xml文本)
        else:
            return
        声明 = 根.findall("interface")
        # 第一遍：先把所有接口对象建出来（消息表里会互相引用）
        for 节点 in 声明:
            o = WlInterface()
            o.name = 节点.get("name").encode()
            o.version = int(节点.get("version"))
            o.method_count = 0
            o.methods = POINTER(WlMessage)()
            o.event_count = 0
            o.events = POINTER(WlMessage)()
            self._活口.append(o)
            self.接口[节点.get("name")] = pointer(o)
        # 第二遍：建消息表
        for 节点 in 声明:
            o = self.接口[节点.get("name")].contents
            o.methods, o.method_count = self._建表(节点.findall("request"))
            o.events, o.event_count = self._建表(节点.findall("event"))

    def _建表(self, 节点表):
        n = len(节点表)
        if n == 0:
            return POINTER(WlMessage)(), 0
        数组 = (WlMessage * n)()
        for i, 节点 in enumerate(节点表):
            # types 数组是「按参数位置对齐」的，非对象参数留空
            参数 = 节点.findall("arg")
            # 槽位是按「参数个数」开的（一个方法最多 8 个参数），不是按方法数
            槽位 = (POINTER(WlInterface) * max(len(参数), 1))()
            签名 = ""
            for j, a in enumerate(参数):
                t = 类型字符[a.get("type")]
                # 可空参数，签名里要加 '?'（wayland-scanner 的规矩）。
                # 注意：不只是 object —— string 也可以是可空的（如 wl_data_offer.accept 的 u?s）。
                # '?' 只占签名位、不占 types 槽位。
                if a.get("allow-null") == "true":
                    签名 += "?"
                签名 += t
                if t in ("o", "n") and a.get("interface"):
                    槽位[j] = self.接口[a.get("interface")]
            since = int(节点.get("since", "1"))
            # wayland-scanner 的规矩：since>1 时签名最前面加版本数字
            数组[i].name = 节点.get("name").encode()
            数组[i].signature = ((str(since) if since > 1 else "") + 签名).encode()
            数组[i].types = cast(槽位, POINTER(POINTER(WlInterface)))
            self._活口.append(槽位)
        self._活口.append(数组)
        return 数组, n

    def 查(self, 接口名, 名字, 是事件=False):
        """按名字取 opcode —— 不靠硬编码数字，协议改了也不会错位。"""
        o = self.接口[接口名].contents
        表 = o.events if 是事件 else o.methods
        数 = o.event_count if 是事件 else o.method_count
        for i in range(数):
            if 表[i].name.decode() == 名字:
                return i, 表[i]
        raise KeyError(f"{接口名} 里没有 {'事件' if 是事件 else '请求'} {名字!r}")


# ------------------------------------------------------------- 代理对象

def 解码签名(msg):
    """English: Signature -> the plain per-argument type characters.
    中文：把签名还原成「每个参数一个字符」。要去掉两种前缀：since 版本数字（如 4iiii 的 4）
    和可空标记 '?'（如 ?oii 的 ?）—— 它们都只占签名位、不占参数位。"""
    s = msg.signature.decode()
    while s and s[0].isdigit():
        s = s[1:]
    return s.replace("?", "")


class 代理:
    """English: A thin callable wrapper around one wl_proxy.
    中文：一个 wl_proxy 的薄封装，方法名直接当属性用（如 面.set_input_region(...)）。"""

    __slots__ = ("连", "p", "iface")

    def __init__(self, 连接, p, iface):
        object.__setattr__(self, "连", 连接)
        object.__setattr__(self, "p", p)
        object.__setattr__(self, "iface", iface)

    def __repr__(self):
        return f"<代理 {self.iface.contents.name.decode()} @{self.p:#x}>"

    def __getattr__(self, 名字):
        if 名字.startswith("_"):
            raise AttributeError(名字)
        序, 消息 = self.连.协议.查(self.iface.contents.name.decode(), 名字)
        签名 = 解码签名(消息)

        def 呼叫(*实参):
            # new_id 参数可以不写，自动补 None（libwayland 自己分配 id）
            空位 = [i for i, c in enumerate(签名) if c == "n"]
            if len(实参) == len(签名) - len(空位):
                实参 = list(实参)
                for i in 空位:
                    实参.insert(i, None)
                if len(实参) != len(签名):
                    raise TypeError(名字)  # 理论到不了，纯防御
            if len(实参) != len(签名):
                raise TypeError(f"{名字} 要 {len(签名)} 个参数（其中 {len(空位)} 个 new_id 可省略），"
                                f"给了 {len(实参)}")
            转好 = []
            for 字符, 值 in zip(签名, 实参):
                if 字符 in ("i", "f", "h"):
                    转好.append(值 if isinstance(值, C._SimpleCData) else c_int32(int(值)))
                elif 字符 == "u":
                    转好.append(值 if isinstance(值, C._SimpleCData) else c_uint32(int(值)))
                elif 字符 == "s":
                    转好.append(值 if isinstance(值, C._SimpleCData)
                                else (None if 值 is None else c_char_p(值 if isinstance(值, bytes) else str(值).encode())))
                else:  # o / n
                    if isinstance(值, C._SimpleCData):
                        转好.append(值)
                    elif 值 is None:
                        转好.append(None)
                    elif isinstance(值, 代理):
                        转好.append(c_void_p(值.p))
                    else:
                        转好.append(c_void_p(值))
            # 构造器：第 3 参给它要造出来的接口，第 4 参给它要的版本
            新接口, 新版本 = None, None
            for j, 字符 in enumerate(签名):
                if 字符 == "n":
                    槽 = 消息.types[j]
                    if 槽:
                        新接口 = 槽.contents
                        新版本 = int(实参[j]) if isinstance(实参[j], int) and 实参[j] else 1
                    break
            # 非构造器：版本要用这个代理自己的版本，不能拍脑袋给 1
            给版本 = 新版本 if 新接口 is not None else int(self.连.lib.wl_proxy_get_version(self.p))
            返回 = self.连.lib.wl_proxy_marshal_flags(
                self.p, 序, 新接口 and pointer(新接口), 给版本, 0, *转好
            )
            if 新接口 is not None:
                return 代理(self.连, 返回, pointer(新接口))
            return None

        return 呼叫


# --------------------------------------------------------------- 连接

class 连接:
    """English: One Wayland connection with registry, binding and event dispatch.
    中文：一条 Wayland 连接：注册表枚举、绑定全局、事件分发。"""

    def __init__(self, 名字=None, lib=None, 协议=None):
        self.lib = lib or 载入库()
        self.协议 = 协议 or self._默认协议()
        self.名字 = 名字 or os.environ.get("WAYLAND_DISPLAY", "wayland-0")
        self.d = self.lib.wl_display_connect(self.名字.encode())
        if not self.d:
            raise RuntimeError(f"连不上 Wayland 显示 {self.名字!r}")
        self._回调库存 = []
        self.全局 = []          # [(名字, 接口名, 版本)]
        self._注册表 = None
        self.取注册表()

    # -- 标准接口表直接借用 libwayland 导出的，只有 xdg-shell 需要自己造
    def _默认协议(self):
        # 延迟到连上以后由 装扩展 填充；这里先只放核心
        核心 = {}
        for 名 in ("wl_display", "wl_registry", "wl_compositor", "wl_surface",
                   "wl_region", "wl_shm", "wl_shm_pool", "wl_buffer", "wl_callback",
                   "wl_output", "wl_seat", "wl_pointer", "wl_keyboard", "wl_touch",
                   "wl_subcompositor", "wl_subsurface"):
            try:
                核心[名] = 真接口(self.lib, 名 + "_interface")
            except ValueError:
                pass
        return 协议集(补充=核心, lib=self.lib)

    def 装扩展(self, xml路径=None, xml文本=None, 补充=None):
        """把额外协议的 XML 挂进来（xdg-shell、layer-shell 之类）。"""
        更多 = dict(补充 or {})
        self.协议 = 协议集(xml路径=xml路径, xml文本=xml文本,
                           补充={**{k: v for k, v in self.协议.接口.items()}, **更多},
                           lib=self.lib)
        return self.协议

    def 找接口(self, 名):
        try:
            return self.协议.接口[名]
        except KeyError:
            raise KeyError(f"协议表里没有接口 {名!r}（是不是忘了 装扩展？）")

    # -- 注册表
    def 取注册表(self):
        iface = self.找接口("wl_registry")
        p = self.lib.wl_proxy_marshal_flags(self.d, 1, iface, 1, 0, None)
        self._注册表 = 代理(self, p, iface)
        self.挂监听(self._注册表, {
            "global": self._收到全局,
            "global_remove": lambda d, reg, name: None,
        })
        self.lib.wl_display_roundtrip(self.d)
        return self._注册表

    def _收到全局(self, _数据, _reg, 名字, 接口名, 版本):
        接口名 = 接口名.decode() if isinstance(接口名, bytes) else 接口名
        self.全局.append((int(名字), 接口名, int(版本)))

    def 绑(self, 接口名, 版本=None):
        """English: Bind a global by interface name. / 中文：按接口名绑定一个全局对象。"""
        候选 = [g for g in self.全局 if g[1] == 接口名]
        if not 候选:
            raise KeyError(f"合成器没提供 {接口名}")
        名字, _, 可用 = 候选[0]
        v = min(版本 or 可用, 可用)
        iface = self.找接口(接口名)
        p = self.lib.wl_proxy_marshal_flags(self._注册表.p, 0, iface, v, 0,
                                            c_uint32(名字), c_char_p(接口名.encode()),
                                            c_uint32(v), None)
        return 代理(self, p, iface)

    # -- 事件
    def 挂监听(self, 代理对象, 处理表):
        iface = 代理对象.iface.contents
        n = iface.event_count
        数组 = (c_void_p * (n + 1))()
        for i in range(n):
            消息 = iface.events[i]
            名 = 消息.name.decode()
            签名 = 解码签名(消息)
            函数 = 处理表.get(名)
            # ⚠️ 事件回调的 C 签名是 (void *data, struct xxx *代理, 事件参数...)：
            #   前面有两个指针，不是只有一个！少写一个 proxy，参数表整体错位一格，
            #   uint32 的 name 会被当成 char* 去 strlen，直奔野指针 —— 这个坑我们用 gdb 抓过。
            参数类型 = [c_void_p, c_void_p] + [回参类型[c] for c in 签名]
            if 函数 is None:
                壳 = CFUNCTYPE(None, *参数类型)(lambda *a: None)
            else:
                壳 = CFUNCTYPE(None, *参数类型)(
                    lambda 数据, 代理, *实参, _f=函数: _f(数据, 代理, *实参)
                )
            数组[i] = cast(壳, c_void_p)
            self._回调库存.append(壳)
        self._回调库存.append(数组)
        self.lib.wl_proxy_add_listener(代理对象.p, 数组, None)

    # -- 事件循环
    def 排空(self):
        self.lib.wl_display_flush(self.d)
        self.lib.wl_display_dispatch_pending(self.d)

    def 等一批(self, 超时毫秒=1000):
        """prepare_read + poll + read_events 的标准写法，能自己决定什么时候画。"""
        import select
        while self.lib.wl_display_prepare_read(self.d) != 0:
            self.lib.wl_display_dispatch_pending(self.d)
        self.lib.wl_display_flush(self.d)
        fd = self.lib.wl_display_get_fd(self.d)
        try:
            就绪 = bool(select.select([fd], [], [], 超时毫秒 / 1000.0)[0])
        except OSError:
            就绪 = False
        if not 就绪:
            self.lib.wl_display_cancel_read(self.d)
            return False
        self.lib.wl_display_read_events(self.d)
        self.lib.wl_display_dispatch_pending(self.d)
        return True

    def 关(self):
        if self.d:
            self.lib.wl_display_disconnect(self.d)
            self.d = None


# ------------------------------------------------- 协议描述文件的运行时定位

def 找协议xml(相对路径, 核心=False):
    """English: Locate a protocol description file without hard-coding any path.
    中文：定位协议描述文件，不写死任何本机路径。

    查找顺序：环境变量 WAYLAND_PROTOCOLS_DIR → 常见系统共享目录 →
    容器化运行时（Flatpak 等）里随附的副本。
    核心协议在 <datadir>/wayland/ 下，第三方协议在 <datadir>/wayland-protocols/ 下。
    """
    根目录 = []
    if os.environ.get("WAYLAND_PROTOCOLS_DIR"):
        根目录.append(os.environ["WAYLAND_PROTOCOLS_DIR"])
    家 = os.path.expanduser("~")
    根目录 += ["/usr/share", "/usr/local/share", os.path.join(家, ".local/share")]
    # 容器化运行时：<运行时>/x86_64/<版本>/<提交指纹>/files/share
    # ⚠️ 版本号与指纹随每次更新变化，深度也不保证，所以按层走而不是拼死路径。
    #    踩过：原以为只有 x86_64/<指纹>/files/share 一层，结果少走一层，静默找不到。
    运行时根 = os.path.join(家, ".local/share/flatpak/runtime")
    if os.path.isdir(运行时根):
        尾巴 = os.sep + os.path.join("files", "share")
        for 运行时 in sorted(os.listdir(运行时根)):
            架构目录 = os.path.join(运行时根, 运行时, "x86_64")
            if not os.path.isdir(架构目录):
                continue
            基准 = 架构目录.rstrip(os.sep).count(os.sep)
            for 当前, 子目录, _ in os.walk(架构目录):
                # 深度 0=x86_64、1=版本、2=指纹、3=files、4=share；再深就没必要走了
                if 当前.rstrip(os.sep).count(os.sep) - 基准 >= 5:
                    子目录[:] = []
                    continue
                if 当前.endswith(尾巴):
                    根目录.append(当前)
    子目录 = "wayland" if 核心 else "wayland-protocols"
    for 根 in 根目录:
        候选 = os.path.join(根, 子目录, 相对路径)
        if os.path.isfile(候选):
            return 候选
    raise FileNotFoundError(
        f"找不到协议描述文件 {相对路径}。请安装 wayland-protocols"
        f"（核心协议还需 wayland 包），或用 WAYLAND_PROTOCOLS_DIR 显式指定目录。"
    )


def 找扫描器():
    """English: Locate the authoritative wayland-scanner binary.
    中文：定位协议表的权威生成工具；优先环境变量 WAYLAND_SCANNER，其次 PATH。"""
    if os.environ.get("WAYLAND_SCANNER"):
        return os.environ["WAYLAND_SCANNER"]
    命中 = shutil.which("wayland-scanner")
    if 命中:
        return 命中
    raise FileNotFoundError(
        "找不到 wayland-scanner。请安装 libwayland-bin（Debian/Ubuntu）"
        "或 wayland-utils，或用 WAYLAND_SCANNER 显式指定可执行文件路径。"
    )

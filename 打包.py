#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""打包 —— 把「原生身体」做成一个 AppImage（黑盒交付用）。

做法（不用 linuxdeploy / pyinstaller，全部自己来，省得猜）：
    ① 独立 CPython（python-build-standalone，stripped）当解释器；
    ② 从本机 venv 里挑出真正用到的 PySide6 模块，再用 ldd 求出它们的 .so 依赖闭包，
       只把这些库复制进包（venv 那份 PySide6 是 649 MB，闭包只有几十 MB）；
    ③ 宿主代码 + 上游的贴图资产拷进去；
    ④ AppRun 设好 PYTHONHOME/PYTHONPATH/LD_LIBRARY_PATH/QT_PLUGIN_PATH 后启动；
    ⑤ 用 AppImage 官方 runtime + mksquashfs（-offset）拼成 .AppImage。

用法：python3 打包.py            # 生成 ~/Desktop/78/coopanion-native-host-x86_64.AppImage
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

家 = Path.home()
构建 = 家 / "appimage-build"
PyDir = 构建 / "python"                      # 独立 CPython（已解压）
venv = 家 / "dsh-pet-opt/.venv"
PySide = venv / "lib/python3.12/site-packages/PySide6"
Shiboken = venv / "lib/python3.12/site-packages/shiboken6"
AppDir = 构建 / "coopanion-native-host.AppDir"
产物 = 家 / "Desktop/78/coopanion-native-host-x86_64.AppImage"

# 需要的 PySide6 模块（只这些，别的全不要）
留模块 = ["QtCore", "QtGui", "QtWidgets", "QtNetwork", "QtWebSockets"]
# 平台插件：X11 用 xcb，万一没有就退到 minimal（至少能看到报错）
留插件 = ["platforms/libqxcb.so", "platforms/libqminimal.so", "platforms/libqoffscreen.so"]
# 不打包的系统库（打包了反而容易跟宿主打架）
不打包 = re.compile(r"(libc\.so|libm\.so|libdl\.so|libpthread\.so|librt\.so|ld-linux|"
                    r"libstdc\+\+|libgcc_s|libGL|libEGL|libGLX|libGLdispatch|libdrm|"
                    r"libnvidia|libcuda|libvulkan|libX11\.so|libxcb\.so|libxcb-.*\.so)")


def 跑(命令, **kw):
    return subprocess.run(命令, capture_output=True, text=True, **kw)


def ldd依赖(文件: Path) -> list[Path]:
    出 = 跑(["ldd", str(文件)])
    依赖 = []
    for 行 in 出.stdout.splitlines():
        m = re.search(r"=>\s+(\S+)\s", 行)
        if m and m.group(1).startswith("/"):
            依赖.append(Path(m.group(1)).resolve())
    return 依赖


def 清空(路径: Path):
    if 路径.exists():
        shutil.rmtree(路径)
    路径.mkdir(parents=True)


def 装python(目标: Path):
    """把独立 Python 拷进去，顺手丢掉用不到的（tcl/tk/idle/测试/2to3）。"""
    shutil.copytree(PyDir, 目标, symlinks=False, ignore=shutil.ignore_patterns(
        "idlelib", "tcl*", "tkinter", "test", "lib2to3", "ensurepip", "pydoc_data",
        "__pycache__", "*.pyc"))
    for 名 in ("idle3", "idle3.12", "2to3", "2to3-3.12", "pydoc3", "pydoc3.12",
               "pip", "pip3", "pip3.12", "python", "python3"):
        p = 目标 / "bin" / 名
        if p.exists():
            p.unlink()
    for 名 in ("include", "share", "lib/pkgconfig"):
        p = 目标 / 名
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)
    # 库目录里的 tcl/tk 也删掉
    for 名 in ("tcl9", "tcl9.0", "itcl4.3.8", "tk9.0"):
        p = 目标 / "lib" / 名
        if p.exists():
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()


def 装pyside(目标: Path):
    """只拷用到的 PySide6 模块 + 它们的 .so 依赖闭包（不整目录抄，省得把 QtWebEngine 也拖进来）。"""
    站点 = 目标 / "lib/python3.12/site-packages"
    站点.mkdir(parents=True, exist_ok=True)
    ps = 站点 / "PySide6"
    ps.mkdir(exist_ok=True)
    sh = 站点 / "shiboken6"
    sh.mkdir(exist_ok=True)
    入口 = []
    for f in ("__init__.py", "_config.py"):
        p = PySide / f
        if p.exists():
            shutil.copy2(p, ps / f)
    # 这两个是 PySide6 自己的运行时陪伴库，模块 .so 会直接 dlopen 它们
    for f in sorted(PySide.glob("libpyside6*.so*")):
        shutil.copy2(f, ps / f.name)
    for f in sorted(Shiboken.glob("libshiboken6*.so*")):
        shutil.copy2(f, sh / f.name)
    for 子 in ("lib",):
        d = Shiboken / 子
        if d.is_dir():
            shutil.copytree(d, sh / 子, dirs_exist_ok=True, symlinks=False)
    入口根 = []      # 用来算闭包的「入口 .so」
    for 模 in 留模块:
        for 后缀 in (".abi3.so", ".so"):
            p = PySide / f"{模}{后缀}"
            if p.exists():
                shutil.copy2(p, ps / p.name)
                入口根.append(p)
        d = PySide / 模
        if d.is_dir():
            shutil.copytree(d, ps / 模, dirs_exist_ok=True)
    for p in Shiboken.iterdir():
        if p.is_file():
            shutil.copy2(p, sh / p.name)
            if p.suffix == ".so":
                入口根.append(p)
    for 相对 in 留插件:
        src = PySide / "Qt/plugins" / 相对
        if src.exists():
            dst = ps / "Qt/plugins" / 相对
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            入口根.append(src)
    # 闭包：从入口开始 ldd，缺谁补谁。
    # ⚠️ 关键：同名库要**优先用 venv 里 PySide6 自带的那份**（6.11），
    #    否则 ldd 会解析到系统 Qt（6.4），版本对不上 → undefined symbol。
    Qt库源 = PySide / "Qt/lib"
    Qt名表 = {f.name: f for f in Qt库源.glob("*.so*")} if Qt库源.is_dir() else {}
    见过 = set()
    补过: dict[str, int] = {}
    待办 = list(入口根)
    轮 = 0
    while 待办 and 轮 < 12:
        轮 += 1
        新 = []
        for f in 待办:
            for dep in ldd依赖(f):
                if dep in 见过:
                    continue
                见过.add(dep)
                名 = dep.name
                if 不打包.search(名):
                    continue
                if str(dep).startswith(str(PySide)) or str(dep).startswith(str(Shiboken)):
                    continue          # 已经拷过 / 是 Qt 自己的库，下面统一补
                if str(dep).startswith(str(venv)):
                    continue
                源 = Qt名表.get(名, dep)          # ← 优先 PySide6 自带那份
                落点 = 站点 / 名
                if not 落点.exists():
                    try:
                        shutil.copy2(源, 落点)
                        补过[名] = 源.stat().st_size
                    except Exception:
                        continue
                新.append(落点)
        待办 = 新
    # Qt 自己的 .so：只补闭包里真正用到的那几个（按 soname 在 PySide6/Qt/lib 里找）
    要的 = {d.name for d in 见过 if str(d).startswith(str(PySide / "Qt/lib"))}
    Qt落点 = ps / "Qt/lib"
    Qt落点.mkdir(parents=True, exist_ok=True)
    for 名 in sorted(要的):
        src = Qt库源 / 名
        if src.exists():
            shutil.copy2(src, Qt落点 / 名)
            补过[f"Qt/{名}"] = src.stat().st_size
    return 补过


def 装应用(目标: Path):
    """宿主代码 + 上游的贴图资产。"""
    应用 = 目标 / "usr/share/coopanion-native-host"
    应用.mkdir(parents=True, exist_ok=True)
    源码 = 家 / "coop-linux/原生"
    for f in sorted(源码.glob("*.py")):
        if f.name in ("量路线.py", "量帧率.py", "量理论.py", "量快版.py", "量渲染.py",
                      "量一轮.py", "看一眼.py", "戳一下.py"):
            continue          # 量测脚本不进包
        shutil.copy2(f, 应用 / f.name)
    网页 = 家 / "coop-linux/app/packages/cortico-world-desktop-pet/web"
    # 只要 whale 目录（模型 + 贴图 + 配色）
    shutil.copytree(网页 / "whale", 应用 / "web/whale",
                    ignore=shutil.ignore_patterns("thumbs", "*.原版备份", "__pycache__"))
    return 应用


def main():
    print("① 清空 AppDir 并装独立 Python")
    清空(AppDir)
    装python(AppDir / "usr")
    print("   Python 装好：", sum(f.stat().st_size for f in (AppDir / "usr").rglob("*") if f.is_file()) // 1048576, "MB")
    print("② 装 PySide6（只挑用到的 + ldd 闭包）")
    闭包 = 装pyside(AppDir / "usr")
    总 = sum(闭包.values()) / 1048576
    print(f"   拷了 {len(闭包)} 个库，合计 {总:.1f} MB")
    最大 = sorted(闭包.items(), key=lambda x: -x[1])[:6]
    for 名, 大小 in 最大:
        print(f"      {大小/1048576:6.1f} MB  {名}")
    print("③ 安装宿主代码与资产")
    应用 = 装应用(AppDir)
    print("④ 写 AppRun / desktop / 图标 / 说明")
    (AppDir / "AppRun").write_text('''#!/bin/bash
# Coopanion Native Host宿主（PySide6 + QPainter，不用 Electron/Chromium）
HERE="$(dirname "$(readlink -f "$0")")"
export PYTHONHOME="$HERE/usr"
export PYTHONPATH="$HERE/usr/lib/python3.12/site-packages:$HERE/usr/share/coopanion-native-host"
export LD_LIBRARY_PATH="$HERE/usr/lib/python3.12/site-packages:$HERE/usr/lib/python3.12/site-packages/PySide6/Qt/lib:$LD_LIBRARY_PATH"
export QT_PLUGIN_PATH="$HERE/usr/lib/python3.12/site-packages/PySide6/Qt/plugins"
# 只连本地 ws://，不需要 TLS；把「没有 TLS 后端」的唠叨关掉
export QT_LOGGING_RULES="qt.network.ssl.warning=false"
export COOP_ASSETS="$HERE/usr/share/coopanion-native-host/web"
export COOP_LOG="${XDG_CACHE_HOME:-$HOME/.cache}/Coopanion Native Host"
exec "$HERE/usr/bin/python3.12" "$HERE/usr/share/coopanion-native-host/原生身体.py" "$@"
''', encoding="utf-8")
    (AppDir / "AppRun").chmod(0o755)
    # 说明文件与许可：包根放一份（解开就能看见），应用目录也放一份（--说明 用）
    源 = 家 / "coop-linux/原生"
    for 名 in ("README-quickstart.txt",):
        if (源 / 名).exists():
            shutil.copy2(源 / 名, AppDir / 名)
            shutil.copy2(源 / 名, 应用 / 名)
    lic = 家 / "coop-linux/app/LICENSE"
    if lic.exists():
        shutil.copy2(lic, AppDir / "LICENSE-上游-MIT.txt")
    (AppDir / "NOTICE.txt").write_text(
        "本包内含 Pal-AI-Lab/Coopanion 的角色资产（web/whale/**、model.json），"
        "按上游 MIT License 使用，全文见 LICENSE-上游-MIT.txt。\n"
        "宿主代码（usr/share/coopanion-native-host/*.py）是另外写的，同样以 MIT 提供。\n", encoding="utf-8")
    (AppDir / "coopanion-native-host.desktop").write_text(
        "[Desktop Entry]\nType=Application\nName=Coopanion Native Host\n"
        "Comment=Coopanion 的原生宿主（无 Chromium）\nExec=Coopanion Native Host\nIcon=Coopanion Native Host\nCategories=Utility;\n",
        encoding="utf-8")
    # 图标：用她的一张立绘缩一个
    图 = 家 / "Desktop/78/Coopanion-原生身体-2026-09-28.png"
    if 图.exists():
        subprocess.run(["convert", str(图), "-resize", "256x256", str(AppDir / "coopanion-native-host.png")])
    print("⑤ 打包成 AppImage")
    产物.parent.mkdir(parents=True, exist_ok=True)
    if 产物.exists():
        产物.unlink()
    # ⚠️ 不能用 mksquashfs -offset：它会把开头填 0（把 runtime 冲掉）。
    #    正确做法是「先单独压出 squashfs，再 cat 到 runtime 后面」。
    runtime = 构建 / "runtime-x86_64"
    中间 = 构建 / "根文件系统.sqfs"
    if 中间.exists():
        中间.unlink()
    r = 跑(["mksquashfs", str(AppDir), str(中间), "-comp", "zstd", "-b", "128K",
            "-root-owned", "-noappend", "-no-progress"])
    if r.returncode != 0:
        print(r.stdout[-2000:]); print(r.stderr[-2000:]); sys.exit(1)
    with open(产物, "wb") as 出, open(runtime, "rb") as a, open(中间, "rb") as b:
        shutil.copyfileobj(a, 出)
        shutil.copyfileobj(b, 出)
    产物.chmod(0o755)
    大小 = 产物.stat().st_size / 1048576
    print(f"   好了：{产物}  {大小:.1f} MB")


if __name__ == "__main__":
    main()

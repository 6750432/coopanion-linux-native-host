#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量路线 —— 起一条路线（老的 Chromium 外壳 / 新的原生身体），量它到底吃多少。

量这些东西：
    · 窗口出现要多久（从拉起脚本到宠物窗口真的出现在 X 上）
    · 进程树内存：RSS 合计 + **PSS 合计**（PSS 会把共享库按比例摊，比 RSS 诚实）
    · 进程树 CPU：/proc/<pid>/stat 的 utime+stime 增量（整棵树求和）
    · 进程个数、温度

用法：
    python3 量路线.py 老          # 跑 ~/coop-linux/启动.sh（Chromium）
    python3 量路线.py 原生        # 跑 ~/coop-linux/启动-原生.sh
    python3 量路线.py 原生 COOP_GRID=2 COOP_FPS=24
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

家 = Path.home() / "coop-linux"
窗口关键词 = {"老": "Cortico", "原生": "原生身体"}


def 整棵树(pgid: int):
    """按进程组抓（启动脚本用 start_new_session 起的，pgid 就是它自己的 pid）。"""
    出 = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            字段 = open(f"/proc/{pid}/stat").read().split(") ", 1)[1].split()
            if int(字段[2]) != pgid:      # 字段[2] = pgrp
                continue
        except Exception:
            continue
        出.append(int(pid))
    return 出


def 内存(pids):
    rss = pss = 0
    for pid in pids:
        try:
            for 行 in open(f"/proc/{pid}/smaps_rollup"):
                if 行.startswith("Pss:"):
                    pss += int(行.split()[1])
                elif 行.startswith("Rss:"):
                    rss += int(行.split()[1])
        except Exception:
            pass
    return rss / 1024, pss / 1024


def CPU(pids):
    t = 0.0
    for pid in pids:
        try:
            字段 = open(f"/proc/{pid}/stat").read().split(") ", 1)[1].split()
            t += (int(字段[11]) + int(字段[12])) / os.sysconf("SC_CLK_TCK")   # utime+stime
        except Exception:
            pass
    return t


def 有窗口了吗(关键词: str) -> bool:
    环 = dict(os.environ, DISPLAY=":0", XAUTHORITY=str(Path.home() / ".Xauthority"),
              DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000/bus")
    try:
        out = subprocess.run(["wmctrl", "-l"], capture_output=True, text=True, env=环, timeout=5).stdout
        return 关键词 in out
    except Exception:
        return False


def 温度():
    出 = {}
    for h in Path("/sys/class/hwmon").glob("hwmon*"):
        try:
            名 = (h / "name").read_text().strip()
        except Exception:
            continue
        if 名 in ("coretemp", "pch_skylake"):
            try:
                出[名] = int((h / "temp2_input").read_text()) // 1000 if 名 == "coretemp" \
                    else int((h / "temp1_input").read_text()) // 1000
            except Exception:
                pass
    return 出


def main():
    路线 = sys.argv[1] if len(sys.argv) > 1 else "原生"
    额外 = dict(a.split("=", 1) for a in sys.argv[2:])
    脚本 = 家 / ("启动.sh" if 路线 == "老" else "启动-原生.sh")
    环 = dict(os.environ)
    环.update(额外)
    环["DISPLAY"] = ":0"
    环["XAUTHORITY"] = str(Path.home() / ".Xauthority")
    print(f"══ 起「{路线}」路线：{脚本.name} {额外 if 额外 else ''} ══")
    进程 = subprocess.Popen(["bash", str(脚本)], cwd=str(家), env=环,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
    pgid = 进程.pid
    t0 = time.time()
    窗口耗时 = None
    while time.time() - t0 < 90:
        if 有窗口了吗(窗口关键词.get(路线, "原生身体")):
            窗口耗时 = time.time() - t0
            break
        time.sleep(.25)
    print(f"  窗口出现：{窗口耗时:.1f} 秒" if 窗口耗时 else "  窗口 90 秒都没出来（失败）")
    # 再养一会儿让缓存/着色器稳定
    time.sleep(max(0, 40 - (time.time() - t0)))
    # 采 6 段，每段 5 秒 —— 她会走会停，单点采样不诚实，看区间
    样 = []
    rss = pss = 0
    段数 = int(os.environ.get("MEASURE_SEGS", "6"))
    每段 = float(os.environ.get("MEASURE_SEC", "5"))
    拆分: dict[int, float] = {}
    for i in range(段数):
        pids = 整棵树(pgid)
        rss, pss = 内存(pids)
        起 = {q: CPU([q]) for q in pids}
        time.sleep(每段)
        c1 = CPU(整棵树(pgid))
        样.append((c1 - sum(起.values())) / 每段 * 100)
        for q in pids:
            拆分[q] = 拆分.get(q, 0.0) + (CPU([q]) - 起.get(q, 0.0)) / 每段 * 100 / max(1, 段数)
    print(f"  进程数 {len(整棵树(pgid))}")
    for q, v in sorted(拆分.items(), key=lambda x: -x[1])[:3]:
        try:
            raw = open(f"/proc/{q}/cmdline", "rb").read().decode(errors="replace").replace("\x00", " ").strip()
        except Exception:
            raw = "?"
        名 = "核心" if "boot.ts" in raw else ("外壳/身体" if ("外壳.py" in raw or "原生身体" in raw) else raw[:40])
        print(f"    {名:10s} {v:.1f}%（整段平均）")
    print(f"  内存 RSS {rss:.0f} MB（PSS {pss:.0f} MB）")
    print(f"  CPU   六段：{' '.join(f'{x:.0f}' for x in 样)}  → 最低 {min(样):.1f}% / 平均 {sum(样)/len(样):.1f}% / 最高 {max(样):.1f}%")
    print(f"  温度  {温度()}")
    # 收工：整组杀掉
    try:
        os.killpg(pgid, signal.SIGTERM)
    except Exception:
        pass
    time.sleep(4)
    for pid in 整棵树(pgid):
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    time.sleep(1)
    剩 = 整棵树(pgid)
    if 剩:
        细 = []
        for pid in 剩:
            try:
                raw = open(f"/proc/{pid}/cmdline", "rb").read().decode(errors="replace").replace("\x00", " ").strip()
                st = open(f"/proc/{pid}/stat").read().split(") ", 1)[1].split()[0]
                细.append(f"{pid}[{st}] {raw[:50]}")
            except Exception:
                pass
        print(f"  ⚠️ 还剩 {len(剩)} 个：{细}")
    else:
        print("  收干净了 ✓")


if __name__ == "__main__":
    main()

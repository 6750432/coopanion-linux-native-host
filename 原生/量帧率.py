#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量帧率 —— 原生身体最高能跑多少帧？

思路：把「忙时帧率」和「闲时帧率」设成同一个数（这样自适应降帧不掺和），
然后看它到底跑得动多少：日志里每 5 秒一行「N 帧（X fps）｜重绘每次 Y ms」，
再配 /proc 的 CPU 增量。

用法：
    python3 量帧率.py                      # 默认矩阵（格步 1/2/3/4 × 几档上限）
    python3 量帧率.py COOP_FPS=240 COOP_GRID=3 COOP_SCALE=0.62
"""
from __future__ import annotations

import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path

家 = Path.home() / "coop-linux/原生"
V = Path.home() / "dsh-pet-opt/.venv/bin/python"
日志 = 家 / "logs/原生.log"
行格式 = re.compile(r"(\d+) 帧（([\d.]+) fps）｜每帧 ([\d.]+) ms.*?每次 ([\d.]+) ms")


def 起(环境: dict):
    环 = dict(os.environ)
    环.update(环境)
    环["DISPLAY"] = ":0"
    环["XAUTHORITY"] = str(Path.home() / ".Xauthority")
    环.setdefault("COOP_FPS_IDLE", str(环.get("COOP_FPS", "24")))   # 关掉自适应
    日志.write_text("")
    p = subprocess.Popen([str(V), "-u", str(家 / "原生身体.py")], cwd=str(家), env=环,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    return p


def 读cpu(pid: int):
    try:
        字段 = open(f"/proc/{pid}/stat").read().split(") ", 1)[1].split()
        return (int(字段[11]) + int(字段[12])) / os.sysconf("SC_CLK_TCK")
    except Exception:
        return None


def 一档(名: str, 环境: dict, 热=14.0, 量=15.0):
    p = 起(环境)
    time.sleep(热)
    c0 = 读cpu(p.pid)
    t0 = time.time()
    time.sleep(量)
    c1 = 读cpu(p.pid)
    用了 = time.time() - t0
    行 = 行格式.findall(日志.read_text(errors="replace"))
    # 只认测量窗口里那几行：日志每 5 秒一行，取最后两三行
    用 = 行[-3:] if len(行) >= 3 else 行
    if 用:
        fps = sum(float(x[1]) for x in 用) / len(用)
        帧ms = sum(float(x[2]) for x in 用) / len(用)
        画ms = sum(float(x[3]) for x in 用) / len(用)
    else:
        fps = 帧ms = 画ms = float("nan")
    cpu = None if (c0 is None or c1 is None) else (c1 - c0) / 用了 * 100
    print(f"  {名:34s} 实测 {fps:6.1f} fps ｜ 每帧 {帧ms:5.1f} ms（重绘 {画ms:5.1f}）"
          f" ｜ CPU {cpu if cpu is None else round(cpu, 1):>5} %")
    try:
        os.killpg(p.pid, signal.SIGTERM)
    except Exception:
        pass
    time.sleep(3)
    for pid in 整组(p.pid):
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass
    time.sleep(.5)
    return fps, 帧ms, cpu


def 整组(pgid: int):
    出 = []
    for pid in os.listdir("/proc"):
        if not pid.isdigit():
            continue
        try:
            字段 = open(f"/proc/{pid}/stat").read().split(") ", 1)[1].split()
            if int(字段[2]) == pgid:
                出.append(int(pid))
        except Exception:
            continue
    return 出


def 主():
    if len(sys.argv) > 1:
        环境 = dict(a.split("=", 1) for a in sys.argv[1:])
        print("== 单档 ==")
        一档(" ".join(f"{k}={v}" for k, v in 环境.items()), 环境)
        return
    档 = [
        ("格步3 上限24（现默认）", {"COOP_GRID": "3", "COOP_FPS": "24"}),
        ("格步3 上限60", {"COOP_GRID": "3", "COOP_FPS": "60"}),
        ("格步3 上限120", {"COOP_GRID": "3", "COOP_FPS": "120"}),
        ("格步3 上限240", {"COOP_GRID": "3", "COOP_FPS": "240"}),
        ("格步2 上限240", {"COOP_GRID": "2", "COOP_FPS": "240"}),
        ("格步1 上限240", {"COOP_GRID": "1", "COOP_FPS": "240"}),
        ("格步4 上限240", {"COOP_GRID": "4", "COOP_FPS": "240"}),
        ("格步3 小个子(0.42) 240", {"COOP_GRID": "3", "COOP_FPS": "240", "COOP_SCALE": "0.42"}),
    ]
    print("== 上限矩阵（每组 14 秒热身 + 15 秒计时；闲时帧率=忙时帧率，关掉自适应）==")
    for 名, 环境 in 档:
        一档(名, 环境)


if __name__ == "__main__":
    主()

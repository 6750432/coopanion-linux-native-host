#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量一轮 —— 换参数各跑一小段，量 CPU 与内存（原生身体用）。

用法： python3 量一轮.py            # 跑默认的四组对照
       python3 量一轮.py COOP_GRID=3 COOP_FPS=24
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

家 = Path.home() / "coop-linux/原生"
V = Path.home() / "dsh-pet-opt/.venv/bin/python"
脚本 = 家 / "原生身体.py"


def 起(环境: dict, 秒: float = 9.0):
    环 = dict(os.environ)
    环.update(环境)
    环["DISPLAY"] = ":0"
    环["XAUTHORITY"] = str(Path.home() / ".Xauthority")
    out = open("/tmp/量一轮.out", "wb")
    p = subprocess.Popen([str(V), str(脚本)], cwd=str(家), env=环,
                         stdout=out, stderr=subprocess.STDOUT, start_new_session=True)
    time.sleep(秒)
    return p


def 读cpu(pid: int, 秒: float = 4.0):
    def 一次():
        try:
            with open(f"/proc/{pid}/stat") as f:
                li = f.read().split()
            return (int(li[13]) + int(li[14])) / os.sysconf("SC_CLK_TCK")
        except Exception:
            return None
    a = 一次()
    time.sleep(秒)
    b = 一次()
    if a is None or b is None:
        return None, None
    rss = None
    try:
        with open(f"/proc/{pid}/status") as f:
            for 行 in f:
                if 行.startswith("VmRSS"):
                    rss = int(行.split()[1]) / 1024
    except Exception:
        pass
    return (b - a) / 秒 * 100, rss


def 杀(p):
    p.terminate()
    try:
        p.wait(timeout=5)
    except Exception:
        p.kill()


def 跑一组(名: str, 环境: dict):
    p = 起(环境)
    cpu, rss = 读cpu(p.pid)
    日志 = Path("/tmp/量一轮.out").read_text(errors="replace")
    每帧 = ""
    if "平均每帧" in 日志:
        每帧 = [l for l in 日志.splitlines() if "平均每帧" in l][-1].split("跑了")[-1].strip()
    print(f"  {名:26s} CPU {cpu if cpu is None else round(cpu,1):>5} %   RSS {round(rss) if rss else '?':>4} MB   {每帧}")
    杀(p)
    time.sleep(1.5)


def main():
    if len(sys.argv) > 1:
        环境 = dict(a.split("=", 1) for a in sys.argv[1:])
        print("== 单组 ==")
        跑一组(" ".join(f"{k}={v}" for k, v in 环境.items()), 环境)
        return
    组 = [
        ("格步2 24fps（现配置）", {"COOP_GRID": "2", "COOP_FPS": "24"}),
        ("格步3 24fps", {"COOP_GRID": "3", "COOP_FPS": "24"}),
        ("格步2 12fps", {"COOP_GRID": "2", "COOP_FPS": "12"}),
        ("格步3 16fps", {"COOP_GRID": "3", "COOP_FPS": "16"}),
        ("格步1 24fps", {"COOP_GRID": "1", "COOP_FPS": "24"}),
    ]
    print("== 对照实测（每组跑 9 秒热身 + 4 秒计时）==")
    for 名, 环境 in 组:
        跑一组(名, 环境)


if __name__ == "__main__":
    main()

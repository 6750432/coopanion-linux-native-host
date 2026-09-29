#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""鲸鱼模型的读取与绑骨表（对应 app/packages/cortico-world-desktop-pet/web/whale/model.json
与 figure.js 里那份 deformers 定义）。

给「原生身体」用：不读网页、不起 Chromium，直接把 model.json 和贴图读成 QImage。

单位说明（照抄 figure.js 的注释）：
    绑骨空间 = 桌宠的 logo 单位，x=128 在身体正下方，脚底 y=256，面朝右。
    母图（master drawing）像素 → 绑骨：U(x) = 128 + (x - X0) * S，V(y) = 256 - (FEET - y) * S
    贴图分辨率是母图的 DS 倍（DS=0.6），所以 1 绑骨单位 = (1/S)*DS 个贴图像素。
"""
from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtGui import QImage

# 网页那边的固定常量（figure.js 顶部）
FACE = {"x": 520, "y": 578, "w": 390, "h": 252}   # 脸贴图覆盖的母图矩形（母图像素）
HEAD = [30, 12, 215, 168]                          # 头部视差变形的范围（绑骨单位）


class 鲸鱼模型:
    """One `model.json` plus the textures of one colour scheme.
    
    一份 model.json + 一套配色的贴图。
    """

    def __init__(self, 网页目录: Path, 配色: str = "deepsea", 默认配色: str = "deepseek"):
        self.网页目录 = Path(网页目录)
        self.鲸鱼目录 = self.网页目录 / "whale"
        原样 = json.loads((self.鲸鱼目录 / "model.json").read_text(encoding="utf-8"))
        self.原始 = 原样
        self.单 = 原样["units"]                      # S / X0 / FEET / DS / featDS
        self.pivots = 原样["pivots"]
        self.feat = 原样["feat"]
        self.view = 原样["view"]                     # [x0, y0, x1, y1]，绑骨单位
        self.配色表 = [s for s in 原样.get("schemes", [{"id": "deepseek"}]) if s.get("ready") is not False]
        self.配色 = 配色 if any(s["id"] == 配色 for s in self.配色表) else self.配色表[0]["id"]
        self.默认配色 = self.配色表[0]["id"]

        self.S = self.单["S"]
        self.贴图比例 = self.单["DS"] / self.S            # 贴图像素 / 绑骨单位

        # 部件：原样 + 程序画出来的脸（faceFx），和 figure.js 里 parts.push(...) 一致
        self.部件 = [dict(p) for p in 原样["parts"]]
        self.部件.append({
            "id": "faceFx", "tex": "faceFx", "z": 9, "parent": "headFeat", "grid": [4, 4],
            "box": [self.U(FACE["x"]), self.V(FACE["y"]), FACE["w"] * self.S, FACE["h"] * self.S],
        })
        self.盒 = {p["id"]: p["box"] for p in self.部件}

        # 变形器表（照 figure.js 的 deformers 抄）
        PV, R = self.pivots, self.矩形
        self.变形器 = {
            "body":     {"kind": "rot",  "pivot": PV["body"]},
            "skirt":    {"kind": "warp", "parent": "body",    "rect": R("skirt")},
            "skirtSit": {"kind": "warp", "parent": "body",    "rect": R("skirt_sit")},
            "armNear":  {"kind": "rot",  "parent": "body",    "pivot": PV["armNear"]},
            "armFar":   {"kind": "rot",  "parent": "body",    "pivot": PV["armFar"]},
            "legBack":  {"kind": "rot",  "parent": "body",    "pivot": PV["legBack"]},
            "legFront": {"kind": "rot",  "parent": "body",    "pivot": PV["legFront"]},
            "tail":     {"kind": "rot",  "parent": "body",    "pivot": PV["tail"]},
            "tailBend": {"kind": "warp", "parent": "tail",    "rect": R("tail")},
            "neck":     {"kind": "rot",  "parent": "body",    "pivot": PV["neck"]},
            "headBack":  {"kind": "warp", "parent": "neck", "rect": HEAD},
            "headMid":   {"kind": "warp", "parent": "neck", "rect": HEAD},
            "headFeat":  {"kind": "warp", "parent": "neck", "rect": HEAD},
            "headFront": {"kind": "warp", "parent": "neck", "rect": HEAD},
            "hairSway":  {"kind": "warp", "parent": "headBack", "rect": R("hair_back")},
            "bangsSway": {"kind": "warp", "parent": "headFront", "rect": R("bangs")},
            "finNear":  {"kind": "rot",  "parent": "headMid",  "pivot": PV["finNear"]},
            "finFar":   {"kind": "rot",  "parent": "headBack", "pivot": PV["finFar"]},
            "ahoge":    {"kind": "rot",  "parent": "headFront", "pivot": PV["ahoge"]},
        }
        self._贴图: dict[str, QImage] = {}
        self.读贴图()

    # ── 坐标换算 ──────────────────────────────────────────────
    def U(self, x: float) -> float:
        """母图像素 x → 绑骨单位 x。"""
        return 128 + (x - self.单["X0"]) * self.S

    def V(self, y: float) -> float:
        """母图像素 y → 绑骨单位 y。"""
        return 256 - (self.单["FEET"] - y) * self.S

    def 矩形(self, 部件号: str):
        x, y, w, h = self.盒[部件号]
        return [x, y, x + w, y + h]

    def 链(self, 变形器号: str | None) -> list[str]:
        """从该变形器往上的整条链，**由内到外**（rig.js 的 chainOf）。"""
        c, d = [], 变形器号
        while d:
            c.append(d)
            d = self.变形器.get(d, {}).get("parent")
        return c

    # ── 贴图 ────────────────────────────────────────────────
    def 找贴图(self, 名字: str) -> Path | None:
        子目录 = "feat" if 名字 not in {p["tex"] for p in self.部件} else "tex"
        if 名字 == "faceFx":
            子目录 = "tex"
        前缀 = "" if self.配色 == self.默认配色 else f"schemes/{self.配色}/"
        p = self.鲸鱼目录 / 前缀 / 子目录 / f"{名字}.png"
        return p if p.exists() else None

    def 读贴图(self):
        """把本配色要用的贴图全部读进内存；缺的记一笔，不炸。"""
        self.缺失 = []
        for p in self.部件:
            if p["id"] == "faceFx":
                continue                       # 脸是每帧画出来的，不当文件读
            文件 = self.找贴图(p["tex"])
            if 文件 is None:
                self.缺失.append(p["tex"])
                continue
            im = QImage(str(文件))
            if im.isNull():
                self.缺失.append(p["tex"])
                continue
            self._贴图[p["tex"]] = im.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
        # 脸的零件（眼睛、嘴、表情精灵）
        self.脸图: dict[str, QImage] = {}
        前缀 = "" if self.配色 == self.默认配色 else f"schemes/{self.配色}/"
        for f in sorted((self.鲸鱼目录 / 前缀 / "feat").glob("*.png")):
            im = QImage(str(f))
            if not im.isNull():
                self.脸图[f.stem] = im.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)

    def 取图(self, 名字: str) -> QImage | None:
        return self._贴图.get(名字)

    # ── 脸部零件名（figure.js 的 featNames）──────────────────
    def 脸零件名(self) -> list[str]:
        名 = list(self.feat["sprites"].keys())
        for k in ("eyeL", "eyeR"):
            e = self.feat["eyes"][k]
            for n in ("lash", "ball", "iris", *(["rim"] if e.get("rim") else [])):
                名.append(f"{k}_{n}")
        return 名


if __name__ == "__main__":
    m = 鲸鱼模型(Path(__file__).resolve().parent.parent / "app/packages/cortico-world-desktop-pet/web")
    print(f"配色 {m.配色}／可选 {[s['id'] for s in m.配色表]}")
    print(f"部件 {len(m.部件)}，贴图 {len(m._贴图)}，脸零件 {len(m.脸图)}，缺 {m.缺失}")
    print(f"grid 总格数 = {sum(p['grid'][0] * p['grid'][1] for p in m.部件)}")

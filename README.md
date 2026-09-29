# Coopanion Linux 原生宿主 / Native Host

> **⚠️ 本项目为第三方独立原生宿主，并非官方版本，仅供架构参考。**
>
> **This is an independent third-party native host, NOT an official build. Provided for
> architectural reference only.** 官方版本请看 [Pal-AI-Lab/Coopanion](https://github.com/Pal-AI-Lab/Coopanion)。

一个**不用 Electron、不用 Chromium** 的 Coopanion 宠物窗口实现：把网页那一层
（渲染 + 窗口 + 输入 + 气泡）用 **Python + PySide6** 重写，内核照旧用上游的 Node 进程。

A drop-in replacement for Coopanion's pet window on Linux, written in **Python + PySide6**
instead of Electron/Chromium. The upstream Node core is reused as-is.

> 一句话：**同一只桌宠、同一个内核，换掉那一层 Chromium。**
> 本机实测宠物端内存从约 503 MB（PSS）降到约 149 MB。

---

## ⚠️ 上游版本关系（请先读这一节）

| | 版本 | 说明 |
|---|---|---|
| **本项目基于** | 上游 **v0.1.6** | `figure.js` / `rig.js` / `model.json` 的 Python 移植都照这一版写的 |
| **上游当前** | **v0.1.7**（2026-09-29） | ① 新增**官方 Linux 支持**（`.deb` + `.AppImage`）；② **鲸鱼角色重画**：部件 **16 → 25**，新增眉毛 `brows`、眼皮褶线 `eye_creases`，卷发/前发/后腰蝴蝶结拆成独立图层 |

**上游官方现在自己就支持 Linux 了。** 本项目因此**不再是「让 Linux 能用」的唯一办法**，
而是一个**更省内存的替代窗口层** —— 玩法不变，只是换掉 Chromium 那一层。

**本项目尚未同步到 v0.1.7。** 直接拿 v0.1.7 的 `model.json` 跑会少画 9 个新部件
（眉毛、褶线、几层头发与蝴蝶结），它们的动画逻辑也还没移植。同步是下一步计划，不是已完成的工作。

> **只想要「能跑」：直接用上游官方的 v0.1.7。** 本项目面向的是
> 「想把宠物窗口那一层做得更轻 / 想自己写一个宿主」的场景。

---

## 它是怎么接上去的（没改上游一行代码）

上游把「宠物窗口」设计成了可替换的一层，本项目走的就是这两个官方扩展点：

- 页面侧：`const host = window.petHost || null` —— 宿主把同名对象注入进去即可；
- 内核侧：环境变量 `CORTICO_DESKTOP_PET_HOST` —— 内核按它拉起宿主进程，并通过
  `--pet-url=http://127.0.0.1:<端口>/pet` 把 WebSocket 地址传下来。

之后全部走官方的 WebSocket 协议：`hello / say / act / walk / listen / thinking / prefs / ask`。
**`cortico` 内核与 desktop-pet world 一行未改。**

---

## 实测对比（同一台机器、同一个内核、背靠背量的）

| | 官方 Electron/QtWebEngine 宿主 | 本项目原生宿主 |
|---|---|---|
| 内存 RSS | 626 MB | **195 MB** |
| 内存 PSS（诚实口径） | 503 MB | **149 MB** |
| 其中宠物端 | 约 509 MB | 约 78 MB |
| CPU（60 秒 12 段均值） | 64.1%（50.4~80.6%） | 52.0%（19.0~82.2%） |
| 窗口出现 | 1.8 秒 | 1.0 秒 |

**三个必须说清楚的前提，否则这些数字会误导人：**

1. 本机 QtWebEngine **拿不到硬件 GPU**（`GBM is not supported` → 软件渲染），
   所以官方那一侧的数字**偏悲观**；两条路是在同一条件下量的，横向比才公平。
2. 这组数字是**对上游 v0.1.6 时期**的 Electron 宿主量的，
   **没有对官方 v0.1.7 的新 Linux 包做过实测**。
3. 后来复测 CPU 稳定在 **43.4%**（四段 42/44/44/43%）；
   早先 19~82% 的区间是「会走会停」造成的采样假象，不是真实波动。

**本机硬件**：i7-6700 / RTX 2060 / 16 GB / Linux Mint 22.3 / X11 + xfwm4 / 1920×1080 @144Hz。

---

## 怎么跑

```bash
# 1) 需要 Python 3.12 + PySide6（开发时用 6.11）
# 2) 指向你 clone 下来的 Coopanion 仓库
export COOP_APP=/path/to/Coopanion
# 3) 启动原生那条路
bash 启动-原生.sh
```

参数（在 `启动-原生.sh` 里，可用环境变量覆盖）：

| 变量 | 默认 | 含义 |
|---|---|---|
| `COOP_FPS` | 24 | 忙时帧率上限 |
| `COOP_FPS_IDLE` | 12 | 闲着时自动减半 |
| `COOP_SCALE` | 0.62 | 缩放（0.42 是网页版原大小） |
| `COOP_GRID` | 3 | 网格抽稀 1~4，越大越快越糙 |

不想开窗口、只验渲染：

```bash
QT_QPA_PLATFORM=offscreen python3 原生/看一眼.py     # 离线出姿势对照图
QT_QPA_PLATFORM=offscreen python3 原生/量快版.py     # 渲染优化基准
python3 原生/量路线.py 原生                          # 端到端量内存/CPU
```

---

## 目录

```
原生/          原生宿主的实现
  原生身体.py      窗口、输入、主循环、与核心通话
  身体.py          createPet 的移植（状态机 + 物理）
  小鱼.py          figure.js 的移植（弹簧、骨骼参数、头顶花样）
  脸.py            每帧画一张 390×252 的脸
  网格.py          rig.js 的 QPainter 版（逐格裁切的网格形变）
  接线.py          QWebSocket + 台词打字机
  泡泡.py          无边框、点击穿透的对话气泡
  模型.py          model.json 的加载与形变器表
  面板.py          左上角 HUD（内存/帧率/CPU）+ 演示模式剧本
外壳.py        另一条路：QtWebEngine 外壳（保留，两条路互不影响）
外挂/          可插拔的「外挂」：角色人设 / 配色 / 本地模型大脑
  管理器.py        勾选式开关界面，往目录里丢一个包就自动出现
工具/          启动器与诊断脚本
其他用法见 原生/README-quickstart.txt
```

---

## 已知限制（诚实交代）

- **没同步到上游 v0.1.7**（见上）。
- **macOS / Windows 没跑过**，本项目只针对 Linux/X11。
- 音效、麦克风、右键菜单、装扮窗、键盘回话、`prefs.scale` 热更新**都还没做**。
- 渲染是 **CPU 光栅**（QPainter），不是 GPU；本机实测格步 3（81 格）约 5.7 ms/帧、
  格步 1（547 格）约 18.6 ms/帧 —— 想要更高帧率就调大 `COOP_GRID`。

---

## 许可与致谢 / License & Credits

本仓库是**独立编写的第三方宿主**，不是上游官方仓库，与 Pal-AI-Lab 无隶属关系。

- **上游项目：[Pal-AI-Lab/Coopanion](https://github.com/Pal-AI-Lab/Coopanion)**
  （内核为 [Pal-AI-Lab/Cortico](https://github.com/Pal-AI-Lab/Cortico)）。
  角色、美术、内核与官方 Linux 支持**全部归上游作者所有**。
- 本项目**不携带**上游的角色资产；运行时直接读你本地的 Coopanion 仓库里的
  `web/whale/**` 与 `model.json`。
- `外挂/配色-深海青/` 里的贴图是**基于上游 v0.1.6 素材生成的派生作品**（配色重映射），
  同样遵循上游的 MIT 许可。
- [`LICENSE`](LICENSE) 是上游 MIT 许可全文的**逐字节拷贝，版权声明一字未改**
  （`Copyright (c) 2026 Phantivia`）。
- 本项目自行编写的宿主代码同样以 MIT 提供。

**特别感谢上游**：把「宠物窗口」设计成可替换的一层（页面侧 `window.petHost` 探测 +
内核侧 `CORTICO_DESKTOP_PET_HOST`），本项目才可能在不改动内核一个字节的前提下换掉渲染层；
也感谢上游在 v0.1.7 里补齐了官方 Linux 支持。

### License

MIT License —— 全文见 [`LICENSE`](LICENSE)。上游版权声明原样保留。

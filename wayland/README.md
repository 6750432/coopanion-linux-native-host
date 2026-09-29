# wayland/ — Wayland 协议层适配与测试床 / Wayland Protocol Adaptation and Testbed

> ## ⚠️ 本目录**尚未完成**的事项（先读）
>
> - **本地真实 Wayland 会话未测试** —— 本机没有该环境，按隔离原则未强行运行。
> - **层壳协议（降级第 1 层）从未实际运行** —— 没有 wlroots 系合成器可用。
> - **未在真实桌面合成器（GNOME / KDE）上运行过。**
> - **未接入宿主启动路径** —— 宿主仍然只走 X11，本目录只在手动执行时运行。
> - **单缓冲、未接缓冲释放事件**；多显示器与分数缩放未测。
>
> ## ⚠️ What this directory has **NOT** done (read first)
>
> - **No local real-Wayland-session test** — the host has no such environment; not forced, per the isolation policy.
> - **The layer-shell protocol (Tier 1) has never been executed** — no wlroots-family compositor available.
> - **Never run under a real desktop compositor (GNOME / KDE).**
> - **Not wired into the host's startup path** — the host still runs X11 only; this directory runs only when invoked manually.
> - **Single-buffered, no buffer-release handling**; multi-monitor and fractional scaling untested.

**中**　本目录是《[Wayland 适配研究](../docs/Wayland-Adaptation-Research.md)》的可复现代码。它**不参与宿主进程的启动** —— 宿主目前仍走 X11；这里存放的是评估 Wayland 后端时用到的一切。

**EN**　This directory holds the reproducible code behind [Wayland Adaptation Research](../docs/Wayland-Adaptation-Research.md). It is **not part of the host's startup path** — the host still runs on X11; what lives here is everything used while evaluating a Wayland backend.

---

## 隔离原则 / Isolation Policy

**中**

- 所有 Wayland 协议逻辑**先在沙盒测试床中验证**（合成器解压到用户目录直接运行，不需要 root、不安装系统包、不改动宿主会话配置）。
- 真实的**本地 Wayland 会话验证，仅在本地存在此类会话时执行**。本次执行时本机不具备该条件（无 Wayland socket、未安装合成器、`XDG_SESSION_TYPE` 未设置），因此**未执行本地测试，也未为此改动宿主 X11 环境的任何配置**。
- 当前状态：**沙盒已验证，本地暂缺环境。**

**EN**

- All Wayland protocol logic is **validated in a sandbox testbed first** (the compositor is extracted into a user directory and run directly: no root, no system packages, no changes to the host session's configuration).
- **Validation against a genuine local Wayland session is performed only when such a session exists locally.** At the time of execution the host did not satisfy that condition (no Wayland socket, no compositor installed, `XDG_SESSION_TYPE` unset), so **no local test was performed and no part of the host's X11 configuration was altered to enable one**.
- Current status: **sandbox-verified, no local session available.**

---

## 文件 / Files

| 文件 | 作用 |
|---|---|
| `wlraw.py` | 纯 `ctypes` 的 Wayland 底层库：运行时协议表生成、代理对象、事件循环、协议文件定位 |
| `验表2.py` | 用 `wayland-scanner` 的产出逐字段校验接口表生成器（实测 28/28 全等） |
| `原型.py` | 提交策略性能实测：小窗 / 全屏整屏 damage / 全屏局部 damage |
| `子表面.py` | 子表面方案：父面全透明、提交一次；形状挂子面，每帧只传 360×360 |
| `点穿.py` | 点击穿透端到端验证（核心协议输入区 + 真实鼠标注入） |
| `敲.py` | 向绝对屏幕坐标注入真实鼠标点击（`libXtst`） |
| `起合成器.sh` | 测试床启动脚本：`headless`（无头）或 `x11`（嵌套进真实桌面） |

| File | Purpose |
|---|---|
| `wlraw.py` | Pure-`ctypes` Wayland layer: runtime table generation, proxy objects, event loop, protocol-file discovery |
| `验表2.py` | Field-by-field verification of the table generator against `wayland-scanner` output (measured 28/28 identical) |
| `原型.py` | Commit-strategy performance runs: small window / full-screen full damage / full-screen partial damage |
| `子表面.py` | Sub-surface approach: fully transparent parent committed once; shape on a sub-surface uploading 360×360 per frame |
| `点穿.py` | Click-through end-to-end verification (core-protocol input region plus real mouse injection) |
| `敲.py` | Inject real mouse clicks at absolute screen coordinates (`libXtst`) |
| `起合成器.sh` | Testbed launcher: `headless`, or `x11` to nest inside the real desktop |

---

## 快速上手 / Quick Start

```bash
# 起测试床（根目录默认 ~/wayland-test，可用 WAYLAND_TESTBED 覆盖）
bash 起合成器.sh headless

export XDG_RUNTIME_DIR=~/wayland-test/rt
export WAYLAND_DISPLAY=wayland-test
export WESTON_PID=$(cat ~/wayland-test/weston.pid)

# 协议表校验（需要 wayland-scanner：libwayland-bin 或 wayland-utils）
export WAYLAND_SCANNER=/path/to/wayland-scanner   # 不在 PATH 里时显式指定
python3 验表2.py

# 性能
python3 原型.py --模式=子表面 2>/dev/null || SW=1920 SH=1080 SEC=8 python3 子表面.py
```

---

## 依赖与路径 / Dependencies and Paths

**中**

- 运行期只依赖 `libwayland-client`（几乎所有桌面系统自带）与 Python 3.10+ 标准库。
- 协议描述文件与 `wayland-scanner` **由运行时查找**，不写死任何路径：优先环境变量
  `WAYLAND_PROTOCOLS_DIR` / `WAYLAND_SCANNER`，其次常见系统目录，最后是容器化运行时里随附的副本。
- 测试床用的合成器来自发行版安装包，解压到用户目录即可运行，**不需要 root**。

**EN**

- Runtime dependencies are `libwayland-client` (shipped by virtually every desktop system) and the Python 3.10+ standard library.
- Protocol description files and `wayland-scanner` are **resolved at runtime, with no hard-coded paths**: the `WAYLAND_PROTOCOLS_DIR` / `WAYLAND_SCANNER` environment variables take priority, then common system directories, then copies bundled inside containerised runtimes.
- The testbed compositor comes from distribution packages and runs directly from a user directory — **no root required**.

---

## 已知限制 / Known Limitations

**中**　层壳协议（Tier 1）从未实际运行（本机没有 wlroots 系合成器）；未在真实桌面合成器上运行过；多显示器与分数缩放未测；协议原型使用单缓冲，正式实现需要双缓冲。完整清单见[研究文档第 6 节](../docs/Wayland-Adaptation-Research.md#6-未验证事项--unverified-items)。

**EN**　The layer-shell protocol (Tier 1) has never actually been executed (no wlroots-family compositor on this host); never run under a real desktop compositor; multi-monitor and fractional scaling untested; the protocol prototype is single-buffered, and a production implementation requires double buffering. The complete list is in [Section 6 of the research document](../docs/Wayland-Adaptation-Research.md#6-未验证事项--unverified-items).

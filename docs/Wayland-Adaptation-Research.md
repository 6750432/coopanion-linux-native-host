# Wayland 适配研究 / Wayland Adaptation Research

**中**　本文件记录本项目在 Wayland 合成器下运行所需的协议层实现、实测数据、生态现状与降级策略。
**EN**　This document records the protocol-layer implementation, measured data, ecosystem status and degradation strategy required to run this project under a Wayland compositor.

| | |
|---|---|
| 日期 / Date | 2026-09-29 |
| 状态 / Status | **沙盒已验证；本地暂缺环境 / Sandbox-verified; no local session available** |
| 关联代码 / Code | `wayland/` |
| 原始记录 / Raw log | 本文档即权威记录，数据均由 `wayland/` 下的脚本产出 / This document is the authoritative record; all figures are produced by the scripts in `wayland/` |

---

## 0. 摘要 / Abstract

**中**

本项目原先只针对 **X11** 会话编写，依赖三项 X11 专有机制：窗口自主定位、窗口常驻置顶、以及用 X 扩展把透明区域从输入区中挖掉（点击穿透）。

本项工作评估并实现了迁移到 Wayland 合成器的路径。核心判断是：**本项目的渲染器本来就产出「CPU 光栅化完成的 ARGB 位图」，而 Wayland 的共享内存机制本质上就是「共享一块像素缓冲」，因此渲染层无需任何改动**，需要替换的只有窗口层与输入层。

实现方式为**纯 `ctypes` 直接调用 `libwayland-client`**，不依赖编译器、不依赖任何 Wayland 绑定库、不依赖 GUI 工具包。协议接口表在运行时由协议描述文件生成，并已用协议表的权威生成工具逐字段验证。

**EN**

This project was originally written for **X11** sessions and depends on three X11-specific mechanisms: client-side window positioning, persistent always-on-top stacking, and carving transparent areas out of the input region via an X extension (click-through).

This work evaluates and implements a path to Wayland compositors. The central observation is that **this project's renderer already emits CPU-rasterised ARGB bitmaps, and Wayland's shared-memory mechanism is fundamentally "share a pixel buffer"; the rendering layer therefore needs no change at all.** Only the window and input layers must be replaced.

The implementation calls `libwayland-client` **directly through pure `ctypes`** — no compiler, no Wayland binding library, no GUI toolkit. Protocol interface tables are generated at runtime from the protocol description files and have been verified field-by-field against the authoritative table generator.

---

## 1. 测试环境与隔离原则 / Test Environment and Isolation Policy

**中**

全部验证在 `~/wayland-test/`（仓库内对应 `wayland/`，测试床根目录可用环境变量 `WAYLAND_TESTBED` 覆盖）中完成。该测试床**不需要 root、不安装任何系统包**：合成器及其依赖以安装包形式下载后解压到用户目录直接运行。

| 项 | 值 |
|---|---|
| 宿主会话 | X11 |
| 处理器 / 内存 | 4 核 8 线程 x86-64 / 16 GB |
| 合成器 | weston 13.0.0（用户目录解压，非系统安装） |
| 合成器渲染器 | pixman（纯 CPU 光栅） |
| 合成器外壳 | kiosk（不需要辅助客户端） |
| 输出（无头） | 1920×1080 |
| 输出（嵌套） | 900×560，嵌在真实桌面内 |
| CPU 调频 | `powersave`，实测主频在 2800–3700 MHz 之间波动 |

**隔离原则。** 所有 Wayland 协议逻辑先在上述沙盒测试床中验证。真实的本地 Wayland 会话验证**仅在本地存在此类会话时执行**；本次执行时本机不具备该条件，因此**未执行本地测试**，也未为此改动宿主 X11 环境的任何配置。该缺口的记录见 §6。

**EN**

All validation was performed inside `~/wayland-test/` (mirrored in this repository as `wayland/`; the testbed root can be overridden with the `WAYLAND_TESTBED` environment variable). The testbed **requires no root and installs no system package**: the compositor and its dependencies are downloaded as distribution packages and extracted into a user directory.

| Item | Value |
|---|---|
| Host session | X11 |
| CPU / RAM | 4-core/8-thread x86-64 / 16 GB |
| Compositor | weston 13.0.0 (extracted into a user directory, not system-installed) |
| Compositor renderer | pixman (pure CPU raster) |
| Compositor shell | kiosk (requires no helper clients) |
| Output (headless) | 1920×1080 |
| Output (nested) | 900×560, nested inside the real desktop |
| CPU frequency | `powersave` governor; observed 2800–3700 MHz |

**Isolation policy.** All Wayland protocol logic is validated in the sandbox testbed described above. Validation against a genuine local Wayland session is performed **only when such a session exists locally**; at the time of execution the host did not satisfy that condition, so **no local test was performed**, and no part of the host's X11 configuration was altered to enable one. That gap is recorded in §6.

---

## 2. 协议层实现与校验 / Protocol Layer Implementation and Verification

### 2.1 实现方式 / Approach

**中**

不使用 `pywayland`，不使用 `wayland-scanner` 生成的绑定，完全以 `ctypes` 直接调用 `libwayland-client` 的 C 接口。关键认识：`wl_interface` 结构只有三个标量字段加两张消息表，完全可以在运行时构造；而核心协议（`wl_compositor`、`wl_surface`、`wl_shm` 等）的接口表本身就是客户端库导出的**数据符号**，可以直接借用，无需自行构造。

只有第三方协议（如 `xdg-shell`）需要自行生成接口表。生成器支持 `since > 1` 的版本前缀与 `allow-null` 的可空前缀。

**EN**

No `pywayland`, no `wayland-scanner`-generated bindings. `libwayland-client`'s C interface is called directly through `ctypes`. The key insight: the `wl_interface` structure is three scalar fields plus two message tables, constructible at runtime; and the core protocol tables (`wl_compositor`, `wl_surface`, `wl_shm`, …) are themselves **data symbols exported by the client library**, so they can simply be borrowed rather than reconstructed.

Only third-party protocols (e.g. `xdg-shell`) require locally generated tables. The generator handles the `since > 1` version prefix and the `allow-null` nullable prefix.

### 2.2 用权威工具校验 / Verification Against the Authoritative Tool

**中**

接口表最容易出现「看着正确、实际错位一格」的缺陷，这类缺陷不会立即报错，而是在特定消息上表现为内存访问错误。因此校验方式是：调用协议描述文件的**权威生成工具**（`wayland-scanner`）产出参考实现，再逐字段比对 —— 接口名、版本号、请求与事件的条数、每条消息的名称与签名、以及每个参数位所引用的接口。

**结果：28 个接口逐字段全等，0 处不一致。**

| 组 | 接口数 | 结果 |
|---|---|---|
| 核心协议 | 23 | 全等 |
| `xdg-shell` | 5 | 全等 |

**EN**

Interface tables are exactly where "looks correct, actually off by one slot" defects hide. Such defects do not fail immediately; they surface later as invalid memory accesses on specific messages. Verification therefore invokes the **authoritative generator** (`wayland-scanner`) on the protocol description files to produce a reference implementation, then compares field by field: interface name, version, request and event counts, each message's name and signature, and the interface referenced at every argument position.

**Result: 28 interfaces matched field for field, 0 discrepancies.**

| Group | Interfaces | Result |
|---|---|---|
| Core protocol | 23 | identical |
| `xdg-shell` | 5 | identical |

### 2.3 校验过程中确认的三条规则 / Three Rules Established During Verification

**中**

1. **签名存在版本前缀。** `since > 1` 的消息在签名最前面附加版本数字（例如 `4iiii`、`4ii`、`5a`）。
2. **签名存在可空前缀。** 以 `?` 标注，且**不限于对象类型** —— 可空字符串同样使用（例如 `u?s`）。这两种前缀都只占签名的字符位，**不占参数位**。
3. **协议描述文件不等于线上协议。** 某一条注册表绑定请求在描述文件中只声明 2 个参数，而线上真实签名是 4 个（`usun`），由生成工具以硬编码特例补齐。此外，客户端库内建的接口表比随发行版提供的描述文件**版本更新**（例如 `wl_compositor` 内建 v7、描述文件 v6）。

**由第 3 条得出的设计约束：核心协议一律直接借用客户端库导出的内建表，只有第三方协议才自行生成。** 这同时回避了描述文件与运行时库之间的版本代差。

**EN**

1. **Signatures carry a version prefix.** Messages with `since > 1` prepend the version digit (`4iiii`, `4ii`, `5a`).
2. **Signatures carry a nullable prefix.** Marked with `?`, and **not limited to object types** — nullable strings use it too (e.g. `u?s`). Both prefixes occupy a signature character slot but **not an argument slot**.
3. **The protocol description file is not the wire protocol.** One registry bind request declares only 2 arguments in the description file while its true wire signature has 4 (`usun`), filled in by a hard-coded special case in the generator. Separately, the client library's built-in tables are **newer** than the description files shipped by the distribution (e.g. `wl_compositor` is v7 built-in versus v6 in the description file).

**The design constraint derived from point 3: core protocol always borrows the client library's built-in tables; only third-party protocols are generated locally.** This also sidesteps version skew between description files and the runtime library.

---

## 3. 性能实测：四种提交策略 / Performance: Four Commit Strategies

**中**

**测量方法。** 同一台机器、同一个合成器、同样内容（一条 360×360 带透明度的图形，每帧移动位置），只改变提交策略。每个模式运行 8 秒，每轮开始时重启合成器以保证口径一致；连续两轮（A / B）。

| 模式 | 画面 | 帧率 | 客户端 CPU | 合成器 CPU | 绘制 ms |
|---|---|---|---|---|---|
| 小窗 | 360×360 | 39.5 / 39.4 | 2.5 / 2.5 | 1.6 / 1.9 | 0.35 / 0.34 |
| 全屏层，整屏提交 | 1920×1080 | 35.7 / 35.7 | 5.1 / 5.1 | **10.9 / 11.0** | 1.13 / 1.10 |
| 全屏层，局部提交 | 1920×1080 | 39.4 / 39.4 | 4.0 / 3.7 | **1.7 / 1.6** | 0.68 / 0.66 |
| **子表面** | 父面 1920×1080 | 39.4 / 39.4 | **1.2 / 1.2** | 1.9 / 1.7 | **0.06 / 0.05** |

（每格为「第一轮 / 第二轮」）

**三条结论：**

1. **合成器只为被报告为「已损坏」的区域付出代价。** 同样的全屏缓冲，整屏提交使合成器占用升至 10.9~11.0%，只提交受影响的小矩形时降至 1.6~1.7% —— **相差约 6.5 倍**，且与 360×360 小窗模式（1.6~1.9%）基本持平。
2. **在 Wayland 上，输入区裁剪属于核心协议而非扩展。** X11 路径依靠一个 X 扩展实现点击穿透；Wayland 的对应请求属于基础协议，性质上更规范。
3. **子表面方案把降级路径的代价压低约一个数量级。** 客户端 CPU 由 3.7~4.0% 降至 1.2%；绘制耗时由 0.66~0.68 ms 降至 0.05~0.06 ms（约 11 倍）。折合每帧客户端 CPU 用时：全屏局部约 0.99 ms/帧 → 子表面约 0.30 ms/帧。

**子表面方案的原理**：父面全屏、全透明、**提交一次之后不再更新**；宠物挂在子表面上，每帧只上传 360×360，位置由子表面的定位请求变更。每帧必须产出的像素量因此从 8.3 MB 降至 0.5 MB。

**测量方差说明（重要）。** 本机 CPU 调频为 `powersave`，实测主频在 2800–3700 MHz 之间波动；同一份代码、同一台机器，**在不同会话中测得的绝对 CPU 占用可相差约 2.6 倍**。而同一会话内、背靠背两轮的复现性优于 ±10%（见上表两列）。因此本报告以**同一会话内的比值**为主要结论，绝对值仅作量级参考。

**EN**

**Method.** Same host, same compositor, same content (one 360×360 alpha-bearing shape, repositioned each frame); only the commit strategy varies. Each mode runs 8 seconds; the compositor is restarted before each round to keep the conditions identical. Two consecutive rounds (A / B).

| Mode | Surface | FPS | Client CPU | Compositor CPU | Draw ms |
|---|---|---|---|---|---|
| Small window | 360×360 | 39.5 / 39.4 | 2.5 / 2.5 | 1.6 / 1.9 | 0.35 / 0.34 |
| Full-screen layer, full damage | 1920×1080 | 35.7 / 35.7 | 5.1 / 5.1 | **10.9 / 11.0** | 1.13 / 1.10 |
| Full-screen layer, partial damage | 1920×1080 | 39.4 / 39.4 | 4.0 / 3.7 | **1.7 / 1.6** | 0.68 / 0.66 |
| **Sub-surface** | parent 1920×1080 | 39.4 / 39.4 | **1.2 / 1.2** | 1.9 / 1.7 | **0.06 / 0.05** |

(Each cell is "round one / round two".)

**Three conclusions:**

1. **A compositor pays only for regions reported as damaged.** With an identical full-screen buffer, full-screen damage raises compositor occupancy to 10.9–11.0%, whereas committing only the affected small rectangles drops it to 1.6–1.7% — a **factor of about 6.5**, essentially level with the 360×360 small-window mode (1.6–1.9%).
2. **On Wayland, input-region clipping is core protocol rather than an extension.** The X11 path depends on an X extension for click-through; the corresponding Wayland request is part of the base protocol and is therefore more canonical.
3. **The sub-surface approach cuts the cost of the degradation path by about an order of magnitude.** Client CPU falls from 3.7–4.0% to 1.2%; draw time falls from 0.66–0.68 ms to 0.05–0.06 ms (about 11×). In per-frame terms: roughly 0.99 ms/frame for full-screen partial commit versus about 0.30 ms/frame for the sub-surface.

**How the sub-surface approach works:** the parent surface is full-screen and fully transparent and is **committed once and then never updated**; the shape lives on a sub-surface that uploads only 360×360 per frame and is repositioned through the sub-surface's positioning request. Per-frame pixel production therefore drops from 8.3 MB to 0.5 MB.

**On measurement variance (important).** The host's CPU governor is `powersave`, with observed frequencies between 2800 and 3700 MHz. The same code on the same machine **can differ by roughly 2.6× in absolute CPU occupancy between sessions**, while back-to-back rounds within one session agree to better than ±10% (see the two columns above). This report therefore treats **ratios measured within a single session** as its primary conclusions, and absolute values as order-of-magnitude references only.

### 3.1 子表面方案的三条实现约束 / Three Implementation Constraints of the Sub-Surface Approach

**中**

以下三条中任何一条不满足，功能都会直接失效：

1. **父面必须设置为「空区域」作为输入区，不可传空指针。** 空指针的语义是「恢复为整个表面接收输入」，与本意完全相反。
2. **子表面必须显式切换为非同步模式（`set_desync`）。** 默认的同步模式要求子表面的状态变更随父面提交而生效，而本方案的父面提交一次后不再更新，因此不同步即永不刷新。
3. **子表面需显式声明置于父面内容之上**（`place_above`）。

**EN**

Failing to satisfy any one of the following three breaks the feature outright:

1. **The parent surface must be given an *empty region* as its input region; a null pointer must not be used.** The null semantics are "restore input over the whole surface" — precisely the opposite of intent.
2. **The sub-surface must be explicitly switched to desynchronised mode (`set_desync`).** The default synchronised mode applies sub-surface state changes on the parent's commit, and in this design the parent is committed once and never updated — so without desynchronisation it would never refresh.
3. **The sub-surface must be explicitly declared above the parent's content** (`place_above`).

---

## 4. 端到端验证 / End-to-End Verification

**中**

性能数字只说明「便宜」，不足以说明「正确」—— 便宜的另一种可能是「根本没有绘制」。因此另做了两项端到端验证，均在嵌套于真实桌面的合成器窗口中完成。

### 4.1 画面确实呈现 / The Image Is Genuinely Presented

| 项 | 值 |
|---|---|
| 截图尺寸 | 900×560 |
| 非黑像素 | **95132**（18.9%） |
| 包围盒 | **348×348**（与生成的图形一致） |
| 采样颜色 | (120, 120, 148)（与生成的图形一致） |
| 帧率 | **60.0 fps**（真实垂直同步） |

### 4.2 点击穿透确实成立 / Click-Through Genuinely Holds

**方法。** 在 900×560 的面上以核心协议请求挖出一个 240×240 的输入区域（位于表面坐标 60,60），其余区域全部穿透。随后向合成器窗口注入真实鼠标点击：区域内 2 次、区域外 2 次，观察客户端能否收到 `wl_pointer` 事件。

| 项 | 结果 |
|---|---|
| 区域内指针进入事件 | **3 次** |
| 按键事件 | **4 次** |
| 区域外指针事件 | **0 次** |
| 结论 | **点击穿透成立** |

区域外点击**一个事件都没有泄漏进客户端**，说明输入区裁剪在协议层真实生效。

**EN**

Performance figures show only that something is *cheap*, not that it is *correct* — "cheap" may also mean "nothing is drawn at all". Two end-to-end verifications were therefore performed, both against a compositor window nested inside the real desktop.

### 4.1 The Image Is Genuinely Presented

| Item | Value |
|---|---|
| Capture size | 900×560 |
| Non-black pixels | **95132** (18.9%) |
| Bounding box | **348×348** (matches the generated shape) |
| Sampled colour | (120, 120, 148) (matches the generated shape) |
| Frame rate | **60.0 fps** (real vertical sync) |

### 4.2 Click-Through Genuinely Holds

**Method.** A 240×240 input region (at surface coordinates 60,60) is carved out of a 900×560 surface using the core protocol request; all remaining area passes through. Real mouse clicks are then injected into the compositor window — two inside the region, two outside — while the client watches for `wl_pointer` events.

| Item | Result |
|---|---|
| Pointer-enter events inside the region | **3** |
| Button events | **4** |
| Pointer events outside the region | **0** |
| Conclusion | **Click-through holds** |

Not a single event from the outside clicks leaked into the client, confirming that input-region clipping takes effect at the protocol level.

---

## 5. 生态现状与降级策略 / Ecosystem Status and Degradation Strategy

### 5.1 上游协议治理的事实 / The Facts of Upstream Protocol Governance

**中**

层壳协议（`zwlr_layer_shell_v1`，可让客户端自主定位并常驻置顶）并非通用协议：它由 wlroots 系合成器提供，桌面环境 KDE（KWin）亦支持，而 **GNOME（Mutter）明确不支持**。

GNOME 维护者 **ebassi** 就此给出的说明，是本项目决定降级策略的直接依据。**原文引用**如下：

> "No, there aren't any replacements.
>
> Not all windowing systems provide the ability for applications to control the window stacking order; Wayland is one of those.
>
> The stacking order is under the control of the window manager, as a privileged component; GTK can integrate with the window manager to offer the ability to the user to control the window state, but it's not really up to the toolkit to provide API to do that to the application developer.
>
> You can use platform-specific API, if you want to access that functionality."

> 「没有替代品。不是所有窗口系统都让应用控制堆叠顺序，Wayland 就是其中之一。堆叠顺序归窗口管理器这个特权组件管……你想用的话可以用平台专属 API。」

**特别感谢 GNOME 维护者 ebassi 的提醒**：这段说明澄清了「窗口堆叠顺序归窗口管理器这一特权组件管理」是 Wayland 协议治理的既定设计取向，而非实现缺失。而上面提到的「平台专属 API」—— 即层壳协议 —— 在 GNOME 上并不存在。

**这正是本项目在无 `zwlr_layer_shell_v1` 的环境下选择降级为 X11 / XWayland 后端的根本原因**：不是对某一桌面环境的抱怨，而是在尊重上游协议治理与窗口管理器主权的前提下，选择能力可满足需求的后端。

生态侧的两项独立佐证：存在专门为基础窗口协议补齐该能力的第三方合成器分支；以及某知名应用已实现「无该协议时降级到基础窗口协议」的分支。

**EN**

The layer-shell protocol (`zwlr_layer_shell_v1`, which lets a client position itself and stay on top) is not a universal protocol: it is provided by wlroots-family compositors and supported by the KDE desktop environment (KWin), while being **explicitly unsupported by GNOME (Mutter)**.

The explanation given by GNOME maintainer **ebassi** is the direct basis for this project's degradation strategy. **Quoted verbatim:**

> "No, there aren't any replacements.
>
> Not all windowing systems provide the ability for applications to control the window stacking order; Wayland is one of those.
>
> The stacking order is under the control of the window manager, as a privileged component; GTK can integrate with the window manager to offer the ability to the user to control the window state, but it's not really up to the toolkit to provide API to do that to the application developer.
>
> You can use platform-specific API, if you want to access that functionality."

**Particular thanks are due to GNOME maintainer ebassi for this reminder.** The statement clarifies that "window stacking order is under the control of the window manager as a privileged component" is a deliberate design stance in Wayland's protocol governance, not an implementation gap. And the "platform-specific API" it refers to — i.e. the layer-shell protocol — does not exist on GNOME.

**This is precisely why this project degrades to an X11 / XWayland backend where `zwlr_layer_shell_v1` is unavailable**: not a complaint about any desktop environment, but a choice — made in respect of upstream protocol governance and of the window manager's sovereignty — of the backend whose capabilities meet the requirement.

Two independent ecosystem corroborations: a third-party compositor fork exists that adds this capability to the base window protocol, and a well-known application already ships an explicit "fall back to the base window protocol when it is unavailable" path.

### 5.2 三级降级策略 / Three-Tier Degradation Strategy

**中**

因为不存在一条所有桌面环境都支持的原生协议，可移植的形态是**按能力分层、运行时探测**，而不是按发行版名称分支：

| 层级 | 探测条件 | 使用的能力 | 覆盖范围 |
|---|---|---|---|
| **第 1 层** | 注册表中存在 `zwlr_layer_shell_v1` | 原生层壳：自主定位、常驻置顶、输入区裁剪 | wlroots 系合成器、KDE |
| **第 2 层** | 无层壳协议，但 X11 连接可用 | **现有 X11 后端，无需改动**：窗口自主定位、`_NET_WM_STATE_ABOVE` 置顶、X 扩展输入区裁剪 | GNOME、以及任何提供兼容层的会话 |
| **第 3 层** | 两者皆不可用 | 原生全屏窗口 + 子表面（§3） | 兜底 |

**关于第 2 层的位置值得特别说明**：在缺少层壳协议的环境（例如 GNOME）下，**X11 / XWayland 路径的能力反而优于原生 Wayland 路径**，因为它能提供原生路径无法提供的窗口定位与常驻置顶。因此探测的是**能力**，而不是「当前会话是不是 Wayland」这一个布尔值。

**关于第 3 层的一条硬限制**：Wayland 协议中**不存在**「我的窗口位于屏幕何处」这一类事件 —— 窗口配置事件只提供尺寸，表面进入事件只提供输出信息。因此在第 3 层中，若要把宠物放置在屏幕绝对坐标上，父窗口**必须请求全屏**，以获得「原点即 (0,0)、尺寸即屏幕尺寸」这一前提；否则只能得知宠物相对于窗口的位置，而无法得知窗口在屏幕上的位置。

**EN**

Because no single native protocol is supported by every desktop environment, the portable shape is **capability tiering with runtime probing**, not branching on distribution name:

| Tier | Probe condition | Capabilities used | Coverage |
|---|---|---|---|
| **Tier 1** | `zwlr_layer_shell_v1` present in the registry | Native layer-shell: self-positioning, persistent always-on-top, input-region clipping | wlroots-family compositors, KDE |
| **Tier 2** | No layer-shell, but an X11 connection is available | **Existing X11 backend, unchanged**: client-side positioning, `_NET_WM_STATE_ABOVE`, X-extension input-region clipping | GNOME, and any session offering a compatibility layer |
| **Tier 3** | Neither available | Native full-screen window plus sub-surface (§3) | Fallback |

**On the placement of Tier 2.** In environments lacking the layer-shell protocol (GNOME, for instance), the **X11 / XWayland path has strictly greater capability than the native Wayland path**, because it offers window positioning and persistent always-on-top that the native path cannot provide. What is probed is therefore **capability**, not the single boolean "is this session Wayland".

**On a hard constraint of Tier 3.** The Wayland protocol has **no** event of the form "here is where your window sits on screen": a window configure event supplies size only, and a surface enter event supplies output information only. Hence in Tier 3, to place the shape at absolute screen coordinates, the parent window **must request full-screen**, obtaining the premise "origin is (0,0), size is screen size". Otherwise only the shape's position relative to the window is known, never the window's position on screen.

---

## 6. 未验证事项 / Unverified Items

**中**

以下项目**尚未验证**，不以任何形式混入上文结论。

1. **本地真实 Wayland 会话未测试。** 执行本项工作时，本机不具备原生 Wayland 会话（无 Wayland socket、未安装任何 Wayland 合成器、`XDG_SESSION_TYPE` 未设置）。按隔离原则，**未执行本地测试，也未为此改动宿主 X11 环境的任何配置**。当前状态应记为「沙盒已验证，本地暂缺环境」。
2. **层壳协议（第 1 层）从未实际运行。** 沙盒合成器不提供该协议，本机也没有 wlroots 系合成器。该路径目前只有能力探测代码，没有实机数据。
3. **未在真实桌面合成器（GNOME / KDE）上运行。** 第 2 层中关于 X11 兼容层的窗口定位与置顶属性的可用性，是按惯例推断，未经实机确认。
4. **多显示器与分数缩放未测。**
5. **缓冲管理。** 协议原型使用单缓冲，未处理缓冲释放事件；正式实现需要双缓冲。
6. **合成器口径。** 沙盒合成器使用 pixman 纯 CPU 光栅，真实桌面普遍使用 GPU 合成，因此本报告中的合成器侧数字**偏悲观**。方向性结论不受影响，绝对值不可直接外推。

**EN**

The following items are **not yet verified** and are not mixed into the conclusions above in any form.

1. **No local real-Wayland-session test.** At the time of this work the host had no native Wayland session (no Wayland socket, no Wayland compositor installed, `XDG_SESSION_TYPE` unset). Per the isolation policy, **no local test was performed and no part of the host's X11 configuration was altered to enable one.** The current status should be recorded as "sandbox-verified, no local session available".
2. **The layer-shell protocol (Tier 1) has never actually been executed.** The sandbox compositor does not provide it, and no wlroots-family compositor is present on the host. That path currently has capability-probing code only, with no hardware data.
3. **Never run under a real desktop compositor (GNOME / KDE).** The availability of window positioning and always-on-top in Tier 2's X11 compatibility layer is inferred from convention and is not confirmed on hardware.
4. **Multi-monitor and fractional scaling are untested.**
5. **Buffer management.** The protocol prototype uses a single buffer and does not handle buffer-release events; a production implementation requires double buffering.
6. **Compositor caveat.** The sandbox compositor uses pixman pure-CPU rasterisation, whereas real desktops generally composite on the GPU, so the compositor-side figures here are **pessimistic**. Directional conclusions are unaffected; absolute values must not be extrapolated directly.

---

## 7. 复现方式 / Reproduction

**中**

```bash
cd wayland

# 1) 起测试床（不需要 root；合成器与依赖已解压到用户目录）
#    根目录默认 ~/wayland-test，可用 WAYLAND_TESTBED 覆盖
bash 起合成器.sh headless      # 无头：跑性能
bash 起合成器.sh x11           # 嵌套在真实桌面里：跑像素与点击穿透

# 2) 客户端环境
export XDG_RUNTIME_DIR=~/wayland-test/rt
export WAYLAND_DISPLAY=wayland-test        # x11 后端则是 wayland-x11
export WESTON_PID=$(cat ~/wayland-test/weston.pid)   # 让脚本能量到合成器 CPU

# 3) 接口表校验（需要 wayland-scanner：libwayland-bin 或 wayland-utils）
export WAYLAND_SCANNER=/path/to/wayland-scanner      # 不在 PATH 里时显式指定
python3 验表2.py

# 4) 性能：四种提交策略
python3 原型.py --模式=小窗 --秒=8
python3 原型.py --模式=全屏 --秒=8
python3 原型.py --模式=全屏局部 --秒=8
SW=1920 SH=1080 SEC=8 python3 子表面.py

# 5) 点击穿透端到端（需要 x11 嵌套后端）
CT_W=900 CT_H=560 CT_SEC=14 python3 点穿.py &
python3 敲.py <屏幕X> <屏幕Y>
```

协议描述文件与 `wayland-scanner` 均由运行时查找：优先环境变量 `WAYLAND_PROTOCOLS_DIR` / `WAYLAND_SCANNER`，其次常见系统目录，最后是容器化运行时里随附的副本。**代码中不含任何本机绝对路径。**

**EN**

```bash
cd wayland

# 1) Start the testbed (no root; the compositor and its dependencies are already extracted)
#    Root defaults to ~/wayland-test and can be overridden with WAYLAND_TESTBED
bash 起合成器.sh headless      # headless: performance runs
bash 起合成器.sh x11           # nested in the real desktop: pixels and click-through

# 2) Client environment
export XDG_RUNTIME_DIR=~/wayland-test/rt
export WAYLAND_DISPLAY=wayland-test        # wayland-x11 for the X11 backend
export WESTON_PID=$(cat ~/wayland-test/weston.pid)   # lets the scripts read compositor CPU

# 3) Interface-table verification (needs wayland-scanner: libwayland-bin or wayland-utils)
export WAYLAND_SCANNER=/path/to/wayland-scanner      # only if not on PATH
python3 验表2.py

# 4) Performance: four commit strategies
python3 原型.py --模式=小窗 --秒=8
python3 原型.py --模式=全屏 --秒=8
python3 原型.py --模式=全屏局部 --秒=8
SW=1920 SH=1080 SEC=8 python3 子表面.py

# 5) Click-through end-to-end (requires the nested X11 backend)
CT_W=900 CT_H=560 CT_SEC=14 python3 点穿.py &
python3 敲.py <screen-x> <screen-y>
```

Protocol description files and `wayland-scanner` are resolved at runtime: the `WAYLAND_PROTOCOLS_DIR` / `WAYLAND_SCANNER` environment variables take priority, then common system directories, then copies bundled inside containerised runtimes. **No absolute local path appears anywhere in the code.**

---

## 8. 文件清单 / File Inventory

| 文件 | 作用 |
|---|---|
| `wlraw.py` | 纯 `ctypes` 的 Wayland 底层库：协议表生成、代理对象、事件循环、协议文件定位 |
| `验表2.py` | 用 `wayland-scanner` 的产出逐字段校验接口表生成器 |
| `原型.py` | 四种提交策略的性能实测（小窗 / 全屏整屏 / 全屏局部 / — ） |
| `子表面.py` | 子表面方案：父面全透明提交一次 + 宠物挂子面 |
| `点穿.py` | 点击穿透端到端验证（核心协议输入区 + 真鼠标注入） |
| `敲.py` | 向指定屏幕坐标注入真实鼠标点击（`libXtst`） |
| `起合成器.sh` | 无头 / X11 嵌套两种后端的测试床启动脚本 |

| File | Purpose |
|---|---|
| `wlraw.py` | Pure-`ctypes` Wayland layer: table generation, proxy objects, event loop, protocol-file discovery |
| `验表2.py` | Field-by-field verification of the table generator against `wayland-scanner` output |
| `原型.py` | Performance runs for the commit strategies (small window / full damage / partial damage) |
| `子表面.py` | Sub-surface approach: fully transparent parent committed once, shape on a sub-surface |
| `点穿.py` | Click-through end-to-end verification (core-protocol input region plus real mouse injection) |
| `敲.py` | Inject real mouse clicks at absolute screen coordinates (`libXtst`) |
| `起合成器.sh` | Testbed launcher for the headless and nested-X11 backends |

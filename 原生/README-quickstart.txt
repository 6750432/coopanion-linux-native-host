Coopanion Native Host — Quickstart（先看这里）
================================
（Coopanion on Linux：把「宠物窗口」用 Python + PySide6 重写，替掉 Electron/QtWebEngine）

这是什么
--------
角色还是上游仓库里那只 **web/whale（蓝发鲸鱼女仆）**，骨骼/弹簧/脸部绘制全部照搬 figure.js 与 rig.js 的算法，
只把「画出来」这一步从 WebGL2 换成了 QPainter（CPU 光栅）。
**核心（cortico / desktop-pet world）一行都没改** —— 走的是你们设计好的扩展点
`CORTICO_DESKTOP_PET_HOST` + 页面里的 `window.petHost` 机制。

怎么用（两种，同一个文件）
--------------------------
1) 直接双击 / 运行（演示模式，不需要装任何东西）：
       ./coopanion-native-host-x86_64.AppImage
   她会出现在桌面右下角，并自带一小段剧本（说话、走动、坐下睡觉）。
   左上角牌子实时显示：**内存 / 渲染帧率 / CPU**；戳她、拖她、甩出去都有反应；
   点牌子右上角的 ✕ 退出。

2) 接你们自己的 Coopanion（宿主模式）：
       CORTICO_DESKTOP_PET_HOST='["/绝对路径/coopanion-native-host-x86_64.AppImage"]' <你们的启动命令>
   （AppImage 会收到 `--pet-url=http://127.0.0.1:<端口>/pet`，然后连上去当宠物窗口，
     用的就是官方宿主那套 WebSocket 协议：hello / say / act / walk / listen / thinking / prefs / ask。）

实测（同一台机器、同一个核心、背靠背量的）
------------------------------------------
                            官方 Electron/QtWebEngine 宿主    这个原生宿主
    内存 RSS                626 MB                            195 MB
    内存 PSS（诚实口径）     503 MB                            149 MB
    其中宠物端              约 509 MB                         约 78 MB
    CPU（60 秒 12 段均值）   64.1%（50.4~80.6%）               52.0%（19.0~82.2%）
    窗口出现                1.8 秒                            1.0 秒
    CPU 峰值（24 fps 巡航）  约一个核                          约半个核

    注：这台机器上 QtWebEngine 拿不到硬件 GPU（「GBM is not supported」→ 软件渲染），
    所以官方宿主那侧的数字偏悲观；两条路是在同一条件下量的，横向比是公平的。

还没做的
--------
音效、语音（麦克风）、右键菜单、装扮窗、键盘回话、prefs.scale 热更新。
（动作、表情、气泡打字机、被戳/被拎/被甩、睡着冒 z、听你说话的弧线 —— 这些都和网页版一样。）

包里有什么
----------
    AppRun                        启动脚本（设好 PYTHONHOME/LD_LIBRARY_PATH 后拉起下面的程序）
    usr/bin/python3.12            独立 CPython（python-build-standalone，不需要你系统里有 Python）
    usr/lib/python3.12/...        PySide6 6.11 里**只挑了用到的模块** + 它们的 .so 依赖闭包
    usr/share/coopanion-native-host/*.py         宿主源码（身体/小鱼/脸/网格/气泡/接线/面板…），
                                  没有编译、没有混淆，随手可读、随便改
    usr/share/coopanion-native-host/web/whale    你们的贴图与 model.json（原样带着）
    LICENSE / NOTICE              许可与出处

许可
----
上游资产（web/whale/** 与 model.json）来自 Pal-AI-Lab/Coopanion，MIT License（随包附全文）。
宿主代码由本项目另行编写，同样以 MIT 提供；如需并入上游或提出改动，欢迎开 issue。

自检（不想开窗口时）
--------------------
    ./coopanion-native-host-x86_64.AppImage --说明      # 打印本文件
    ./coopanion-native-host-x86_64.AppImage --秒=20     # 跑 20 秒自动退出（演示模式）

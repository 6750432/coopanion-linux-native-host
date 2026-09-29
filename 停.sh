#!/usr/bin/env bash
# 一键停掉 Coopanion 桌宠（核心 + 外壳）。只认精确脚本名，且绝不动调用者自己的进程树。
python3 - <<'PY'
import os, signal, time
祖先, p = set(), os.getpid()
while p > 1:
    祖先.add(p)
    try: p = int(open(f'/proc/{p}/stat').read().split()[3])
    except Exception: break
祖先.add(os.getppid())
标记 = ('起核心.cjs', '外壳.py', 'boot.ts')
ids = []
for d in os.listdir('/proc'):
    if not d.isdigit() or int(d) in 祖先: continue
    try: l = ' '.join(open(f'/proc/{d}/cmdline','rb').read().decode(errors='ignore').split('\0'))
    except Exception: continue
    if any(m in l for m in 标记): ids.append(int(d))
for p in ids:
    try: os.kill(p, signal.SIGTERM)
    except Exception: pass
time.sleep(1.2)
for p in ids:
    try: os.kill(p, 0); os.kill(p, signal.SIGKILL)
    except Exception: pass
print(f'  已停 {len(ids)} 个')
PY

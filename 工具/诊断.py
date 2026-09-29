#!/usr/bin/env python
# 诊断：单独开一个 QtWebEngine 页去载入桌宠页，把控制台/JS 报错/DOM 状态全打到 stdout。
# 用完就退，不影响常驻外壳（但会顶掉它的 WebSocket 连接，所以查完要重启外壳）。
# 用法：python 诊断.py [url] [等待秒数]
import json
import sys

from PySide6.QtCore import QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7797/pet"
等待 = int(sys.argv[2]) if len(sys.argv) > 2 else 12

# 在页面最早期装一个错误收集器（unhandledrejection 才是动态 import 失败的真凶）
钩子 = r"""
window.__errs = [];
addEventListener('error', e => window.__errs.push('error: ' + (e.message || e.type) + ' @' + (e.filename||'') + ':' + (e.lineno||0)));
addEventListener('unhandledrejection', e => {
  const r = e.reason;
  window.__errs.push('reject: ' + (r && (r.stack || r.message) || String(r)));
});
"""

探针 = r"""
(() => {
  const out = { errs: window.__errs, ready: document.readyState };
  out.svg = document.querySelectorAll('svg').length;
  out.canvas = document.querySelectorAll('canvas').length;
  out.img = document.querySelectorAll('img').length;
  out.hasHost = !!window.petHost;
  out.bodyBg = getComputedStyle(document.body).backgroundColor;
  const st = document.getElementById('stage') || document.querySelector('svg');
  if (st) { const r = st.getBoundingClientRect(); out.stage = [r.x|0, r.y|0, r.width|0, r.height|0]; }
  out.groups = [...document.querySelectorAll('svg > * > *')].map(g => g.tagName + (g.id ? '#' + g.id : '')).slice(0, 12);
  out.bodyLen = document.body.innerHTML.length;
  return JSON.stringify(out);
})()
"""


class 页(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
        名 = {0: "log", 1: "warn", 2: "ERROR", 3: "info"}.get(int(level), str(level))
        print(f"[网页/{名}] {message}   ({source.split('/')[-1]}:{line})", flush=True)


app = QApplication(sys.argv)
v = QWebEngineView()
p = 页(v)                                   # ⚠️ 这个组合收不到 loadFinished，所以只靠定时器，不靠信号
v.setPage(p)
s = QWebEngineScript()
s.setName("err-hook")
s.setSourceCode(钩子)
s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
p.scripts().insert(s)

p.load(QUrl(URL))
print(f"载入 {URL}，等 {等待} 秒…", flush=True)


def 查() -> None:
    def 收(v2) -> None:
        print("--- DOM 探针 ---", flush=True)
        print(v2, flush=True)
        app.quit()

    p.runJavaScript(探针, 0, 收)


QTimer.singleShot(等待 * 1000, 查)
QTimer.singleShot((等待 + 8) * 1000, app.quit)   # 兜底
app.exec()

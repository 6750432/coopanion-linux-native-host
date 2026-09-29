#!/usr/bin/env python
# 诊断二：把桌宠页放进一个**真的显示出来**的窗口（1920×1080），量出 #pet 的屏幕位置，
# 并把这个窗口自身截图存下来（grabshot.png），这样能直接看到鲸鱼画没画出来、画在哪。
# 用法：python 诊断2.py [url] [等待秒数]
import sys

from PySide6.QtCore import QRect, Qt, QTimer, QUrl
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineScript
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWidgets import QApplication

URL = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:7797/pet"
等待 = int(sys.argv[2]) if len(sys.argv) > 2 else 14

钩子 = r"""
window.__errs = [];
addEventListener('error', e => window.__errs.push('error: ' + (e.message || e.type) + ' @' + (e.filename||'') + ':' + (e.lineno||0)));
addEventListener('unhandledrejection', e => { const r = e.reason; window.__errs.push('reject: ' + (r && (r.stack || r.message) || String(r))); });
"""

探针 = r"""
(() => {
  const o = { errs: window.__errs, win: [innerWidth, innerHeight] };
  const pet = document.getElementById('pet');
  if (pet) { const r = pet.getBoundingClientRect(); o.pet = [r.x|0, r.y|0, r.width|0, r.height|0]; }
  const st = document.getElementById('stage');
  if (st) { const r = st.getBoundingClientRect(); o.stage = [r.x|0, r.y|0, r.width|0, r.height|0]; }
  const cv = document.querySelector('#pet canvas') || document.querySelector('canvas');
  if (cv) { const r = cv.getBoundingClientRect(); o.canvas = [r.x|0, r.y|0, r.width|0, r.height|0]; o.cvSize = [cv.width, cv.height]; }
  const svg = document.getElementById('stageSvg');
  if (svg) o.svgRect = [svg.getBoundingClientRect().width|0, svg.getBoundingClientRect().height|0];
  o.groups = [...document.querySelectorAll('#pet *')].map(e => e.tagName + '/' + (e.id||e.getAttribute('class')||'')).slice(0, 14);
  o.transform = pet ? pet.getAttribute('transform') : null;
  return JSON.stringify(o);
})()
"""


class 页(QWebEnginePage):
    def javaScriptConsoleMessage(self, level, message, line, source):  # noqa: N802
        名 = {0: "log", 1: "warn", 2: "ERROR", 3: "info"}.get(int(level), str(level))
        print(f"[网页/{名}] {message}   ({source.split('/')[-1]}:{line})", flush=True)


app = QApplication(sys.argv)
v = QWebEngineView()
p = 页(v)
v.setPage(p)
s = QWebEngineScript()
s.setName("err-hook")
s.setSourceCode(钩子)
s.setInjectionPoint(QWebEngineScript.InjectionPoint.DocumentCreation)
s.setWorldId(QWebEngineScript.ScriptWorldId.MainWorld)
p.scripts().insert(s)
v.page().setBackgroundColor(Qt.GlobalColor.transparent)
v.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
v.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
v.setGeometry(QRect(0, 0, 1920, 1080))
v.show()
p.load(QUrl(URL))
print(f"载入 {URL}（窗口已显示 1920×1080），等 {等待} 秒…", flush=True)


def 查() -> None:
    def 收(v2) -> None:
        print("--- 探针 ---", flush=True)
        print(v2, flush=True)
        img = v.grab()
        img.save("/tmp/诊断截图.png")
        print("已存 /tmp/诊断截图.png", flush=True)
        app.quit()

    p.runJavaScript(探针, 0, 收)


QTimer.singleShot(等待 * 1000, 查)
QTimer.singleShot((等待 + 10) * 1000, app.quit)
app.exec()

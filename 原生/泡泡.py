#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""气泡窗 —— 她说话时头顶那个圆角小牌子（网页那边是 <div class="bubble">）。

网页里气泡是长在页面上的，页面就是一整屏；咱们的窗口只有 360×360，放不下气泡，所以
单独开一个小窗：不抢焦点、不吃鼠标（点上去等于点桌面）、跟着她脑袋走。

样式照 pet.css 抄：底色 #151A22、字色 #E9EDF2、圆角 18、2.5 像素描边（取配色的强调色）、
右下角一个小三角尾巴；「听了半天」那种用虚线框、不画尾巴。
"""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

底色 = QColor("#151A22")
字色 = QColor("#E9EDF2")
灰字 = QColor("#8C95A3")
内边距 = (10, 14)          # 上下、左右
圆角 = 18.0
描边 = 2.5
最大宽 = 300
字号 = 14.5


class 气泡窗(QWidget):
    """Borderless, input-transparent speech bubble pinned above the pet.
    
    无边框、点击穿透的气泡小窗，钉在宠物头顶。
    """
    def __init__(self, 强调色: QColor | str = "#4D6BFE"):
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint |
                            Qt.WindowType.Tool | Qt.WindowType.WindowDoesNotAcceptFocus |
                            Qt.WindowType.WindowTransparentForInput | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.边色 = QColor(强调色) if not isinstance(强调色, QColor) else 强调色
        self.字体 = QFont()
        for 名 in ("Noto Sans CJK SC", "Source Han Sans SC", "WenQuanYi Micro Hei", "Sans Serif"):
            self.字体.setFamily(名)
            if QFontMetrics(self.字体).horizontalAdvance("汉字") > 0:
                break
        self.字体.setPointSizeF(字号)
        self.全文 = ""
        self.已显 = 0
        self.种类 = "say"
        self.尾巴 = 0.5
        self.显示中 = False
        self.候选: list[str] = []
        self.点击 = None
        self.点过 = None
        self.锚 = (0, 0)
        self.setFixedSize(1, 1)

    def 设选项(self, 候选: list[str], 回调):
        """问句的选项按钮。有按钮的时候这扇窗才吃鼠标（平时点上去等于点桌面）。"""
        self.候选 = list(候选 or [])
        self.点击 = 回调
        if self.候选:
            self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, False)
            self.show()
        else:
            self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
        self._量尺寸()
        self.update()

    def _选项框(self, i: int) -> QRectF:
        """第 i 个按钮的矩形（画和点都用它，保证一致）。"""
        顶 = self.height() - 8 - (len(self.候选) - i) * 30 - 4
        return QRectF(内边距[1] - 4, 顶, self.width() - (内边距[1] - 4) * 2, 26)

    # ── 内容 ──────────────────────────────────────────────
    def 设(self, 全文: str, 已显: int, 种类: str = "say", 尾巴: float | None = None):
        """全文用来定尺寸（免得打字时窗口一跳一跳），已显用来决定现在画到第几个字。"""
        if not 全文 and not self.候选:
            self.收(); return
        改尺寸 = (全文 != self.全文) or (种类 != self.种类) or (已显 == 0 and self.全文 == "")
        self.全文, self.种类 = 全文, 种类
        self.已显 = max(0, min(已显, len(全文)))
        if 尾巴 is not None:
            self.尾巴 = 尾巴
        if 改尺寸:
            self._量尺寸()
        self.显示中 = True
        self.show()
        self.update()

    def 收(self):
        if self.显示中:
            self.显示中 = False
            self.hide()

    def _量尺寸(self):
        宽上限 = 最大宽 - 内边距[1] * 2
        格 = QFontMetrics(self.字体)
        最大行 = 格.boundingRect(QRect(0, 0, 宽上限, 10000), Qt.TextFlag.TextWordWrap, self.全文 or " ")
        宽 = min(最大宽, 最大行.width() + 内边距[1] * 2)
        for c in self.候选:
            宽 = max(宽, min(最大宽, 格.horizontalAdvance(c) + 内边距[1] * 2 + 24))
        高 = 最大行.height() + 内边距[0] * 2 + 8 + (len(self.候选) * 30 + 6 if self.候选 else 0)
        self.setFixedSize(max(40, int(宽)), max(30, int(高)))


    def 摆(self, 锚x: float, 锚y: float, 屏: QRect):
        """把气泡摆在她脑袋上方（锚点 = 头顶），不出屏幕。"""
        if not self.显示中:
            return
        self.锚 = (锚x, 锚y)
        x = int(锚x - self.width() * self.尾巴)
        y = int(锚y - self.height())
        x = max(屏.left() + 4, min(屏.right() - self.width() - 4, x))
        y = max(屏.top() + 4, min(屏.bottom() - self.height() - 4, y))
        if (x, y) != (self.x(), self.y()):
            self.move(x, y)

    # ── 画 ────────────────────────────────────────────────
    def paintEvent(self, ev):
        if not self.全文:
            return
        pen = QPainter(self)
        try:
            pen.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            pen.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
            h = self.height() - 8
            方 = QRectF(1.5, 1.5, self.width() - 3, h - 3)
            路 = QPainterPath()
            路.addRoundedRect(方, 圆角, 圆角)
            pen.setBrush(底色)
            if self.种类 == "heard":
                pen.setPen(QPen(self.边色, 描边, Qt.PenStyle.DashLine))
            else:
                pen.setPen(QPen(self.边色, 描边))
            pen.drawPath(路)
            if self.种类 != "heard":       # 小尾巴
                尾x = 方.left() + 方.width() * self.尾巴
                尾 = QPainterPath(QPointF(尾x - 6, h - 2))
                尾.lineTo(QPointF(尾x + 6, h - 2))
                尾.lineTo(QPointF(尾x, h + 6))
                尾.closeSubpath()
                pen.setPen(Qt.PenStyle.NoPen)
                pen.setBrush(底色)
                pen.drawPath(尾)
                笔2 = QPen(self.边色, 描边)
                pen.setPen(笔2)
                pen.drawLine(QPointF(尾x - 6, h - 1.6), QPointF(尾x, h + 6))
                pen.drawLine(QPointF(尾x, h + 6), QPointF(尾x + 6, h - 1.6))
            # 正文
            pen.setPen(字色)
            pen.setFont(self.字体)
            文方 = QRectF(内边距[1], 内边距[0] - 1, self.width() - 内边距[1] * 2, h - 内边距[0] * 2 + 4)
            pen.drawText(文方, int(Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft), self.全文[:self.已显])
            # 选项按钮
            if self.候选:
                f2 = QFont(self.字体); f2.setPointSizeF(字号 - 1)
                pen.setFont(f2)
                for i, c in enumerate(self.候选):
                    框 = self._选项框(i)
                    选中 = (self.点过 == i)
                    pen.setPen(QPen(self.边色, 1.5))
                    pen.setBrush(QColor(self.边色.red(), self.边色.green(), self.边色.blue(),
                                        70 if 选中 else 30))
                    pen.drawRoundedRect(框, 11, 11)
                    pen.setPen(字色 if not 选中 else self.边色)
                    pen.drawText(框.adjusted(10, 0, -8, 0), int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                                 f"{i + 1}. {c}")
                pen.setFont(self.字体)
            # 打字光标
            if self.已显 < len(self.全文) and not self.候选:
                格 = QFontMetrics(self.字体)
                行 = self.全文[:self.已显].count("\n")
                尾行 = self.全文[:self.已显].split("\n")[-1]
                宽 = 格.horizontalAdvance(尾行)
                pen.fillRect(QRectF(文方.left() + min(宽, 文方.width() - 3),
                                    文方.top() + 格.height() * (0.15 + 行), 2, 格.height() * .95), self.边色)
        finally:
            pen.end()

    def mousePressEvent(self, ev):
        if not self.候选 or self.点击 is None:
            return
        y = ev.position().y()
        for i in range(len(self.候选)):
            if self._选项框(i).contains(ev.position()):
                self.点过 = i
                self.update()
                回 = self.点击
                self.候选 = []
                self.setWindowFlag(Qt.WindowType.WindowTransparentForInput, True)
                回(i)
                return
        _ = y

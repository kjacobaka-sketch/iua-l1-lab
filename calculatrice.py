"""
Calculatrice moderne — PySide6 (Qt6), interface native.

Installation :  pip install PySide6
Lancement    :  python calculatrice.py

Fonctionnalités :
  - Mode clair / sombre avec transition animée (préférence mémorisée)
  - Historique des calculs (panneau coulissant, 50 entrées, mémorisé)
  - Fond dégradé animé en continu
  - Boutons arrondis : survol, appui, effet "ripple"
  - Résultat en direct pendant la saisie, avec fondu
  - Clavier complet : chiffres, + - * / % . Entrée, Retour arrière, Échap
        T = changer de thème, H = historique
  - Évaluation sécurisée (pas de eval(), analyse via le module ast)
"""

import ast
import json
import math
import operator
import re
import sys

from PySide6.QtCore import (
    QEasingCurve, QPointF, QPropertyAnimation, QRect, QRectF, QSettings, QSize,
    Qt, QTimer, QVariantAnimation,
)
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen,
)
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QFrame, QGraphicsOpacityEffect, QGridLayout,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget,
)

OP_CHARS = "+−×÷"
NUM_END = re.compile(r"(\d+\.?\d*|\.\d+)$")        # dernier nombre de l'expression
NEG_WRAP = re.compile(r"\(−(\d+\.?\d*)\)$")        # nombre négatif entre parenthèses
HISTORY_MAX = 50


# --------------------------------------------------------------------------- #
#  Logique de calcul (sécurisée)
# --------------------------------------------------------------------------- #
_BIN_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
}


def evaluate(expr: str) -> float:
    """Évalue une expression arithmétique sans utiliser eval()."""
    s = (expr.replace("×", "*").replace("÷", "/")
             .replace("−", "-").replace("%", "/100"))

    def ev(node):
        if isinstance(node, ast.Expression):
            return ev(node.body)
        if (isinstance(node, ast.Constant)
                and isinstance(node.value, (int, float))
                and not isinstance(node.value, bool)):
            return float(node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in _BIN_OPS:
            return _BIN_OPS[type(node.op)](ev(node.left), ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        raise ValueError("Expression invalide")

    return ev(ast.parse(s, mode="eval"))


def format_number(v: float) -> str:
    if not math.isfinite(v):
        raise ValueError("Résultat non fini")
    if v == int(v) and abs(v) < 1e15:
        text = str(int(v))
    else:
        text = f"{v:.12g}"
    return text.replace("-", "−")


# --------------------------------------------------------------------------- #
#  Couleurs et thèmes
# --------------------------------------------------------------------------- #
def mix(a, b, t: float) -> QColor:
    a, b = QColor(a), QColor(b)
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )


def css(c: QColor) -> str:
    return f"rgba({c.red()},{c.green()},{c.blue()},{c.alpha() / 255:.3f})"


# nom: (valeur sombre, valeur claire)
PALETTE = {
    "bg1a": ("#12122B", "#EEF1FF"),
    "bg1b": ("#2B1559", "#F7E9FF"),
    "bg2a": ("#0A1D3B", "#E2F1FF"),
    "bg2b": ("#4B1342", "#FFE6F0"),
    "card": (QColor(255, 255, 255, 18), QColor(255, 255, 255, 175)),
    "card_border": (QColor(255, 255, 255, 26), QColor(110, 110, 190, 45)),
    "text": ("#FFFFFF", "#1D2040"),
    "sub": ("#9AA0D0", "#6F76AA"),
    "panel": (QColor(26, 26, 56, 245), QColor(255, 255, 255, 245)),
    "item": (QColor(255, 255, 255, 14), QColor(110, 110, 190, 22)),
    "item_hover": (QColor(255, 255, 255, 34), QColor(110, 110, 190, 48)),
    "accent": ("#FF7BAA", "#E0356F"),
    "btn_border": (QColor(255, 255, 255, 30), QColor(100, 100, 170, 40)),
    "shadow": (QColor(0, 0, 0, 0), QColor(70, 70, 140, 45)),
}

# type: ((base, survol, texte) sombre, (base, survol, texte) clair)
STYLES = {
    "num": (("#262A47", "#363C66", "#FFFFFF"), ("#FFFFFF", "#EBEEFF", "#1D2040")),
    "fn":  (("#3A3F6B", "#4D5493", "#C9CCFF"), ("#DCE0FF", "#C8CFFF", "#3B3F7A")),
    "clr": (("#C2415A", "#E55A75", "#FFFFFF"), ("#FF7F95", "#FF6279", "#FFFFFF")),
    "op":  (("#7C5CFF", "#9879FF", "#FFFFFF"), ("#7C5CFF", "#9879FF", "#FFFFFF")),
    "eq":  (("#FF4F8B", "#FF7BAA", "#FFFFFF"), ("#FF4F8B", "#FF7BAA", "#FFFFFF")),
}

LAYOUT = [
    [("C", "clr"), ("⌫", "fn"), ("%", "fn"), ("÷", "op")],
    [("7", "num"), ("8", "num"), ("9", "num"), ("×", "op")],
    [("4", "num"), ("5", "num"), ("6", "num"), ("−", "op")],
    [("1", "num"), ("2", "num"), ("3", "num"), ("+", "op")],
    [("±", "fn"), ("0", "num"), (".", "num"), ("=", "eq")],
]


# --------------------------------------------------------------------------- #
#  Bouton animé
# --------------------------------------------------------------------------- #
class AnimatedButton(QPushButton):
    def __init__(self, label, kind, font_size=20, parent=None):
        super().__init__(label, parent)
        self.kind = kind
        dark = STYLES[kind][0]
        self.base, self.hover_c, self.fg = QColor(dark[0]), QColor(dark[1]), QColor(dark[2])
        self.border = QColor(255, 255, 255, 30)
        self.shadow = QColor(0, 0, 0, 0)
        self._font_size = font_size
        self._hover = 0.0
        self._press = 0.0
        self._ripple = 1.0
        self._ripple_pos = QPointF()

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(64, 52)

        self._a_hover = self._make_anim("_hover", 160)
        self._a_press = self._make_anim("_press", 110)
        self._a_ripple = self._make_anim("_ripple", 480)

    def apply(self, base, hover, fg, border, shadow):
        self.base, self.hover_c, self.fg = QColor(base), QColor(hover), QColor(fg)
        self.border, self.shadow = QColor(border), QColor(shadow)
        self.update()

    def _make_anim(self, attr, ms):
        a = QVariantAnimation(self)
        a.setDuration(ms)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)

        def on_value(v, name=attr):
            setattr(self, name, float(v))
            self.update()

        a.valueChanged.connect(on_value)
        return a

    def _go(self, anim, attr, target):
        anim.stop()
        anim.setStartValue(getattr(self, attr))
        anim.setEndValue(target)
        anim.start()

    def _start_ripple(self, pos):
        self._ripple_pos = QPointF(pos)
        self._ripple = 0.0
        self._go(self._a_ripple, "_ripple", 1.0)

    def enterEvent(self, e):
        self._go(self._a_hover, "_hover", 1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._go(self._a_hover, "_hover", 0.0)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        self._go(self._a_press, "_press", 1.0)
        self._start_ripple(e.position())
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._go(self._a_press, "_press", 0.0)
        super().mouseReleaseEvent(e)

    def tap(self):
        """Simule visuellement un appui (utilisé pour le clavier)."""
        self._start_ripple(QPointF(self.width() / 2, self.height() / 2))
        self._go(self._a_press, "_press", 1.0)
        QTimer.singleShot(110, lambda: self._go(self._a_press, "_press", 0.0))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()

        scale = 1.0 - 0.06 * self._press
        p.translate(w / 2, h / 2)
        p.scale(scale, scale)
        p.translate(-w / 2, -h / 2)

        rect = QRectF(3, 3, w - 6, h - 9)
        radius = min(rect.width(), rect.height()) * 0.32
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)

        if self.shadow.alpha() > 0:                 # ombre douce (mode clair)
            sp = QPainterPath(path)
            sp.translate(0, 3)
            p.fillPath(sp, self.shadow)

        color = mix(self.base, self.hover_c, self._hover)
        grad = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        grad.setColorAt(0, color.lighter(112))
        grad.setColorAt(1, color.darker(106))
        p.fillPath(path, grad)

        p.setPen(QPen(self.border, 1))
        p.drawPath(path)

        if self._ripple < 1.0:                      # effet "ripple"
            p.save()
            p.setClipPath(path)
            r = max(w, h) * 1.2 * self._ripple
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, int(90 * (1 - self._ripple))))
            p.drawEllipse(self._ripple_pos, r, r)
            p.restore()

        f = QFont(self.font())
        f.setPointSize(self._font_size)
        f.setWeight(QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(self.fg)
        p.drawText(rect, Qt.AlignmentFlag.AlignCenter, self.text())


# --------------------------------------------------------------------------- #
#  Bouton-icône dessiné (soleil / lune / horloge)
# --------------------------------------------------------------------------- #
class IconButton(QPushButton):
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind                 # "theme" ou "history"
        self.color = QColor("white")
        self.progress = 0.0              # 0 = sombre (lune), 1 = clair (soleil)
        self._hover = 0.0
        self.setFixedSize(40, 40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)

        self._a = QVariantAnimation(self)
        self._a.setDuration(160)
        self._a.valueChanged.connect(self._on_hover)

    def _on_hover(self, v):
        self._hover = float(v)
        self.update()

    def enterEvent(self, e):
        self._a.stop()
        self._a.setStartValue(self._hover)
        self._a.setEndValue(1.0)
        self._a.start()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._a.stop()
        self._a.setStartValue(self._hover)
        self._a.setEndValue(0.0)
        self._a.start()
        super().leaveEvent(e)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c = QColor(self.color)

        bg = QColor(c)
        bg.setAlpha(int(40 * self._hover))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawEllipse(self.rect().adjusted(2, 2, -2, -2))

        p.translate(self.width() / 2, self.height() / 2)
        pen = QPen(c, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        if self.kind == "history":
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(QPointF(0, 0), 9.5, 9.5)
            p.drawLine(QPointF(0, 0), QPointF(0, -5.5))
            p.drawLine(QPointF(0, 0), QPointF(4.5, 2.5))
            return

        t = self.progress
        # Soleil (visible en mode clair)
        p.save()
        p.setOpacity(t)
        p.rotate(-90 * (1 - t))
        p.setPen(pen)
        p.setBrush(c)
        p.drawEllipse(QPointF(0, 0), 4.5, 4.5)
        for i in range(8):
            p.save()
            p.rotate(i * 45)
            p.drawLine(QPointF(0, -8), QPointF(0, -11))
            p.restore()
        p.restore()
        # Lune (visible en mode sombre)
        p.save()
        p.setOpacity(1 - t)
        p.rotate(90 * t)
        outer, inner = QPainterPath(), QPainterPath()
        outer.addEllipse(QPointF(0, 0), 9, 9)
        inner.addEllipse(QPointF(4.5, -3.5), 7.5, 7.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(c)
        p.drawPath(outer.subtracted(inner))
        p.restore()


# --------------------------------------------------------------------------- #
#  Fenêtre principale
# --------------------------------------------------------------------------- #
class Calculator(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Calculatrice")
        self.setMinimumSize(360, 600)
        self.resize(390, 680)

        self.expr = ""
        self.last_expr = ""
        self.just_evaluated = False
        self.error = False
        self._phase = 0.0
        self._faded_in = False
        self.history_open = False
        self._res_text = "0"
        self._top_text = ""

        # Préférences mémorisées
        self.settings = QSettings("CalculatriceModerne", "Calculatrice")
        self.tm = 1.0 if self.settings.value("theme", "dark") == "light" else 0.0
        self._theme_target = self.tm
        try:
            self.history = [list(x) for x in json.loads(self.settings.value("history", "[]"))]
        except Exception:
            self.history = []

        # Fond animé
        self._bg = QVariantAnimation(self)
        self._bg.setStartValue(0.0)
        self._bg.setEndValue(1.0)
        self._bg.setDuration(14000)
        self._bg.setLoopCount(-1)
        self._bg.valueChanged.connect(self._on_phase)
        self._bg.start()

        # Transition de thème
        self._theme_anim = QVariantAnimation(self)
        self._theme_anim.setDuration(450)
        self._theme_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._theme_anim.valueChanged.connect(self._on_theme_tick)

        self._build_ui()
        self._build_history_panel()
        self.apply_theme()
        self.refresh(pulse=False)

    # ----- couleurs
    def col(self, name) -> QColor:
        d, l = PALETTE[name]
        return mix(d, l, self.tm)

    # ----- interface
    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(16)

        self.display_frame = QFrame()
        self.display_frame.setObjectName("display")
        fl = QVBoxLayout(self.display_frame)
        fl.setContentsMargins(14, 10, 22, 18)
        fl.setSpacing(2)

        top = QHBoxLayout()
        top.setSpacing(2)
        self.btn_theme = IconButton("theme")
        self.btn_theme.setToolTip("Changer de thème (T)")
        self.btn_theme.clicked.connect(self.toggle_theme)
        self.btn_hist = IconButton("history")
        self.btn_hist.setToolTip("Historique (H)")
        self.btn_hist.clicked.connect(self.toggle_history)

        self.expr_label = QLabel("")
        self.expr_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        f = self.expr_label.font()
        f.setPointSize(15)
        self.expr_label.setFont(f)

        top.addWidget(self.btn_theme)
        top.addWidget(self.btn_hist)
        top.addSpacing(10)
        top.addWidget(self.expr_label, 1)

        self.result_label = QLabel("0")
        self.result_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self._opacity = QGraphicsOpacityEffect(self.result_label)
        self.result_label.setGraphicsEffect(self._opacity)
        self._pulse_anim = QPropertyAnimation(self._opacity, b"opacity", self)
        self._pulse_anim.setDuration(240)
        self._pulse_anim.setStartValue(0.25)
        self._pulse_anim.setEndValue(1.0)
        self._pulse_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        fl.addLayout(top)
        fl.addWidget(self.result_label, 1)
        root.addWidget(self.display_frame, 2)

        grid = QGridLayout()
        grid.setSpacing(10)
        self.buttons = {}
        for r, row in enumerate(LAYOUT):
            for c, (label, kind) in enumerate(row):
                btn = AnimatedButton(label, kind,
                                     font_size=22 if kind in ("op", "eq") else 20)
                btn.clicked.connect(lambda _=False, k=label: self.on_key(k))
                grid.addWidget(btn, r, c)
                self.buttons[label] = btn
        root.addLayout(grid, 5)

    def _build_history_panel(self):
        self.panel = QFrame(self)
        self.panel.setObjectName("hist")
        pl = QVBoxLayout(self.panel)
        pl.setContentsMargins(18, 16, 18, 16)
        pl.setSpacing(8)

        head = QHBoxLayout()
        title = QLabel("Historique")
        title.setObjectName("ht")
        tf = title.font()
        tf.setPointSize(16)
        tf.setWeight(QFont.Weight.DemiBold)
        title.setFont(tf)
        self.clear_btn = QPushButton("Effacer")
        self.clear_btn.setObjectName("hclear")
        self.clear_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clear_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.clear_btn.clicked.connect(self.clear_history)
        head.addWidget(title)
        head.addStretch(1)
        head.addWidget(self.clear_btn)
        pl.addLayout(head)

        self.hist_list = QListWidget()
        self.hist_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.hist_list.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.hist_list.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.hist_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.hist_list.setCursor(Qt.CursorShape.PointingHandCursor)
        self.hist_list.itemClicked.connect(self._on_history_click)

        self.hist_empty = QLabel("Aucun calcul pour le moment")
        self.hist_empty.setObjectName("hempty")
        self.hist_empty.setAlignment(Qt.AlignmentFlag.AlignCenter)

        pl.addWidget(self.hist_list, 1)
        pl.addWidget(self.hist_empty, 1)

        self._panel_anim = QPropertyAnimation(self.panel, b"geometry", self)
        self._panel_anim.setDuration(380)
        self._panel_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._panel_anim.finished.connect(self._on_panel_done)
        self.panel.hide()

    # ----- thème
    def toggle_theme(self):
        self._theme_target = 0.0 if self._theme_target > 0.5 else 1.0
        self._theme_anim.stop()
        self._theme_anim.setStartValue(self.tm)
        self._theme_anim.setEndValue(self._theme_target)
        self._theme_anim.start()
        self.settings.setValue("theme", "light" if self._theme_target > 0.5 else "dark")

    def _on_theme_tick(self, v):
        self.tm = float(v)
        self.apply_theme()

    def apply_theme(self):
        c, tm = self.col, self.tm
        for btn in self.buttons.values():
            dk, lt = STYLES[btn.kind]
            btn.apply(mix(dk[0], lt[0], tm), mix(dk[1], lt[1], tm), mix(dk[2], lt[2], tm),
                      c("btn_border"), c("shadow"))
        for ib in (self.btn_theme, self.btn_hist):
            ib.color = c("text")
            ib.progress = tm
            ib.update()

        self.display_frame.setStyleSheet(
            f"#display{{background:{css(c('card'))};"
            f"border:1px solid {css(c('card_border'))};border-radius:26px;}}")
        self.expr_label.setStyleSheet(f"color:{css(c('sub'))};background:transparent;")
        self.result_label.setStyleSheet(f"color:{css(c('text'))};background:transparent;")
        self.panel.setStyleSheet(f"""
            #hist{{background:{css(c('panel'))};border:1px solid {css(c('card_border'))};
                  border-radius:26px;}}
            #hist QLabel{{background:transparent;}}
            #ht{{color:{css(c('text'))};}}
            #hempty{{color:{css(c('sub'))};}}
            #he{{color:{css(c('sub'))};}}
            #hr{{color:{css(c('text'))};}}
            #hclear{{color:{css(c('accent'))};background:transparent;border:none;
                    padding:6px 12px;border-radius:12px;font-weight:600;}}
            #hclear:hover{{background:{css(c('item_hover'))};}}
            QListWidget{{background:transparent;border:none;outline:0;}}
            QListWidget::item{{background:{css(c('item'))};border-radius:16px;margin:3px 0;}}
            QListWidget::item:hover{{background:{css(c('item_hover'))};}}
            QScrollBar:vertical{{width:6px;background:transparent;margin:4px 0;}}
            QScrollBar::handle:vertical{{background:{css(c('item_hover'))};
                                        border-radius:3px;min-height:24px;}}
            QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{{height:0;}}
        """)
        self.update()

    # ----- fond dégradé animé
    def _on_phase(self, v):
        self._phase = float(v)
        self.update()

    def paintEvent(self, _):
        t = (1 - math.cos(2 * math.pi * self._phase)) / 2
        c1 = mix(self.col("bg1a"), self.col("bg1b"), t)
        c2 = mix(self.col("bg2a"), self.col("bg2b"), t)
        g = QLinearGradient(0, 0, self.width(), self.height())
        g.setColorAt(0, c1)
        g.setColorAt(1, c2)
        p = QPainter(self)
        p.fillRect(self.rect(), g)

    def showEvent(self, e):
        super().showEvent(e)
        if not self._faded_in:                     # fondu à l'ouverture
            self._faded_in = True
            self.setWindowOpacity(0.0)
            self._fade = QPropertyAnimation(self, b"windowOpacity", self)
            self._fade.setDuration(500)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._fade.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_texts()
        if self.panel.isVisible() and self._panel_anim.state() != QPropertyAnimation.State.Running:
            self.panel.setGeometry(self._panel_rect(self.history_open))

    # ----- historique
    def _panel_rect(self, opened: bool) -> QRect:
        top = self.display_frame.geometry().bottom() + 16
        r = QRect(20, top, self.width() - 40, self.height() - top - 20)
        if not opened:
            r.moveTop(self.height())
        return r

    def toggle_history(self):
        self._panel_anim.stop()
        if not self.history_open:
            self.history_open = True
            self._rebuild_history()
            self.panel.setGeometry(self._panel_rect(False))
            self.panel.show()
            self.panel.raise_()
            self._panel_anim.setStartValue(self.panel.geometry())
            self._panel_anim.setEndValue(self._panel_rect(True))
        else:
            self.history_open = False
            self._panel_anim.setStartValue(self.panel.geometry())
            self._panel_anim.setEndValue(self._panel_rect(False))
        self._panel_anim.start()

    def _on_panel_done(self):
        if not self.history_open:
            self.panel.hide()

    def _rebuild_history(self):
        self.hist_list.clear()
        has = bool(self.history)
        self.hist_list.setVisible(has)
        self.clear_btn.setVisible(has)
        self.hist_empty.setVisible(not has)
        maxw = max(120, self.width() - 130)

        for expr, res in reversed(self.history):
            item = QListWidgetItem(self.hist_list)
            item.setSizeHint(QSize(0, 68))
            item.setData(Qt.ItemDataRole.UserRole, (expr, res))

            w = QWidget()
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            lay = QVBoxLayout(w)
            lay.setContentsMargins(16, 8, 16, 8)
            lay.setSpacing(0)

            e = QLabel()
            e.setObjectName("he")
            ef = e.font()
            ef.setPointSize(11)
            e.setFont(ef)
            e.setText(QFontMetrics(ef).elidedText(f"{expr} =", Qt.TextElideMode.ElideLeft, maxw))
            e.setAlignment(Qt.AlignmentFlag.AlignRight)

            r = QLabel()
            r.setObjectName("hr")
            rf = r.font()
            rf.setPointSize(17)
            rf.setWeight(QFont.Weight.DemiBold)
            r.setFont(rf)
            r.setText(QFontMetrics(rf).elidedText(res, Qt.TextElideMode.ElideRight, maxw))
            r.setAlignment(Qt.AlignmentFlag.AlignRight)

            lay.addWidget(e)
            lay.addWidget(r)
            self.hist_list.setItemWidget(item, w)

    def add_history(self, expr, res):
        entry = [expr, res]
        if self.history and self.history[-1] == entry:
            return
        self.history.append(entry)
        self.history = self.history[-HISTORY_MAX:]
        self._save_history()
        if self.history_open:
            self._rebuild_history()

    def clear_history(self):
        self.history = []
        self._save_history()
        self._rebuild_history()

    def _save_history(self):
        self.settings.setValue("history", json.dumps(self.history, ensure_ascii=False))

    def _on_history_click(self, item):
        expr, res = item.data(Qt.ItemDataRole.UserRole)
        self.last_expr, self.expr = expr, res
        self.just_evaluated, self.error = True, False
        self.toggle_history()
        self.refresh()

    # ----- affichage
    def refresh(self, pulse=True):
        if self.error:
            top, res = "", "Erreur"
        elif self.just_evaluated:
            top, res = f"{self.last_expr} =", self.expr
        else:
            has_op = any(ch in self.expr[1:] for ch in OP_CHARS) or "%" in self.expr
            top = self.expr if has_op else ""
            if not has_op:
                res = self.expr or "0"
            else:
                try:
                    res = format_number(evaluate(self.expr.rstrip(OP_CHARS)))
                except Exception:
                    res = "0"
        self._top_text, self._res_text = top, res
        self._fit_texts()
        if pulse:
            self._pulse_anim.stop()
            self._pulse_anim.start()

    def _fit_texts(self):
        fm = QFontMetrics(self.expr_label.font())
        self.expr_label.setText(
            fm.elidedText(self._top_text, Qt.TextElideMode.ElideLeft,
                          max(40, self.expr_label.width() - 4)))
        self.result_label.setText(self._res_text)
        width = max(60, self.result_label.width() - 8)
        size = 54
        f = QFont(self.result_label.font())
        f.setWeight(QFont.Weight.Light)
        while size > 16:
            f.setPointSize(size)
            if QFontMetrics(f).horizontalAdvance(self._res_text) <= width:
                break
            size -= 2
        f.setPointSize(size)
        self.result_label.setFont(f)

    # ----- logique des touches
    def _implicit_mul(self):
        if self.expr and self.expr[-1] in "%)":
            self.expr += "×"

    def on_key(self, k: str):
        if self.error and k != "C":
            self.expr, self.error = "", False

        if k == "C":
            self.expr, self.last_expr = "", ""
            self.just_evaluated = self.error = False

        elif k.isdigit():
            if self.just_evaluated:
                self.expr, self.just_evaluated = "", False
            self._implicit_mul()
            m = NUM_END.search(self.expr)
            if m and m.group(0) == "0":
                self.expr = self.expr[:-1]
            self.expr += k

        elif k == ".":
            if self.just_evaluated:
                self.expr, self.just_evaluated = "", False
            m = NUM_END.search(self.expr)
            if m:
                if "." in m.group(0):
                    return
                self.expr += "."
            else:
                self._implicit_mul()
                self.expr += "0."

        elif k in OP_CHARS:
            self.just_evaluated = False
            if not self.expr:
                if k == "−":
                    self.expr = "−"
            elif self.expr[-1] in OP_CHARS:
                if len(self.expr) == 1:
                    return
                self.expr = self.expr[:-1] + k
            else:
                self.expr += k

        elif k == "%":
            if self.expr and (self.expr[-1].isdigit() or self.expr[-1] in ")%"):
                self.just_evaluated = False
                self.expr += "%"

        elif k == "⌫":
            if self.just_evaluated:
                self.expr, self.just_evaluated = "", False
            else:
                m = NEG_WRAP.search(self.expr)
                self.expr = self.expr[:m.start()] if m else self.expr[:-1]

        elif k == "±":
            self.just_evaluated = False
            m = NEG_WRAP.search(self.expr)
            if m:                                           # (−5) -> 5
                self.expr = self.expr[:m.start()] + m.group(1)
            elif re.fullmatch(r"−\d+\.?\d*", self.expr):    # −5 -> 5
                self.expr = self.expr[1:]
            else:
                m = NUM_END.search(self.expr)
                if not m:
                    return
                if m.start() == 0:                          # 5 -> −5
                    self.expr = "−" + self.expr
                else:                                       # 3+5 -> 3+(−5)
                    self.expr = self.expr[:m.start()] + f"(−{m.group(1)})"

        elif k == "=":
            if not self.expr or self.just_evaluated:
                return
            ok = False
            try:
                result = format_number(evaluate(self.expr.rstrip(OP_CHARS)))
                self.last_expr = self.expr.rstrip(OP_CHARS)
                self.expr = result
                self.just_evaluated = True
                ok = True
            except Exception:
                self.error = True
            if ok:
                self.add_history(self.last_expr, result)

        self.refresh()

    # ----- clavier
    def keyPressEvent(self, e):
        key, text = e.key(), e.text()
        mapping = {"*": "×", "/": "÷", "-": "−", ",": ".", "x": "×", "X": "×"}

        if text in ("t", "T"):
            self.toggle_theme()
            return
        if text in ("h", "H"):
            self.toggle_history()
            return
        if key == Qt.Key.Key_Escape and self.history_open:
            self.toggle_history()
            return

        k = None
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) or text == "=":
            k = "="
        elif key == Qt.Key.Key_Backspace:
            k = "⌫"
        elif key in (Qt.Key.Key_Escape, Qt.Key.Key_Delete):
            k = "C"
        elif text and text in "0123456789.+%":
            k = text
        elif text in mapping:
            k = mapping[text]

        if k and k in self.buttons:
            self.buttons[k].tap()
            self.on_key(k)
        else:
            super().keyPressEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = Calculator()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()

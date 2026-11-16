"""
Calcul Éclair — jeu de calcul mental (PySide6 / Qt6)  —  version 3.2 (corrigée)

Installation :  pip install PySide6
Lancement    :  python jeu_calcul.py

Corrections de la 3.2 :
  - les sélecteurs Mode / Opération envoient maintenant le nom complet de l'option
    (avant : « Zen », « Extrême » et « Mélange » faisaient planter le jeu)
  - mode Zen : Échap termine la partie et affiche les résultats
  - mode Extrême : le temps ne dépasse plus 15 secondes
  - politique de confidentialité mise à jour (mode et opération enregistrés)
"""

import atexit
import math
import os
import random
import shutil
import struct
import sys
import tempfile
import time
import wave

from PySide6.QtCore import (
    QEasingCurve, QEvent, QPointF, QPropertyAnimation, QRectF, QSettings, QSize, Qt,
    QTimer, QUrl, QVariantAnimation, Signal,
)
from PySide6.QtGui import (
    QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen,
    QPolygonF, QRadialGradient,
)
from PySide6.QtWidgets import (
    QApplication, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QSizePolicy, QStackedLayout, QVBoxLayout, QWidget,
)

# --------------------------------------------------------------------------- #
#  Réglages du jeu
# --------------------------------------------------------------------------- #
MAX_TIME = 60.0
TIME_BONUS = 2.0
START_LIVES = 3
FAST_ANSWER = 4.0
MIN_AGE, MAX_AGE = 5, 99

POLICY_VERSION = 1
POLICY_DATE = "9 novembre 2026"
CONTACT_EMAIL = "k.jacobaka@gmail.com"

POLICY = [
    ("En bref", [
        "Calcul Éclair est un petit jeu de calcul mental créé dans le cadre d'un projet étudiant. "
        "Il fonctionne entièrement sur ton appareil : pas de compte, pas de publicité, pas de suivi "
        "et aucune connexion à Internet pour jouer.",
    ]),
    ("Les données enregistrées", [
        "• Ton âge (facultatif).",
        "• Tes scores, tes records, ton nombre de parties et ta meilleure série.",
        "• Tes réglages : niveau de difficulté, mode de jeu, opération choisie, thème clair ou sombre, "
        "son activé ou non.",
        "Le jeu ne demande ni ton nom, ni ton adresse, ni ton email, ni ta localisation.",
    ]),
    ("Où elles sont stockées", [
        "Uniquement sur ton appareil, dans l'espace de préférences de l'application. Elles ne sont "
        "jamais envoyées à un serveur et ne sont partagées avec personne.",
        "Pour produire les sons, le jeu crée de petits fichiers temporaires qui sont supprimés quand "
        "tu fermes le jeu. Il n'utilise ni micro, ni caméra, ni tes fichiers personnels.",
    ]),
    ("Pourquoi on te demande ton âge", [
        "Uniquement pour te proposer un niveau de départ adapté et afficher ton profil. Ton âge n'est "
        "ni vendu, ni partagé, ni utilisé pour de la publicité. Le donner est facultatif : "
        "tu peux jouer sans.",
    ]),
    ("Jeunes joueurs", [
        "Si tu es mineur(e), lis cette politique avec un parent ou un tuteur. "
        "Pour les moins de 13 ans, nous demandons l'accord d'un parent ou tuteur avant de jouer.",
    ]),
    ("Tes droits et tes choix", [
        "Tu peux à tout moment modifier ou retirer ton âge depuis l'écran « Profil ».",
        "Tu peux effacer toutes tes données (âge, scores, réglages) avec le bouton "
        "« Effacer mes données » de cet écran.",
    ]),
    ("Modifications de cette politique", [
        "Cette politique peut évoluer. Si elle change, le jeu te redemandera ton accord au prochain "
        "lancement.",
    ]),
    ("Contact", [
        f"Pour toute question sur tes données : {CONTACT_EMAIL}",
    ]),
]

STAR_STEPS = (100, 250, 450)

LEVELS = {
    "Facile":    (1, 20, 1),
    "Moyen":     (10, 99, 2),
    "Difficile": (100, 999, 3),
}

MODES = {
    "Classique": {"time": 60.0, "lives": 3, "bonus": 2.0},
    "Zen":       {"time": float("inf"), "lives": float("inf"), "bonus": 0.0},
    "Extrême":   {"time": 15.0, "lives": 1, "bonus": 1.0},
}

OPERATIONS = ["+", "−", "×", "÷", "Mélange"]


# --------------------------------------------------------------------------- #
#  Outils & Thème
# --------------------------------------------------------------------------- #
def clamp01(x):
    return max(0.0, min(1.0, x))

def ease_out(x):
    return 1 - (1 - x) ** 3

def ease_out_back(x):
    c1 = 1.70158
    c3 = c1 + 1
    return 1 + c3 * (x - 1) ** 3 + c1 * (x - 1) ** 2

def mix(a, b, t):
    a, b = QColor(a), QColor(b)
    return QColor(
        int(a.red() + (b.red() - a.red()) * t),
        int(a.green() + (b.green() - a.green()) * t),
        int(a.blue() + (b.blue() - a.blue()) * t),
        int(a.alpha() + (b.alpha() - a.alpha()) * t),
    )

def with_alpha(c, a):
    c = QColor(c)
    c.setAlpha(int(max(0, min(255, a))))
    return c

UI_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "SF Pro Text", "Helvetica Neue", "Arial"]
NUM_FAMILIES = ["Bahnschrift", "Segoe UI Variable Display", "Segoe UI", "SF Pro Display", "Arial"]

def font(px, weight=QFont.Weight.Normal, nums=False, spacing=0.0):
    f = QFont()
    f.setFamilies(NUM_FAMILIES if nums else UI_FAMILIES)
    f.setPixelSize(max(6, int(px)))
    f.setWeight(weight)
    if spacing:
        f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, spacing)
    return f

def draw_text(p, rect, text, fnt, color, align=Qt.AlignmentFlag.AlignCenter, alpha=1.0):
    p.setFont(fnt)
    p.setPen(with_alpha(color, QColor(color).alpha() * clamp01(alpha)))
    p.drawText(rect, align, text)

PALETTE = {
    "bg0": ("#070A12", "#EEF2FA"),
    "bg1": ("#0F1630", "#DDE5F5"),
    "blobA": (QColor(79, 70, 229, 100), QColor(99, 102, 241, 70)),
    "blobB": (QColor(20, 184, 166, 70), QColor(45, 212, 191, 85)),
    "blobC": (QColor(167, 139, 250, 60), QColor(244, 114, 182, 55)),
    "card": (QColor(255, 255, 255, 13), QColor(255, 255, 255, 205)),
    "line": (QColor(255, 255, 255, 26), QColor(15, 23, 42, 28)),
    "text": ("#F1F5FF", "#0F172A"),
    "sub": ("#8B95B4", "#5B6785"),
    "accent": ("#5EEAD4", "#0D9488"),
    "accent2": ("#A78BFA", "#7C3AED"),
    "warm": ("#FBBF24", "#D97706"),
    "danger": ("#FB7185", "#E11D48"),
    "good": ("#34D399", "#059669"),
    "track": (QColor(255, 255, 255, 24), QColor(15, 23, 42, 26)),
    "shadow": (QColor(0, 0, 0, 90), QColor(30, 41, 90, 40)),
}

KEYS = {
    "num": dict(face=("#172036", "#FFFFFF"), hover=("#212D4A", "#F1F4FC"),
                depth=("#0A0F1C", "#C7D0E4"), text=("#E8EDFB", "#0F172A")),
    "fn": dict(face=("#202B4D", "#E4E9FA"), hover=("#2B3963", "#D6DEF6"),
               depth=("#0C1226", "#B4BFDD"), text=("#B7A4FF", "#6D3FE0")),
    "primary": dict(face=("#2DD4BF", "#14B8A6"), hover=("#5EEAD4", "#2DD4BF"),
                    depth=("#0E8C7D", "#0A7469"), text=("#04262A", "#FFFFFF")),
}

class Theme:
    tm = 0.0

    @staticmethod
    def c(name):
        d, l = PALETTE[name]
        return mix(d, l, Theme.tm)


# --------------------------------------------------------------------------- #
#  Sons
# --------------------------------------------------------------------------- #
SR = 22050

def _synth(notes):
    total = max(s + d for s, d, *_ in notes) + 0.05
    n = int(total * SR)
    buf = [0.0] * n
    two_pi = 2 * math.pi
    for start, dur, freq, vol, kind, decay in notes:
        i0 = int(start * SR)
        cnt = int(dur * SR)
        for i in range(cnt):
            t = i / SR
            env = math.exp(-decay * t) * min(1.0, t / 0.004) * min(1.0, (dur - t) / 0.012)
            ph = two_pi * freq * t
            if kind == "bell":
                s = math.sin(ph) + 0.35 * math.sin(2 * ph) + 0.12 * math.sin(3 * ph)
            elif kind == "buzz":
                s = math.tanh(2.5 * math.sin(ph))
            else:
                s = math.sin(ph)
            buf[i0 + i] += vol * env * s
    peak = max(abs(x) for x in buf) or 1.0
    scale = 0.9 / peak if peak > 0.9 else 1.0
    return b"".join(struct.pack("<h", int(max(-1.0, min(1.0, x * scale)) * 32767)) for x in buf)

def _sound_defs():
    d = {}
    d["click"] = [(0, 0.035, 1500, 0.30, "soft", 110)]
    d["pop"] = [(0, 0.07, 700, 0.30, "soft", 40)]
    d["count"] = [(0, 0.02, 2600, 0.14, "soft", 90)]
    d["tick"] = [(0, 0.05, 1100, 0.35, "soft", 55)]
    d["beep"] = [(0, 0.14, 660, 0.50, "soft", 9)]
    d["go"] = [(0, 0.45, 1046.5, 0.50, "bell", 6), (0, 0.45, 1568.0, 0.32, "bell", 6)]
    for i, f in enumerate([523.25, 587.33, 659.25, 783.99, 880.0, 1046.5]):
        d[f"correct{i}"] = [(0, 0.22, f, 0.55, "bell", 9), (0.07, 0.30, f * 1.5, 0.45, "bell", 8)]
    d["wrong"] = [(0, 0.16, 196.0, 0.50, "buzz", 6), (0.13, 0.30, 147.0, 0.50, "buzz", 5)]
    for i, f in enumerate([659.25, 783.99, 987.77]):
        d[f"star{i}"] = [(0, 0.35, f, 0.55, "bell", 7), (0, 0.35, f * 2, 0.20, "bell", 9)]
    d["finish"] = [(0.00, 0.20, 523.25, 0.50, "bell", 8), (0.11, 0.20, 659.25, 0.50, "bell", 8),
                   (0.22, 0.20, 783.99, 0.50, "bell", 8), (0.33, 0.60, 1046.5, 0.55, "bell", 5)]
    d["gameover"] = [(0.00, 0.30, 392.0, 0.50, "bell", 5), (0.20, 0.30, 329.63, 0.50, "bell", 5),
                     (0.40, 0.65, 261.63, 0.55, "bell", 4)]
    d["record"] = [(0.00, 0.20, 523.25, 0.45, "bell", 7), (0.10, 0.20, 659.25, 0.45, "bell", 7),
                   (0.20, 0.20, 783.99, 0.45, "bell", 7), (0.30, 0.25, 1046.5, 0.45, "bell", 6),
                   (0.45, 0.90, 1318.5, 0.45, "bell", 4), (0.45, 0.90, 1046.5, 0.35, "bell", 4),
                   (0.45, 0.90, 784.0, 0.30, "bell", 4)]
    return d

class SoundBank:
    def __init__(self, muted=False):
        self.muted = muted
        self.files, self.effects, self.backend = {}, {}, None
        self._winsound = None
        self.dir = tempfile.mkdtemp(prefix="calcul_eclair_")
        atexit.register(shutil.rmtree, self.dir, True)

        try:
            for name, notes in _sound_defs().items():
                path = os.path.join(self.dir, name + ".wav")
                with wave.open(path, "wb") as wf:
                    wf.setnchannels(1)
                    wf.setsampwidth(2)
                    wf.setframerate(SR)
                    wf.writeframes(_synth(notes))
                self.files[name] = path
        except Exception:
            self.files = {}

        try:
            from PySide6.QtMultimedia import QSoundEffect
            for name, path in self.files.items():
                e = QSoundEffect()
                e.setSource(QUrl.fromLocalFile(path))
                e.setVolume(0.8)
                self.effects[name] = e
            self.backend = "qt" if self.effects else None
        except Exception:
            try:
                import winsound
                self._winsound = winsound
                self.backend = "winsound"
            except Exception:
                self.backend = None

    def play(self, name):
        if self.muted or name not in self.files:
            return
        try:
            if self.backend == "qt":
                self.effects[name].play()
            elif self.backend == "winsound":
                self._winsound.PlaySound(
                    self.files[name],
                    self._winsound.SND_FILENAME | self._winsound.SND_ASYNC | self._winsound.SND_NODEFAULT)
        except Exception:
            pass


# --------------------------------------------------------------------------- #
#  Composants Visuels & UI
# --------------------------------------------------------------------------- #
class Particles:
    GRAVITY = 560.0

    def __init__(self):
        self.items = []

    def burst(self, x, y, n, colors, speed=300.0, life=(0.7, 1.3), size=(3.0, 6.5)):
        for _ in range(n):
            a = random.uniform(0, 2 * math.pi)
            v = random.uniform(0.35, 1.0) * speed
            self.items.append([x, y, math.cos(a) * v, math.sin(a) * v - speed * 0.35,
                               random.uniform(*life), 0.0, QColor(random.choice(colors)),
                               random.uniform(*size)])

    def step(self, dt):
        alive = []
        for it in self.items:
            it[5] += dt
            if it[5] >= it[4]:
                continue
            it[0] += it[2] * dt
            it[1] += it[3] * dt
            it[3] += self.GRAVITY * dt
            it[2] *= 0.992
            alive.append(it)
        self.items = alive

    def paint(self, p):
        p.setPen(Qt.PenStyle.NoPen)
        for x, y, _vx, _vy, life, age, col, size in self.items:
            k = 1 - age / life
            p.setBrush(with_alpha(col, 255 * min(1.0, k * 1.6)))
            r = size * (0.5 + 0.5 * k)
            p.drawEllipse(QPointF(x, y), r, r)

def paint_background(p, w, h):
    t = time.monotonic() / 38.0
    g = QLinearGradient(0, 0, 0, h)
    g.setColorAt(0, Theme.c("bg0"))
    g.setColorAt(1, Theme.c("bg1"))
    p.fillRect(QRectF(0, 0, w, h), g)

    blobs = [("blobA", 0.22, 0.14, 0.00, 0.14, 0.08, 0.95),
             ("blobB", 0.85, 0.52, 0.33, 0.12, 0.10, 0.85),
             ("blobC", 0.30, 0.92, 0.66, 0.16, 0.07, 0.90)]
    for name, bx, by, ph, ax, ay, rad in blobs:
        cx = (bx + ax * math.sin(2 * math.pi * (t + ph))) * w
        cy = (by + ay * math.cos(2 * math.pi * (t + ph))) * h
        r = rad * max(w, h) * 0.75
        col = Theme.c(name)
        rg = QRadialGradient(QPointF(cx, cy), r)
        rg.setColorAt(0, col)
        rg.setColorAt(1, with_alpha(col, 0))
        p.fillRect(QRectF(0, 0, w, h), rg)

class AnimatedButton(QPushButton):
    def __init__(self, label, kind="num", px=22, nums=True, parent=None):
        super().__init__(label, parent)
        self.kind, self.px, self.nums = kind, px, nums
        self.glow, self._hover, self._press, self._ripple = 0.0, 0.0, 0.0, 1.0
        self._rp = QPointF()

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(64, 54)

        self._a_hover = self._make("_hover", 180)
        self._a_press = self._make("_press", 100)
        self._a_ripple = self._make("_ripple", 520)

    def _make(self, attr, ms):
        a = QVariantAnimation(self)
        a.setDuration(ms)
        a.setEasingCurve(QEasingCurve.Type.OutCubic)
        a.valueChanged.connect(lambda v, name=attr: (setattr(self, name, float(v)), self.update()))
        return a

    def _go(self, anim, attr, target):
        anim.stop()
        anim.setStartValue(getattr(self, attr))
        anim.setEndValue(target)
        anim.start()

    def enterEvent(self, e):
        self._go(self._a_hover, "_hover", 1.0)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._go(self._a_hover, "_hover", 0.0)
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        self._go(self._a_press, "_press", 1.0)
        self._rp = QPointF(e.position())
        self._ripple = 0.0
        self._go(self._a_ripple, "_ripple", 1.0)
        super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        self._go(self._a_press, "_press", 0.0)
        super().mouseReleaseEvent(e)

    def tap(self):
        self._rp = QPointF(self.width() / 2, self.height() / 2)
        self._ripple = 0.0
        self._go(self._a_ripple, "_ripple", 1.0)
        self._go(self._a_press, "_press", 1.0)
        QTimer.singleShot(100, lambda: self._go(self._a_press, "_press", 0.0))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        if not self.isEnabled():
            p.setOpacity(0.38)
        k, tm = KEYS[self.kind], Theme.tm

        face = mix(mix(k["face"][0], k["face"][1], tm), mix(k["hover"][0], k["hover"][1], tm), self._hover)
        depth = mix(k["depth"][0], k["depth"][1], tm)
        fg = mix(k["text"][0], k["text"][1], tm)

        D = 5.0
        fh = h - 6 - D
        off = self._press * D * 0.8
        r = min(fh * 0.32, 20.0)
        rect_d = QRectF(3, 3 + D, w - 6, fh)
        rect_f = QRectF(3, 3 + off, w - 6, fh)

        if self.glow > 0 and self.kind == "primary":
            ac = Theme.c("accent")
            for i in range(1, 5):
                gp = QPainterPath()
                gp.addRoundedRect(rect_f.adjusted(-i * 4, -i * 4, i * 4, i * 4 + D), r + i * 4, r + i * 4)
                p.fillPath(gp, with_alpha(ac, 34 * self.glow / i))

        pd = QPainterPath()
        pd.addRoundedRect(rect_d, r, r)
        p.fillPath(pd, depth)

        pf = QPainterPath()
        pf.addRoundedRect(rect_f, r, r)
        g = QLinearGradient(rect_f.topLeft(), rect_f.bottomLeft())
        g.setColorAt(0, face.lighter(112))
        g.setColorAt(1, face.darker(104))
        p.fillPath(pf, g)
        p.setPen(QPen(Theme.c("line"), 1))
        p.drawPath(pf)

        if self._ripple < 1.0:
            p.save()
            p.setClipPath(pf)
            rr = max(w, h) * 1.1 * self._ripple
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(255, 255, 255, int(70 * (1 - self._ripple))))
            p.drawEllipse(self._rp, rr, rr)
            p.restore()

        p.setFont(font(self.px, QFont.Weight.DemiBold, nums=self.nums))
        p.setPen(fg)
        p.drawText(rect_f, Qt.AlignmentFlag.AlignCenter, self.text())

class IconButton(QPushButton):
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.muted = False
        self._hover = 0.0
        self.setFixedSize(42, 42)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._a = QVariantAnimation(self)
        self._a.setDuration(180)
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
        c = Theme.c("text")
        circle = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.setPen(QPen(Theme.c("line"), 1))
        p.setBrush(mix(Theme.c("card"), with_alpha(c, 40), self._hover))
        p.drawEllipse(circle)

        p.translate(self.width() / 2, self.height() / 2)
        pen = QPen(c, 2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)

        if self.kind == "theme":
            t = Theme.tm
            p.save()
            p.setOpacity(t)
            p.rotate(-90 * (1 - t))
            p.setPen(pen)
            p.setBrush(c)
            p.drawEllipse(QPointF(0, 0), 4.2, 4.2)
            for i in range(8):
                p.save()
                p.rotate(i * 45)
                p.drawLine(QPointF(0, -7.5), QPointF(0, -10))
                p.restore()
            p.restore()
            p.save()
            p.setOpacity(1 - t)
            p.rotate(90 * t)
            outer, inner = QPainterPath(), QPainterPath()
            outer.addEllipse(QPointF(0, 0), 8, 8)
            inner.addEllipse(QPointF(4, -3.2), 6.8, 6.8)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawPath(outer.subtracted(inner))
            p.restore()
        else:
            p.translate(-3, 0)
            spk = QPolygonF([QPointF(-6, -3), QPointF(-2, -3), QPointF(3, -7),
                             QPointF(3, 7), QPointF(-2, 3), QPointF(-6, 3)])
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(c)
            p.drawPolygon(spk)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            if self.muted:
                p.drawLine(QPointF(7, -4), QPointF(13, 4))
                p.drawLine(QPointF(13, -4), QPointF(7, 4))
            else:
                p.drawArc(QRectF(-1, -5, 10, 10), -45 * 16, 90 * 16)
                p.drawArc(QRectF(-5, -9, 18, 18), -45 * 16, 90 * 16)

class TextLabel(QWidget):
    def __init__(self, text="", px=14, weight=QFont.Weight.Normal, color="text",
                 nums=False, spacing=0.0, align=Qt.AlignmentFlag.AlignCenter, parent=None):
        super().__init__(parent)
        self._text, self._px, self._weight = text, px, weight
        self._color, self._nums, self._spacing, self._align = color, nums, spacing, align

    def setText(self, t):
        self._text = t
        self.updateGeometry()
        self.update()

    def sizeHint(self):
        fm = QFontMetrics(font(self._px, self._weight, self._nums, self._spacing))
        return QSize(fm.horizontalAdvance(self._text) + 8, fm.height() + 6)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        p.setFont(font(self._px, self._weight, self._nums, self._spacing))
        p.setPen(Theme.c(self._color))
        p.drawText(QRectF(self.rect()), self._align, self._text)

BOLT = [(0.58, 0.08), (0.26, 0.56), (0.46, 0.56), (0.40, 0.92), (0.74, 0.40), (0.52, 0.40)]

class LogoMark(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(96, 96)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        glow = 0.6 + 0.25 * math.sin(time.monotonic() * 1.6)
        ac = Theme.c("accent")
        rg = QRadialGradient(QPointF(w / 2, h / 2), w * 0.52)
        rg.setColorAt(0, with_alpha(ac, 120 * glow))
        rg.setColorAt(1, with_alpha(ac, 0))
        p.fillRect(QRectF(0, 0, w, h), rg)

        tile = QRectF(16, 16, w - 32, h - 32)
        path = QPainterPath()
        path.addRoundedRect(tile, 20, 20)
        g = QLinearGradient(tile.topLeft(), tile.bottomRight())
        g.setColorAt(0, Theme.c("accent"))
        g.setColorAt(1, Theme.c("accent2"))
        p.fillPath(path, g)

        s = tile.width()
        poly = QPolygonF([QPointF(tile.left() + x * s, tile.top() + y * s) for x, y in BOLT])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#06141F"))
        p.drawPolygon(poly)

class StatPill(QWidget):
    def __init__(self, label, parent=None):
        super().__init__(parent)
        self.label, self.value = label, "0"
        self.setFixedHeight(78)

    def set_value(self, v):
        self.value = v
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        rect = QRectF(0.5, 0.5, w - 1, h - 1)
        path = QPainterPath()
        path.addRoundedRect(rect, 20, 20)
        p.fillPath(path, Theme.c("card"))
        p.setPen(QPen(Theme.c("line"), 1))
        p.drawPath(path)
        draw_text(p, QRectF(0, 12, w, 16), self.label, font(10, QFont.Weight.DemiBold, spacing=1.6), Theme.c("sub"))
        draw_text(p, QRectF(0, 28, w, h - 34), self.value, font(28, QFont.Weight.Bold, nums=True), Theme.c("text"))

class SegmentedControl(QWidget):
    changed = Signal(str)

    def __init__(self, options, current, parent=None):
        super().__init__(parent)
        # CORRECTION : on normalise les options en paires (nom, sous-titre).
        # Avant, une option « Zen » donnait o[0] == "Z" (première lettre) -> plantage.
        self.options = [o if isinstance(o, tuple) else (o, "") for o in options]
        names = [o[0] for o in self.options]
        self.index = names.index(current) if current in names else 0
        self._pos = float(self.index)
        self.setFixedHeight(54)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(340)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(lambda v: (setattr(self, "_pos", float(v)), self.update()))

    def _move(self, i):
        self.index = i
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(float(i))
        self._anim.start()

    def select(self, i):
        i = max(0, min(len(self.options) - 1, i))
        if i == self.index:
            return
        self._move(i)
        self.changed.emit(self.options[i][0])

    def set_current(self, name):
        names = [o[0] for o in self.options]
        if name in names and names.index(name) != self.index:
            self._move(names.index(name))

    def mousePressEvent(self, e):
        seg = (self.width() - 10) / len(self.options)
        self.select(int((e.position().x() - 5) / seg))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        track = QPainterPath()
        track.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 20, 20)
        p.fillPath(track, Theme.c("card"))
        p.setPen(QPen(Theme.c("line"), 1))
        p.drawPath(track)

        n = len(self.options)
        pad = 4.0
        seg = (w - 2 * pad) / n
        pill_rect = QRectF(pad + self._pos * seg, pad, seg, h - 2 * pad)
        pill = QPainterPath()
        pill.addRoundedRect(pill_rect, 16, 16)
        g = QLinearGradient(pill_rect.topLeft(), pill_rect.bottomRight())
        g.setColorAt(0, with_alpha(Theme.c("accent"), 48))
        g.setColorAt(1, with_alpha(Theme.c("accent2"), 48))
        p.fillPath(pill, g)
        p.setPen(QPen(with_alpha(Theme.c("accent"), 150), 1.2))
        p.drawPath(pill)

        for i, (name, sub) in enumerate(self.options):
            rect = QRectF(pad + i * seg, pad, seg, h - 2 * pad)
            close = max(0.0, 1 - abs(self._pos - i))
            col = mix(Theme.c("sub"), Theme.c("accent"), close)
            if sub:
                draw_text(p, QRectF(rect.left(), rect.top() + 4, rect.width(), rect.height() * 0.5),
                          name, font(14, QFont.Weight.DemiBold), col)
                draw_text(p, QRectF(rect.left(), rect.top() + rect.height() * 0.52, rect.width(), rect.height() * 0.4),
                          sub, font(10, nums=True), with_alpha(col, 190))
            else:
                draw_text(p, rect, name, font(13, QFont.Weight.DemiBold), col)

def heart_path(s):
    path = QPainterPath()
    path.moveTo(0, s * 0.95)
    path.cubicTo(-s * 1.7, -s * 0.05, -s * 0.95, -s * 1.15, 0, -s * 0.38)
    path.cubicTo(s * 0.95, -s * 1.15, s * 1.7, -s * 0.05, 0, s * 0.95)
    path.closeSubpath()
    return path

class HeartsWidget(QWidget):
    def __init__(self, n=3, parent=None):
        super().__init__(parent)
        self.n = self.lives = n
        self.lost = -1
        self._beat = 1.0
        self.setFixedSize(120, 44)
        self._a = QVariantAnimation(self)
        self._a.setDuration(750)
        self._a.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._a.valueChanged.connect(lambda v: (setattr(self, "_beat", float(v)), self.update()))

    def set_lives(self, lives, animate=False):
        if animate and lives < self.lives:
            self.lost = lives
            self._a.stop()
            self._a.setStartValue(0.0)
            self._a.setEndValue(1.0)
            self._a.start()
        elif not animate:
            self.lost = -1
            self._beat = 1.0
        self.lives = lives
        self.update()

    def paintEvent(self, _):
        if math.isinf(self.lives):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            draw_text(p, QRectF(0, 0, self.width(), self.height()), "∞ VIES",
                      font(14, QFont.Weight.Bold), Theme.c("good"), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        danger, sub = Theme.c("danger"), Theme.c("sub")
        for i in range(self.n):
            cx, cy = 16 + i * 34, self.height() / 2
            scale, dx = 1.0, 0.0
            fill, stroke = None, None
            if i == self.lost and self._beat < 1.0:
                k = self._beat
                scale = 1.0 + 0.55 * (1 - k)
                dx = math.sin(k * 20) * (1 - k) * 3
                fill = mix(danger, with_alpha(sub, 50), k)
            elif i < self.lives:
                fill = danger
            else:
                fill, stroke = with_alpha(sub, 36), with_alpha(sub, 110)
            p.save()
            p.translate(cx + dx, cy)
            p.scale(scale, scale)
            path = heart_path(11)
            p.fillPath(path, fill)
            if stroke:
                p.setPen(QPen(stroke, 1.5))
                p.drawPath(path)
            p.restore()

class TimerRing(QWidget):
    def __init__(self, max_time, parent=None):
        super().__init__(parent)
        self.max_time = self.remaining = max_time
        self.bonus_text = ""
        self._bonus = 1.0
        self.setFixedSize(104, 118)
        self._a = QVariantAnimation(self)
        self._a.setDuration(950)
        self._a.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._a.valueChanged.connect(lambda v: (setattr(self, "_bonus", float(v)), self.update()))

    def set_remaining(self, r):
        self.remaining = r
        self.update()

    def show_bonus(self, text):
        self.bonus_text = text
        self._a.stop()
        self._a.setStartValue(0.0)
        self._a.setEndValue(1.0)
        self._a.start()

    def paintEvent(self, _):
        if math.isinf(self.remaining):
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
            w = self.width()
            p.translate(w / 2, 68)
            rect = QRectF(-38, -38, 76, 76)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(Theme.c("track"), 7))
            p.drawEllipse(rect)
            draw_text(p, QRectF(-32, -24, 64, 36), "∞",
                      font(36, QFont.Weight.Bold), Theme.c("good"))
            draw_text(p, QRectF(-32, 11, 64, 14), "ZEN", font(9, QFont.Weight.DemiBold, spacing=1.6), Theme.c("sub"))
            return

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w = self.width()
        frac = clamp01(self.remaining / self.max_time)
        low = 0 < self.remaining <= 10

        if self._bonus < 1.0 and self.bonus_text:
            draw_text(p, QRectF(0, 16 - self._bonus * 14, w, 18), self.bonus_text,
                      font(14, QFont.Weight.Bold, nums=True), Theme.c("accent"), alpha=1 - self._bonus)

        pulse = 1.0 + (0.04 * math.sin(time.monotonic() * 4 * math.pi) if low else 0.0)
        p.translate(w / 2, 68)
        p.scale(pulse, pulse)
        rect = QRectF(-38, -38, 76, 76)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(Theme.c("track"), 7))
        p.drawEllipse(rect)

        if frac > 0.5:
            col = Theme.c("accent")
        elif frac > 0.25:
            col = mix(Theme.c("warm"), Theme.c("accent"), (frac - 0.25) / 0.25)
        else:
            col = mix(Theme.c("danger"), Theme.c("warm"), frac / 0.25)
        pen = QPen(col, 7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        if frac > 0:
            p.drawArc(rect, 90 * 16, int(-frac * 360 * 16))

        draw_text(p, QRectF(-32, -24, 64, 36), str(math.ceil(self.remaining)),
                  font(30, QFont.Weight.Bold, nums=True), Theme.c("danger") if low else Theme.c("text"))
        draw_text(p, QRectF(-32, 11, 64, 14), "SEC", font(9, QFont.Weight.DemiBold, spacing=1.6), Theme.c("sub"))

class ScoreWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.target = 0
        self.shown = 0.0
        self._pop = 1.0
        self.setFixedSize(120, 76)
        self._a_show = QVariantAnimation(self)
        self._a_show.setDuration(650)
        self._a_show.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._a_show.valueChanged.connect(lambda v: (setattr(self, "shown", float(v)), self.update()))
        self._a_pop = QVariantAnimation(self)
        self._a_pop.setDuration(380)
        self._a_pop.setEasingCurve(QEasingCurve.Type.OutBack)
        self._a_pop.valueChanged.connect(lambda v: (setattr(self, "_pop", float(v)), self.update()))

    def reset(self):
        self._a_show.stop()
        self._a_pop.stop()
        self.target, self.shown, self._pop = 0, 0.0, 1.0
        self.update()

    def set_score(self, v):
        if v == self.target:
            return
        up = v > self.target
        self.target = v
        self._a_show.stop()
        self._a_show.setStartValue(self.shown)
        self._a_show.setEndValue(float(v))
        self._a_show.start()
        if up:
            self._a_pop.stop()
            self._a_pop.setStartValue(0.0)
            self._a_pop.setEndValue(1.0)
            self._a_pop.start()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w = self.width()
        draw_text(p, QRectF(0, 4, w, 16), "SCORE", font(10, QFont.Weight.DemiBold, spacing=2.0),
                  Theme.c("sub"), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        s = 1.0 + 0.22 * (1 - self._pop)
        p.translate(w, 46)
        p.scale(s, s)
        draw_text(p, QRectF(-w, -28, w, 56), str(int(round(self.shown))),
                  font(40, QFont.Weight.Bold, nums=True), Theme.c("text"),
                  Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

class StreakBadge(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.streak = 0
        self._pop = 1.0
        self.setFixedHeight(34)
        self._a = QVariantAnimation(self)
        self._a.setDuration(350)
        self._a.setEasingCurve(QEasingCurve.Type.OutBack)
        self._a.valueChanged.connect(lambda v: (setattr(self, "_pop", float(v)), self.update()))

    def set_streak(self, n):
        up = n > self.streak
        self.streak = n
        if up and n >= 2:
            self._a.stop()
            self._a.setStartValue(0.0)
            self._a.setEndValue(1.0)
            self._a.start()
        self.update()

    def paintEvent(self, _):
        if self.streak < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        warm = Theme.c("warm")
        text = f"SÉRIE ×{self.streak}"
        f = font(12, QFont.Weight.Bold, spacing=1.6)
        tw = QFontMetrics(f).horizontalAdvance(text)
        bw, bh = tw + 52, 28
        s = 1.0 + 0.18 * (1 - self._pop)
        p.translate(self.width() / 2, self.height() / 2)
        p.scale(s, s)
        rect = QRectF(-bw / 2, -bh / 2, bw, bh)
        path = QPainterPath()
        path.addRoundedRect(rect, 14, 14)
        p.fillPath(path, with_alpha(warm, 40))
        p.setPen(QPen(with_alpha(warm, 150), 1.2))
        p.drawPath(path)
        poly = QPolygonF([QPointF(rect.left() + 14 + x * 14 - 7, -7 + y * 14) for x, y in BOLT])
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(warm)
        p.drawPolygon(poly)
        draw_text(p, QRectF(rect.left() + 26, rect.top(), rect.width() - 26, rect.height()), text, f, warm)

class QuestionCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        self.qa = self.qb = self.op = self.answer = ""
        self.prev = None
        self.tag_right = self.popup_text = ""
        self._flash_kind = "good"
        self._flash, self._shake, self._enter, self._popup = 0.0, 1.0, 1.0, 1.0
        self._caret = True
        self.particles = Particles()
        self._plast = 0.0

        self._a_flash = self._anim("_flash", 700, QEasingCurve.Type.OutCubic)
        self._a_shake = self._anim("_shake", 480, QEasingCurve.Type.Linear)
        self._a_enter = self._anim("_enter", 330, QEasingCurve.Type.OutCubic)
        self._a_popup = self._anim("_popup", 1000, QEasingCurve.Type.Linear)

        self._blink = QTimer(self)
        self._blink.setInterval(520)
        self._blink.timeout.connect(self._toggle_caret)
        self._blink.start()

        self._ptimer = QTimer(self)
        self._ptimer.setInterval(16)
        self._ptimer.timeout.connect(self._step_particles)

    def _anim(self, attr, ms, curve):
        a = QVariantAnimation(self)
        a.setDuration(ms)
        a.setEasingCurve(curve)
        a.valueChanged.connect(lambda v, name=attr: (setattr(self, name, float(v)), self.update()))
        return a

    @staticmethod
    def _run(anim, start, end, ms=None):
        anim.stop()
        if ms:
            anim.setDuration(ms)
        anim.setStartValue(start)
        anim.setEndValue(end)
        anim.start()

    def _toggle_caret(self):
        self._caret = not self._caret
        self.update()

    def _step_particles(self):
        now = time.monotonic()
        dt = min(0.05, now - self._plast)
        self._plast = now
        self.particles.step(dt)
        if not self.particles.items:
            self._ptimer.stop()
        self.update()

    def _burst(self, colors, n=34):
        r = self._card_rect()
        self.particles.burst(r.center().x(), r.top() + r.height() * 0.5, n, colors, speed=330)
        if not self._ptimer.isActive():
            self._plast = time.monotonic()
            self._ptimer.start()

    def reset_state(self):
        for a in (self._a_flash, self._a_shake, self._a_enter, self._a_popup):
            a.stop()
        self._flash, self._shake, self._enter, self._popup = 0.0, 1.0, 1.0, 1.0
        self.qa = self.qb = self.op = self.answer = ""
        self.prev = None
        self.particles.items = []
        self.update()

    def set_question(self, a, b, op="+"):
        self.prev = (self.qa, self.qb, self.op, self.answer) if self.qa else None
        self.qa, self.qb, self.op, self.answer = str(a), str(b), op, ""
        self._run(self._a_enter, 0.0, 1.0)

    def set_answer(self, text):
        self.answer = text
        self._caret = True
        self.update()

    def flash_good(self, text):
        self._flash_kind = "good"
        self.popup_text = text
        self._run(self._a_flash, 1.0, 0.0, 700)
        self._run(self._a_popup, 0.0, 1.0, 1000)
        self._burst([Theme.c("good"), Theme.c("accent"), Theme.c("accent2"), Theme.c("warm"), QColor("white")])

    def flash_bad(self, text):
        self._flash_kind = "bad"
        self.popup_text = text
        self._run(self._a_flash, 1.0, 0.0, 1000)
        self._run(self._a_shake, 0.0, 1.0)
        self._run(self._a_popup, 0.0, 1.0, 1100)

    def _card_rect(self):
        return QRectF(10, 6, self.width() - 20, self.height() - 24)

    def _draw_question(self, p, rect, qa, qb, op, dx, alpha):
        size = rect.height() * 0.30
        sep = f"  {op}  "
        while size > 16:
            f = font(size, QFont.Weight.Normal, nums=True)
            fm = QFontMetrics(f)
            if fm.horizontalAdvance(qa) + fm.horizontalAdvance(sep) + fm.horizontalAdvance(qb) <= rect.width() - 56:
                break
            size -= 2
        f = font(size, QFont.Weight.Normal, nums=True)
        fm = QFontMetrics(f)
        total = fm.horizontalAdvance(qa) + fm.horizontalAdvance(sep) + fm.horizontalAdvance(qb)
        y = rect.top() + rect.height() * 0.40 + (fm.ascent() - fm.descent()) / 2
        x = rect.center().x() - total / 2 + dx
        p.setFont(f)
        p.setPen(with_alpha(Theme.c("text"), 255 * alpha))
        p.drawText(QPointF(x, y), qa)
        x += fm.horizontalAdvance(qa)
        p.setPen(with_alpha(Theme.c("accent"), 255 * alpha))
        p.drawText(QPointF(x, y), sep)
        x += fm.horizontalAdvance(sep)
        p.setPen(with_alpha(Theme.c("text"), 255 * alpha))
        p.drawText(QPointF(x, y), qb)

    def _draw_answer(self, p, rect, answer, dx, alpha, flash_col, flash, caret):
        f = font(rect.height() * 0.17, QFont.Weight.DemiBold, nums=True)
        fm = QFontMetrics(f)
        shown = answer if answer else "?"
        tw = fm.horizontalAdvance(shown)
        base_y = rect.top() + rect.height() * 0.80
        x = rect.center().x() - tw / 2 + dx
        col = mix(Theme.c("text") if answer else with_alpha(Theme.c("sub"), 160), flash_col, flash)
        p.setFont(f)
        p.setPen(with_alpha(col, 255 * alpha))
        p.drawText(QPointF(x, base_y), shown)

        line_w = max(tw + 64, rect.width() * 0.36)
        lc = mix(Theme.c("accent") if answer else Theme.c("line"), flash_col, flash)
        pen = QPen(with_alpha(lc, 255 * alpha), 2.5)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        ly = base_y + 14
        p.drawLine(QPointF(rect.center().x() - line_w / 2 + dx, ly), QPointF(rect.center().x() + line_w / 2 + dx, ly))
        if caret and answer:
            cx = x + tw + 6
            p.setPen(QPen(with_alpha(Theme.c("accent"), 255 * alpha), 2.5))
            p.drawLine(QPointF(cx, base_y - f.pixelSize() * 0.78), QPointF(cx, base_y + 2))

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        rect = self._card_rect()
        fcol = Theme.c("good") if self._flash_kind == "good" else Theme.c("danger")

        dx_shake = math.sin(self._shake * math.pi * 8) * (1 - self._shake) * 20 if self._shake < 1.0 else 0.0
        p.translate(dx_shake, 0)

        for i in range(1, 5):
            sp = QPainterPath()
            sp.addRoundedRect(rect.adjusted(-i * 3, -i * 2 + 12, i * 3, i * 3 + 12), 30 + i * 3, 30 + i * 3)
            p.fillPath(sp, with_alpha(Theme.c("shadow"), Theme.c("shadow").alpha() / (i * 1.6)))

        path = QPainterPath()
        path.addRoundedRect(rect, 30, 30)
        p.fillPath(path, mix(Theme.c("card"), with_alpha(fcol, 70), self._flash))
        gb = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        gb.setColorAt(0, mix(with_alpha(QColor("white"), 60 if Theme.tm < 0.5 else 0), fcol, self._flash))
        gb.setColorAt(1, mix(Theme.c("line"), fcol, self._flash))
        p.setPen(QPen(gb, 1.6))
        p.drawPath(path)

        op_name = {"+": "ADDITION", "−": "SOUSTRACTION", "×": "MULTIPLICATION", "÷": "DIVISION"}.get(self.op, "CALCUL")
        draw_text(p, QRectF(rect.left() + 22, rect.top() + 16, 140, 16), op_name,
                  font(10, QFont.Weight.DemiBold, spacing=2.2), Theme.c("sub"),
                  Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        draw_text(p, QRectF(rect.right() - 162, rect.top() + 16, 140, 16), self.tag_right,
                  font(10, QFont.Weight.DemiBold, spacing=2.2), Theme.c("accent"),
                  Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        clip = QPainterPath()
        clip.addRoundedRect(rect.adjusted(2, 2, -2, -2), 28, 28)
        p.save()
        p.setClipPath(clip)
        e = self._enter
        slide = rect.width() * 0.35
        if self.prev and e < 1.0:
            pa, pb, pop, pans = self.prev
            self._draw_question(p, rect, pa, pb, pop, -e * slide, 1 - e)
            self._draw_answer(p, rect, pans, -e * slide, 1 - e, fcol, 0.0, False)
        if self.qa:
            dx = (1 - e) * slide
            self._draw_question(p, rect, self.qa, self.qb, self.op, dx, e)
            self._draw_answer(p, rect, self.answer, dx, e, fcol, self._flash, self._caret and self._flash < 0.05)
        p.restore()

        if self._popup < 1.0 and self.popup_text:
            k = self._popup
            a = 1.0 if k < 0.6 else (1 - k) / 0.4
            col = Theme.c("good") if self._flash_kind == "good" else Theme.c("danger")
            draw_text(p, QRectF(rect.left(), rect.top() + 36 - k * 22, rect.width(), 30), self.popup_text,
                      font(rect.height() * 0.11, QFont.Weight.Bold, nums=True), col, alpha=a)

        p.translate(-dx_shake, 0)
        self.particles.paint(p)

class CountdownOverlay(QWidget):
    def __init__(self, parent):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.text, self.go, self._t = "", False, 1.0
        self._a = QVariantAnimation(self)
        self._a.setDuration(680)
        self._a.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._a.valueChanged.connect(lambda v: (setattr(self, "_t", float(v)), self.update()))
        self._a.finished.connect(lambda: self.hide() if self.go else None)
        self.hide()

    def show_value(self, text, go=False):
        self.text, self.go = text, go
        self.setGeometry(self.parent().rect())
        self.show()
        self.raise_()
        self._a.stop()
        self._a.setStartValue(0.0)
        self._a.setEndValue(1.0)
        self._a.start()

    def paintEvent(self, _):
        if not self.text:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        t = self._t
        p.fillRect(QRectF(0, 0, w, h), with_alpha(Theme.c("bg0"), 175 * (1 - t if self.go else 1.0)))

        cx, cy = w / 2, h / 2
        ac = Theme.c("accent") if self.go else Theme.c("accent2")
        p.setPen(QPen(with_alpha(ac, 170 * (1 - t)), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QPointF(cx, cy), 70 + 190 * t, 70 + 190 * t)

        size = 120 if self.go else 190
        p.save()
        p.translate(cx, cy)
        p.scale(1.55 - 0.55 * t, 1.55 - 0.55 * t)
        draw_text(p, QRectF(-w / 2, -size * 0.7, w, size * 1.4), self.text,
                  font(size, QFont.Weight.Bold, nums=True),
                  Theme.c("accent") if self.go else Theme.c("text"), alpha=1.0 if t < 0.7 else (1 - t) / 0.3)
        p.restore()

def star_poly(cx, cy, R):
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = R if i % 2 == 0 else R * 0.46
        pts.append(QPointF(cx + math.cos(ang) * rad, cy + math.sin(ang) * rad))
    return QPolygonF(pts)

class ResultsView(QWidget):
    DURATION = 3.9

    def __init__(self, sounds, parent=None):
        super().__init__(parent)
        self.sounds = sounds
        self.res = None
        self.t = self.DURATION
        self._fired = set()
        self._last_count = -1.0
        self.particles = Particles()
        self._plast = 0.0
        self.setMinimumHeight(380)

        self._anim = QVariantAnimation(self)
        self._anim.setDuration(int(self.DURATION * 1000))
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(self.DURATION)
        self._anim.setEasingCurve(QEasingCurve.Type.Linear)
        self._anim.valueChanged.connect(self._on_t)

        self._ptimer = QTimer(self)
        self._ptimer.setInterval(16)
        self._ptimer.timeout.connect(self._step_particles)

    def finished(self):
        return self.t >= self.DURATION - 1e-6

    def start(self, res):
        self.res = res
        self._fired = set()
        self._last_count = -1.0
        self.particles.items = []
        self.t = 0.0
        self._anim.stop()
        self._anim.start()
        self.update()

    def skip(self):
        self._anim.stop()
        self.t = self.DURATION
        self.update()

    def mousePressEvent(self, e):
        if not self.finished():
            self.skip()

    def _on_t(self, v):
        self.t = float(v)
        self._triggers()
        self.update()

    def _step_particles(self):
        now = time.monotonic()
        dt = min(0.05, now - self._plast)
        self._plast = now
        self.particles.step(dt)
        if not self.particles.items:
            self._ptimer.stop()
        self.update()

    def _burst(self, x, y, n, speed=380):
        cols = [Theme.c("warm"), Theme.c("accent"), Theme.c("accent2"), Theme.c("good"),
                Theme.c("danger"), QColor("white")]
        self.particles.burst(x, y, n, cols, speed=speed, life=(0.9, 1.7), size=(3.5, 7.5))
        if not self._ptimer.isActive():
            self._plast = time.monotonic()
            self._ptimer.start()

    def _fire(self, key, at, fn):
        if key not in self._fired and self.t >= at:
            self._fired.add(key)
            fn()

    def _star_pos(self, i):
        w, h = self.width(), self.height()
        star_r = min(w * 0.07, h * 0.055)
        return w / 2 + (i - 1) * star_r * 2.9, h * 0.38 + abs(i - 1) * star_r * 0.45, star_r

    def _star_fx(self, i):
        if i < self.res["stars"]:
            self.sounds.play(f"star{i}")
            x, y, _ = self._star_pos(i)
            self._burst(x, y, 14, speed=220)

    def _record_fx(self):
        w, h = self.width(), self.height()
        self.sounds.play("record")
        self._burst(w * 0.2, h * 0.2, 34)
        self._burst(w * 0.8, h * 0.2, 34)
        self._burst(w / 2, h * 0.52, 40, speed=420)

    def _triggers(self):
        r = self.res
        if not r:
            return
        t = self.t
        lost_all = r["reason"] == "plus de vies" and r["stars"] == 0
        self._fire("open", 0.05, lambda: self.sounds.play("gameover" if lost_all else "finish"))
        if 0.35 <= t <= 1.75 and r["score"] > 0 and t - self._last_count >= 0.07:
            self._last_count = t
            self.sounds.play("count")
        for i in range(3):
            self._fire(f"star{i}", 1.8 + 0.32 * i, lambda idx=i: self._star_fx(idx))
        for i in range(4):
            self._fire(f"stat{i}", 2.3 + 0.14 * i, lambda: self.sounds.play("pop"))
        if r["record"]:
            self._fire("record", 3.1, self._record_fx)

    def paintEvent(self, _):
        r = self.res
        if not r:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        t = self.t

        head_y = h * 0.02
        score_cy = h * 0.18
        score_px = min(h * 0.15, w * 0.25)
        badge_cy = h * 0.48
        grid_top = h * 0.55
        grid_h = h * 0.26

        a = ease_out(clamp01(t / 0.5))
        draw_text(p, QRectF(0, head_y, w, 24),
                  f"{r['reason'].upper()}  ·  {r['level'].upper()}",
                  font(12, QFont.Weight.DemiBold, spacing=2.6), Theme.c("sub"), alpha=a)

        k = clamp01((t - 0.3) / 1.4)
        val = int(round(r["score"] * ease_out(k)))
        pop = 1.0 + (0.09 * max(0.0, 1 - (t - 1.7) / 0.3) if t >= 1.7 else 0.0)
        col = Theme.c("warm") if (r["record"] and k >= 1) else Theme.c("text")
        p.save()
        p.translate(w / 2, score_cy)
        p.scale(pop, pop)
        draw_text(p, QRectF(-w / 2, -score_px * 0.6, w, score_px * 1.2), str(val),
                  font(score_px, QFont.Weight.Bold, nums=True), col, alpha=ease_out(clamp01((t - 0.2) / 0.3)))
        p.restore()
        draw_text(p, QRectF(0, score_cy + score_px * 0.55, w, 20), "POINTS",
                  font(11, QFont.Weight.DemiBold, spacing=3.0), Theme.c("sub"),
                  alpha=ease_out(clamp01((t - 0.5) / 0.4)))

        base_a = ease_out(clamp01((t - 1.5) / 0.4))
        for i in range(3):
            cx, cy, R = self._star_pos(i)
            if base_a > 0:
                p.setPen(QPen(with_alpha(Theme.c("sub"), 120 * base_a), 2))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawPolygon(star_poly(cx, cy, R))
            kk = clamp01((t - (1.8 + 0.32 * i)) / 0.4)
            if i < r["stars"] and kk > 0:
                sc = ease_out_back(kk)
                warm = Theme.c("warm")
                p.save()
                p.translate(cx, cy)
                p.scale(sc, sc)
                rg = QRadialGradient(QPointF(0, 0), R * 2.0)
                rg.setColorAt(0, with_alpha(warm, 120 * min(1.0, kk)))
                rg.setColorAt(1, with_alpha(warm, 0))
                p.fillRect(QRectF(-R * 2, -R * 2, R * 4, R * 4), rg)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(warm)
                p.drawPolygon(star_poly(0, 0, R))
                p.restore()

        if r["record"]:
            kk = clamp01((t - 3.1) / 0.5)
            if kk > 0:
                sc = ease_out_back(kk)
                text = "NOUVEAU RECORD"
                f = font(12, QFont.Weight.Bold, spacing=2.2)
                bw = QFontMetrics(f).horizontalAdvance(text) + 40
                bh = 32
                p.save()
                p.translate(w / 2, badge_cy)
                p.scale(sc, sc)
                rect = QRectF(-bw / 2, -bh / 2, bw, bh)
                path = QPainterPath()
                path.addRoundedRect(rect, 16, 16)
                g = QLinearGradient(rect.topLeft(), rect.bottomRight())
                g.setColorAt(0, Theme.c("warm").lighter(115))
                g.setColorAt(1, Theme.c("warm").darker(105))
                p.fillPath(path, g)
                draw_text(p, rect, text, f, QColor("#2A1A00"))
                p.restore()
        else:
            a = ease_out(clamp01((t - 2.0) / 0.5))
            draw_text(p, QRectF(0, badge_cy - 12, w, 24), f"Record : {r['best']}",
                      font(14, QFont.Weight.Medium, nums=True), Theme.c("sub"), alpha=a)

        items = [("BONNES RÉPONSES", r["correct"], "int"),
                 ("PRÉCISION", r["accuracy"], "pct"),
                 ("MEILLEURE SÉRIE", r["streak"], "int"),
                 ("TEMPS MOYEN", r["avg"], "sec")]
        gap = 10.0
        cw = (w - gap) / 2
        ch = (grid_h - gap) / 2
        for i, (label, v, kind) in enumerate(items):
            row, colm = divmod(i, 2)
            kk = clamp01((t - (2.3 + 0.14 * i)) / 0.5)
            if kk <= 0:
                continue
            e = ease_out(kk)
            x = colm * (cw + gap)
            y = grid_top + row * (ch + gap) + (1 - e) * 14
            p.save()
            p.setOpacity(e)
            path = QPainterPath()
            path.addRoundedRect(QRectF(x, y, cw, ch), 16, 16)
            p.fillPath(path, Theme.c("card"))
            p.setPen(QPen(Theme.c("line"), 1))
            p.drawPath(path)
            draw_text(p, QRectF(x + 12, y + 8, cw - 24, 16), label,
                      font(9, QFont.Weight.DemiBold, spacing=1.4), Theme.c("sub"),
                      Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            if kind == "sec":
                txt = "—" if v is None else f"{v * e:.1f} s"
            elif kind == "pct":
                txt = f"{int(round(v * e))}%"
            else:
                txt = str(int(round(v * e)))
            draw_text(p, QRectF(x + 12, y + ch * 0.35, cw - 24, ch * 0.55), txt,
                      font(min(ch * 0.45, 28), QFont.Weight.Bold, nums=True), Theme.c("text"),
                      Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            p.restore()

        if r.get("errors") and t >= 3.0:
            err_y = grid_top + grid_h + 10
            draw_text(p, QRectF(0, err_y, w, 20), f"Erreurs à réviser : {', '.join(r['errors'][:3])}",
                      font(11, QFont.Weight.Medium), Theme.c("danger"))

        self.particles.paint(p)


# --------------------------------------------------------------------------- #
#  Composants d'Ergonomie
# --------------------------------------------------------------------------- #
class LinkButton(QPushButton):
    def __init__(self, text, color="sub", px=13, parent=None):
        super().__init__(text, parent)
        self.color, self.px = color, px
        self._hover = 0.0
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedHeight(32)
        self._a = QVariantAnimation(self)
        self._a.setDuration(160)
        self._a.valueChanged.connect(lambda v: (setattr(self, "_hover", float(v)), self.update()))

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

    def sizeHint(self):
        fm = QFontMetrics(font(self.px, QFont.Weight.Medium))
        return QSize(fm.horizontalAdvance(self.text()) + 20, 32)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        base = Theme.c(self.color)
        col = mix(base, Theme.c("text"), 0.55 * self._hover) if self.color == "sub" else mix(base, base.lighter(125), self._hover)
        if not self.isEnabled():
            col = with_alpha(col, 90)
        f = font(self.px, QFont.Weight.Medium)
        p.setFont(f)
        p.setPen(col)
        p.drawText(QRectF(self.rect()), Qt.AlignmentFlag.AlignCenter, self.text())
        fm = QFontMetrics(f)
        tw = fm.horizontalAdvance(self.text())
        y = self.height() / 2 + fm.height() / 2 - 1
        x0 = (self.width() - tw) / 2
        p.setPen(QPen(with_alpha(col, 200 * self._hover), 1.2))
        p.drawLine(QPointF(x0, y), QPointF(x0 + tw * self._hover, y))

class CheckRow(QWidget):
    toggled = Signal(bool)

    def __init__(self, text, parent=None):
        super().__init__(parent)
        self.text = text
        self.checked = False
        self._k = 0.0
        self.setFixedHeight(40)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._a = QVariantAnimation(self)
        self._a.setDuration(240)
        self._a.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._a.valueChanged.connect(lambda v: (setattr(self, "_k", float(v)), self.update()))

    def set_checked(self, v, emit=False):
        v = bool(v)
        if v == self.checked:
            return
        self.checked = v
        self._a.stop()
        self._a.setStartValue(self._k)
        self._a.setEndValue(1.0 if v else 0.0)
        self._a.start()
        if emit:
            self.toggled.emit(v)

    def mousePressEvent(self, e):
        self.set_checked(not self.checked, emit=True)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        f = font(14, QFont.Weight.Medium)
        tw = QFontMetrics(f).horizontalAdvance(self.text)
        box = 24.0
        total = box + 12 + tw
        x0 = (self.width() - total) / 2
        rect = QRectF(x0, (self.height() - box) / 2, box, box)
        k = self._k

        path = QPainterPath()
        path.addRoundedRect(rect, 8, 8)
        p.fillPath(path, mix(Theme.c("card"), Theme.c("accent"), k))
        p.setPen(QPen(mix(Theme.c("line"), Theme.c("accent"), k), 1.6))
        p.drawPath(path)

        if k > 0:
            c = rect.center()
            a, b, d = QPointF(c.x() - 5.5, c.y() + 0.5), QPointF(c.x() - 1.5, c.y() + 4.5), QPointF(c.x() + 5.5, c.y() - 4)
            pen = QPen(QColor("#04262A"), 2.4)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            if k < 0.4:
                q = k / 0.4
                p.drawLine(a, QPointF(a.x() + (b.x() - a.x()) * q, a.y() + (b.y() - a.y()) * q))
            else:
                q = (k - 0.4) / 0.6
                p.drawLine(a, b)
                p.drawLine(b, QPointF(b.x() + (d.x() - b.x()) * q, b.y() + (d.y() - b.y()) * q))

        draw_text(p, QRectF(x0 + box + 12, 0, tw + 4, self.height()), self.text, f, Theme.c("text"),
                  Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

class AgeDisplay(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.value = None
        self._pop = 1.0
        self.setFixedHeight(100)
        self._a = QVariantAnimation(self)
        self._a.setDuration(320)
        self._a.setEasingCurve(QEasingCurve.Type.OutBack)
        self._a.valueChanged.connect(lambda v: (setattr(self, "_pop", float(v)), self.update()))

    def set_value(self, v):
        changed = v != self.value
        self.value = v
        if changed and v is not None:
            self._a.stop()
            self._a.setStartValue(0.0)
            self._a.setEndValue(1.0)
            self._a.start()
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        w, h = self.width(), self.height()
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 24, 24)
        p.fillPath(path, Theme.c("card"))
        p.setPen(QPen(Theme.c("line"), 1))
        p.drawPath(path)

        v = self.value
        invalid = v is not None and not (MIN_AGE <= v <= MAX_AGE)
        txt = "?" if v is None else str(v)
        col = Theme.c("sub") if v is None else (Theme.c("danger") if invalid else Theme.c("text"))
        s = 1.0 + 0.18 * (1 - self._pop)
        p.save()
        p.translate(w / 2, h * 0.44)
        p.scale(s, s)
        draw_text(p, QRectF(-w / 2, -34, w, 66), txt, font(56, QFont.Weight.Bold, nums=True), col)
        p.restore()
        draw_text(p, QRectF(0, h - 28, w, 18), "ANS", font(11, QFont.Weight.DemiBold, spacing=2.4), Theme.c("sub"))


# --------------------------------------------------------------------------- #
#  Fenêtre Principale
# --------------------------------------------------------------------------- #
class GameWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Calcul Éclair")
        self.setMinimumSize(390, 750)
        self.resize(430, 850)

        self.settings = QSettings("CalculatriceModerne", "CalculEclair")
        Theme.tm = 1.0 if self.settings.value("theme", "dark") == "light" else 0.0
        self._theme_target = Theme.tm
        lvl = self.settings.value("level", "Facile")
        self.level = lvl if lvl in LEVELS else "Facile"
        mode = self.settings.value("mode", "Classique")
        self.mode = mode if mode in MODES else "Classique"
        op = self.settings.value("op", "+")
        self.op = op if op in OPERATIONS else "+"
        muted = str(self.settings.value("muted", "false")).lower() == "true"
        self.sounds = SoundBank(muted)

        self.running = False
        self.counting = False
        self.busy = False
        self._gen = 0
        self.score = 0
        self.lives = MODES[self.mode]["lives"]
        self.streak = 0
        self.best_streak = 0
        self.correct = 0
        self.wrong = 0
        self.times = []
        self.errors = []
        self.remaining = MODES[self.mode]["time"]
        self.a = self.b = 0
        self.cur_op = "+"
        self.answer = ""
        self.q_start = time.monotonic()
        self.last_tick = time.monotonic()
        self.last_pair = None
        self._last_sec = 999
        self._faded_in = False
        self.first_run = False
        self._policy_from = 0
        self._erase_armed = False
        self.age_buf = ""

        self._bgtimer = QTimer(self)
        self._bgtimer.setInterval(33)
        self._bgtimer.timeout.connect(self._bg_tick)
        self._bgtimer.start()

        self._theme_anim = QVariantAnimation(self)
        self._theme_anim.setDuration(450)
        self._theme_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._theme_anim.valueChanged.connect(self._on_theme_tick)

        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self.tick)

        self._build_ui()
        self.sound_btn.muted = self.sounds.muted
        self.update_menu()

        onboarded = str(self.settings.value("onboarded", "false")).lower() == "true"
        if not onboarded or self.geti("policy_version") < POLICY_VERSION:
            self.open_profile(first=True)

    def changeEvent(self, e):
        if e.type() in (QEvent.Type.WindowStateChange, QEvent.Type.ActivationChange):
            if not self.isActiveWindow() or self.isMinimized():
                self._bgtimer.stop()
            else:
                if not self._bgtimer.isActive():
                    self._bgtimer.start()
        super().changeEvent(e)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedLayout()
        root.addLayout(self.stack)
        self.stack.addWidget(self._build_menu())
        self.stack.addWidget(self._build_game())
        self.stack.addWidget(self._build_results())
        self.stack.addWidget(self._build_profile())
        self.stack.addWidget(self._build_privacy())

        self.overlay = CountdownOverlay(self)
        self.theme_btn = IconButton("theme", self)
        self.theme_btn.setToolTip("Changer de thème (T)")
        self.theme_btn.clicked.connect(self.toggle_theme)
        self.sound_btn = IconButton("sound", self)
        self.sound_btn.setToolTip("Son (M)")
        self.sound_btn.clicked.connect(self.toggle_mute)

    def _build_menu(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(26, 60, 26, 20)
        lay.setSpacing(10)

        self.logo = LogoMark()
        lay.addWidget(self.logo, 0, Qt.AlignmentFlag.AlignHCenter)
        title = TextLabel("Calcul Éclair", 36, QFont.Weight.DemiBold, "text")
        title.setFixedHeight(48)
        sub = TextLabel("Entraîne ton cerveau au calcul mental", 13, QFont.Weight.Normal, "sub")
        sub.setFixedHeight(20)
        lay.addWidget(title)
        lay.addWidget(sub)

        lbl_op = TextLabel("OPÉRATION", 10, QFont.Weight.DemiBold, "sub", spacing=1.6)
        lbl_op.setFixedHeight(14)
        lay.addWidget(lbl_op)
        self.seg_op = SegmentedControl(OPERATIONS, self.op)
        self.seg_op.changed.connect(self.set_op)
        lay.addWidget(self.seg_op)

        lbl_mode = TextLabel("MODE DE JEU", 10, QFont.Weight.DemiBold, "sub", spacing=1.6)
        lbl_mode.setFixedHeight(14)
        lay.addWidget(lbl_mode)
        self.seg_mode = SegmentedControl(list(MODES.keys()), self.mode)
        self.seg_mode.changed.connect(self.set_mode)
        lay.addWidget(self.seg_mode)

        lbl_lvl = TextLabel("DIFFICULTÉ", 10, QFont.Weight.DemiBold, "sub", spacing=1.6)
        lbl_lvl.setFixedHeight(14)
        lay.addWidget(lbl_lvl)
        self.seg_lvl = SegmentedControl([(n, f"{lo}–{hi}") for n, (lo, hi, _) in LEVELS.items()], self.level)
        self.seg_lvl.changed.connect(self.set_level)
        lay.addWidget(self.seg_lvl)

        stats = QHBoxLayout()
        stats.setSpacing(10)
        self.st_best = StatPill("RECORD")
        self.st_streak = StatPill("SÉRIE MAX")
        self.st_games = StatPill("PARTIES")
        for s in (self.st_best, self.st_streak, self.st_games):
            stats.addWidget(s)
        lay.addLayout(stats)

        self.play_btn = AnimatedButton("JOUER", "primary", px=20, nums=False)
        self.play_btn.setMinimumHeight(68)
        self.play_btn.clicked.connect(self.start_game)
        lay.addWidget(self.play_btn)

        links = QHBoxLayout()
        links.setSpacing(6)
        links.addStretch(1)
        link_profile = LinkButton("Profil", "sub", 13)
        link_profile.clicked.connect(lambda _=False: self.open_profile(False))
        dot = TextLabel("·", 13, QFont.Weight.Normal, "sub")
        dot.setFixedWidth(10)
        link_policy = LinkButton("Confidentialité", "sub", 13)
        link_policy.clicked.connect(lambda _=False: self.open_policy(0))
        links.addWidget(link_profile)
        links.addWidget(dot)
        links.addWidget(link_policy)
        links.addStretch(1)
        lay.addLayout(links)

        return page

    def _build_game(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(22, 66, 22, 22)
        lay.setSpacing(8)

        hud = QHBoxLayout()
        self.hearts = HeartsWidget(START_LIVES)
        self.ring = TimerRing(MAX_TIME)
        self.score_w = ScoreWidget()
        hud.addWidget(self.hearts, 0, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        hud.addStretch(1)
        hud.addWidget(self.ring)
        hud.addStretch(1)
        hud.addWidget(self.score_w, 0, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        lay.addLayout(hud)

        self.streak_b = StreakBadge()
        lay.addWidget(self.streak_b)

        self.card = QuestionCard()
        lay.addWidget(self.card, 4)

        grid = QVBoxLayout()
        grid.setSpacing(10)
        self.keys = {}
        rows = [["7", "8", "9"], ["4", "5", "6"], ["1", "2", "3"], ["⌫", "0", "✓"]]
        kinds = {"⌫": "fn", "✓": "primary"}
        for row in rows:
            hb = QHBoxLayout()
            hb.setSpacing(10)
            for k in row:
                b = AnimatedButton(k, kinds.get(k, "num"), px=24, nums=(k.isdigit()))
                b.clicked.connect(lambda _=False, key=k: self.on_key(key))
                hb.addWidget(b)
                self.keys[k] = b
            grid.addLayout(hb, 1)
        lay.addLayout(grid, 5)
        return page

    def _build_results(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(22, 66, 22, 22)
        lay.setSpacing(14)
        self.results = ResultsView(self.sounds)
        lay.addWidget(self.results, 1)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.menu_btn = AnimatedButton("MENU", "num", px=16, nums=False)
        self.replay_btn = AnimatedButton("REJOUER", "primary", px=16, nums=False)
        for b in (self.menu_btn, self.replay_btn):
            b.setMinimumHeight(66)
            b.setMaximumHeight(66)
        self.menu_btn.clicked.connect(self.go_menu)
        self.replay_btn.clicked.connect(self.start_game)
        row.addWidget(self.menu_btn, 1)
        row.addWidget(self.replay_btn, 2)
        lay.addLayout(row)
        return page

    def _build_profile(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(26, 70, 26, 22)
        lay.setSpacing(10)
        lay.addStretch(1)

        self.profile_title = TextLabel("Bienvenue", 36, QFont.Weight.DemiBold, "text")
        self.profile_title.setFixedHeight(52)
        self.profile_sub = TextLabel("", 14, QFont.Weight.Normal, "sub")
        self.profile_sub.setFixedHeight(24)
        lay.addWidget(self.profile_title)
        lay.addWidget(self.profile_sub)
        lay.addSpacing(14)

        row = QHBoxLayout()
        row.setSpacing(12)
        self.age_minus = AnimatedButton("−", "fn", px=30)
        self.age_plus = AnimatedButton("+", "fn", px=30)
        for b in (self.age_minus, self.age_plus):
            b.setFixedSize(72, 100)
        self.age_disp = AgeDisplay()
        row.addWidget(self.age_minus)
        row.addWidget(self.age_disp, 1)
        row.addWidget(self.age_plus)
        lay.addLayout(row)
        self.age_minus.clicked.connect(lambda _=False: self.nudge_age(-1))
        self.age_plus.clicked.connect(lambda _=False: self.nudge_age(1))

        self.age_note = TextLabel("", 12, QFont.Weight.Medium, "warm")
        self.age_note.setFixedHeight(20)
        note2 = TextLabel("Ton âge est facultatif et reste sur ton appareil.", 12, QFont.Weight.Normal, "sub")
        note2.setFixedHeight(20)
        lay.addWidget(self.age_note)
        lay.addWidget(note2)
        lay.addSpacing(8)

        self.check = CheckRow("J'ai lu la politique de confidentialité")
        self.check.toggled.connect(self.update_profile_state)
        lay.addWidget(self.check)
        read = LinkButton("Lire la politique", "accent", 13)
        read.clicked.connect(lambda _=False: self.open_policy(3))
        lay.addWidget(read, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(6)

        self.ok_btn = AnimatedButton("CONTINUER", "primary", px=18, nums=False)
        self.ok_btn.setMinimumHeight(70)
        self.ok_btn.clicked.connect(self.save_profile)
        lay.addWidget(self.ok_btn)
        self.skip_link = LinkButton("Je préfère ne pas donner mon âge", "sub", 13)
        self.skip_link.clicked.connect(self.skip_age)
        lay.addWidget(self.skip_link, 0, Qt.AlignmentFlag.AlignHCenter)
        self.profile_back = LinkButton("← Retour au menu", "sub", 13)
        self.profile_back.clicked.connect(self.go_menu)
        lay.addWidget(self.profile_back, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addStretch(1)
        return page

    def _build_privacy(self):
        page = QWidget()
        lay = QVBoxLayout(page)
        lay.setContentsMargins(22, 66, 22, 22)
        lay.setSpacing(10)
        title = TextLabel("Confidentialité", 30, QFont.Weight.DemiBold, "text")
        title.setFixedHeight(46)
        lay.addWidget(title)

        self.policy_scroll = QScrollArea()
        self.policy_scroll.setWidgetResizable(True)
        self.policy_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.policy_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.policy_label = QLabel()
        self.policy_label.setWordWrap(True)
        self.policy_label.setTextFormat(Qt.TextFormat.RichText)
        self.policy_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.policy_label.setMargin(6)
        self.policy_scroll.setWidget(self.policy_label)
        lay.addWidget(self.policy_scroll, 1)

        self.erase_link = LinkButton("Effacer mes données", "danger", 13)
        self.erase_link.clicked.connect(self.erase_data)
        lay.addWidget(self.erase_link, 0, Qt.AlignmentFlag.AlignHCenter)
        back = AnimatedButton("RETOUR", "num", px=16, nums=False)
        back.setMinimumHeight(64)
        back.setMaximumHeight(64)
        back.clicked.connect(self.close_policy)
        lay.addWidget(back)
        self._style_policy()
        return page

    def _style_policy(self):
        if not hasattr(self, "policy_label"):
            return
        c = Theme.c
        text, sub, acc = c("text").name(), c("sub").name(), c("accent").name()
        h = with_alpha(c("sub"), 90)
        handle = f"rgba({h.red()},{h.green()},{h.blue()},{h.alpha() / 255:.3f})"
        self.policy_scroll.setStyleSheet(
            "QScrollArea{background:transparent;border:none;}"
            "QScrollArea>QWidget>QWidget{background:transparent;}"
            "QScrollBar:vertical{width:6px;background:transparent;margin:4px 0;}"
            f"QScrollBar::handle:vertical{{background:{handle};border-radius:3px;min-height:28px;}}"
            "QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical{height:0;}")
        parts = []
        for heading, paras in POLICY:
            parts.append(f"<p style='margin:16px 0 4px 0;'><span style='color:{acc};font-size:15px;"
                         f"font-weight:600;'>{heading}</span></p>")
            for para in paras:
                parts.append(f"<p style='margin:4px 0;color:{text};font-size:13px;'>{para}</p>")
        parts.append(f"<p style='margin:18px 0 6px 0;color:{sub};font-size:12px;'>"
                     f"Dernière mise à jour : {POLICY_DATE}</p>")
        self.policy_label.setText("".join(parts))
        self.policy_label.setStyleSheet("background:transparent;")

    def open_profile(self, first=False):
        self.first_run = first
        self.profile_title.setText("Bienvenue" if first else "Ton profil")
        self.profile_sub.setText("Quelques infos pour adapter le jeu" if first
                                 else "Modifie ton âge ou relis la politique")
        raw = self.settings.value("age", None)
        try:
            age = int(raw) if raw not in (None, "") else None
        except (TypeError, ValueError):
            age = None
        self.age_buf = str(age) if age is not None else ""
        self.age_disp.set_value(age)
        accepted = (str(self.settings.value("consent", "false")).lower() == "true"
                    and self.geti("policy_version") >= POLICY_VERSION)
        self.check.set_checked(accepted)
        self.ok_btn.setText("CONTINUER" if first else "ENREGISTRER")
        self.profile_back.setVisible(not first)
        self.update_profile_state()
        self.show_page(3)

    def update_profile_state(self, *_):
        age = self.age_disp.value
        valid = age is not None and MIN_AGE <= age <= MAX_AGE
        consent = self.check.checked
        self.ok_btn.setEnabled(valid and consent)
        self.skip_link.setEnabled(consent)
        if valid and age < 13:
            note = "Moins de 13 ans : demande l'accord d'un parent."
        elif age is not None and not valid:
            note = f"L'âge doit être compris entre {MIN_AGE} et {MAX_AGE} ans."
        else:
            note = ""
        self.age_note.setText(note)

    def nudge_age(self, d):
        cur = self.age_disp.value
        new = 14 if cur is None else max(MIN_AGE, min(MAX_AGE, cur + d))
        self.age_buf = str(new)
        self.age_disp.set_value(new)
        self.sounds.play("click")
        self.update_profile_state()

    def type_age(self, digit):
        self.age_buf = (self.age_buf + digit)[-2:]
        self.age_disp.set_value(int(self.age_buf))
        self.sounds.play("click")
        self.update_profile_state()

    def backspace_age(self):
        self.age_buf = self.age_buf[:-1]
        self.age_disp.set_value(int(self.age_buf) if self.age_buf else None)
        self.sounds.play("click")
        self.update_profile_state()

    def save_profile(self, *_):
        age = self.age_disp.value
        if age is None or not (MIN_AGE <= age <= MAX_AGE) or not self.check.checked:
            return
        self.settings.setValue("age", age)
        self._finish_profile(age)

    def skip_age(self, *_):
        if not self.check.checked:
            return
        self.settings.remove("age")
        self._finish_profile(None)

    def _finish_profile(self, age):
        first = self.first_run
        self.settings.setValue("consent", "true")
        self.settings.setValue("onboarded", "true")
        self.settings.setValue("policy_version", POLICY_VERSION)
        if first and age is not None and not self.settings.contains("level"):
            self.level = "Facile" if age <= 11 else "Moyen"
            self.settings.setValue("level", self.level)
        self.first_run = False
        self.sounds.play("go" if first else "click")
        self.update_menu()
        self.show_page(0)

    def open_policy(self, from_page=0):
        self._policy_from = from_page
        self._style_policy()
        self.policy_scroll.verticalScrollBar().setValue(0)
        self.erase_link.setVisible(not self.first_run)
        self.sounds.play("click")
        self.show_page(4)

    def close_policy(self):
        self.sounds.play("click")
        self.show_page(3 if self._policy_from == 3 else 0)

    def erase_data(self, *_):
        if not self._erase_armed:
            self._erase_armed = True
            self.erase_link.setText("Confirmer : tout effacer ?")
            self.sounds.play("pop")
            QTimer.singleShot(3500, self._disarm_erase)
            return
        self._erase_armed = False
        self.erase_link.setText("Effacer mes données")
        self.settings.clear()
        self.level = "Facile"
        self.mode = "Classique"
        self.op = "+"
        self.update_menu()
        self.sounds.play("wrong")
        self.open_profile(first=True)

    def _disarm_erase(self):
        if self._erase_armed:
            self._erase_armed = False
            self.erase_link.setText("Effacer mes données")

    def _bg_tick(self):
        if not self.isActiveWindow() or self.isMinimized():
            return
        self.update()
        if self.stack.currentIndex() == 0:
            self.play_btn.glow = 0.55 + 0.45 * math.sin(time.monotonic() * 2.2)
            self.play_btn.update()
            self.logo.update()

    def paintEvent(self, _):
        p = QPainter(self)
        paint_background(p, self.width(), self.height())

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self.theme_btn.move(self.width() - 58, 16)
        self.sound_btn.move(self.width() - 106, 16)
        self.overlay.setGeometry(self.rect())

    def showEvent(self, e):
        super().showEvent(e)
        if not self._faded_in:
            self._faded_in = True
            self.setWindowOpacity(0.0)
            self._fade = QPropertyAnimation(self, b"windowOpacity", self)
            self._fade.setDuration(500)
            self._fade.setStartValue(0.0)
            self._fade.setEndValue(1.0)
            self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)
            self._fade.start()

    def toggle_theme(self):
        self.sounds.play("click")
        self._theme_target = 0.0 if self._theme_target > 0.5 else 1.0
        self._theme_anim.stop()
        self._theme_anim.setStartValue(Theme.tm)
        self._theme_anim.setEndValue(self._theme_target)
        self._theme_anim.start()
        self.settings.setValue("theme", "light" if self._theme_target > 0.5 else "dark")

    def _on_theme_tick(self, v):
        Theme.tm = float(v)
        self._style_policy()
        for w in self.findChildren(QWidget):
            w.update()
        self.update()

    def toggle_mute(self):
        self.sounds.muted = not self.sounds.muted
        self.sound_btn.muted = self.sounds.muted
        self.sound_btn.update()
        self.settings.setValue("muted", "true" if self.sounds.muted else "false")
        if not self.sounds.muted:
            self.sounds.play("pop")

    def show_page(self, index):
        self.stack.setCurrentIndex(index)
        page = self.stack.currentWidget()
        eff = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self)
        anim.setDuration(380)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.finished.connect(lambda pg=page: pg.setGraphicsEffect(None))
        anim.start()
        self._page_anim = anim

    def geti(self, key):
        try:
            return int(self.settings.value(key, 0))
        except (TypeError, ValueError):
            return 0

    def best(self, level):
        return self.geti(f"best_{self.op}_{self.mode}_{level}")

    def set_level(self, name):
        self.level = name
        self.settings.setValue("level", name)
        self.sounds.play("click")
        self.update_menu()

    def set_mode(self, name):
        if name not in MODES:
            return
        self.mode = name
        self.settings.setValue("mode", name)
        self.sounds.play("click")
        self.update_menu()

    def set_op(self, name):
        if name not in OPERATIONS:
            return
        self.op = name
        self.settings.setValue("op", name)
        self.sounds.play("click")
        self.update_menu()

    def update_menu(self):
        self.seg_lvl.set_current(self.level)
        self.seg_mode.set_current(self.mode)
        self.seg_op.set_current(self.op)
        self.st_best.set_value(str(self.best(self.level)))
        self.st_streak.set_value(str(self.geti("best_streak_all")))
        self.st_games.set_value(str(self.geti("games_played")))

    def go_menu(self):
        self.sounds.play("click")
        self.update_menu()
        self.show_page(0)

    def start_game(self):
        self._gen += 1
        gen = self._gen
        self.timer.stop()
        self.running = False
        self.busy = False
        self.counting = True
        m = MODES[self.mode]
        self.score = 0
        self.lives = m["lives"]
        self.streak = 0
        self.best_streak = self.correct = self.wrong = 0
        self.times = []
        self.errors = []
        self.remaining = m["time"]
        self.last_pair = None
        self.answer = ""

        self.hearts.n = 3 if math.isinf(m["lives"]) else m["lives"]
        self.hearts.set_lives(m["lives"])
        self.ring.max_time = 60.0 if math.isinf(m["time"]) else m["time"]
        self.ring.set_remaining(m["time"])
        self.score_w.reset()
        self.streak_b.set_streak(0)
        self.card.reset_state()
        self.card.tag_right = f"{self.op} · {self.level.upper()}"
        self.show_page(1)

        self.sounds.play("click")
        for text, ms in (("3", 250), ("2", 950), ("1", 1650), ("GO!", 2350)):
            QTimer.singleShot(ms, lambda t=text, g=gen: self._count_step(t, g))

    def _count_step(self, text, gen):
        if gen != self._gen or not self.counting:
            return
        if text == "GO!":
            self.overlay.show_value("GO!", go=True)
            self.sounds.play("go")
            self.counting = False
            self.begin_play()
        else:
            self.overlay.show_value(text)
            self.sounds.play("beep")

    def begin_play(self):
        self.running = True
        self._last_sec = 999
        self.new_question()
        self.last_tick = time.monotonic()
        if not math.isinf(self.remaining):
            self.timer.start()

    def new_question(self):
        lo, hi, _ = LEVELS[self.level]
        ops = ["+", "−", "×", "÷"] if self.op == "Mélange" else [self.op]
        cur_op = random.choice(ops)

        while True:
            if cur_op == "+":
                a, b = random.randint(lo, hi), random.randint(lo, hi)
            elif cur_op == "−":
                a = random.randint(lo, hi)
                b = random.randint(lo, a)
            elif cur_op == "×":
                max_mult = 12 if self.level == "Facile" else (20 if self.level == "Moyen" else 50)
                a, b = random.randint(1, max_mult), random.randint(1, max_mult)
            else:  # "÷"
                b = random.randint(1, 12 if self.level == "Facile" else 25)
                res = random.randint(1, 12 if self.level == "Facile" else 25)
                a = b * res
            if (a, b, cur_op) != self.last_pair:
                break

        self.last_pair = (a, b, cur_op)
        self.a, self.b, self.cur_op = a, b, cur_op
        self.answer = ""
        self.q_start = time.monotonic()
        self.card.set_question(a, b, cur_op)

    def tick(self):
        now = time.monotonic()
        dt = now - self.last_tick
        self.last_tick = now
        if not self.running or math.isinf(self.remaining):
            return
        self.remaining -= dt
        if self.remaining <= 0:
            self.remaining = 0
            self.ring.set_remaining(0)
            self.end_game("temps écoulé")
            return
        self.ring.set_remaining(self.remaining)
        sec = math.ceil(self.remaining)
        if sec <= 10 and sec != self._last_sec:
            self._last_sec = sec
            self.sounds.play("tick")

    def on_key(self, k):
        if not self.running or self.busy:
            return
        if k.isdigit():
            if len(self.answer) < 5:
                self.answer += k
                self.sounds.play("click")
        elif k == "⌫":
            if self.answer:
                self.sounds.play("click")
            self.answer = self.answer[:-1]
        elif k == "✓":
            self.validate()
            return
        self.card.set_answer(self.answer)

    def validate(self):
        if not self.answer:
            return
        if self.cur_op == "+":
            target = self.a + self.b
        elif self.cur_op == "−":
            target = self.a - self.b
        elif self.cur_op == "×":
            target = self.a * self.b
        else:  # "÷"
            target = self.a // self.b

        if int(self.answer) == target:
            self.on_correct()
        else:
            self.on_wrong(target)

    def on_correct(self):
        mult = LEVELS[self.level][2]
        elapsed = time.monotonic() - self.q_start
        self.streak += 1
        self.best_streak = max(self.best_streak, self.streak)
        self.correct += 1
        self.times.append(elapsed)
        pts = mult * (10 + min(self.streak - 1, 5) * 2)
        if elapsed < FAST_ANSWER:
            pts += 5 * mult
        self.score += pts

        bonus = MODES[self.mode]["bonus"]
        if not math.isinf(self.remaining) and bonus > 0:
            # CORRECTION : le temps ne dépasse jamais la durée du mode (15 s en Extrême)
            self.remaining = min(MODES[self.mode]["time"], self.remaining + bonus)
            self.ring.set_remaining(self.remaining)
            self.ring.show_bonus(f"+{int(bonus)} s")

        self.sounds.play(f"correct{min(self.streak - 1, 5)}")
        self.score_w.set_score(self.score)
        self.streak_b.set_streak(self.streak)
        self.card.flash_good(f"+{pts}")
        self.new_question()

    def on_wrong(self, target):
        if not math.isinf(self.lives):
            self.lives -= 1
        self.wrong += 1
        self.streak = 0
        self.busy = True
        self.errors.append(f"{self.a} {self.cur_op} {self.b} = {target}")
        self.sounds.play("wrong")
        self.hearts.set_lives(self.lives, animate=True)
        self.streak_b.set_streak(0)
        self.card.flash_bad(f"Réponse : {target}")
        QTimer.singleShot(1000, self._after_wrong)

    def _after_wrong(self):
        self.busy = False
        if not self.running:
            return
        if not math.isinf(self.lives) and self.lives <= 0:
            self.end_game("plus de vies")
        else:
            self.new_question()

    def end_game(self, reason):
        if not self.running:
            return
        self.running = False
        self.timer.stop()

        total = self.correct + self.wrong
        accuracy = round(100 * self.correct / total) if total else 0
        avg = (sum(self.times) / len(self.times)) if self.times else None
        mult = LEVELS[self.level][2]
        stars = sum(1 for s in STAR_STEPS if self.score >= s * mult)
        prev_best = self.best(self.level)
        record = self.score > prev_best and self.score > 0
        if record:
            self.settings.setValue(f"best_{self.op}_{self.mode}_{self.level}", self.score)
        self.settings.setValue("games_played", self.geti("games_played") + 1)
        self.settings.setValue("best_streak_all", max(self.geti("best_streak_all"), self.best_streak))

        res = dict(level=f"{self.op} ({self.mode})", reason=reason, score=self.score, correct=self.correct,
                   accuracy=accuracy, streak=self.best_streak, avg=avg, stars=stars,
                   record=record, best=max(prev_best, self.score), errors=self.errors)
        gen = self._gen
        QTimer.singleShot(800, lambda: self._goto_results(res, gen))

    def _goto_results(self, res, gen):
        if gen != self._gen or self.running or self.counting:
            return
        self.show_page(2)
        self.results.start(res)

    def abandon(self):
        # CORRECTION : en mode Zen (sans fin), Échap termine la partie et affiche les résultats
        if self.running and self.mode == "Zen" and (self.correct + self.wrong) > 0:
            self.end_game("partie terminée")
            return
        self._gen += 1
        self.counting = False
        self.running = False
        self.busy = False
        self.timer.stop()
        self.overlay.hide()
        self.go_menu()

    def keyPressEvent(self, e):
        key, text = e.key(), e.text()
        if text in ("t", "T"):
            self.toggle_theme()
            return
        if text in ("m", "M"):
            self.toggle_mute()
            return

        page = self.stack.currentIndex()
        enter = key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        if page == 0:
            if enter:
                self.start_game()
                return
            if text in ("1", "2", "3"):
                self.seg_lvl.select(int(text) - 1)
                return
        elif page == 1:
            if key == Qt.Key.Key_Escape:
                self.abandon()
                return
            k = None
            if text and text in "0123456789":
                k = text
            elif key == Qt.Key.Key_Backspace:
                k = "⌫"
            elif enter:
                k = "✓"
            if k:
                if self.running and not self.busy:
                    self.keys[k].tap()
                self.on_key(k)
                return
        elif page == 2:
            if key == Qt.Key.Key_Escape:
                self.go_menu()
                return
            if enter or key == Qt.Key.Key_Space:
                if not self.results.finished():
                    self.results.skip()
                else:
                    self.start_game()
                return
        elif page == 3:
            if text and text in "0123456789":
                self.type_age(text)
                return
            if key == Qt.Key.Key_Backspace:
                self.backspace_age()
                return
            if key == Qt.Key.Key_Up:
                self.nudge_age(1)
                return
            if key == Qt.Key.Key_Down:
                self.nudge_age(-1)
                return
            if enter:
                self.save_profile()
                return
            if key == Qt.Key.Key_Escape and not self.first_run:
                self.go_menu()
                return
        elif page == 4:
            if key == Qt.Key.Key_Escape:
                self.close_policy()
                return
        super().keyPressEvent(e)


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    w = GameWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
"""侧边 Tab：收起态可拖动箭头，展开态图标盘+动作列。"""
from __future__ import annotations
import math
from PySide6.QtWidgets import (QWidget, QPushButton, QVBoxLayout, QGridLayout,
                               QFrame, QLabel, QGraphicsOpacityEffect)
from PySide6.QtCore import (Qt, QTimer, QPropertyAnimation, QRect, QRectF,
                            QPointF, QPoint, QSize, QEvent)
from PySide6.QtGui import (QGuiApplication, QColor, QPainter, QPen, QPolygonF,
                           QPainterPath, QPixmap, QIcon, QLinearGradient,
                           QRadialGradient)
from .._paths import resource_dir
from ..i18n import t
from ..cats import get as get_cat_def
from .tips import install as install_tip

# 图标猫用 Saint 定义
_SAINT = get_cat_def("saint")
_HEAD_ATLAS, _HEAD_FAM = _SAINT.frames["head"]
_FACE_ATLAS, _FACE_FAM = _SAINT.frames["face"]

COLLAPSED_W, COLLAPSED_H = 24, 48
EXPANDED_W = 120
EXPANDED_H = 250                       # 仅估值，实际走 _expanded_h()
SLIDE_MS = 150
# 图标盘配色（贴合面板绿橄榄调）
_ICON_GREY = QColor(192, 199, 183)
_ICON_GREY_DARK = QColor(78, 84, 74)
_ICON_GREY_LIGHT = QColor(150, 158, 142)
_POLE_EDGE = QColor(20, 22, 26)
_POLE_SHEEN = QColor(104, 112, 126)
_POLE_CORE = QColor(40, 42, 47)
_POLE_TILE = QColor(255, 255, 255, 12)
_ICON_SAINT = QColor(*_SAINT.body_color)
_ICON_EYE = QColor(*_SAINT.eye_color)
_ICON_AMBER = QColor(233, 203, 138)
_ICON_FACET = QColor(70, 76, 66, 160)
_ICON_RED = QColor(210, 96, 84)
_FRUIT_TOP = QColor(140, 185, 255)
_FRUIT_BOT = QColor(28, 64, 210)
_FRUIT_OUTLINE = QColor(22, 26, 44)
_LAMP_OUTLINE = QColor(255, 70, 20)
_LAMP_FLESH = QColor(255, 248, 230)
_SLIME_BODY = QColor(255, 122, 26)
_SLIME_TENDRIL = QColor(204, 92, 16)
_SLIME_GLOW = QColor(255, 150, 50, 90)
_BAT_BODY = QColor(24, 26, 30)
_BAT_EYE = QColor(232, 236, 226)
_LIZ_BODY = QColor(122, 158, 108)
_LIZ_EYE = QColor(238, 244, 250)
_SQUID_BODY = QColor(236, 240, 245)
_SQUID_WING = QColor(206, 222, 238, 170)
_SQUID_SHELL = QColor(126, 190, 226)
_PEARL_BALL = QColor(240, 243, 248)
_PEARL_EDGE = QColor(138, 180, 214)
_PEARL_SHINE = QColor(255, 255, 255)
_ICON_GOLD = QColor(206, 158, 76)
_SPEAR_SHAFT = QColor(126, 100, 74)
_NWORM_BODY = QColor(224, 158, 196)
_NWORM_HI = QColor(255, 214, 232)
_SPEAR_TIP = QColor(198, 206, 214)
_SCAV_BODY = QColor(58, 62, 50)
_SCAV_MASK = QColor(232, 238, 232)
_SCAV_EYE = QColor(24, 26, 22)
_SC_LEAF = QColor(96, 116, 66)
_SC_SEED = QColor(255, 118, 78)


def _pen(c, w, cap=True):
    p = QPen(c, w)
    p.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    if cap:
        p.setCapStyle(Qt.PenCapStyle.RoundCap)
    return p


_CAT_HEAD = "Kill_Slugcat"             # 横杆实心猫头帧


def _cat_ready(atlas):
    """图集含所需帧才叠猫，否则回退纯杆。"""
    if atlas is None:
        return False
    base = atlas.get("base")
    return (base.has("BodyA") and base.has("LegsAVerticalPole") and base.has("PlayerArm0")
            and atlas.get(_FACE_ATLAS).has(_FACE_FAM + "1") and base.has("OnTopOfTerrainHand")
            and atlas.get(_HEAD_ATLAS).has(_HEAD_FAM + "0") and atlas.get("ui").has(_CAT_HEAD))


def _blit(p, atlas, key, frame, center, k, w, rot=0.0, tint=None):
    """图集帧染色缩放绘制；rot 顺时针度。"""
    pm = atlas.sprite(key, frame, tint or _ICON_SAINT, padded=False)
    sc = k * w / 22.0
    pw, ph = pm.width() * sc, pm.height() * sc
    p.save()
    p.translate(center.x(), center.y())
    if rot:
        p.rotate(rot)
    p.drawPixmap(QRectF(-pw / 2, -ph / 2, pw, ph), pm, QRectF(pm.rect()))
    p.restore()


def _pole_rod(p, r, vertical):
    """近黑圆柱杆 + 高光渐变 + 圆头。"""
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    if vertical:
        bw = w * 0.22
        rod = QRectF(cx - bw / 2, r.top() + h * 0.04, bw, h * 0.92)
        g = QLinearGradient(rod.left(), 0.0, rod.right(), 0.0)   # 横向受光
        rad = bw / 2
    else:
        bh = h * 0.24
        rod = QRectF(r.left() + w * 0.04, cy - bh / 2, w * 0.92, bh)
        g = QLinearGradient(0.0, rod.top(), 0.0, rod.bottom())   # 纵向受光
        rad = bh / 2
    g.setColorAt(0.0, _POLE_EDGE)
    g.setColorAt(0.30, _POLE_SHEEN)
    g.setColorAt(0.55, _POLE_CORE)
    g.setColorAt(1.0, _POLE_EDGE)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(g)
    p.drawRoundedRect(rod, rad, rad)


def _paint_pole_icon(p, r, vertical, atlas=None):
    """近黑杆+高光渐变；有图集叠 Saint 绿蛞蝓猫。"""
    w = r.width()
    L, T = r.left(), r.top()

    def Pt(fx, fy):
        return QPointF(L + fx * w, T + fy * r.height())

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_POLE_TILE)
    p.drawRoundedRect(r, w * 0.24, w * 0.24)

    if not _cat_ready(atlas):
        _pole_rod(p, r, vertical)
        return

    if vertical:
        # 整猫在杆后，右手压杆前
        _blit(p, atlas, "base", "LegsAVerticalPole", Pt(0.60, 0.66), 0.95, w)
        _blit(p, atlas, "base", "BodyA", Pt(0.64, 0.48), 0.50, w)
        _blit(p, atlas, "base", "PlayerArm0", Pt(0.56, 0.47), 0.36, w, rot=16.0)
        _blit(p, atlas, _HEAD_ATLAS, _HEAD_FAM + "0", Pt(0.64, 0.30), 0.46, w)
        _blit(p, atlas, _FACE_ATLAS, _FACE_FAM + "1", Pt(0.64, 0.28), 0.46, w, tint=_ICON_EYE)
        _blit(p, atlas, "base", "OnTopOfTerrainHand", Pt(0.39, 0.35), 0.37, w)  # 左手·杆后
        _pole_rod(p, r, vertical)                           # 杆压上
        _blit(p, atlas, "base", "OnTopOfTerrainHand", Pt(0.575, 0.47), 0.37, w)  # 右手·杆前
    else:
        # 先画猫，最后压杆盖住臂中段
        p.setPen(_pen(_ICON_SAINT, 0.11 * w))
        p.drawLine(Pt(0.5, 0.78), Pt(0.5, 0.88))            # 小身
        p.setPen(_pen(_ICON_SAINT, 0.045 * w))
        p.drawLine(Pt(0.5, 0.88), Pt(0.44, 0.97))           # 双腿垂
        p.drawLine(Pt(0.5, 0.88), Pt(0.56, 0.97))
        _blit(p, atlas, "ui", _CAT_HEAD, Pt(0.5, 0.82), 0.60, w)   # 大头
        p.setPen(_pen(_ICON_SAINT, 0.055 * w))              # 双臂上举
        p.drawLine(Pt(0.45, 0.74), Pt(0.415, 0.325))
        p.drawLine(Pt(0.55, 0.74), Pt(0.585, 0.325))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_ICON_SAINT)
        rr = 0.033 * w
        for hx in (0.415, 0.585):                           # 爪尖
            p.drawEllipse(Pt(hx, 0.325), rr, rr)
        _pole_rod(p, r, vertical)                           # 杆最后压上


# ── 原版物件/生物图标（ui 图集，就是 wiki 上那些图标）──
# 反编译依据：
#   ItemSymbol.SpriteNameForItem   → Symbol_Rock / Symbol_Spear / Symbol_Pearl /
#                                    Symbol_Lantern / Symbol_DangleFruit /
#                                    Symbol_SeedCob / Symbol_SlimeMold
#   ItemSymbol.ColorForItem        → 上面那张贴图的 myColor（正片叠底）
#   CreatureSymbol.SpriteNameOfCreature → Kill_Bat / Kill_Standard_Lizard /
#                                    Kill_Cicada / Kill_Scavenger / Kill_NeedleWorm
#   CreatureSymbol.ColorOfCreature → 生物贴图的 myColor（蜥蜴取 LizardBreeds.standardColor）
# 原版菜单 = 贴图 + myColor，没有别的画法；这里照抄，所以图标与游戏内/wiki 完全同源。
# 缺图集（没有 uisprites/uiSprites）时 _paint_symbol_icon 返回 False，退回原来的矢量画法。
_SYMBOL_ICONS = {
    "stone":     ("ui", "Symbol_Rock",          (1.0, 1.0, 1.0)),
    "spear":     ("ui", "Symbol_Spear",         (1.0, 1.0, 1.0)),
    "pearl":     ("ui", "Symbol_Pearl",         (0.55, 0.75, 1.0)),
    "lamp":      ("ui", "Symbol_Lantern",       (1.0, 0.5725, 0.3176)),
    "fruit":     ("ui", "Symbol_DangleFruit",   (0.0, 0.0, 1.0)),
    "seedcob":   ("ui", "Symbol_SeedCob",       (0.6824, 0.1569, 0.1176)),
    "slimemold": ("ui", "Symbol_SlimeMold",     (1.0, 0.6, 0.0)),
    # 生物：Kill_* 是原版图鉴/竞技场击杀列表用的贴图
    "batfly":      ("ui", "Kill_Bat",              (0.5, 0.5, 0.5)),
    "lizard":      ("ui", "Kill_Standard_Lizard",  (1.0, 0.0, 1.0)),   # 粉蜥 standardColor
    "squidcada":   ("ui", "Kill_Cicada",           (1.0, 1.0, 1.0)),   # CicadaA
    "needleworm":  ("ui", "Kill_NeedleWorm",       (1.0, 0.5961, 0.5961)),
    "scavenger":   ("ui", "Kill_Scavenger",        (0.5, 0.5, 0.5)),
}


_WIKI_ICON_CACHE = {}


def _wiki_icon(kind):
    """wiki 图源图标：本仓库打包的 resources/icons/<kind>.png。

    用户口径：图标按 wiki 的 `<名字>_icon.png` 直接提取（已带原版配色），
    不再走 ItemSymbol 的 myColor 正片叠底。缺失返回 None。
    """
    if kind in _WIKI_ICON_CACHE:
        return _WIKI_ICON_CACHE[kind]
    pm = None
    try:
        path = resource_dir() / "icons" / (kind + ".png")
        if path.is_file():
            img = QPixmap(str(path))
            if not img.isNull():
                pm = img
    except Exception:
        pm = None
    _WIKI_ICON_CACHE[kind] = pm
    return pm


def _paint_symbol_icon(p, kind, r, atlas=None) -> bool:
    """原版图标：wiki 贴图优先，其次 ui 图集 Symbol_* / Kill_* 按 myColor 叠色。

    返回 True=已画（调用方不要再走矢量回退）；False=没有这一帧。
    """
    pm = _wiki_icon(kind)
    w = h = 0
    if pm is not None:
        w, h = pm.width(), pm.height()
    else:
        spec = _SYMBOL_ICONS.get(kind)
        if spec is None or atlas is None:
            return False
        key, frame, rgb = spec
        try:
            at = atlas.get(key)
            if not at.has(frame):
                return False
            w, h = atlas.source_size(key, frame)
            tint = QColor(int(round(rgb[0] * 255)), int(round(rgb[1] * 255)),
                          int(round(rgb[2] * 255)))
            pm = atlas.sprite(key, frame, tint)
        except Exception:
            return False
    if pm is None or w <= 0 or h <= 0:
        return False
    k = min(r.width() / float(w), r.height() / float(h)) * 0.94
    pw, ph = w * k, h * k
    cx, cy = r.center().x(), r.center().y()
    p.save()
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)  # 原版点采样
    p.drawPixmap(QRectF(cx - pw / 2, cy - ph / 2, pw, ph), pm, QRectF(pm.rect()))
    p.restore()
    return True


def _paint_place_icon(p, kind, r, atlas=None):
    """在矩形 r 内画一个可交互实体图标。"""
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()

    if _paint_symbol_icon(p, kind, r, atlas):
        return                       # 原版贴图优先（就是 wiki/游戏内那张）

    if kind == "vpole":
        _paint_pole_icon(p, r, vertical=True, atlas=atlas)
    elif kind == "hpole":
        _paint_pole_icon(p, r, vertical=False, atlas=atlas)
    elif kind == "fruit":
        # 果子 sprite 缩小+蓝渐变，缺图集回退矢量
        if atlas is not None and atlas.get("base").has("DangleFruit0A"):
            _paint_fruit_sprite(p, r, atlas)
        else:
            _paint_fruit_fallback(p, r)
    elif kind == "stone":
        # 不规则鹅卵石 + 棱线
        ox, oy = cx, cy + h * 0.04
        pts = [(-0.54, 0.12), (-0.30, -0.40), (0.10, -0.46),
               (0.54, -0.12), (0.46, 0.34), (-0.12, 0.46)]
        poly = [QPointF(ox + dx * w * 0.56, oy + dy * h * 0.50) for dx, dy in pts]
        p.setPen(_pen(_ICON_GREY, max(1.8, w * 0.13), cap=False)); p.setBrush(_ICON_GREY)
        p.drawPolygon(QPolygonF(poly))
        p.setPen(_pen(_ICON_FACET, max(1.2, w * 0.07))); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawLine(QPointF(ox - w * 0.20, oy - h * 0.16),
                   QPointF(ox + w * 0.08, oy - h * 0.24))
    elif kind == "lamp":
        # 灯泡 sprite+暖光圈，缺图集回退矢量
        if atlas is not None and atlas.get("base").has("DangleFruit0A"):
            _paint_lamp_sprite(p, r, atlas)
        else:
            d = w * 0.42
            bulb = QRectF(0, 0, d, d); bulb.moveCenter(QPointF(cx, cy))
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(_ICON_AMBER)
            p.drawEllipse(bulb)
            p.setPen(_pen(_ICON_AMBER, max(1.4, w * 0.08))); p.setBrush(Qt.BrushStyle.NoBrush)
            bc, rad = bulb.center(), d / 2
            for k in range(8):
                a = math.radians(22.5 + 45 * k)
                p.drawLine(
                    QPointF(bc.x() + math.cos(a) * (rad + w * 0.05),
                            bc.y() - math.sin(a) * (rad + w * 0.05)),
                    QPointF(bc.x() + math.cos(a) * (rad + w * 0.18),
                            bc.y() - math.sin(a) * (rad + w * 0.18)))
    elif kind == "slimemold":
        _paint_slimemold_icon(p, r, atlas)
    elif kind == "batfly":
        # 蝙蝠剪影：身+双翅+亮眼
        bx, by = cx, cy + h * 0.06
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(_BAT_BODY)
        for sgn in (-1, 1):                                    # 双翅镜像
            wing = [QPointF(bx + sgn * w * 0.02, by - h * 0.16),
                    QPointF(bx + sgn * w * 0.46, by - h * 0.34),
                    QPointF(bx + sgn * w * 0.30, by + h * 0.06),
                    QPointF(bx + sgn * w * 0.02, by + h * 0.10)]
            p.drawPolygon(QPolygonF(wing))
        body = QRectF(0, 0, w * 0.26, h * 0.40)
        body.moveCenter(QPointF(bx, by))
        p.drawEllipse(body)
        p.setBrush(_BAT_EYE)
        p.drawEllipse(QPointF(bx, by - h * 0.09), w * 0.035, w * 0.035)
    elif kind == "lizard":
        _paint_lizard_icon(p, r)
    elif kind == "squidcada":
        _paint_squidcada_icon(p, r)
    elif kind == "needleworm":
        _paint_needleworm_icon(p, r)
    elif kind == "pearl":
        _paint_pearl_icon(p, r)
    elif kind == "spear":
        _paint_spear_icon(p, r)
    elif kind == "scavenger":
        _paint_scavenger_icon(p, r)
    elif kind == "seedcob":
        _paint_seedcob_icon(p, r)
    elif kind == "karmaflower":
        _paint_karmaflower_icon(p, r)
    elif kind == "erase":
        # 橡皮：右下角一个小物件轮廓 + 压在上面的红叉
        d = min(w, h) * 0.52
        obj = QRectF(0, 0, d, d)
        obj.moveCenter(QPointF(cx - w * 0.10, cy + h * 0.10))
        p.setPen(_pen(_ICON_GREY, max(1.4, w * 0.09)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(obj)
        p.setPen(_pen(_ICON_RED, max(2.2, w * 0.16)))
        q = min(w, h) * 0.34
        p.drawLine(QPointF(cx - q, cy - q), QPointF(cx + q, cy + q))
        p.drawLine(QPointF(cx + q, cy - q), QPointF(cx - q, cy + q))
    elif kind == "shelter":
        # 庇护所：外框 + 内部 + 两块门板（与小屋同一套视觉语言）
        body = QRectF(cx - w * 0.44, cy - h * 0.34, w * 0.88, h * 0.68)
        p.setPen(_pen(_ICON_GREY, max(1.4, w * 0.09)))
        p.setBrush(_ICON_GREY_DARK)
        p.drawRect(body)
        p.setPen(_pen(_ICON_GREY_LIGHT, max(1.0, w * 0.06)))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(body.adjusted(w * 0.10, h * 0.10, -w * 0.10, -h * 0.10))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(_ICON_GREY_LIGHT)
        dw = w * 0.16
        p.drawRect(QRectF(cx + w * 0.05, body.bottom() - h * 0.34, dw * 0.5, h * 0.34))
        p.drawRect(QRectF(cx + w * 0.05 + dw * 0.5, body.bottom() - h * 0.34, dw * 0.5, h * 0.34))
    elif kind == "clear":
        # 禁止圈 ⊘
        d = min(w, h) * 0.90
        ring = QRectF(0, 0, d, d); ring.moveCenter(QPointF(cx, cy))
        p.setPen(_pen(_ICON_RED, max(1.8, w * 0.13))); p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(ring)
        a, rr = math.radians(45), d / 2
        p.drawLine(QPointF(cx - math.cos(a) * rr, cy + math.sin(a) * rr),
                   QPointF(cx + math.cos(a) * rr, cy - math.sin(a) * rr))


def _paint_squidcada_icon(p, r):
    """蝉乌贼：白色小虫 + 双侧薄翅 + 淡蓝背甲 + 亮眼。"""
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_SQUID_WING)
    for sgn in (-1, 1):
        p.drawPolygon(QPolygonF([QPointF(cx + sgn * w * 0.04, cy + h * 0.06),
                                 QPointF(cx + sgn * w * 0.50, cy - h * 0.34),
                                 QPointF(cx + sgn * w * 0.42, cy + h * 0.12)]))
    p.setBrush(_SQUID_BODY)
    body = QRectF(0, 0, w * 0.46, h * 0.64)
    body.moveCenter(QPointF(cx, cy))
    p.drawEllipse(body)
    p.setBrush(_SQUID_SHELL)
    shell = QRectF(0, 0, w * 0.36, h * 0.28)
    shell.moveCenter(QPointF(cx, cy - h * 0.18))
    p.drawEllipse(shell)
    p.setBrush(_BAT_EYE)
    p.drawEllipse(QPointF(cx + w * 0.03, cy + h * 0.02), w * 0.065, w * 0.065)


def _paint_needleworm_icon(p, r):
    """面条蝇：横向分节虫身 + 双翅 + 亮眼（与程序化绘制一致）。"""
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_SQUID_WING)
    for sgn in (-1, 1):
        p.drawPolygon(QPolygonF([QPointF(cx + sgn * w * 0.02, cy - h * 0.02),
                                 QPointF(cx + sgn * w * 0.44, cy - h * 0.40),
                                 QPointF(cx + sgn * w * 0.30, cy + h * 0.06)]))
    p.setBrush(_NWORM_BODY)
    body = QRectF(0, 0, w * 0.78, h * 0.30)
    body.moveCenter(QPointF(cx, cy + h * 0.04))
    p.drawRoundedRect(body, h * 0.15, h * 0.15)
    p.setBrush(_NWORM_HI)
    for i in range(4):
        dx = (i - 1.5) * w * 0.14
        dot = QRectF(0, 0, w * 0.07, h * 0.16)
        dot.moveCenter(QPointF(cx + dx, cy + h * 0.04))
        p.drawEllipse(dot)
    p.setBrush(_BAT_EYE)
    p.drawEllipse(QPointF(cx + w * 0.26, cy + h * 0.02), w * 0.055, w * 0.055)


def _paint_pearl_icon(p, r):
    """珍珠：带渐变与高光的圆珠。"""
    cx, cy = r.center().x(), r.center().y()
    d = min(r.width(), r.height()) * 0.80
    ball = QRectF(0, 0, d, d)
    ball.moveCenter(QPointF(cx, cy))
    grad = QLinearGradient(ball.topLeft(), ball.bottomRight())
    grad.setColorAt(0.0, _PEARL_SHINE)
    grad.setColorAt(0.45, _PEARL_BALL)
    grad.setColorAt(1.0, _PEARL_EDGE)
    p.setPen(_pen(_PEARL_EDGE, max(1.1, d * 0.09)))
    p.setBrush(grad)
    p.drawEllipse(ball)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_PEARL_SHINE)
    p.drawEllipse(QPointF(cx - d * 0.20, cy - d * 0.24), d * 0.15, d * 0.15)


def _paint_spear_icon(p, r):
    """矛：斜置木杆 + 金属尖 + 尾部配重。"""
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    dx, dy = w * 0.40, h * 0.40
    tx, ty = cx + dx, cy - dy
    p.setPen(_pen(_SPEAR_SHAFT, max(2.0, w * 0.14)))
    p.drawLine(QPointF(cx - dx, cy + dy), QPointF(tx, ty))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_SPEAR_TIP)
    p.drawPolygon(QPolygonF([QPointF(tx + w * 0.14, ty - h * 0.14),
                             QPointF(tx + w * 0.20, ty + h * 0.04),
                             QPointF(tx - w * 0.06, ty + h * 0.06)]))
    p.setBrush(_SPEAR_SHAFT)
    p.drawEllipse(QPointF(cx - dx, cy + dy), w * 0.05, w * 0.05)


def _paint_scavenger_icon(p, r):
    """拾荒者：两足长臂剪影 + 白色面具头。"""
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    p.setPen(_pen(_SCAV_BODY, max(2.0, w * 0.14), cap=False))
    p.drawLine(QPointF(cx - w * 0.06, cy + h * 0.10), QPointF(cx - w * 0.24, cy + h * 0.44))
    p.drawLine(QPointF(cx + w * 0.06, cy + h * 0.10), QPointF(cx + w * 0.24, cy + h * 0.44))
    p.drawLine(QPointF(cx, cy - h * 0.04), QPointF(cx - w * 0.32, cy + h * 0.24))
    p.drawLine(QPointF(cx, cy - h * 0.04), QPointF(cx + w * 0.32, cy + h * 0.24))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_SCAV_BODY)
    torso = QRectF(0, 0, w * 0.36, h * 0.48)
    torso.moveCenter(QPointF(cx, cy + h * 0.04))
    p.drawEllipse(torso)
    p.setBrush(_SCAV_MASK)
    head = QRectF(0, 0, w * 0.38, h * 0.34)
    head.moveCenter(QPointF(cx, cy - h * 0.26))
    p.drawEllipse(head)
    p.setBrush(_SCAV_EYE)
    p.drawEllipse(QPointF(cx - w * 0.06, cy - h * 0.26), w * 0.04, w * 0.04)
    p.drawEllipse(QPointF(cx + w * 0.06, cy - h * 0.26), w * 0.04, w * 0.04)

def _paint_karmaflower_icon(p, r):
    """业力花：四片金色花瓣 + 花心亮点（对应原版 KarmaPetal / EndGameCircle）。"""
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(4):
        a = -90.0 + i * 90.0
        px = cx + math.sin(math.radians(a)) * w * 0.20
        py = cy - math.cos(math.radians(a)) * h * 0.20
        p.save()
        p.translate(px, py)
        p.rotate(a)
        p.setBrush(_ICON_GOLD)
        petal = QRectF(-w * 0.10, -h * 0.20, w * 0.20, h * 0.36)
        p.drawEllipse(petal)
        p.restore()
    p.setBrush(_ICON_AMBER)
    p.drawEllipse(QPointF(cx, cy), w * 0.11, h * 0.11)


def _paint_seedcob_icon(p, r):
    """爆米花：从顶垂下的暗色细茎 + 黄色豆荚 + 顶端两片叶。"""
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    top = cy - h * 0.48
    pod_top = cy - h * 0.10
    pod_bot = cy + h * 0.46
    p.setPen(_pen(_POLE_CORE, max(1.4, w * 0.09), cap=False))
    p.setBrush(Qt.BrushStyle.NoBrush)
    p.drawLine(QPointF(cx - w * 0.10, top), QPointF(cx, pod_top))
    p.drawLine(QPointF(cx + w * 0.10, top), QPointF(cx, pod_top))
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_ICON_AMBER)
    pod = QRectF(0, 0, w * 0.30, pod_bot - pod_top)
    pod.moveCenter(QPointF(cx, (pod_top + pod_bot) * 0.5))
    p.drawEllipse(pod)
    p.setBrush(_SC_LEAF)
    for sgn in (-1, 1):
        p.drawPolygon(QPolygonF([QPointF(cx, pod_top + h * 0.06),
                                 QPointF(cx + sgn * w * 0.40, pod_top - h * 0.04),
                                 QPointF(cx + sgn * w * 0.14, pod_top + h * 0.20)]))
    p.setBrush(_SC_SEED)
    for k in range(3):
        p.drawEllipse(QPointF(cx, pod_top + (pod_bot - pod_top) * (0.24 + 0.26 * k)),
                      w * 0.055, w * 0.055)


def _paint_lizard_icon(p, r):
    """蜥蜴剪影：长身+尾+四条短腿+带眼头。"""
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    body = QPainterPath()
    body.moveTo(cx - w * 0.46, cy + h * 0.02)                 # 尾尖
    body.cubicTo(cx - w * 0.28, cy - h * 0.16,
                 cx - w * 0.12, cy - h * 0.20,
                 cx + w * 0.12, cy - h * 0.20)                 # 背
    body.cubicTo(cx + w * 0.30, cy - h * 0.20,
                 cx + w * 0.36, cy - h * 0.08,
                 cx + w * 0.40, cy - h * 0.02)                 # 吻
    body.cubicTo(cx + w * 0.30, cy + h * 0.06,
                 cx + w * 0.08, cy + h * 0.12,
                 cx - w * 0.30, cy + h * 0.14)                 # 腹
    body.cubicTo(cx - w * 0.38, cy + h * 0.12,
                 cx - w * 0.44, cy + h * 0.08,
                 cx - w * 0.46, cy + h * 0.02)
    body.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_LIZ_BODY)
    p.drawPath(body)
    # 四条短腿
    p.setPen(_pen(_LIZ_BODY, max(1.2, w * 0.09), cap=True))
    for dx, dy in ((-0.16, 1.0), (0.02, 1.0), (0.16, 1.0), (0.30, 1.0)):
        x = cx + w * dx
        y = cy + h * (0.10 if dx < 0.1 else 0.06)
        p.drawLine(QPointF(x, y), QPointF(x - w * 0.03, y + h * 0.16 * dy))
    # 眼
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(_LIZ_EYE)
    p.drawEllipse(QPointF(cx + w * 0.31, cy - h * 0.09), w * 0.045, w * 0.045)


def _paint_lamp_sprite(p, r, atlas):
    """灯笼 sprite 缩小+暖光圈。"""
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    glow_r = min(w, h) * 0.52
    grad = QRadialGradient(QPointF(cx, cy), glow_r)
    grad.setColorAt(0.0, QColor(255, 150, 70, 165))
    grad.setColorAt(0.45, QColor(255, 100, 35, 80))
    grad.setColorAt(1.0, QColor(255, 70, 0, 0))
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(grad)
    p.drawEllipse(QPointF(cx, cy), glow_r, glow_r)
    sw, sh = atlas.source_size("base", "DangleFruit0A")
    s = min(w / sw, h / sh) * 0.58                                 # 留出光圈
    dw, dh = sw * s, sh * s
    dst = QRectF(cx - dw / 2, cy - dh / 2, dw, dh)
    outline = atlas.sprite("base", "DangleFruit0A", _LAMP_OUTLINE)
    flesh = atlas.sprite("base", "DangleFruit0B", _LAMP_FLESH)
    p.save()                                                      # 镜像：粗头朝上
    p.translate(cx, cy); p.scale(1.0, -1.0)
    local = QRectF(-dw / 2, -dh / 2, dw, dh)
    p.drawPixmap(local, outline, QRectF(outline.rect()))
    p.drawPixmap(local, flesh, QRectF(flesh.rect()))
    p.restore()


def _paint_fruit_sprite(p, r, atlas):
    """果子 sprite 缩小绘入 r，果肉套蓝渐变。"""
    sw, sh = atlas.source_size("base", "DangleFruit0A")
    s = min(r.width() / sw, r.height() / sh) * 0.8
    dw, dh = sw * s, sh * s
    dst = QRectF(r.center().x() - dw / 2, r.center().y() - dh / 2, dw, dh)
    outline = atlas.sprite("base", "DangleFruit0A", _FRUIT_OUTLINE)
    flesh = atlas.sprite("base", "DangleFruit0B")                  # 白模，下面渐变上色
    ss = 4                                                          # 超采样防锯齿
    lw, lh = max(1, int(dw * ss)), max(1, int(dh * ss))
    layer = QPixmap(lw, lh); layer.fill(Qt.GlobalColor.transparent)
    lp = QPainter(layer)
    lp.drawPixmap(QRectF(0, 0, lw, lh), flesh, QRectF(flesh.rect()))
    lp.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
    g = QLinearGradient(QPointF(0, 0), QPointF(0, lh))
    g.setColorAt(0.0, _FRUIT_TOP); g.setColorAt(1.0, _FRUIT_BOT)
    lp.fillRect(layer.rect(), g); lp.end()
    p.drawPixmap(dst, outline, QRectF(outline.rect()))
    p.drawPixmap(dst, layer, QRectF(layer.rect()))


def _paint_slimemold_icon(p, r, atlas=None):
    """黏菌 sprite 染橙；缺图集回退矢量。"""
    if atlas is not None and atlas.get("ui").has("Symbol_SlimeMold"):
        sw, sh = atlas.source_size("ui", "Symbol_SlimeMold")
        s = min(r.width() / sw, r.height() / sh) * 0.92
        dw, dh = sw * s, sh * s
        pm = atlas.sprite("ui", "Symbol_SlimeMold", _SLIME_BODY)
        p.drawPixmap(QRectF(r.center().x() - dw / 2, r.center().y() - dh / 2, dw, dh),
                     pm, QRectF(pm.rect()))
        return
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    bx, by = cx, cy - h * 0.14
    glow_r = min(w, h) * 0.42
    grad = QRadialGradient(QPointF(bx, by), glow_r)
    grad.setColorAt(0.0, _SLIME_GLOW)
    grad.setColorAt(1.0, QColor(255, 150, 50, 0))
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(grad)
    p.drawEllipse(QPointF(bx, by), glow_r, glow_r)
    p.setPen(_pen(_SLIME_TENDRIL, max(1.6, w * 0.09)))
    for dx in (-0.22, -0.05, 0.12, 0.28):
        sx = bx + dx * w
        p.drawLine(QPointF(sx, by + h * 0.06),
                   QPointF(sx + dx * w * 0.25, by + h * 0.42))
    d = min(w, h) * 0.34
    bulb = QRectF(0, 0, d, d); bulb.moveCenter(QPointF(bx, by))
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(_SLIME_BODY)
    p.drawEllipse(bulb)


def _paint_fruit_fallback(p, r):
    """无图集时的矢量水滴果回退。"""
    cx, cy = r.center().x(), r.center().y()
    w, h = r.width(), r.height()
    path = QPainterPath()
    path.moveTo(QPointF(cx, r.top()))
    path.cubicTo(QPointF(cx + w * 0.50, cy - h * 0.10),
                 QPointF(cx + w * 0.42, r.bottom()), QPointF(cx, r.bottom()))
    path.cubicTo(QPointF(cx - w * 0.42, r.bottom()),
                 QPointF(cx - w * 0.50, cy - h * 0.10), QPointF(cx, r.top()))
    g = QLinearGradient(QPointF(0, r.top()), QPointF(0, r.bottom()))
    g.setColorAt(0.0, _FRUIT_TOP); g.setColorAt(1.0, _FRUIT_BOT)
    p.setPen(Qt.PenStyle.NoPen); p.setBrush(g); p.drawPath(path)


def _make_place_icon(kind, size, dpr, atlas=None):
    """渲染图标为 QPixmap（离屏，避免按钮重复开 painter）。"""
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(dpr)
    r = QRectF(0, 0, size, size)
    r.adjust(size * 0.10, size * 0.10, -size * 0.10, -size * 0.10)
    p = QPainter(pm)
    _paint_place_icon(p, kind, r, atlas)
    p.end()
    return pm


class TabBar(QWidget):
    def __init__(self, pet, app, params=None):
        super().__init__()
        self.pet = pet
        self.app = app
        self.params = params or {}
        self.expanded = False
        self._drag = None

        self.setWindowFlags(Qt.WindowType.FramelessWindowHint
                            | Qt.WindowType.WindowStaysOnTopHint
                            | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

        screen = QGuiApplication.primaryScreen().availableGeometry()
        self._screen = screen
        self._edge_x = screen.x() + screen.width() - COLLAPSED_W
        self._y = self.params.get("tab_y", screen.y() + (screen.height() - EXPANDED_H) // 2)

        self._build()
        self._apply_collapsed()

    def _build(self):
        self._panel = QWidget(self)
        lay = QVBoxLayout(self._panel)
        lay.setContentsMargins(6, 6, 6, 6)
        lay.setSpacing(4)
        self._panel_lay = lay     # 供 _expanded_h 读内容高度

        # 图标盘：3 列网格
        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        dpr = QGuiApplication.primaryScreen().devicePixelRatio()
        atlas = getattr(self.pet, "atlas", None)
        place_items = [("pole", t("tip_pole"), self._place_pole),
                       ("fruit", t("tip_fruit"), self._place_fruit),
                       ("stone", t("tip_stone"), self._place_stone),
                       ("lamp", t("tip_lamp"), self._place_lamp),
                       ("slimemold", t("tip_slimemold"), self._place_slimemold),
                       ("batfly", t("tip_batfly"), self._place_batfly),
                       ("lizard", t("tip_lizard"), self._place_lizard),
                       ("squidcada", t("tip_squidcada"), self._place_squidcada),
                       ("needleworm", t("tip_needleworm"), self._place_needleworm),
                       ("pearl", t("tip_pearl"), self._place_pearl),
                       ("spear", t("tip_spear"), self._place_spear),
                       ("slugpup", t("tip_slugpup"), self._place_slugpup),
                       ("seedcob", t("tip_seedcob"), self._place_seedcob),
                       ("karmaflower", t("tip_karmaflower"), self._place_karmaflower),
                       ("shelter", t("tip_shelter"), self._place_shelter),
                       ("erase", t("tip_erase"), self._erase_mode),
                       ("clear", t("tip_clear"), self._clear_all)]
        for i, (kind, tip, cb) in enumerate(place_items):
            ib = QPushButton()
            ib.setIcon(QIcon(_make_place_icon(kind, 22, dpr, atlas)))
            ib.setIconSize(QSize(22, 22))
            ib.setFixedHeight(32)
            install_tip(ib, tip)
            ib.setCursor(Qt.CursorShape.PointingHandCursor)
            ib.clicked.connect(cb)
            grid.addWidget(ib, i // 3, i % 3)
        grid_host = QWidget()
        grid_host.setLayout(grid)
        lay.addWidget(grid_host)
        lay.addWidget(self._divider())

        def btn(text, enabled, cb, tip=None):
            b = QPushButton(text)
            b.setEnabled(enabled)
            if tip:
                install_tip(b, tip)
            if cb:
                b.clicked.connect(cb)
            b.setFixedHeight(28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            lay.addWidget(b)
            return b

        btn(t("btn_open_settings"), True, self._open_settings)
        btn(t("btn_reset_window"), True, self._reset_window,
            t("tip_reset_window"))
        btn(t("btn_quit_app"), True, self._quit)
        self._panel.setStyleSheet(
            "QWidget{background:rgba(30,34,40,235);border-radius:8px;}"
            "QPushButton{color:#e8f5d8;background:rgba(60,70,55,255);border:1px solid #4a5a3a;"
            "border-radius:5px;font-size:12px;}"
            "QPushButton:enabled:hover{background:rgba(80,100,70,255);}"
            "QPushButton:disabled{color:#777;background:rgba(45,48,52,255);}")

        # eventFilter 区分拖动/点击
        self._arrow = QPushButton("‹", self)
        self._arrow.setCursor(Qt.CursorShape.PointingHandCursor)
        self._arrow.installEventFilter(self)
        self._arrow_press = None
        self._arrow_moved = False
        self._arrow.setStyleSheet(
            "QPushButton{color:#cfe8b8;background:rgba(40,46,40,180);"
            "border:none;border-top-left-radius:8px;border-bottom-left-radius:8px;font-size:18px;}"
            "QPushButton:hover{background:rgba(60,72,55,255);}")

        # toast 需顶层窗口，防裁切
        self._toast_lbl = QLabel("", None)
        self._toast_lbl.setWindowFlags(Qt.WindowType.FramelessWindowHint
                                       | Qt.WindowType.WindowStaysOnTopHint
                                       | Qt.WindowType.ToolTip)
        self._toast_lbl.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self._toast_lbl.setStyleSheet(
            "QLabel{color:#fff;background:rgba(20,22,26,235);border-radius:6px;padding:5px 9px;font-size:12px;}")
        self._toast_lbl.hide()
        self._toast_timer = QTimer(self)
        self._toast_timer.setSingleShot(True)
        self._toast_timer.timeout.connect(self._toast_lbl.hide)

    def _apply_collapsed(self):
        self.expanded = False
        h = COLLAPSED_H
        self.setGeometry(self._edge_x, self._y, COLLAPSED_W, h)
        self._arrow.setGeometry(0, 0, COLLAPSED_W, h)
        self._arrow.setText("‹")
        self._arrow.show()
        self._panel.hide()
        eff = QGraphicsOpacityEffect(self._arrow)
        eff.setOpacity(0.45)
        self._arrow.setGraphicsEffect(eff)

    @staticmethod
    def _divider():
        f = QFrame()
        f.setFixedHeight(1)
        f.setStyleSheet("background:rgba(120,150,100,90);border:none;")
        return f

    def _expanded_h(self):
        # 高度随内容自适应
        return self._panel_lay.sizeHint().height()

    def _apply_expanded(self):
        self.expanded = True
        h = self._expanded_h()
        x = self._screen.x() + self._screen.width() - EXPANDED_W
        self.setGeometry(x, self._y, EXPANDED_W, h)
        self._panel.setGeometry(0, 0, EXPANDED_W, h)
        self._panel.show()
        self._arrow.setGeometry(0, 0, 16, h)   # 展开态收起条
        self._arrow.setText("›")
        self._arrow.setGraphicsEffect(None)
        self._arrow.raise_()

    def toggle(self):
        if self.expanded:
            self._animate_to(self._edge_x, COLLAPSED_W, COLLAPSED_H, self._apply_collapsed)
        else:
            self._apply_expanded()

    def _animate_to(self, x, w, h, done):
        anim = QPropertyAnimation(self, b"geometry", self)
        anim.setDuration(SLIDE_MS)
        anim.setStartValue(self.geometry())
        anim.setEndValue(QRect(x, self._y, w, h))
        anim.finished.connect(done)
        anim.start()
        self._anim = anim

    def eventFilter(self, obj, ev):
        if obj is self._arrow:
            try:
                t = ev.type()
            except AttributeError:
                return False                   # 关停期丢 type，放行
            if t == QEvent.Type.MouseButtonPress and ev.button() == Qt.MouseButton.LeftButton:
                self._arrow_press = ev.globalPosition().y() - self.y()
                self._arrow_moved = False
                return False
            if t == QEvent.Type.MouseMove and self._arrow_press is not None and not self.expanded:
                ny = int(ev.globalPosition().y() - self._arrow_press)
                ny = max(self._screen.y(),
                         min(self._screen.y() + self._screen.height() - self.height(), ny))
                if abs(ny - self._y) > 2:
                    self._arrow_moved = True
                self._y = ny
                self.move(self._edge_x, ny)
                return False
            if t == QEvent.Type.MouseButtonRelease and ev.button() == Qt.MouseButton.LeftButton \
                    and self._arrow_press is not None:
                moved = self._arrow_moved
                self._arrow_press = None
                self._arrow_moved = False
                if moved and not self.expanded:
                    self.params["tab_y"] = self._y
                else:
                    self.toggle()
                return True
        return super().eventFilter(obj, ev)

    def _toast(self, msg):
        self._toast_lbl.setText(msg)
        self._toast_lbl.adjustSize()
        # 全局坐标定位于 tab 左侧
        right = EXPANDED_W if self.expanded else COLLAPSED_W
        gx = self._screen.x() + self._screen.width() - self._toast_lbl.width() - right - 8
        gy = self._y + 10
        self._toast_lbl.move(gx, gy)
        self._toast_lbl.show()
        self._toast_lbl.raise_()
        self._toast_timer.start(1600)

    def _collapse(self):
        """收起 tab，让出屏幕。"""
        if self.expanded:
            self.toggle()

    def _place_fruit(self):
        self.pet.enter_place_fruit_mode()
        self._collapse()

    def _place_stone(self):
        self.pet.enter_place_stone_mode()
        self._collapse()

    def _place_lamp(self):
        # 单灯替换旧灯，清除走"清除物体"
        self.pet.enter_place_lamp_mode()
        self._collapse()

    def _place_slimemold(self):
        self.pet.enter_place_slimemold_mode()
        self._collapse()

    def _place_batfly(self):
        self.pet.enter_place_batfly_mode()
        self._collapse()

    def _place_lizard(self):
        self.pet.enter_place_lizard_mode()
        self._collapse()

    def _place_pole(self):
        self.pet.enter_place_pole_mode()
        self._collapse()

    def _place_squidcada(self):
        self.pet.enter_place_squidcada_mode()
        self._collapse()

    def _place_needleworm(self):
        self.pet.enter_place_needleworm_mode()
        self._collapse()

    def _place_pearl(self):
        self.pet.enter_place_pearl_mode()
        self._collapse()

    def _place_spear(self):
        self.pet.enter_place_spear_mode()
        self._collapse()

    def _place_scavenger(self):
        self.pet.enter_place_scavenger_mode()
        self._collapse()

    def _place_slugpup(self):
        self.pet.enter_place_slugpup_mode()

    def _place_seedcob(self):
        self.pet.enter_place_seedcob_mode()
        self._collapse()

    def _place_karmaflower(self):
        self.pet.enter_place_karmaflower_mode()
        self._collapse()

    def _place_shelter(self):
        self.pet.enter_place_shelter_mode()
        self._collapse()

    def _erase_mode(self):
        self.pet.enter_erase_mode()
        self._collapse()

    def _clear_all(self):
        if (self.pet.fruits or self.pet.stones or self.pet.slimemolds
                or self.pet.batflies or self.pet.lizards or self.pet.poles
                or self.pet.squidcadas or self.pet.pearls or self.pet.spears
                or self.pet.needleworms
                or self.pet.scavengers or self.pet.seedcobs or self.pet.seeds
                or self.pet.lamp is not None
                or self.pet.pup_count() > 0):          # 幼崽也算「可交互实体」
            self.pet.clear_all_items(clear_pups=True)
            # 清完重新枚举窗口地形：用户实测「清了重画就好」的那份过期
            # 平台 / 背景就在这里一起重置掉。
            self.pet.reset_window_geometry()
        else:
            self._toast(t("toast_no_object"))

    def _reset_window(self):
        """窗口重置：重新枚举桌面窗口（顶边 + 背景）并丢掉导航缓存。"""
        try:
            self.pet.reset_window_geometry()
        except Exception:
            pass
        self._toast(t("toast_window_reset"))

    def _open_settings(self):
        # 转发给 window 打开设置窗
        self.pet.open_settings()

    def _quit(self):
        # 释放劫持后再 quit
        try:
            from ..platform.cursorfx import abort_all
            abort_all()
        except Exception:
            pass
        self.app.quit()

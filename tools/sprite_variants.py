# -*- coding: utf-8 -*-
"""多角度/多变体精灵切换审计：原版生物按角度/情况换贴图行，我们是否跟着换。

原版里「同一个部件换贴图」分两类：
  1. 按角度分行：蜥蜴头 5 片（LizardJaw/LowerTeeth/UpperTeeth/Head/Eyes 各 0..3 行）、
     禅乌贼（Cicada{0..8}{body,head,shield,eyes1,eyes2}）、蛞蝓猫头（HeadA/B/C 0..17）、
     蛞蝓猫脸（FaceA..D 0..8）。
  2. 按距离/侧别取档：蜥蜴腿 LizardArm_01..54、蛞蝓猫手 PlayerArm0..12、
     蛞蝓猫腿 LegsA / LegsACrawling / LegsAAir / LegsAOnPole / LegsAPole /
     LegsAVerticalPole / LegsAWall、面条蝇翅与獠牙按 z 轴侧别。
这两种都必须在本桌宠里真的发生过，否则就是「贴图停在某一帧」。

做法：拦截图集查找（AtlasSet.find_atlas 静默跳过缺帧；Atlas.sprite 直取会 KeyError），
把所有生物放进场景跑一段（并强制扫描蜥蜴头深度 -1..+1、禅乌贼 z 轴 -180..180），
统计：① 请求了但图集没有的帧（= 画面缺件）② 各族实际用到的变体号。

用法：
    python tools/sprite_variants.py            # 有 Qt + 本机图集即可
    python tools/sprite_variants.py --brief    # 只打印结论
"""
from __future__ import annotations
import collections
import math
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtWidgets import QApplication                      # noqa: E402
from PySide6.QtGui import QImage, QPainter, QColor              # noqa: E402

import slugcatpet.rendering.atlas as atlasmod                   # noqa: E402

BRIEF = "--brief" in sys.argv
TICKS = 900

MISS: collections.Counter[str] = collections.Counter()
HIT: collections.Counter[str] = collections.Counter()


def instrument() -> None:
    orig_find = atlasmod.AtlasSet.find_atlas

    def find_atlas(self, frame):
        key = orig_find(self, frame)
        (HIT if key is not None else MISS)[frame] += 1
        return key

    orig_sprite = atlasmod.Atlas.sprite

    def sprite(self, frame_name, *a, **k):
        if not self.has(frame_name):
            MISS["<Atlas.sprite> " + frame_name] += 1
        HIT[frame_name] += 1
        return orig_sprite(self, frame_name, *a, **k)

    atlasmod.AtlasSet.find_atlas = find_atlas
    atlasmod.Atlas.sprite = sprite


# 各族的期望变体（来自反编译的选择式，见 docs/PARTS_AUDIT.md 第四节）
FAMILIES = [
    ("蜥蜴头 4 行", r"Lizard(Head|Jaw|UpperTeeth|LowerTeeth|Eyes)\d\."),
    ("蜥蜴腿 01..54", r"LizardArm_(0[1-9]|[1-4]\d|5[0-4])$"),
    ("禅乌贼 9 行", r"Cicada[0-8](body|head|shield|eyes1|eyes2)$"),
    ("蛞蝓猫头 HeadA/B/C", r"Head[ABC]\d+$"),
    ("蛞蝓猫脸 Face*", r"Face[ABCD]\d$"),
    ("蛞蝓猫腿 LegsA*", r"LegsA[A-Za-z]*\d*$"),
    ("蛞蝓猫手 PlayerArm0..12", r"PlayerArm\d+$"),
    ("蝙蝠 4 片", r"Fly(Body|Wing|Eyes)$"),
    ("拾荒者手 A/B", r"ScavengerHand[AB]$"),
]


def main() -> int:
    app = QApplication(sys.argv)                                # noqa: F841
    instrument()
    from slugcatpet.window import PetWindow, spawnable_kinds

    variants = ("survivor", "monk", "hunter", "rivulet", "saint", "artificer")
    win = PetWindow(params={"pets": [{"variant": v} for v in variants]}, debug=True)
    win.resize(760, 520)
    win.show()
    img = QImage(int(win._WL), int(win._HL), QImage.Format.Format_ARGB32_Premultiplied)

    def paint() -> None:
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        try:
            win._paint_world(p, 1.0)
        finally:
            p.end()

    kinds = [k for k in sorted(spawnable_kinds()) if k != "erase"]
    for i, kind in enumerate(kinds):
        fn = getattr(win, "place_" + kind, None)
        if fn is not None:
            fn(win._WL * (0.12 + 0.76 * ((i * 0.37) % 1.0)),
               win._HL - 30.0 - 22.0 * ((i * 0.53) % 1.0))
    win._place_mode = False
    paint()

    for t in range(TICKS):
        ph = (t % 160) / 160.0
        depth = -1.0 + 2.0 * (ph * 2.0 if ph < 0.5 else 2.0 - ph * 2.0)
        for lz in win.lizards:
            lz.last_head_depth = getattr(lz, "head_depth", depth)
            lz.head_depth = depth
            lz.last_depth = getattr(lz, "depth", depth)
            lz.depth = depth
        r = math.radians((t % 120) / 120.0 * 360.0 - 180.0)
        for sc in win.squidcadas:
            sc.lzx = sc.zx = math.sin(r)
            sc.lzy = sc.zy = -math.cos(r)
        win._do_tick()
        if t % 3 == 0:
            paint()

    used = HIT
    print("请求过的帧：%d 个" % (len(used) + len(MISS)))
    print("缺帧（图集里没有 → 画面缺件）：%d 个" % len(MISS))
    for name, n in MISS.most_common(40):
        print("   MISS %-34s x%d" % (name, n))
    print()
    import re
    for label, pat in FAMILIES:
        got = sorted(n for n in used if re.search(pat, n))
        if not BRIEF or not got:
            print("%-24s %3d 种 %s" % (label, len(got), "" if BRIEF else got[:40]))
    return 1 if MISS else 0


if __name__ == "__main__":
    raise SystemExit(main())

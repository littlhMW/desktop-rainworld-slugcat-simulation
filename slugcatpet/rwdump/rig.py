# -*- coding: utf-8 -*-
"""Rig / 动画 / 图层 / 逻辑层。

把两部分合成数据：

* 游戏自身的骨架 —— 从反编译源码里抽出身体节、尾巴段长、三角网格表、层序与精灵下标；
* 本作已跑通的绘制规则 —— `graphics_draw.py` 的精灵级顺序与各部件依赖，
  反向整理成同一份 schema，方便两边对拍。

产物：

* `layers.json`       FContainer 层序（RoomCamera.SpriteLayerIndex）+ 本作精灵级绘制顺序
* `rigs/<Name>.json`  逻辑骨架：身体节 / 头 / 腿 / 手 / 尾（含分段长度与网格表）
* `animations/*.json` 从图集帧名反推的帧族（LegsA0..7、FaceA0..8…），带 ticks/loop/条件
* `creatures/*.json`  每只生物「怎么画」：下标 = 图层序、容器、元件、变换、依赖
* `logic/*.json`      每个方法的写入语句（哪些精灵的哪些属性被哪段逻辑写）
"""
from __future__ import annotations

import re
from pathlib import Path

from . import code as C

# ── 本作精灵级绘制顺序（graphics_draw.draw_sprites 的真实顺序） ──────────

SLUGCAT_DRAW_ORDER = [
    {"part": "body", "elements": ["BodyA"], "depends_on": ["bodyChunks[0]", "bodyChunks[1]"],
     "condition": "始终；rotation = 体轴，scaleX 吃呼吸/力竭，scaleY 竖直呼吸走 y"},
    {"part": "hips", "elements": ["HipsA"], "depends_on": ["bodyChunks[1]", "tail[0]"],
     "condition": "始终；rotation = 胸→tail[0] 方向；sleep 时下沉 3px"},
    {"part": "tail", "elements": ["<tail mesh>"], "depends_on": ["tail[0]", "tail[1]", "tail[2]", "tail[3]"],
     "condition": "始终；根 = 75% 臀 + 25% 胸；尖段收成单点"},
    {"part": "tail_speckles", "elements": ["TailSpeck", "TailNeedle"], "depends_on": ["tail[0]", "tail[1]", "tail[2]", "tail[3]"],
     "condition": "仅矛大师；尾之上、头之下"},
    {"part": "head", "elements": ["HeadA0..8", "HeadB0..8"], "depends_on": ["head", "bodyChunks[0]"],
     "condition": "始终；帧号单一真值源见 animations/head.json"},
    {"part": "legs", "elements": ["LegsA*"], "depends_on": ["legs", "bodyChunks[1]"],
     "condition": "bodyMode=Swimming(deep) 不画；其余按 bodyMode 选帧族"},
    {"part": "arms", "elements": ["PlayerArm*", "OnTopOfTerrainHand"], "depends_on": ["hands[0]", "hands[1]"],
     "condition": "始终；左手 scaleX=-1"},
    {"part": "gills", "elements": ["Gills*"], "depends_on": ["head"],
     "condition": "仅溪流"},
    {"part": "face", "elements": ["FaceA0..8", "FaceB*", "FaceC*", "FaceD*"], "depends_on": ["head"],
     "condition": "表情族 + 眨眼族 + 晕眩/死亡脸；sleep_curl>0 时闭眼优先"},
    {"part": "tongue", "elements": ["<rope>"], "depends_on": ["head"],
     "condition": "仅圣徒；绳索物理"},
    {"part": "glow", "elements": [], "depends_on": [],
     "condition": "仅守望者（首遇陀螺后发光）"},
]

# ── 帧族语义（图集帧名反推 + 触发条件） ──────────────────────────────

FAMILY_ROLES = {
    "HeadA": ("head", 1, False, "非 Saint 头族"),
    "HeadB": ("head", 1, False,
              "sleep>0 → lerp(7,4,sleep)；dead/stun → 0；Crawl → 7；"
              "Stand&&moving → 6；ZeroG → 0；否则 round(|headAngle|/360*34)"),
    "FaceA": ("face", 1, True, "普通脸（角度帧）"),
    "FaceB": ("face", 1, False, "眨眼脸"),
    "FaceC": ("face", 1, True, "睁大眼 / 特殊表情"),
    "FaceD": ("face", 1, True, "说话 / 咀嚼"),
    "FaceStunned": ("face_stunned", 1, False, "晕眩脸（复活按压借用的表情）"),
    "FaceDead": ("face_dead", 1, False, "死亡脸"),
    "LegsA": ("legs_walk", 1, True, "站立走：af % n"),
    "LegsACrawling": ("legs_crawl", 2, True, "匍匐：af//2 % n"),
    "LegsAAir": ("legs_air", 1, False, "空中腿"),
    "LegsAPole": ("legs_pole", 1, False, "杆尖挂腿"),
    "LegsAOnPole": ("legs_on_pole", 1, True, "站横杆：af<7 取帧，否则 0"),
    "LegsAVerticalPole": ("legs_vpole", 1, False, "爬竖杆腿"),
    "BodyA": ("body", 1, False, "单帧身体"),
    "HipsA": ("hips", 1, False, "单帧臀"),
    "PlayerArm": ("arm", 1, True, "手臂族（0..12）"),
    "OnTopOfTerrainHand": ("hand_grip", 1, False, "抓地手"),
    "Gills": ("gills", 1, True, "溪流鳃"),
    "TailSpeck": ("tail_speck", 1, True, "矛大师尾斑"),
    "TailNeedle": ("tail_needle", 1, True, "矛大师尾针"),
}

# ── 小工具 ────────────────────────────────────────────────────────

def _dotf(s):
    try:
        return float((s or "").rstrip("fF"))
    except Exception:
        return None


def paren_group(masked: str, i: int):
    """i 指向 '(' 时返回 (内容起, 内容止)。"""
    if i >= len(masked) or masked[i] != "(":
        return None
    depth = 0
    for j in range(i, len(masked)):
        if masked[j] == "(":
            depth += 1
        elif masked[j] == ")":
            depth -= 1
            if depth == 0:
                return (i + 1, j)
    return None


COND_RE = re.compile(r"\b(else\s+if|if|else)\b")


def conditional_blocks(src: str, masked: str) -> list:
    """全部 if / else if / else 块：{cond, start, end, kw}（start/end 为块体区间）。"""
    out = []
    for m in COND_RE.finditer(masked):
        kw = m.group(1)
        j = m.end()
        while j < len(masked) and masked[j] in " \t\r\n":
            j += 1
        cond = ""
        if kw != "else":
            if j < len(masked) and masked[j] == "(":
                g = paren_group(masked, j)
                if not g:
                    continue
                cond = re.sub(r"\s+", " ", src[g[0]:g[1]]).strip()
                j = g[1] + 1
                while j < len(masked) and masked[j] in " \t\r\n":
                    j += 1
        if j < len(masked) and masked[j] == "{":
            br = C.brace_body(masked, j)
            if br:
                out.append({"cond": cond or "else", "start": br[0], "end": br[1],
                            "kw": m.start()})
    return out


def _enclosing(blocks, pos):
    """包含 pos 的块，从外到内。"""
    return [b for b in blocks if b["start"] <= pos < b["end"]]


# ── 图层 ──────────────────────────────────────────────────────────

def extract_layers(decomp_root: Path, warnings: list) -> dict:
    """FContainer 层序（游戏）+ 精灵级绘制顺序（本作规则）。"""
    layers = []
    room = Path(decomp_root) / "RoomCamera.cs"
    if room.exists():
        src = room.read_text(encoding="utf-8", errors="replace")
        for m in C.LAYER_RE.finditer(src):
            layers.append({"name": m.group(1), "order": int(m.group(2))})
        layers.sort(key=lambda r: r["order"])
    else:
        warnings.append("找不到 RoomCamera.cs，层序留空")
    return {"container_layers": layers,
            "slugcat_draw_order": SLUGCAT_DRAW_ORDER,
            "note": "container_layers 是游戏的 FContainer 层序；"
                    "slugcat_draw_order 是同容器内的精灵绘制顺序（后画盖前画）。"}


# ── 蛞蝓猫骨架 ────────────────────────────────────────────────────

BODYCHUNK_RE = re.compile(
    r"bodyChunks\[(\d+)\]\s*=\s*new\s+BodyChunk\(this\s*,\s*(\d+)\s*,\s*"
    r"new\s+Vector2\(([^)]*)\)\s*,\s*([-\d.efa-zA-Z*/ ]+?)\s*,\s*([^;,)]+)")
TAILSEG_RE = re.compile(
    r"tail\[(\d+)\]\s*=\s*new\s+TailSegment\(this\s*,\s*([-\d.efa-zA-Z*/ ]+?)\s*,\s*"
    r"([-\d.efa-zA-Z*/ ]+?)\s*,\s*(null|tail\[\d+\])\s*,\s*([-\d.ef]+)\s*,\s*([-\d.ef]+)")
TRI_RE = re.compile(
    r"new\s+TriangleMesh\.Triangle\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")
SPRITE_MAP_RE = re.compile(
    r"(?:private|public)\s+int\s+(\w*Sprite\w*)\s*(?:\([^)]*\))?\s*(?:=>|\{)\s*"
    r"(?:return\s+)?([^;{}]+);")


def _sprite_index_map(decomp_root: Path) -> dict:
    """`BodySprite = 0;` 这类「部件 → 精灵下标」常量（含 => 表达式）。"""
    out = {}
    for name in ("PlayerGraphics.cs", "Player.cs"):
        p = Path(decomp_root) / name
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8", errors="replace")
        msk = C.mask(src)
        for m in re.finditer(r"\b(\w*Sprite\w*)\s*=\s*([^;]+);", msk):
            key, val = m.group(1), src[m.start(2):m.end(2)].strip()
            if "Sprite" in key and re.fullmatch(r"[-\d\s+*]+", val):
                out.setdefault(key, val)
        for m in SPRITE_MAP_RE.finditer(msk):
            out.setdefault(m.group(1), m.group(2).strip())
    return {k: v for k, v in sorted(out.items())}


def extract_player_rig(decomp_root: Path, classes: dict, warnings: list) -> dict:
    """蛞蝓猫骨架：身体节、尾段（按种族分支）、尾巴网格表、部件→精灵下标。"""
    decomp_root = Path(decomp_root)
    rig = {"class": "Player", "sprite_index": _sprite_index_map(decomp_root)}

    pl = decomp_root / "Player.cs"
    if pl.exists():
        src = pl.read_text(encoding="utf-8", errors="replace")
        chunks = []
        for m in BODYCHUNK_RE.finditer(C.mask(src)):
            chunks.append({
                "index": int(m.group(1)),
                "declared_index": int(m.group(2)),
                "offset": re.sub(r"\s+", " ", src[m.start(3):m.end(3)]).strip(),
                "radius": _dotf(src[m.start(4):m.end(4)].strip()),
                "mass": re.sub(r"\s+", " ", src[m.start(5):m.end(5)]).strip(),
            })
        if chunks:
            rig["body_chunks"] = chunks
        else:
            warnings.append("Player.cs 里没抽到 bodyChunks（写法变了？）")

    pg = decomp_root / "PlayerGraphics.cs"
    if pg.exists():
        src = pg.read_text(encoding="utf-8", errors="replace")
        msk = C.mask(src)
        blocks = conditional_blocks(src, msk)
        segs = {}
        for m in TAILSEG_RE.finditer(msk):
            idx = int(m.group(1))
            pos = m.start()
            chain = [b["cond"] for b in _enclosing(blocks, pos)]
            chain = [c for c in chain if ("SlugCatClass" in c or "isPup" in c
                                          or "MSC" in c or "Watcher" in c)][:3]
            key = " / ".join(chain) or "(默认)"
            segs.setdefault(key, []).append({
                "index": idx,
                "radius": _dotf(src[m.start(2):m.end(2)].strip()),
                "length": _dotf(src[m.start(3):m.end(3)].strip()),
                "parent": m.group(4),
                "friction": _dotf(m.group(5)),
                "air_friction": _dotf(m.group(6)),
            })
        rig["tail_branches"] = [{"condition": k, "segments": sorted(v, key=lambda s: s["index"])}
                                for k, v in sorted(segs.items())]
        tris = [[int(m.group(1)), int(m.group(2)), int(m.group(3))]
                for m in TRI_RE.finditer(msk)]
        if tris:
            rig["tail_mesh_triangles"] = tris
        # 头/腿/手 的 BodyPart 定义
        parts = {}
        for m in re.finditer(r"new\s+GenericBodyPart\(this\s*,\s*([-\d.ef]+)\s*,\s*"
                             r"([-\d.ef]+)\s*,\s*([-\d.ef]+)\s*,\s*([^)]+)\)", msk):
            parts.setdefault("GenericBodyPart", []).append({
                "mass": _dotf(m.group(1)), "radius": _dotf(m.group(2)),
                "surface_friction": _dotf(m.group(3)),
                "connected_to": src[m.start(4):m.end(4)].strip()})
        if parts:
            rig["body_parts"] = parts

    cls = classes.get("PlayerGraphics")
    if cls:
        rig["sprites"] = cls["sprites"]
        rig["total_sprites"] = cls["total_sprites"]
        rig["containers"] = cls.get("containers", [])
    else:
        warnings.append("PlayerGraphics 没进 classes（InitiateSprites 没解析出来）")
    return rig


# ── 精灵锚点（游戏在 InitiateSprites 里写死的那些） ──────────────────

def sprite_anchors(classes: dict) -> dict:
    """从 PlayerGraphics 的精灵图里读锚点：`sLeaser.sprites[0].anchorY = 0.7894737f`。

    口径同 assets.py：`qt_ay = 1 - unity_anchorY`（我们的 blit 从贴图顶边量）。
    本作 rendering/graphics_draw.py 的硬编码锚点应与这里逐条一致。
    """
    out = {}
    rec = (classes or {}).get("PlayerGraphics")
    if not rec:
        return out
    for sp in rec["sprites"]:
        el = sp.get("element")
        if not el:
            continue
        info = {}
        ay = sp["draw"].get("anchorY")
        ax = sp["draw"].get("anchorX")
        if ay:
            v = _first_float(ay)
            if v is not None:
                info["unity_anchor_y"] = v
                info["qt_ay"] = 1.0 - v
        if ax:
            v = _first_float(ax)
            if v is not None:
                info["ax"] = v
        if sp["draw"].get("scaleY"):
            info["scaleY"] = sp["draw"]["scaleY"]
        if info:
            info["sprite_index"] = sp["index"]
            info["source"] = "PlayerGraphics.InitiateSprites"
            out.setdefault(el, info)
    return out


def anchor_of(anchors: dict, frame: str) -> dict:
    """帧 → 锚点。同族共用：PlayerArm5 用 PlayerArm0 的锚点。"""
    if not anchors:
        return {}
    if frame in anchors:
        return anchors[frame]
    base = re.sub(r"\d+$", "", frame) + "0"
    return anchors.get(base) or {}


def _first_float(s):
    m = re.search(r"-?\d+(?:\.\d+)?", s or "")
    return float(m.group(0)) if m else None


# ── 帧族 ──────────────────────────────────────────────────────────

_NUM_TAIL_RE = re.compile(r"^(.*?)(\d+)$")


def frame_families(atlas_db: dict, min_frames: int = 2) -> list:
    """图集帧名 → 帧族（`LegsA0..7`）。口径与 rendering/graphics.py:_family_frames 一致。"""
    fams: dict = {}
    for atlas_name in sorted(atlas_db):
        for name in sorted(atlas_db[atlas_name]["frames"]):
            m = _NUM_TAIL_RE.match(name)
            prefix, num = (m.group(1), int(m.group(2))) if m else (name + "#", -1)
            fams.setdefault((atlas_name, prefix), []).append((num, name))
    out = []
    for (atlas_name, prefix), items in sorted(fams.items()):
        if len(items) < min_frames:
            continue
        items.sort()
        role, tpf, loop, cond = FAMILY_ROLES.get(prefix, ("sprite_sequence", 1, True, ""))
        first = atlas_db[atlas_name]["frames"][items[0][1]]
        out.append({
            "prefix": prefix, "atlas": atlas_name, "role": role,
            "frames": [n for _i, n in items], "count": len(items),
            "ticks_per_frame": tpf, "loop": loop, "condition": cond or None,
            "source_size": first["source_size"], "rotated": first["rotated"],
            "trimmed": first["trimmed"], "pivot": first["pivot"],
        })
    return out


# ── 游戏自报的帧族缓存表 ────────────────────────────────────────────

AGC_RE = re.compile(r"(\w+)\s*=\s*new\s+AGCachedStrings(2Dim|3Dim|4Dim)?\s*\((.*?)\)\s*;", re.S)
STRARR_RE = re.compile(r"new\s+string\[\d+\]\s*\{([^}]*)\}")
STR_RE = re.compile(r'"([^"\\]*)"')

# 这些缓存在 DrawSprites 里怎么被索引（原样摘自反编译）
AGC_CONDITION = {
    "_cachedHeads": "sLeaser.sprites[3].element = _cachedHeads[种族 0=A / 1=B / 2=C, num7]",
    "_cachedFaceSpriteNames": "表情：FaceA..E × 0..8，另有 PFace* 变体；[0,4,*] 是闭眼/晕眩脸",
    "_cachedPlayerArms": "index = round(clamp(dist(hand, shoulder)/2, 0, 12))",
    "_cachedLegsA": "elementName = _cachedLegsA[player.animationFrame]",
    "_cachedLegsACrawling": "elementName = _cachedLegsACrawling[player.animationFrame / 2]",
    "_cachedLegsAClimbing": "elementName = _cachedLegsAClimbing[num8]",
    "_cachedLegsAOnPole": "elementName = _cachedLegsAOnPole[af]（af<7 时取帧，否则 0）",
}


def cached_frame_families(decomp_root: Path, sprite_index: dict, warnings: list) -> dict:
    """游戏自己在 `InitCachedSpriteNames()` 里声明的帧族 —— 这是帧名的权威来源。

    每个族与图集对拍：声明了却没有的帧记进 `missing`（例如声明 LegsA0..30
    但图集只有 LegsA0..7）。
    """
    pg = Path(decomp_root) / "PlayerGraphics.cs"
    if not pg.exists():
        warnings.append("找不到 PlayerGraphics.cs，帧族缓存表留空")
        return {"declarations": []}
    src = pg.read_text(encoding="utf-8", errors="replace")
    known = sprite_index or {}
    out = []
    for m in AGC_RE.finditer(C.mask(src)):
        var, dim = m.group(1), m.group(2) or "1Dim"
        args = src[m.start(3):m.end(3)]        # 原文：masked 会把字符串清空
        axes, count = [], None
        for a in STRARR_RE.finditer(args):
            axes.append(STR_RE.findall(a.group(1)))
        probe = re.sub(r"string\[\d+\]", "string[]", re.sub(r'"[^"\\]*"', '""', args))
        nums = re.findall(r"(?<![\w.])(\d+)", probe)
        if dim == "1Dim":
            lit = STR_RE.findall(args)
            if lit:
                axes.append([lit[0]])
        if nums:
            count = int(nums[-1])
        if not axes or count is None:
            continue
        frames = [""]
        for axis in axes:
            frames = [f + a for f in frames for a in axis]
        frames = [p + str(i) for p in frames for i in range(count)]
        resolved = [f for f in frames if f in known] if known else []
        out.append({
            "var": var, "dim": dim, "count": count,
            "axes": axes,
            "frame_count": len(frames),
            "condition": AGC_CONDITION.get(var),
            "frames": frames[:64],
            "resolved": len(resolved),
            "missing": ([] if not known
                        else [f for f in frames if f not in known][:32]),
        })
    return {"declarations": out,
            "note": "来自 PlayerGraphics.InitCachedSpriteNames()：游戏自己声明的帧名与帧数，"
                    "是本作 animations/*.json 里帧族计数的权威参考。"}


# ── 生物 / 逻辑 ───────────────────────────────────────────────────

def build_creatures(classes: dict) -> list:
    """每只生物「怎么画」：下标 = 图层序 + 容器 + 元件 + 变换 + 依赖。"""
    out = []
    for name in sorted(classes):
        rec = classes[name]
        out.append({
            "class": name, "file": rec.get("file"),
            "total_sprites": rec.get("total_sprites"),
            "containers": rec.get("containers", []),
            "sprite_count": len(rec["sprites"]),
            "sprites": rec["sprites"],
        })
    return out


WRITE_RE = re.compile(
    r"(?:sLeaser|Leaser)\.sprites\[([^\]]+)\]\.(\w+)\s*=\s*([^;]+);")


def build_logic(decomp_root: Path, warnings: list) -> list:
    """每个方法写哪些精灵的哪些属性 —— Asset → Graphics → Rig → Animation/Logic 的最后一层。"""
    out = []
    for p in C.iter_cs(decomp_root):
        if not (p.name.endswith("Graphics.cs") or p.name in C.EXTRA_CLASSES):
            continue
        try:
            src = p.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            warnings.append("读不到 %s：%r" % (p.name, e))
            continue
        msk = C.mask(src)
        name = C.class_name(msk, src)
        if not name:
            continue
        ms = C.methods(msk, C.nested_class_ranges(msk))
        consts = C.constants(src, msk)
        helpers = C.index_helpers(msk)
        methods = []
        for fn, br in ms.items():
            writes: dict = {}
            for m in WRITE_RE.finditer(msk, br[0], br[1]):
                prop = m.group(2)
                if prop not in C.DRAW_PROPS and prop not in ("element", "color", "shader"):
                    continue
                slot_expr = msk[m.start(1):m.end(1)].strip()
                val = src[m.start(3):m.end(3)].strip()
                if len(val) > 160:
                    val = val[:160] + "..."
                val_i, expanded = C.eval_index(slot_expr, consts, helpers)
                key = slot_expr if val_i is None else str(val_i)
                writes.setdefault(key, {"index_expr": slot_expr,
                                        "index": val_i,
                                        "index_expanded": expanded if val_i is None else None,
                                        "props": {}})
                writes[key]["props"][prop] = val
            if not writes:
                continue
            exprs = [p2 for w in writes.values() for p2 in w["props"].values()]
            methods.append({"method": fn, "writes": [writes[k] for k in
                                                     sorted(writes, key=lambda x: (x.isdigit() is False, x))],
                            "depends_on": C._depends_on(exprs)})
        if methods:
            out.append({"class": name, "file": p.name, "methods": methods})
    return out
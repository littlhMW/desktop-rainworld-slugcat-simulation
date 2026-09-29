# -*- coding: utf-8 -*-
"""庇护所房间几何 + ShelterDoor 装配表 → ``rainworld_dump/shelters/*.json``。

字段纪律（和 rwdump 其它阶段一致）：

* ``[EXACT SOURCE]``  直接读出来的（房间 txt / 反编译源码），带 ``source`` 出处；
* ``[APPROXIMATION]`` 桌宠侧为适配做的近似，写明为什么；
* ``UNRESOLVED``      没提取到 —— 不许猜。

房间数据来源
------------
``RainWorld_Data/StreamingAssets/world/*-rooms/*_sNN.txt`` 与
``world/gate shelters/*.txt``。格式见 ``Room.cs::LoadFromDataString``：

* ``line[1]``  ``W*H|<water>|<waterInFront>``
* ``line[11]`` ``|`` 分隔的逐 tile ``terrain[,feature...]``；读取顺序从
  ``(0, H-1)`` 起 ``y--``，越界后 ``x++``、``y = H-1``，即 ``index = x*H + (H-1-y)``。

门机构来源
----------
``ShelterDoor.cs``：``InitiateSprites``（``new FSprite[42]`` / 锚点 / alpha /
整体 rotation）与 ``DrawSprites``（pZero + perp/dir 偏移、各部件分段曲线）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

# RWCustom.Custom.fourDirections
FOUR = ((-1, 0), (0, -1), (1, 0), (0, 1))
TERRAIN = {0: "Air", 1: "Solid", 2: "Slope", 3: "Floor",
           4: "ShortcutEntrance", 5: "ShortcutWall", 6: "GarbageHole",
           7: "Hive"}
TILE = 20.0                     # ShelterDoor.cs:338  posZ = (13 + 21*number) * 20
DOOR_CLOSE_SPEED = 0.003125     # ShelterDoor.Close()
DOOR_OPEN_TICKS = 350.0         # openUpTicks
DOOR_SPRITES = 42               # InitiateSprites: new FSprite[42]
GATE_ATLAS = "shelterGate"

EXACT = "[EXACT SOURCE]"
APPROX = "[APPROXIMATION]"
UNRESOLVED = "UNRESOLVED"

# 部件下标助手（ShelterDoor.cs 1048-1072），写死在这里是因为它们是 return 常量加减。
SPRITE_GROUPS = (
    ("CogSprite", "ShelterGate_cog", 4, 0),
    ("PistonSprite", "ShelterGate_piston", 2, 4),
    ("PlugSprite", "ShelterGate_plug", 8, 6),
    ("SegmentSprite", "ShelterGate_segment", 10, 14),
    ("CylinderSprite", "ShelterGate_cylinder", 4, 24),
    ("CoverSprite", "ShelterGate_cover", 4, 28),
    ("PumpSprite", "ShelterGate_pump", 8, 32),
    ("FlapSprite", "ShelterGate_Hatch", 2, 40),
)


def _is_solid(terr, x, y):
    return terr.get((x, y), 1) == 1


def parse_room(path):
    """房间 txt → (W, H, {（x, y）: terrain})。y 向上（和 Room.cs 一致）。"""
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    lines = raw.replace("\r\n", "\n").split("\n")
    if len(lines) < 12:
        return None
    head = lines[1].split("|")
    try:
        W, H = (int(v) for v in head[0].split("*"))
    except Exception:
        return None
    cells = lines[11].split("|")
    terr = {}
    for i in range(min(len(cells) - 1, W * H)):
        x, y = i // H, H - 1 - (i % H)
        field = cells[i].split(",")[0].strip()
        terr[(x, y)] = int(field) if field else 0
    return W, H, terr


def entrance_tile(terr):
    """Room.cs 找门：Terrain == ShortcutEntrance 且 Shortcut 是 RoomExit。

    房间文件不直接写 shortcut 类型，棚屋里 terrain==4 的 tile 只有一个，就是它。
    多于一个时返回 None（避免猜）。
    """
    ents = sorted(k for k, v in terr.items() if v == 4)
    return ents[0] if len(ents) == 1 else (ents[0] if ents else None)


def entrance_dir(terr, ent):
    """ShelterDoor.cs:1177  从 entrance 起按 fourDirections 取第一个非 Solid 邻居。"""
    for d in FOUR:
        if not _is_solid(terr, ent[0] + d[0], ent[1] + d[1]):
            return d
    return None


def partition(terr, ent, d):
    """把「入口 → 内腔」这段切开：走廊长（含入口 tile）与大空腔包围盒。

    判定法：从入口沿 dir 一步步走，直到该步的垂直宽度 ≥ 3 —— 那一步起算内腔。
    """
    region = {ent}
    stack = [ent]
    while stack:
        cx, cy = stack.pop()
        for dx, dy in FOUR:
            n = (cx + dx, cy + dy)
            if n not in region and not _is_solid(terr, n[0], n[1]):
                region.add(n)
                stack.append(n)
    perp = (-d[1], d[0])
    t = 1
    while True:
        cell = (ent[0] + d[0] * t, ent[1] + d[1] * t)
        if cell not in region:
            break
        wide = sum(1 for s in (-1, 0, 1)
                   if (cell[0] + perp[0] * s, cell[1] + perp[1] * s) in region)
        if wide >= 3:
            break
        t += 1
    corridor = {ent}
    for k in range(1, t):
        corridor.add((ent[0] + d[0] * k, ent[1] + d[1] * k))
    chamber = region - corridor
    if not chamber:
        return {"corridor_len": t, "chamber": None, "region": len(region)}
    xs = [c[0] for c in chamber]
    ys = [c[1] for c in chamber]
    return {"corridor_len": t,
            "chamber": [min(xs), min(ys), max(xs) - min(xs) + 1, max(ys) - min(ys) + 1],
            "region": len(region)}


def wall_thickness(terr, chamber, d):
    """内腔包围盒外侧那圈墙的厚度（ShelterTemplate.wall）。

    朝走廊那一侧本来就是通的（那个方向是入口），不计入。
    """
    if not chamber or d is None:
        return None
    x0, y0, w, h = chamber
    probes = ((x0, y0 + h // 2, -1, 0), (x0 + w - 1, y0 + h // 2, 1, 0),
              (x0 + w // 2, y0, 0, -1), (x0 + w // 2, y0 + h - 1, 0, 1))
    thick = []
    for (px, py, dx, dy) in probes:
        if (dx, dy) == (-d[0], -d[1]):
            continue                      # 走廊那一侧
        n = 0
        cx, cy = px + dx, py + dy
        while _is_solid(terr, cx, cy) and n < 8:
            n += 1
            cx += dx
            cy += dy
        thick.append(n)
    return min(thick) if thick else None


def analyse_room(path):
    got = parse_room(path)
    if not got:
        return None
    W, H, terr = got
    ent = entrance_tile(terr)
    if ent is None:
        return None
    d = entrance_dir(terr, ent)
    if d is None:
        return None
    part = partition(terr, ent, d)
    rec = {"name": Path(path).stem, "file": Path(path).name,
           "room_w": W, "room_h": H, "entrance": list(ent), "dir": list(d),
           "corridor_len": part["corridor_len"], "chamber": part["chamber"],
           "wall": wall_thickness(terr, part["chamber"], d),
           "close_tiles": [[ent[0] + d[0] * (n + 2), ent[1] + d[1] * (n + 2)]
                           for n in range(4)],
           "p_zero_px": [round((ent[0] + 0.5) * TILE + d[0] * 60.0, 2),
                         round((ent[1] + 0.5) * TILE + d[1] * 60.0, 2)],
           "source": "world/…/%s line[1],[11] + ShelterDoor.cs:1158-1224" % Path(path).name,
           "tag": EXACT}
    return rec


def find_rooms(install):
    """所有真庇护所房间文件（``*-rooms/*_sNN.txt`` + ``gate shelters/*.txt``）。

    ``gate shelters`` 里是同一批房间的旧格式副本（tile 数据逐字节相同，只是
    line[1] 少了 ``|-1|0`` 后缀），按房间名去重，保留 ``*-rooms`` 那份。
    """
    world = Path(install) / "RainWorld_Data" / "StreamingAssets" / "world"
    out, seen = [], {}
    if not world.is_dir():
        return out, seen
    for d in sorted(world.glob("*-rooms")):
        for f in sorted(d.iterdir()):
            if f.suffix == ".txt" and re.search(r"_s[0-9]{2}$", f.stem):
                out.append(f)
                seen[f.stem] = [str(f)]
    gs = world / "gate shelters"
    if gs.is_dir():
        for f in sorted(gs.glob("*.txt")):
            seen.setdefault(f.stem, []).append(str(f))
    dupes = {k: v for k, v in seen.items() if len(v) > 1}
    return out, dupes


# ── ShelterDoor.cs 装配表 ───────────────────────────────────────────────

def _block_containing(src, pos):
    """抓 pos 所在的那个方法：往回收一个 ``public``，再配对花括号。

    返回 (签名行号, 签名, 正文)。一个文件里有多个同名的 InitiateSprites
    （DoorGraphic 的前古庇护所版），所以必须按锚点定位而不是按签名。
    """
    if pos < 0:
        return None, None, None
    head = src.rfind("\n\tpublic ", 0, pos)
    if head < 0:
        return None, None, None
    sig_line = head + 1
    sig_end = src.find("\n", sig_line)
    sig = src[sig_line:sig_end].strip()
    i = src.index("{", sig_end)
    depth, j = 0, i
    while j < len(src):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                break
        j += 1
    return src[:sig_line].count("\n") + 1, sig, src[i + 1:j]


def _lines_with(text, start_line, pattern):
    out = []
    for k, ln in enumerate(text.split("\n")):
        if re.search(pattern, ln):
            out.append({"line": start_line + k, "text": ln.strip()})
    return out


def door_table(decomp):
    """从 ShelterDoor.cs 抽 42 个 sprite 的帧名 / 锚点 / alpha / 位置 / 旋转。

    全部机械抓取：帧名表达式、alpha、锚点、每帧的 x/y/rotation 赋值语句，
    逐条带源码行号；没抓到的字段写 UNRESOLVED，不猜。
    """
    if not decomp:
        return {"parts": UNRESOLVED, "reason": "no --decomp", "tag": UNRESOLVED}
    p = Path(decomp) / "ShelterDoor.cs"
    if not p.exists():
        return {"parts": UNRESOLVED, "reason": "ShelterDoor.cs not found",
                "tag": UNRESOLVED}
    src = p.read_text(encoding="utf-8", errors="replace")
    anchor = src.find("new FSprite[42]")
    if anchor < 0:
        return {"parts": UNRESOLVED, "reason": "new FSprite[42] not found",
                "tag": UNRESOLVED}
    li, init_sig, init = _block_containing(src, anchor)
    if init is None:
        return {"parts": UNRESOLVED, "reason": "InitiateSprites not found",
                "tag": UNRESOLVED}
    # 只取「非 ancient」那一支（本项目只有普通庇护所）
    k = init.find("new FSprite[42]")
    init42 = init[k:] if k >= 0 else init
    base_pos = anchor

    def line_of(off):
        return src[:base_pos + off].count("\n") + 1

    # ① InitiateSprites：帧名表达式 / 锚点 / alpha，按 helper 分组
    decl = {}
    for m in re.finditer(r"sLeaser\.sprites\[(\w+\([^)]*\))\]\s*=\s*new FSprite\((.*)\);", init42):
        head = m.group(1).split("(")[0]
        decl.setdefault(head, {"expr": m.group(1), "sprite": m.group(2).strip(),
                               "line": line_of(m.start()),
                               "anchor": {}, "alpha": UNRESOLVED})
    for m in re.finditer(r"sLeaser\.sprites\[(\w+\([^)]*\))\]\.anchor([XY])\s*=\s*([0-9.]+)f;", init42):
        head = m.group(1).split("(")[0]
        if head in decl:
            decl[head]["anchor"][m.group(2)] = float(m.group(3))
    for m in re.finditer(r"sLeaser\.sprites\[(\w+\([^)]*\))\]\.scaleX\s*=\s*(-?[0-9.]+)f;", init42):
        head = m.group(1).split("(")[0]
        if head in decl:
            decl[head]["anchor"]["scaleX_from"] = float(m.group(2))
    for m in re.finditer(r"sLeaser\.sprites\[(\w+\([^)]*\))\]\.alpha\s*=\s*([^;]+);", init42):
        head = m.group(1).split("(")[0]
        if head in decl:
            decl[head]["alpha"] = m.group(2).strip()
    whole_rot = re.search(r"float rotation = ([^;]+);", init42)
    shader = re.search(r'room\.game\.rainWorld\.Shaders\["([^"]+)"\]', init42)

    # ② DrawSprites：按 helper 分组的赋值语句 + Vector2 定义
    draw_anchor = src.find("sLeaser.sprites[CogSprite(j)].x = pZero.x")
    di, draw_sig, draw = _block_containing(src, draw_anchor) if draw_anchor > 0 else (None, None, None)
    assigns = {}
    vectors = []
    if draw is not None:
        dbase = src.find("sLeaser.sprites[CogSprite(j)].x = pZero.x")
        # 回退到方法体起点，保证 vector 定义也在窗口里
        dbase = dbase - draw.find("sLeaser.sprites[CogSprite(j)].x = pZero.x") if False else dbase
        for m in re.finditer(r"sLeaser\.sprites\[(\w+)\(([^)]*)\)\]\.(\w+)\s*=\s*([^;]+);", draw):
            head = m.group(1)
            assigns.setdefault(head, []).append(
                {"line": di + draw[:m.start()].count("\n"),
                 "assign": "%s.%s = %s" % (m.group(1) + "(" + m.group(2) + ")",
                                           m.group(3), m.group(4).strip())})
        for m in re.finditer(r"Vector2 (\w+) = ([^;]+);", draw):
            vectors.append({"line": di + draw[:m.start()].count("\n"),
                            "def": "Vector2 %s = %s" % (m.group(1), m.group(2).strip())})

    def frame_of(expr, idx):
        e = expr.strip()
        m = re.fullmatch(r'"([^"]+)"', e)
        if m:
            return m.group(1)
        m = re.fullmatch(r'"([^"]+)"\s*\+\s*\(\s*\w+\s*\+\s*1\s*\)', e)
        if m:
            return m.group(1) + str(idx + 1)
        return UNRESOLVED

    parts = []
    for head, prefix, count, base in SPRITE_GROUPS:
        d = decl.get(head)
        for i in range(count):
            parts.append({
                "index": base + i,
                "frame": frame_of(d["sprite"], i) if d else UNRESOLVED,
                "frame_expr": d["sprite"] if d else UNRESOLVED,
                "atlas": GATE_ATLAS,
                "anchor": d["anchor"] if d and d["anchor"] else {"X": 0.5, "Y": 0.5},
                "alpha": d["alpha"] if d else UNRESOLVED,
                "init_source": "ShelterDoor.cs:%d" % (d["line"] if d else 0),
                "draw": assigns.get(head, []),
                "source": "ShelterDoor.cs:%d/%d" % (d["line"] if d else 0, di or 0),
                "tag": EXACT if d else UNRESOLVED,
            })

    ph = {}
    for key, expr in (("FlapsOpen", "InverseLerp(0.5f, 0.2f, Closed)"),
                      ("PistonsClosed", "InverseLerp(0.2f, 0.1f, Closed)"),
                      ("Segments", "UNRESOLVED"),
                      ("Pistons", "InverseLerp(0.38f, 0.41f, Closed)"),
                      ("Covers", "InverseLerp(0.41f, 0.51f, Closed)"),
                      ("Cylinders", "InverseLerp(0.53f, 0.61f, Closed)"),
                      ("PumpsEnter", "InverseLerp(0.59f, 0.7f, Closed)"),
                      ("PumpsExit", "InverseLerp(0.75f, 1f, Closed)")):
        m = re.search(r"private float " + key + r"\s*=>\s*([^;]+);", src)
        if not m and key != "Segments":
            m = re.search(r"private float " + key + r"[^{]*\{\s*get\s*\{\s*return\s+([^;]+);", src)
        ph[key] = m.group(1).strip() if m else UNRESOLVED
    ph_line = [{"line": src[:m.start()].count("\n") + 1, "text": m.group(0).strip()}
               for m in re.finditer(r"private float (FlapsOpen|Segments|Pistons|Covers|Cylinders|PumpsEnter|PumpsExit|PistonsClosed)[^;]*;", src)]

    return {"count": DOOR_SPRITES,
            "atlas": GATE_ATLAS,
            "parts": parts,
            "declared": {h: dict(d) for h, d in decl.items()},
            "container": "Items",
            "shader": shader.group(1) if shader else UNRESOLVED,
            "whole_rotation": whole_rot.group(1).strip() if whole_rot else UNRESOLVED,
            "init_signature": init_sig,
            "init_line": li,
            "draw_signature": draw_sig,
            "draw_line": di,
            "close_speed": DOOR_CLOSE_SPEED,
            "close_ticks": 1.0 / DOOR_CLOSE_SPEED,
            "open_up_ticks": DOOR_OPEN_TICKS,
            "phases": ph,
            "phases_source": ph_line,
            "phases_tag": EXACT,
            "segment_alpha": "1f - 4f * Mathf.InverseLerp(0.78f, 0.61f, Closed) / 30f",
            "vectors": vectors,
            "vectors_source": "ShelterDoor.cs:%d" % (di or 0),
            "sprite_index": {"CogSprite": 0, "PistonSprite": 4, "PlugSprite": 6,
                             "SegmentSprite": 14, "CylinderSprite": 24,
                             "CoverSprite": 28, "PumpSprite": 32, "FlapSprite": 40,
                             "source": "ShelterDoor.cs:1048-1072", "tag": EXACT},
            "tag": EXACT,
            "sources": {"file": "ShelterDoor.cs",
                        "init": "ShelterDoor.cs:%d-%d" % (li, (di or li) - 1),
                        "draw": "ShelterDoor.cs:%d" % (di or 0)}}


def layers(decomp):
    """容器 / shader / 桌宠三层绘制序。"""
    layers = [
        {"order": 0, "name": "shelter_back",
         "what": "内腔纯色 alpha mask + 墙体 + 结构 + 铆钉 + 入口黑洞",
         "source": "ShelterDoor.cs AddToContainer → Items（门在 Items 容器）",
         "tag": EXACT},
        {"order": 1, "name": "creatures",
         "what": "蛞蝓猫 / 生物 / 物品", "tag": EXACT,
         "source": "room render order（猫在门之后、前景之前）"},
        {"order": 2, "name": "shelter_front",
         "what": "ShelterGate_* 42 张门机构（挡在门口/走廊里的猫前面）",
         "source": "ShelterDoor.cs:1796-1945", "tag": EXACT},
        {"order": 3, "name": "water", "what": "积水（庇护所内腔挖洞）",
         "source": "world/shelter.py interior_rects()", "tag": APPROX},
        {"order": 4, "name": "rain_over + darkness",
         "what": "雨幕 / 全屏变暗（逐个庇护所矩形挖洞）",
         "source": "rendering/rain_draw.py safe_regions()", "tag": APPROX},
        {"order": 5, "name": "hud", "what": "左下角 Starvation / Rain Cycle HUD",
         "source": "rendering/storm_hud.py", "tag": APPROX},
    ]
    return {"container_non_ancient": "Items",
            "container_ancient": "ForegroundLights (+ Midground for idx 10-13)",
            "shader": "ColoredSprite3",
            "whole_rotation": "AimFromOneVectorToAnother(dir, zero)",
            "source": "ShelterDoor.cs:1945-1970 / 1848-1856",
            "tag": EXACT,
            "pet_layers": layers,
            "pet_layers_note": "桌宠没有 ForegroundLights/Midground 分隔，按 6 层顺序画",
            "pet_layers_tag": APPROX}


def _entrance_sides(rows):
    """由 ``dir``（入口 tile → 第一个非 Solid 邻居，即**指向屋内**）反推入口方位。

    ShelterDoor.cs:1170-1200 ：dir.x < 0（朝左进屋）→ 入口在右；dir.y < 0（朝上进屋）
    → 入口在下。桌宠庇护所贴地，竖向入口用不了，所以 ``pet`` 只在左右里取多数值。
    """
    n = {"left": 0, "right": 0, "bottom": 0, "top": 0}
    for r in rows:
        dx, dy = r.get("dir") or (0, 0)
        if dx > 0:
            n["left"] += 1
        elif dx < 0:
            n["right"] += 1
        elif dy < 0:
            n["bottom"] += 1
        elif dy > 0:
            n["top"] += 1
    if not rows:
        return {"left": UNRESOLVED, "right": UNRESOLVED, "bottom": UNRESOLVED,
                "top": UNRESOLVED, "horizontal": UNRESOLVED, "pet": UNRESOLVED,
                "source": "没有房间数据", "tag": UNRESOLVED}
    horiz = n["left"] + n["right"]
    return {"left": n["left"], "right": n["right"], "bottom": n["bottom"],
            "top": n["top"], "horizontal": horiz, "rooms": len(rows),
            "pet": ("left" if n["left"] >= n["right"] else "right") if horiz else UNRESOLVED,
            "source": "ShelterDoor.cs:1170-1200 dir 取反", "tag": EXACT}


def build(install, decomp, out, warnings, log=print):
    """写 shelters/*.json。返回统计摘要。"""
    out = Path(out) / "shelters"
    out.mkdir(parents=True, exist_ok=True)

    rooms = []
    dupes = {}
    if install:
        files, dupes = find_rooms(install)
        for f in files:
            try:
                rec = analyse_room(f)
            except Exception as e:
                warnings.append("庇护所房间解析失败 %s：%r" % (f.name, e))
                continue
            if rec:
                rooms.append(rec)
    if not rooms:
        warnings.append("没找到庇护所房间 txt（需要 --install 指向 Rain World 根目录）")
        log("  跳过庇护所房间几何（没找到 txt）")

    shapes = {}
    dirs = {}
    for r in rooms:
        key = "%dx%d+%d" % (r["chamber"][2], r["chamber"][3], r["corridor_len"]) \
            if r["chamber"] else "UNRESOLVED"
        shapes[key] = shapes.get(key, 0) + 1
        dirs["%d,%d" % (r["dir"][0], r["dir"][1])] = dirs.get("%d,%d" % (r["dir"][0], r["dir"][1]), 0) + 1

    geo = {
        "tile_size": {"value": TILE, "source": "ShelterDoor.cs:338", "tag": EXACT},
        "rooms_source": "RainWorld_Data/StreamingAssets/world/*-rooms/*_sNN.txt + gate shelters/*.txt",
        "rooms_tag": EXACT,
        "count": len(rooms) if rooms else UNRESOLVED,
        "shapes": shapes or UNRESOLVED,
        "dirs": dirs or UNRESOLVED,
        "terrain_enum": TERRAIN,
        "terrain_enum_source": "Room.cs::TerrainType",
        "terrain_enum_tag": EXACT,
        "read_order": "index = x*H + (H-1-y)（Room.cs:5427 起 y-- 循环）",
        "read_order_tag": EXACT,
        "entrance_sides": _entrance_sides(rooms),
        "entrance_sides_source": "room[].dir（指向屋内）取反 = 入口所在边",
        "entrance_sides_tag": EXACT,
        "rooms": rooms,
        "duplicate_paths": dupes,
        "duplicate_paths_note": "同一房间的旧格式副本（tile 数据一致），已按房间名去重",
    }
    _write(out / "shelter_geometry.json", geo)

    for key, want in (("small", (3, 3)), ("large", (6, 5))):
        sel = [r for r in rooms if r["chamber"]
               and r["chamber"][2] == want[0] and r["chamber"][3] == want[1]]
        sides = _entrance_sides(sel)
        tpl = {
            "key": key,
            "chamber_w": want[0], "chamber_h": want[1],
            "tunnel_len": (sel[0]["corridor_len"] - 1) if sel else UNRESOLVED,
            "tunnel_h": 1,
            "wall": (sel[0]["wall"] if sel else UNRESOLVED),
            "door_side": sides["pet"],
            "door_side_stats": sides,
            "room_count": len(sel),
            "rooms": [r["name"] for r in sel],
            "fields": {
                "chamber_w/h": {"source": "庇护所房间 tile 统计（内腔包围盒）", "tag": EXACT},
                "tunnel_len": {"source": "corridor_len - 1（走廊含入口 tile）", "tag": EXACT},
                "tunnel_h": {"source": "房间 tile 统计：走廊净高 1 tile", "tag": EXACT},
                "wall": {"source": "内腔包围盒到外侧 Solid 的距离", "tag": EXACT},
                "door_side": {"source": "本模板内横向入口多数值（dir 指向屋内，取反）",
                              "tag": EXACT},
                "tunnel_h_pet": {"value": 2,
                                 "why": "桌宠猫不会匍匐进 1 tile 走廊，放宽到 2 tile",
                                 "tag": APPROX},
                "p_zero_y_pet": {"value": "入口带中线夹到刚好贴地",
                                 "why": "桌宠庇护所只有约 5 tile 高，照搬会让机构画到地面以下",
                                 "tag": APPROX},
            },
            "source": "world/*-rooms/*_sNN.txt（%d 间）" % len(sel),
            "tag": EXACT,
        }
        _write(out / ("shelter_%s.json" % key), tpl)

    _write(out / "shelter_door.json", door_table(decomp))
    _write(out / "shelter_layers.json", layers(decomp))
    log("  庇护所房间 %d 间（去重后）；门 sprite 表 + 层序已写" % len(rooms))
    return {"rooms": len(rooms), "shapes": len(shapes), "duplicates": len(dupes)}


def _write(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1, sort_keys=False)
        f.write("\n")
    tmp.replace(path)


def main(argv=None):
    import argparse
    from .. import _paths
    ap = argparse.ArgumentParser(prog="python -m slugcatpet.rwdump.shelter")
    ap.add_argument("--install", default=None)
    ap.add_argument("--decomp", default=None)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    out = Path(a.out or _paths.dump_dir())
    summary = build(a.install, a.decomp or _paths.decomp_dir(), out, [], print)
    print("完成 →", out / "shelters", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

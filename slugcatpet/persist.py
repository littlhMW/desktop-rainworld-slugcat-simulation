# -*- coding: utf-8 -*-
"""世界状态存档：退出 / 定时保存西瓜猫之外的全部环境实体（物品 + 生物 + 杆/灯）。

反编译里每个实体都是可序列化的（SaveState），桌宠这边取同样的做法：
每一类实体一张「构造器 + 可恢复字段」表，序列化只存这些字段，恢复 = 用构造器建一个新实体 +
逐字段赋值。这样不依赖 __dict__（都是 __slots__），也不会把不能重建的互指针写进去。

不存的：手里/嘴里的互指（靠这里给出的 hand 字段在恢复后重新抓起）、
矛的 stuck_to（钉到生物身上的那种跨实体引用）。
"""
from __future__ import annotations

import sys

from .world.batfly import BatFly
from .world.fruit import Fruit
from .world.karmaflower import KarmaFlower
from .world.lamp import Lamp
from .world.lizard import BREED_BY_KEY, Lizard
from .world.needleworm import NeedleWorm
from .world.pearl import Pearl
from .world.pole import Pole
from .world.scavenger import Scavenger
from .world.seedcob import Seed, SeedCob
from .world.slimemold import SlimeMold
from .world.spear import Spear
from .world.squidcada import Squidcada
from .world.stone import Stone

SCHEMA = 1

# (kind, 列名, 构造器, 可恢复字段)
# 构造器签名都是 (x, y, seed, ...)；恢复时用存档里的 seed 重建，再逐字段覆盖。
_TABLE = (
    ("fruit", "fruits", lambda d: Fruit(d["x"], d["y"], seed=int(d.get("seed", 0))),
     ("x", "y", "vx", "vy", "state", "rotation", "bites")),
    ("stone", "stones", lambda d: Stone(d["x"], d["y"], seed=int(d.get("seed", 0))),
     ("x", "y", "vx", "vy", "state", "rotation_deg", "spin", "frame", "vibrate",
      "unfetchable")),
    ("slimemold", "slimemolds",
     lambda d: SlimeMold(d["x"], d["y"], seed=int(d.get("seed", 0))),
     ("x", "y", "vx", "vy", "state", "rotation", "bites")),
    ("batfly", "batflies", lambda d: BatFly(d["x"], d["y"], seed=int(d.get("seed", 0))),
     ("x", "y", "vx", "vy", "state", "dead", "eaten", "bites", "facing", "flap")),
    ("lizard", "lizards", None,
     ("x", "y", "vx", "vy", "state", "health", "max_health", "stun", "dead",
      "like", "tamed", "facing", "head_angle", "jaw", "body_rgb", "tail_edge",
      "tail_amt", "anger")),
    ("squidcada", "squidcadas",
     lambda d: Squidcada(d["x"], d["y"], seed=int(d.get("seed", 0))),
     ("x", "y", "vx", "vy", "state", "health", "dead", "stamina", "hue", "male")),
    ("needleworm", "needleworms", None,
     ("x", "y", "vx", "vy", "state", "health", "dead", "facing", "rotation")),
    ("pearl", "pearls", lambda d: Pearl(d["x"], d["y"], seed=int(d.get("seed", 0))),
     ("x", "y", "vx", "vy", "state", "rotation_deg", "spin", "tint")),
    ("spear", "spears",
     lambda d: Spear(d["x"], d["y"], seed=int(d.get("seed", 0)),
                     angle_deg=float(d.get("angle_deg", 90.0))),
     ("x", "y", "vx", "vy", "state", "angle_deg", "spin", "spinning", "stuck",
      "stuck_angle", "embedded", "always_stick", "pinned")),
    ("scavenger", "scavengers", None,
     ("x", "y", "vx", "vy", "state", "health", "dead", "like", "variant",
      "facing", "walk_phase")),
    ("seedcob", "seedcobs",
     lambda d: SeedCob(d["x"], d["y"], seed=int(d.get("seed", 0)),
                       root_y=d.get("root_y")),
     ("root_pos", "root_y", "placed", "open", "opened", "popped", "dead", "state",
      "p0", "p0l", "p1", "p1l")),
    ("seed", "seeds", lambda d: Seed(d["x"], d["y"], seed=int(d.get("seed", 0))),
     ("x", "y", "vx", "vy", "state")),
    ("karmaflower", "karmaflowers",
     lambda d: KarmaFlower(d["x"], d["y"], seed=int(d.get("seed", 0)),
                           ground_y=d.get("ground_y")),
     ("grow_pos", "hover_pos", "petals", "stalk_pts", "grow_t", "movement",
      "face_camera", "drag_pt", "hover_dir_add")),
)

def snapshot(win) -> dict:
    """把窗口里的全部环境实体序列化成 JSON 可存的 dict。"""
    out = {"v": SCHEMA, "kinds": {}, "hand": {}, "spawns": [], "lamp": None}
    idx = {}                       # id(obj) -> (kind, index)
    for kind, attr, _ctor, fields in _TABLE:
        rows = []
        lst = getattr(win, attr, None) or ()
        for obj in lst:
            if getattr(obj, "state", None) in ("gone", "eaten"):
                rows.append(None)
                idx[id(obj)] = (kind, len(rows) - 1)
                continue
            d = {"seed": int(getattr(obj, "seed", 0) or 0)}
            for name in fields:
                v = getattr(obj, name, None)
                if isinstance(v, (int, float, str, bool)) or v is None:
                    d[name] = v
                elif name in ("petals", "stalk_pts", "root_pos", "p0", "p0l",
                              "p1", "p1l", "grow_pos", "hover_pos"):
                    d[name] = _seq(v)
            if kind == "lizard":
                d["breed"] = getattr(getattr(obj, "breed", None), "key", "pink")
                d["id"] = int(getattr(obj, "id", 0) or 0)
            if kind == "needleworm":
                d["age"] = getattr(obj, "age", None)
            if kind == "scavenger":
                d["id"] = int(getattr(obj, "id", 0) or 0)
                d["svariant"] = getattr(obj, "variant", "saint")
            rows.append(d)
            idx[id(obj)] = (kind, len(rows) - 1)
        out["kinds"][kind] = rows
    # 西瓜猫手里 / 背上的东西：记下 (kind, index)，恢复后重新抓起
    for p in getattr(win, "pets", ()):
        b = getattr(p, "body", None)
        if b is None:
            continue
        held = {}
        cf = getattr(b, "carried_fruit", None)
        if cf is not None and id(cf) in idx:
            held["fruit"] = idx[id(cf)]
        cs = getattr(b, "carried_stone", None)
        if cs is not None and id(cs) in idx:
            held["stone"] = idx[id(cs)]
        sp = getattr(b, "carried_spear", None)
        if sp is not None and id(sp) in idx:
            held["spear"] = idx[id(sp)]
        bk = getattr(b, "back_spear", None)
        if bk is not None and id(bk) in idx:
            held["back"] = idx[id(bk)]
        out["hand"][p.id] = held
    for row in getattr(win, "_karma_flower_spawns", ()) or ():
        try:
            out["spawns"].append([float(row[0]), float(row[1]), int(row[2])])
        except Exception:
            pass
    lamp = getattr(win, "lamp", None)
    if lamp is not None:
        out["lamp"] = {"anchor_x": lamp.anchor_x, "anchor_y": lamp.anchor_y,
                       "bulb_x": lamp.bulb_x, "bulb_y": lamp.bulb_y,
                       "edge": lamp.edge, "seed": int(getattr(lamp, "seed", 0) or 0)}
    return out


def _seq(v):
    try:
        return [list(x) if isinstance(x, (list, tuple)) else x for x in v]
    except TypeError:
        return v


def restore(win, data) -> int:
    """按快照建回全部环境实体；返回建回来的实体数。"""
    if not isinstance(data, dict) or int(data.get("v", 0)) != SCHEMA:
        return 0
    kinds = data.get("kinds") or {}
    made = {}                       # kind -> [obj or None]
    n = 0
    for kind, attr, ctor, fields in _TABLE:
        rows = kinds.get(kind) or []
        objs = []
        for i, d in enumerate(rows):
            if not isinstance(d, dict):
                objs.append(None)
                continue
            d.setdefault("seed", i)      # 同种实体各有各的外观（rad/形状），别全都一样
            obj = _build(kind, d, ctor, win)
            if obj is None:
                objs.append(None)
                continue
            for name in fields:
                if name not in d:
                    continue
                try:
                    setattr(obj, name, d[name])
                except Exception:
                    pass
            if getattr(obj, "state", None) in ("carried", "mouse"):
                # 手里那件靠恢复后的重新抓取接回；没接上就落在地上，不留悬空引用
                obj.state = "free"
                obj.held_by_hand = None
                if hasattr(obj, "held_by"):
                    obj.held_by = None
            objs.append(obj)
            n += 1
        made[kind] = objs
        setattr(win, attr, [o for o in objs if o is not None])
    # 业力花排期 + 灯
    spawns = data.get("spawns")
    if isinstance(spawns, list):
        win._karma_flower_spawns = [list(map(float, r[:2])) + [int(r[2])]
                                    for r in spawns if isinstance(r, (list, tuple))
                                    and len(r) >= 3]
    lamp = data.get("lamp")
    if isinstance(lamp, dict):
        try:
            win.lamp = Lamp(lamp["anchor_x"], lamp["anchor_y"], lamp["bulb_x"],
                            lamp["bulb_y"], lamp["edge"],
                            seed=int(lamp.get("seed", 0)))
        except Exception:
            win.lamp = None
    # 手里/背上的东西重新抓起
    held = data.get("hand") or {}
    if isinstance(held, dict):
        for p in getattr(win, "pets", ()):
            row = held.get(getattr(p, "id", ""))
            if not isinstance(row, dict):
                continue
            b = getattr(p, "body", None)
            if b is None:
                continue
            _rehand(b, row, made)
    win.world_version += 1
    win.geometry_version += 1
    return n


def _build(kind, d, ctor, win):
    d.setdefault("x", 0.0)           # 爆米花 / 业力花的构造器也要一个锚点，真位置靠字段恢复
    d.setdefault("y", 0.0)
    try:
        if kind == "lizard":
            breed = BREED_BY_KEY.get(d.get("breed"), None)
            if breed is None:
                return None
            return Lizard(d["x"], d["y"], breed, seed=int(d.get("seed", 0)),
                          id=int(d.get("id", 0) or 0))
        if kind == "needleworm":
            return NeedleWorm(d["x"], d["y"], seed=int(d.get("seed", 0)),
                              age=d.get("age"))
        if kind == "scavenger":
            return Scavenger(d["x"], d["y"], seed=int(d.get("seed", 0)),
                             id=int(d.get("id", 0) or 0),
                             variant=d.get("svariant", "saint"))
        return ctor(d)
    except Exception as e:
        print("[slugcatpet] restore %s failed: %r" % (kind, e), file=sys.stderr)
        return None


def _rehand(body, row, made):
    def _pick(kind, slot):
        got = row.get(slot)
        if not isinstance(got, (list, tuple)) or len(got) != 2:
            return None
        objs = made.get(kind) or []
        i = int(got[1])
        if 0 <= i < len(objs):
            return objs[i]
        return None

    fr = _pick("fruit", "fruit")
    if fr is not None:
        try:
            body.grab_fruit(fr)
        except Exception:
            pass
    st = _pick("stone", "stone")
    if st is not None:
        try:
            grab = getattr(body, "grab_stone", None)
            if grab is not None:
                grab(st)
        except Exception:
            pass
    sp = _pick("spear", "spear")
    if sp is not None:
        try:
            body.grab_spear(sp)
        except Exception:
            pass
    bk = _pick("spear", "back")
    if bk is not None:
        try:
            body.put_spear_on_back(bk)
        except Exception:
            pass
